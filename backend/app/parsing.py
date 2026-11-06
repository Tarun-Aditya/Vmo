"""Split a Markdown contract into header metadata and clauses with page numbers."""

from __future__ import annotations

import re

from app.docgen.library import HEADING_TO_TYPE

PAGE_RE = re.compile(r"^<!--\s*page:\s*(\d+)\s*-->$")
CLAUSE_RE = re.compile(r"^##\s+(\d+)\.\s+(.+?)\s*$")
HEADER_RE = re.compile(r"^\*\*(.+?):\*\*\s*(.+?)\s*$")


def parse_document(md: str) -> tuple[dict[str, str], list[dict]]:
    """Return (header, clauses). Each clause: idx, heading, clause_type, text, page."""
    header: dict[str, str] = {}
    clauses: list[dict] = []
    page, cur = 1, None
    for line in md.splitlines():
        if m := PAGE_RE.match(line):
            page = int(m.group(1))
            continue
        if m := CLAUSE_RE.match(line):
            cur = dict(
                idx=int(m.group(1)),
                heading=m.group(2),
                clause_type=HEADING_TO_TYPE.get(m.group(2), "other"),
                text="",
                page=page,
            )
            clauses.append(cur)
        elif cur is None:
            if m := HEADER_RE.match(line):
                header[m.group(1)] = m.group(2)
        elif line.strip():
            cur["text"] = (cur["text"] + " " + line.strip()).strip()
    # the signature block sits after the last clause; drop it from that clause
    if clauses and clauses[-1]["text"].startswith("Signed for"):
        clauses.pop()
    elif clauses:
        clauses[-1]["text"] = clauses[-1]["text"].split(" Signed for and on behalf")[0]
    return header, clauses
