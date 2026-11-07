from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator

import httpx

SUPPORTED_EXT = (".pdf", ".docx", ".md", ".txt", ".html", ".htm")


@dataclass
class RemoteFile:
    id: str
    name: str
    path: str               # folder path under the connector's root, with the file name
    size: int | None = None
    modified: str | None = None
    etag: str | None = None
    web_url: str | None = None
    export_as: str | None = None      # Google-native documents are exported (e.g. to .docx)
    extra: dict = field(default_factory=dict)


class ConnectorError(RuntimeError):
    pass


def client(follow: bool = True) -> httpx.Client:
    return httpx.Client(timeout=60, follow_redirects=follow, headers={"User-Agent": "ContractIQ-connector/1.0"})


def check(r: httpx.Response, what: str) -> httpx.Response:
    if r.status_code >= 400:
        msg = r.text[:300]
        try:
            j = r.json()
            msg = (j.get("error", {}).get("message") if isinstance(j.get("error"), dict) else j.get("error_description") or j.get("error")) or msg
        except Exception:
            pass
        raise ConnectorError(f"{what} failed ({r.status_code}): {msg}")
    return r


class Connector:
    """Subclasses implement test / list_files / download."""

    def __init__(self, config: dict, secrets: dict):
        self.cfg, self.sec = config, secrets

    def test(self) -> dict:                     # -> {"ok": True, "detail": "..."}
        raise NotImplementedError

    def list_files(self) -> Iterator[RemoteFile]:
        raise NotImplementedError

    def download(self, f: RemoteFile) -> bytes:
        raise NotImplementedError
