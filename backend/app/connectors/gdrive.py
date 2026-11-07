"""Google Drive (REST v3). Auth: a service account key (JSON, folder shared with the service account's e-mail) or an OAuth refresh token."""
from __future__ import annotations

import json
import re
import time
from typing import Iterator

import jwt

from app.connectors.base import SUPPORTED_EXT, Connector, ConnectorError, RemoteFile, check, client

API = "https://www.googleapis.com/drive/v3"
TOKEN = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/drive.readonly"
GFOLDER = "application/vnd.google-apps.folder"
GNATIVE = {"application/vnd.google-apps.document": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx")}


def folder_id_from(url_or_id: str) -> str:
    m = re.search(r"/folders/([A-Za-z0-9_\-]+)", url_or_id) or re.search(r"[?&]id=([A-Za-z0-9_\-]+)", url_or_id)
    return m.group(1) if m else url_or_id.strip()


class GoogleDrive(Connector):
    def __init__(self, config: dict, secrets: dict):
        super().__init__(config, secrets)
        self.api = config.get("api_base") or API
        self.token_url = config.get("token_url") or TOKEN
        self._tok: tuple[str, float] | None = None

    def token(self) -> str:
        if self._tok and self._tok[1] > time.time() + 60:
            return self._tok[0]
        with client() as c:
            if self.sec.get("service_account_json"):
                sa = json.loads(self.sec["service_account_json"]) if isinstance(self.sec["service_account_json"], str) else self.sec["service_account_json"]
                now = int(time.time())
                assertion = jwt.encode({"iss": sa["client_email"], "scope": SCOPE, "aud": self.token_url, "iat": now, "exp": now + 3000}, sa["private_key"], algorithm="RS256")
                r = check(c.post(self.token_url, data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion}), "Google sign-in (service account)")
            elif self.sec.get("refresh_token"):
                r = check(c.post(self.token_url, data={"grant_type": "refresh_token", "refresh_token": self.sec["refresh_token"], "client_id": self.sec.get("client_id", ""),
                                                      "client_secret": self.sec.get("client_secret", "")}), "Google sign-in (OAuth)")
            else:
                raise ConnectorError("add a service account JSON key or an OAuth refresh token")
        j = r.json()
        self._tok = (j["access_token"], time.time() + int(j.get("expires_in", 3600)))
        return self._tok[0]

    def _get(self, c, path: str, **params):
        return check(c.get(f"{self.api}{path}", params=params, headers={"Authorization": f"Bearer {self.token()}"}), f"Google Drive {path.split('?')[0]}")

    def root(self) -> str:
        fid = folder_id_from(self.cfg.get("folder") or "")
        if not fid:
            raise ConnectorError("set the Drive folder (a folder link or its ID)")
        return fid

    def test(self) -> dict:
        with client() as c:
            f = self._get(c, f"/files/{self.root()}", fields="id,name,mimeType", supportsAllDrives="true").json()
        if f.get("mimeType") != GFOLDER:
            raise ConnectorError(f"{f.get('name')} is not a folder")
        n = sum(1 for f in self.list_files() if f.name.lower().endswith(SUPPORTED_EXT))
        return {"ok": True, "detail": f"Connected to the folder “{f['name']}”: {n} supported file(s) found."}

    def list_files(self) -> Iterator[RemoteFile]:
        with client() as c:
            stack = [(self.root(), "")]
            while stack:
                fid, prefix = stack.pop()
                page = None
                while True:
                    j = self._get(c, "/files", q=f"'{fid}' in parents and trashed=false", fields="nextPageToken,files(id,name,mimeType,size,modifiedTime,md5Checksum,webViewLink)",
                                  pageSize="200", supportsAllDrives="true", includeItemsFromAllDrives="true", **({"pageToken": page} if page else {})).json()
                    for f in j.get("files", []):
                        if f["mimeType"] == GFOLDER:
                            if self.cfg.get("recursive", True):
                                stack.append((f["id"], f"{prefix}{f['name']}/"))
                            continue
                        name, export = f["name"], None
                        if f["mimeType"] in GNATIVE:
                            export = GNATIVE[f["mimeType"]][0]
                            name = name if name.lower().endswith(".docx") else name + ".docx"
                        yield RemoteFile(id=f["id"], name=name, path=f"{prefix}{name}", size=int(f["size"]) if f.get("size") else None, modified=f.get("modifiedTime"),
                                         etag=f.get("md5Checksum") or f.get("modifiedTime"), web_url=f.get("webViewLink"), export_as=export)
                    page = j.get("nextPageToken")
                    if not page:
                        break

    def download(self, f: RemoteFile) -> bytes:
        with client() as c:
            if f.export_as:
                r = self._get(c, f"/files/{f.id}/export", mimeType=f.export_as)
            else:
                r = self._get(c, f"/files/{f.id}", alt="media", supportsAllDrives="true")
            return r.content
