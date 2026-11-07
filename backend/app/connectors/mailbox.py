"""Mailbox intake (IMAP): attachments of unread mail in one folder (PDF, Word, text) become files, like a synced folder. Mail that is not an attachment carrier is ignored.
Config: host, port, ssl, folder, username, optional from_filter / subject_filter; secret: password. Messages are marked read once their attachments were taken."""
from __future__ import annotations

import email
import imaplib
from email.header import decode_header, make_header
from typing import Iterator

from app.connectors.base import SUPPORTED_EXT, Connector, ConnectorError, RemoteFile


def _h(v: str | None) -> str:
    return str(make_header(decode_header(v or "")))


class Mailbox(Connector):
    def _open(self):
        try:
            cls = imaplib.IMAP4_SSL if self.cfg.get("ssl", True) not in (False, "false", "False") else imaplib.IMAP4
            m = cls(self.cfg.get("host", ""), int(self.cfg.get("port") or (993 if cls is imaplib.IMAP4_SSL else 143)))
            m.login(self.cfg.get("username", ""), self.sec.get("password", ""))
            typ, _ = m.select(self.cfg.get("folder") or "INBOX")
            if typ != "OK":
                raise ConnectorError(f"mail folder {self.cfg.get('folder') or 'INBOX'} could not be opened")
            return m
        except (imaplib.IMAP4.error, OSError) as e:
            raise ConnectorError(f"mailbox login failed: {e}")

    def test(self) -> dict:
        m = self._open()
        try:
            typ, data = m.search(None, "UNSEEN")
            return {"ok": True, "detail": f"signed in; {len(data[0].split()) if data and data[0] else 0} unread message(s) in {self.cfg.get('folder') or 'INBOX'}"}
        finally:
            m.logout()

    def _query(self) -> str:
        parts = ["UNSEEN"]
        if self.cfg.get("from_filter"):
            parts += ["FROM", f'"{self.cfg["from_filter"]}"']
        if self.cfg.get("subject_filter"):
            parts += ["SUBJECT", f'"{self.cfg["subject_filter"]}"']
        return " ".join(parts)

    def list_files(self) -> Iterator[RemoteFile]:
        m = self._open()
        self._cache: dict[str, bytes] = {}
        self._seen: set[str] = set()
        try:
            typ, data = m.search(None, self._query())
            for num in (data[0].split() if data and data[0] else []):
                typ, msg_data = m.fetch(num, "(BODY.PEEK[])")
                msg = email.message_from_bytes(msg_data[0][1])
                sender, subject, mid = _h(msg.get("From")), _h(msg.get("Subject")), (msg.get("Message-ID") or num.decode()).strip()
                for i, part in enumerate(msg.walk()):
                    name = _h(part.get_filename())
                    if not name or not name.lower().endswith(SUPPORTED_EXT):
                        continue
                    rid = f"{mid}#{i}"
                    self._cache[rid] = part.get_payload(decode=True) or b""
                    self._seen.add(num.decode())
                    yield RemoteFile(id=rid, name=name, path=f"{sender.split('<')[-1].strip('>')}/{name}", size=len(self._cache[rid]), modified=msg.get("Date"), etag=mid,
                                     web_url=None, extra={"from": sender, "subject": subject})
            for n in self._seen:                                   # taken: mark read so the next sync does not fetch them again
                m.store(n, "+FLAGS", "\\Seen")
        finally:
            m.logout()

    def download(self, f: RemoteFile) -> bytes:
        return self._cache[f.id]
