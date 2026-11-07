"""Microsoft Graph: OneDrive and SharePoint document libraries. Auth: app registration with client credentials (Files.Read.All / Sites.Read.All)."""
from __future__ import annotations

import re
import time
from typing import Iterator
from urllib.parse import quote, urlparse

from app.connectors.base import SUPPORTED_EXT, Connector, ConnectorError, RemoteFile, check, client

GRAPH = "https://graph.microsoft.com/v1.0"
LOGIN = "https://login.microsoftonline.com"


class MicrosoftGraph(Connector):
    def __init__(self, config: dict, secrets: dict, kind: str):
        super().__init__(config, secrets)
        self.kind = kind                                   # 'onedrive' | 'sharepoint'
        self.api = (config.get("api_base") or GRAPH).rstrip("/")
        self.login = (config.get("login_base") or LOGIN).rstrip("/")
        self._tok: tuple[str, float] | None = None
        self._drive: str | None = None

    def token(self) -> str:
        if self._tok and self._tok[1] > time.time() + 60:
            return self._tok[0]
        tenant, cid, sec = self.cfg.get("tenant_id"), self.sec.get("client_id") or self.cfg.get("client_id"), self.sec.get("client_secret")
        if not (tenant and cid and sec):
            raise ConnectorError("tenant ID, client ID and client secret are required")
        scope = "https://graph.microsoft.com/.default"
        with client() as c:
            r = check(c.post(f"{self.login}/{tenant}/oauth2/v2.0/token", data={"grant_type": "client_credentials", "client_id": cid, "client_secret": sec, "scope": scope}), "Microsoft sign-in")
        j = r.json()
        self._tok = (j["access_token"], time.time() + int(j.get("expires_in", 3600)))
        return self._tok[0]

    def _get(self, c, url: str, **params):
        full = url if url.startswith("http") else f"{self.api}{url}"
        return check(c.get(full, params=params or None, headers={"Authorization": f"Bearer {self.token()}"}), "Microsoft Graph " + urlparse(full).path)

    def drive_id(self, c) -> str:
        if self._drive:
            return self._drive
        if self.cfg.get("drive_id"):
            self._drive = self.cfg["drive_id"]
        elif self.kind == "onedrive":
            user = self.cfg.get("user")
            if not user:
                raise ConnectorError("OneDrive needs the user (e-mail / UPN) whose drive to read, or a drive ID")
            self._drive = self._get(c, f"/users/{quote(user)}/drive").json()["id"]
        else:
            site = self.cfg.get("site_url") or ""
            u = urlparse(site)
            if not u.netloc:
                raise ConnectorError("SharePoint needs the site URL, e.g. https://contoso.sharepoint.com/sites/Legal")
            site_id = self._get(c, f"/sites/{u.netloc}:{u.path.rstrip('/') or '/'}").json()["id"]
            drives = self._get(c, f"/sites/{site_id}/drives").json().get("value", [])
            lib = (self.cfg.get("library") or "Documents").lower()
            pick = next((d for d in drives if d["name"].lower() == lib), None) or (drives[0] if drives and not self.cfg.get("library") else None)
            if not pick:
                raise ConnectorError(f"document library “{self.cfg.get('library')}” not found; available: {', '.join(d['name'] for d in drives)}")
            self._drive = pick["id"]
        return self._drive

    def _children_url(self, drive: str) -> str:
        folder = (self.cfg.get("folder") or "").strip("/")
        return f"/drives/{drive}/root:/{quote(folder)}:/children" if folder else f"/drives/{drive}/root/children"

    def test(self) -> dict:
        with client() as c:
            drive = self.drive_id(c)
            self._get(c, self._children_url(drive), **{"$top": "1"})
        n = sum(1 for f in self.list_files() if f.name.lower().endswith(SUPPORTED_EXT))
        where = self.cfg.get("site_url") or self.cfg.get("user") or drive
        return {"ok": True, "detail": f"Connected to {where}: {n} supported file(s) found under “{self.cfg.get('folder') or '/'}”."}

    def list_files(self) -> Iterator[RemoteFile]:
        with client() as c:
            drive = self.drive_id(c)
            stack = [(self._children_url(drive), "")]
            while stack:
                url, prefix = stack.pop()
                while url:
                    j = self._get(c, url, **({"$top": "200"} if "?" not in url and url.startswith("/") else {})).json()
                    for it in j.get("value", []):
                        if "folder" in it:
                            if self.cfg.get("recursive", True):
                                stack.append((f"/drives/{drive}/items/{it['id']}/children", f"{prefix}{it['name']}/"))
                            continue
                        yield RemoteFile(id=it["id"], name=it["name"], path=f"{prefix}{it['name']}", size=it.get("size"), modified=it.get("lastModifiedDateTime"),
                                         etag=it.get("eTag") or (it.get("file", {}).get("hashes", {}) or {}).get("quickXorHash") or it.get("lastModifiedDateTime"), web_url=it.get("webUrl"),
                                         extra={"drive": drive})
                    url = j.get("@odata.nextLink")

    def download(self, f: RemoteFile) -> bytes:
        """Graph answers with a redirect to a pre-authenticated download URL: follow it by hand and never send the bearer token there."""
        with client(follow=False) as c:
            drive = f.extra.get("drive") or self.drive_id(c)
            r = c.get(f"{self.api}/drives/{drive}/items/{f.id}/content", headers={"Authorization": f"Bearer {self.token()}"})
            hops = 0
            while r.status_code in (301, 302, 303, 307, 308) and hops < 5:
                r = c.get(r.headers["location"])
                hops += 1
            return check(r, "Microsoft Graph download").content


_ = re
