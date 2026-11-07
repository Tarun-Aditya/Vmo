"""Split a Markdown contract into header metadata and clauses with page numbers."""

from __future__ import annotations

import re

from app.docgen.library import HEADING_TO_TYPE

PAGE_RE = re.compile(r"^<!--\s*page:\s*(\d+)\s*-->$")
CLAUSE_RE = re.compile(r"^##\s+(?:(\d+)\.\s+)?(.+?)\s*$")
HEADER_RE = re.compile(r"^\*\*(.+?):\*\*\s*(.+?)\s*$")


def parse_document(md: str, classify=None) -> tuple[dict[str, str], list[dict]]:
    """Return (header, clauses). Each clause: idx, heading, clause_type, text, page.

    `classify(heading, text) -> key` decides the clause type (the pipeline passes the configurable
    KCC classifier); without it the built-in heading map is used."""
    header: dict[str, str] = {}
    clauses: list[dict] = []
    page, cur = 1, None
    pre: list[tuple[int, str]] = []          # text before the first recognised heading: real contracts put recitals, definitions, even whole sections there
    for line in md.splitlines():
        if m := PAGE_RE.match(line):
            page = int(m.group(1))
            continue
        if m := CLAUSE_RE.match(line):
            cur = dict(idx=int(m.group(1)) if m.group(1) else len(clauses) + 1, heading=m.group(2),
                       clause_type="other", text="", page=page)
            clauses.append(cur)
        elif cur is None:
            if m := HEADER_RE.match(line):
                header[m.group(1)] = m.group(2)
            elif line.strip() and not line.lstrip().startswith("#"):
                pre.append((page, line.strip()))
        elif line.strip():
            cur["text"] = (cur["text"] + " " + line.strip()).strip()
    if sum(len(x) for _, x in pre) > 400:        # keep it (per page, so citations carry the right page) instead of silently dropping it
        by_page: dict[int, list[str]] = {}
        for pg, x in pre:
            by_page.setdefault(pg, []).append(x)
        lead = [dict(idx=0, heading=f"Preamble (page {pg})", clause_type="other", text=" ".join(xs), page=pg) for pg, xs in by_page.items()]
        clauses = lead + clauses
    for c in clauses:
        c["clause_type"] = classify(c["heading"], c["text"]) if classify else HEADING_TO_TYPE.get(c["heading"], "other")
    return header, clauses
