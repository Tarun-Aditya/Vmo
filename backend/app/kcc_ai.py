"""Claude-assisted tagging of clauses an admin added to the library.

Keywords and headings find the obvious cases offline. When Claude is available it also reads each document once per
(document content, clause definition) and finds passages in any wording; the answer is cached by content hash so a run only
pays for documents or definitions that changed."""
from __future__ import annotations

import hashlib
import json
import re

from sqlalchemy import text

from app import llm
from app.config import settings

TAG_SUFFIX = "(AI-tagged)"
MAX_CHARS = 60_000
_TOOL = {
    "name": "report_matches",
    "description": "Report which clause definitions the contract covers.",
    "input_schema": {"type": "object", "properties": {"matches": {"type": "array", "items": {"type": "object", "properties": {
        "key": {"type": "string"}, "clause_index": {"type": "integer"}, "quote": {"type": "string"}}, "required": ["key", "clause_index", "quote"]}}},
        "required": ["matches"]},
}


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip().lower()


def definitions(kcc_cfg: list[dict], have_types: set[str]) -> list[dict]:
    return [k for k in kcc_cfg if not k.get("builtin") and k.get("enabled", True) and k["key"] not in have_types
            and (k.get("description") or k.get("standard_text") or k.get("keywords"))]


def tag(s, clauses: list[dict], content_hash: str, defs: list[dict], doc_type: str | None = None) -> list[dict]:
    """Extra clause records {clause_type, heading, text, page} found by Claude. Offline / no definitions -> []."""
    defs = [d for d in defs if not d.get("applies_to") or doc_type is None or doc_type in d["applies_to"]]
    if not defs or not clauses or not llm.available():
        return []
    out: list[dict] = []
    dh = {d["key"]: hashlib.sha256(json.dumps([d["name"], d.get("description"), d.get("standard_text"), d.get("keywords")], sort_keys=True).encode()).hexdigest()[:24] for d in defs}
    todo = []
    for d in defs:
        hit = s.execute(text("SELECT result FROM kcc_ai_cache WHERE content_hash=:h AND key=:k AND def_hash=:d"), {"h": content_hash, "k": d["key"], "d": dh[d["key"]]}).scalar()
        if hit is None:
            todo.append(d)
        elif hit:
            out.append(hit)
    if todo:
        body, used = [], 0
        for i, c in enumerate(clauses):
            t = c["text"][:1500]
            if used + len(t) > MAX_CHARS:
                break
            body.append(f"[{i}] {c['heading']} (page {c.get('page')}):\n{t}")
            used += len(t)
        user = ("CLAUSE DEFINITIONS:\n" + "\n".join(f"- key={d['key']} | {d['name']} | {d.get('description') or ''} | standard: {d.get('standard_text') or ''} | keywords: {', '.join(d.get('keywords') or [])}" for d in todo)
                + "\n\nCONTRACT CLAUSES:\n" + "\n\n".join(body))
        try:
            res = llm.call_tool("kcc_tag", settings.model_extract, llm.prompt("kcc_tag"), user, _TOOL, max_tokens=2000)
        except Exception as e:      # limit / network: keywords already ran; nothing cached so the next run retries
            llm.note_failure(e)
            return out
        best = {}
        for m in res.get("matches", []):
            i, q = m.get("clause_index"), (m.get("quote") or "").strip()
            if m.get("key") in dh and isinstance(i, int) and 0 <= i < len(clauses) and q and _norm(q) in _norm(clauses[i]["text"]):    # a quote not in the clause is a hallucination
                best.setdefault(m["key"], {"clause_type": m["key"], "heading": f"{clauses[i]['heading'][:60]} {TAG_SUFFIX}", "text": q[:900], "page": clauses[i].get("page", 1), "idx": 0})
        for d in todo:
            r = best.get(d["key"])
            s.execute(text("INSERT INTO kcc_ai_cache (content_hash, key, def_hash, result) VALUES (:h,:k,:d,CAST(:r AS jsonb)) ON CONFLICT (content_hash,key,def_hash) DO UPDATE SET result=EXCLUDED.result"),
                      {"h": content_hash, "k": d["key"], "d": dh[d["key"]], "r": json.dumps(r or {})})
            if r:
                out.append(r)
    return out
