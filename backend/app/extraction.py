"""Field extraction. Claude (forced tool call, JSON schema) when an API key is set, otherwise a
deterministic regex extractor so the pipeline runs offline. Both return the same structure:
{field: {"value", "confidence", "clause_type", "page"}}."""
from __future__ import annotations

import re
from datetime import datetime

from app import llm
from app.config import settings

DATE_RE = r"(\d{1,2} [A-Z][a-z]+ \d{4})"
FIELDS = ["effective_date", "expiry_date", "notice_period_days", "auto_renew", "annual_value",
          "total_value", "payment_terms_days", "liability_cap_multiple", "liability_cap_text",
          "termination_for_convenience", "governing_law", "processes_personal_data", "has_dpa"]


def _iso(s: str) -> str:
    return datetime.strptime(s, "%d %B %Y").date().isoformat()


def _money(s: str) -> float:
    return float(s.replace(",", ""))


def heuristic_extract(header: dict[str, str], clauses: list[dict], doc_type: str) -> dict:
    by = {c["clause_type"]: c for c in clauses}
    out: dict[str, dict] = {}
    amendment = doc_type == "Amendment"

    def put(field, value, conf, ctype=None):
        c = by.get(ctype) if ctype else None
        out[field] = dict(value=value, confidence=conf, clause_type=ctype if c else None,
                          page=c["page"] if c else 1)

    if m := re.search(DATE_RE, header.get("Effective Date", "")):
        put("effective_date", _iso(m.group(1)), 0.98)
    if c := by.get("term"):
        if m := re.search(r"(?:expires on|extended to) " + DATE_RE, c["text"]):
            put("expiry_date", _iso(m.group(1)), 0.97, "term")
    if c := by.get("renewal"):
        if "renews automatically" in c["text"]:
            n = re.search(r"at least (\d+) days", c["text"])
            put("auto_renew", True, 0.97, "renewal")
            put("notice_period_days", int(n.group(1)) if n else None, 0.95 if n else 0.5,
                "renewal")
        else:
            put("auto_renew", False, 0.95, "renewal")
            put("notice_period_days", None, 0.9, "renewal")
    elif not amendment:
        put("auto_renew", False, 0.6)
        put("notice_period_days", None, 0.6)
    if c := by.get("fees"):
        a = re.search(r"annual fees .*? are INR ([\d,]+)", c["text"])
        t = re.search(r"total contract value is INR ([\d,]+)", c["text"])
        put("annual_value", _money(a.group(1)) if a else None, 0.95 if a else 0.4, "fees")
        put("total_value", _money(t.group(1)) if t else None, 0.95 if t else 0.4, "fees")
    elif not amendment:
        put("annual_value", None, 0.7)
        put("total_value", None, 0.7)
    if c := by.get("payment"):
        n = re.search(r"within (\d+) days", c["text"])
        put("payment_terms_days", int(n.group(1)) if n else None, 0.96 if n else 0.4, "payment")
    elif not amendment:
        put("payment_terms_days", None, 0.7)
    if c := by.get("liability_cap"):
        t = c["text"]
        if m := re.search(r"([\d.]+) times", t):
            put("liability_cap_multiple", float(m.group(1)), 0.96, "liability_cap")
            put("liability_cap_text", f"{m.group(1)} times annual fees", 0.96, "liability_cap")
        elif "unlimited" in t.lower():
            put("liability_cap_multiple", None, 0.95, "liability_cap")
            put("liability_cap_text", "Unlimited", 0.95, "liability_cap")
        elif "governed by" in t:
            put("liability_cap_multiple", None, 0.9, "liability_cap")
            put("liability_cap_text", "Governed by MSA", 0.9, "liability_cap")
        else:
            put("liability_cap_multiple", None, 0.3, "liability_cap")
    elif not amendment:
        put("liability_cap_multiple", None, 0.6)
        put("liability_cap_text", None, 0.6)
    if c := by.get("termination_for_convenience"):
        t = c["text"].lower()
        if "neither party may terminate" in t:
            put("termination_for_convenience", False, 0.96, "termination_for_convenience")
        elif "may terminate" in t and "convenience" in t:
            put("termination_for_convenience", True, 0.96, "termination_for_convenience")
        else:
            put("termination_for_convenience", None, 0.3, "termination_for_convenience")
    elif not amendment:
        put("termination_for_convenience", None, 0.6)
    if c := by.get("governing_law"):
        m = re.search(r"laws of ([A-Za-z ]+?)\.", c["text"])
        put("governing_law", m.group(1) if m else None, 0.97 if m else 0.4, "governing_law")
    elif not amendment:
        put("governing_law", None, 0.6)
    if not amendment:
        c = by.get("data_scope")
        if c:
            put("processes_personal_data", "do not involve" not in c["text"], 0.93, "data_scope")
        else:
            put("processes_personal_data", False, 0.6)
        if c := by.get("dpa_reference"):
            put("has_dpa", "Data Processing Agreement dated" in c["text"], 0.95, "dpa_reference")
        else:
            put("has_dpa", False, 0.75)
    return out


def llm_tool() -> dict:
    def f(t):
        return {"type": "object", "properties": {
            "value": {"type": [t, "null"]}, "confidence": {"type": "number"},
            "source_clause": {"type": ["integer", "null"]}},
            "required": ["value", "confidence", "source_clause"]}
    types = dict(effective_date="string", expiry_date="string", notice_period_days="integer",
                 auto_renew="boolean", annual_value="number", total_value="number",
                 payment_terms_days="integer", liability_cap_multiple="number",
                 liability_cap_text="string", termination_for_convenience="boolean",
                 governing_law="string", processes_personal_data="boolean", has_dpa="boolean")
    return {"name": "record_fields", "description": "Record the extracted contract fields.",
            "input_schema": {"type": "object", "properties": {k: f(v) for k, v in types.items()},
                             "required": list(types)}}


def llm_extract(md: str, header: dict, clauses: list[dict], doc_type: str) -> dict:
    res = llm.call_tool("extraction", settings.model_extract, llm.prompt("extract_fields"),
                        f"Document type: {doc_type}\n\n{md}", llm_tool())
    by_idx = {c["idx"]: c for c in clauses}
    out = {}
    for field, r in res.items():
        if doc_type == "Amendment" and r["value"] is None and field != "liability_cap_multiple":
            continue
        c = by_idx.get(r.get("source_clause"))
        out[field] = dict(value=r["value"], confidence=r["confidence"],
                          clause_type=c["clause_type"] if c else None,
                          page=c["page"] if c else 1)
    return out


def extract(md: str, header: dict, clauses: list[dict], doc_type: str,
            mode: str = "auto") -> tuple[dict, str]:
    use_llm = mode == "llm" or (mode == "auto" and llm.available())
    if use_llm:
        return llm_extract(md, header, clauses, doc_type), "llm"
    return heuristic_extract(header, clauses, doc_type), "heuristic"
