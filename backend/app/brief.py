"""Turn free-form deal details (an email, a term sheet, key: value lines, JSON, CSV, a Word file's text) into the
parameters of a New Contract form. Claude fills the schema when a key is set; otherwise a rule-based reader does."""
from __future__ import annotations

import csv
import io
import json
import re
from datetime import date

from app import llm
from app.config import settings

LABELS: dict[str, list[str]] = {
    "vendor": ["vendor", "supplier", "counterparty", "service provider", "company", "party"],
    "title": ["title", "document title", "name"],
    "effective_date": ["effective date", "start date", "commencement", "commencement date", "start", "effective"],
    "term_months": ["term", "term months", "term (months)", "duration", "contract term", "term in months"],
    "owner": ["owner", "contract owner", "business owner", "relationship owner"],
    "category": ["category", "spend category"],
    "scope": ["scope", "scope of work", "services", "description", "project"],
    "annual_fees": ["annual fees", "annual value", "annual fee", "yearly fees", "fees per year", "acv"],
    "fixed_fee": ["fixed fee", "total fee", "total fees", "total value", "fee"],
    "payment_terms_days": ["payment terms", "payment", "payment days", "net"],
    "auto_renew": ["auto renew", "auto-renew", "auto renewal", "auto-renewal", "renewal", "renews"],
    "notice_days": ["notice", "notice days", "notice period", "non-renewal notice"],
    "governing_law": ["governing law", "law", "jurisdiction"],
    "liability_cap": ["liability cap", "cap", "liability", "limitation of liability"],
    "tfc_notice_days": ["termination for convenience", "tfc notice", "tfc", "termination notice"],
    "warranty_days": ["warranty", "warranty days", "warranty period"],
    "insurance_cover_usd": ["insurance", "insurance cover", "insurance cover per claim"],
    "confidentiality_years": ["confidentiality", "confidentiality period", "confidentiality years"],
    "sla": ["sla", "availability", "uptime", "availability sla"],
    "personal_data": ["personal data", "processes personal data", "pii"],
    "subjects": ["data subjects", "whose personal data"],
    "template": ["template", "contract type", "document type", "type"],
}
NUMERIC = {"term_months", "annual_fees", "fixed_fee", "payment_terms_days", "notice_days", "liability_cap", "tfc_notice_days", "warranty_days",
           "insurance_cover_usd", "confidentiality_years", "sla"}
BOOL = {"auto_renew", "personal_data"}
TEMPLATE_WORDS = [("MSA", r"master services|\bmsa\b"), ("WO", r"work order"), ("SOW", r"statement of work|\bsow\b"), ("NDA", r"non-disclosure|\bnda\b|confidentiality agreement"),
                  ("DPA", r"data processing"), ("SaaS", r"saas|subscription|software as a service|licen[cs]e")]
MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()
_ALIAS = {a: k for k, v in LABELS.items() for a in v}


def _money(s: str) -> float | None:
    m = re.search(r"(?:usd|us\$|\$)?\s*([\d][\d,]*(?:\.\d+)?)\s*(m|mm|million|k|thousand|bn|billion)?\b", s.lower())
    if not m:
        return None
    v = float(m.group(1).replace(",", ""))
    return v * {"m": 1e6, "mm": 1e6, "million": 1e6, "k": 1e3, "thousand": 1e3, "bn": 1e9, "billion": 1e9}.get(m.group(2) or "", 1)


def _date(s: str) -> str | None:
    s = s.strip()
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return m.group(0)
    m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})", s)
    if m and m.group(2)[:3].lower() in MONTHS:
        return date(int(m.group(3)), MONTHS.index(m.group(2)[:3].lower()) + 1, int(m.group(1))).isoformat()
    m = re.search(r"([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", s)
    if m and m.group(1)[:3].lower() in MONTHS:
        return date(int(m.group(3)), MONTHS.index(m.group(1)[:3].lower()) + 1, int(m.group(2))).isoformat()
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        return date(int(m.group(3)), int(m.group(1)), int(m.group(2))).isoformat()
    return None


def _months(s: str) -> int | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*[- ]?\s*(year|yr|month|mo)", s.lower())
    if not m:
        return int(s) if s.strip().isdigit() else None
    n = float(m.group(1))
    return int(round(n * 12)) if m.group(2).startswith(("y", "Y")) else int(round(n))


def _bool(s: str) -> bool | None:
    t = s.strip().lower()
    if re.match(r"(yes|y|true|auto|automatic|will|renews|auto-?renew)", t):
        return True
    if re.match(r"(no|n|false|none|not|does not|manual)", t):
        return False
    return None


def _coerce(field: str, raw) -> object | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, (bool, int, float)) and field not in ("effective_date",):
        return raw if field in NUMERIC | BOOL else str(raw)
    s = str(raw).strip()
    if field == "effective_date":
        return _date(s)
    if field == "term_months":
        return _months(s)
    if field in ("annual_fees", "fixed_fee", "insurance_cover_usd"):
        return _money(s)
    if field in ("payment_terms_days", "notice_days", "tfc_notice_days", "warranty_days"):
        m = re.search(r"(\d+)", s)
        return int(m.group(1)) if m else None
    if field == "liability_cap":
        m = re.search(r"(\d+(?:\.\d+)?)", s)
        return float(m.group(1)) if m else None
    if field == "confidentiality_years":
        m = re.search(r"(\d+)", s)
        if not m:
            return None
        n = int(m.group(1))
        return max(1, n // 12) if re.search(r"month", s.lower()) else n
    if field == "sla":
        m = re.search(r"(\d{2,3}(?:\.\d+)?)", s)
        return float(m.group(1)) if m else None
    if field in BOOL:
        return _bool(s)
    if field == "template":
        return guess_template(s)
    return s


def guess_template(text: str) -> str | None:
    t = text.lower()
    for k, pat in TEMPLATE_WORDS:
        if re.search(pat, t):
            return k
    return None


def _structured(text: str) -> dict[str, tuple[object, str]]:
    """key: value lines, a JSON object or a two-column CSV."""
    found: dict[str, tuple[object, str]] = {}
    pairs: list[tuple[str, str]] = []
    t = text.strip()
    if t.startswith("{"):
        try:
            pairs = [(str(k), v if isinstance(v, (bool, int, float)) else str(v)) for k, v in json.loads(t).items()]
        except ValueError:
            pairs = []
    if not pairs and t.count(",") >= 2 and "\n" in t and not re.search(r"^\s*[\w ()/-]+\s*:\s*\S", t, re.M):
        try:
            rows = list(csv.reader(io.StringIO(t)))
            if rows and len(rows[0]) == 2:
                pairs = [(r[0], r[1]) for r in rows if len(r) >= 2]
            elif len(rows) >= 2:
                pairs = list(zip(rows[0], rows[1]))
        except csv.Error:
            pass
    if not pairs:
        for ln in t.splitlines():
            m = re.match(r"^\s*[-*•]?\s*\**([A-Za-z][\w ()/&-]{1,40}?)\**\s*[:=–-]\s*(.+?)\s*$", ln)
            if m:
                pairs.append((m.group(1), re.split(r"\.\s+(?=[A-Z])", m.group(2))[0].rstrip(".")))
    for k, v in pairs:
        f = _ALIAS.get(k.strip().lower().rstrip(":"))
        if f and f not in found:
            c = _coerce(f, v)
            if c is not None:
                found[f] = (c, f"{k}: {v}")
    return found


def _free_text(text: str, found: dict) -> None:
    def put(f: str, v, src: str) -> None:
        if v is not None and f not in found:
            found[f] = (v, src.strip()[:120])

    t = " ".join(text.split())
    m = re.search(r"(?:with|between .{0,40}? and|supplier is|vendor is|engage|engaging|appoint)\s+([A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){0,4}(?:\s+(?:Inc|LLP|LLC|Ltd|Limited|Corp|GmbH|Technologies|Systems|Services))?)", text)
    if m:
        put("vendor", re.sub(r"\s+(for|to|on|under|starting)$", "", m.group(1)).strip(), m.group(0))
    m = re.search(r"(?:effective|start(?:ing)?|commenc\w+|from|begin\w*)\s*(?:on|date)?:?\s*([^.;,]{4,30}\d{4})", t, re.I)
    if m:
        put("effective_date", _date(m.group(1)), m.group(0))
    m = re.search(r"(\d+(?:\.\d+)?)[- ]?(year|yr|month)s?\b(?:\s+(?:term|contract|agreement|initial))?", t, re.I)
    if m:
        put("term_months", _months(m.group(0)), m.group(0))
    m = re.search(r"(?:annual|per year|yearly|a year|/yr)[^$\d]{0,30}((?:usd|us\$|\$)\s*[\d,.]+\s*(?:m|mm|million|k)?)|((?:usd|us\$|\$)\s*[\d,.]+\s*(?:m|mm|million|k)?)\s*(?:per year|annually|a year|/yr|per annum)", t, re.I)
    if m:
        put("annual_fees", _money(m.group(1) or m.group(2)), m.group(0))
    m = re.search(r"(?:fixed fee|fixed price|total (?:fee|price|cost|value)|capped at|budget(?:ed)? (?:of|at)?)\D{0,15}((?:usd|us\$|\$)\s*[\d,.]+\s*(?:m|mm|million|k)?)", t, re.I)
    if m:
        put("fixed_fee", _money(m.group(1)), m.group(0))
    m = re.search(r"(?:net[- ]?(\d{1,3})|payment(?: terms)?[^.\d]{0,25}(\d{1,3})\s*days|(\d{1,3})\s*days? (?:payment|to pay))", t, re.I)
    if m:
        put("payment_terms_days", int(next(g for g in m.groups() if g)), m.group(0))
    m = re.search(r"(?i:governed by) (?:the )?(?i:laws? of) (?:the )?(?:State of )?([A-Z][A-Za-z ]{2,30}?)(?:[.,;]| and | courts)", text)
    if m:
        put("governing_law", m.group(1).strip(), m.group(0))
    m = re.search(r"(?:liability|cap)\D{0,30}(\d+(?:\.\d+)?)\s*(?:x|times)", t, re.I) or re.search(r"(\d+(?:\.\d+)?)\s*(?:x|times)\s*(?:the )?(?:annual )?fees", t, re.I)
    if m:
        put("liability_cap", float(m.group(1)), m.group(0))
    m = re.search(r"(\d{2,3}(?:\.\d+)?)\s*%\s*(?:availability|uptime|sla)|(?:availability|uptime|sla)\D{0,15}(\d{2,3}(?:\.\d+)?)\s*%", t, re.I)
    if m:
        put("sla", float(m.group(1) or m.group(2)), m.group(0))
    m = re.search(r"(\d{1,3})\s*days?[' ]*(?:notice)?\s*(?:of )?(?:non-renewal|notice to (?:not )?renew)|non-renewal notice\D{0,15}(\d{1,3})\s*days?", t, re.I)
    if m:
        put("notice_days", int(m.group(1) or m.group(2)), m.group(0))
    if re.search(r"auto[- ]?renew|renews automatically|automatic(?:ally)? renew", t, re.I) and not re.search(r"(no|not|without)[- ](?:auto[- ]?)?renew|does not (?:auto|renew)", t, re.I):
        put("auto_renew", True, "auto-renew mentioned")
    if re.search(r"personal data|\bpii\b|customer data", t, re.I) and not re.search(r"no personal data|without personal data|not process personal", t, re.I):
        put("personal_data", True, "personal data mentioned")
    m = re.search(r"(?i:(?:contract |business |relationship )?owner)\s*(?:is|:)\s*([A-Z][\w'-]*(?: [A-Z][\w'-]*){0,3})", text)
    if m:
        put("owner", m.group(1), m.group(0))
    m = re.search(r"\bfor (?:a|an|the) ([A-Za-z][^.;]{8,90}?)(?: (?:starting|beginning|commencing|from|effective|for \d|with|at|, )|[.;,])", text)
    if m and re.search(r"(?i)build|platform|migration|implementation|support|managed|transformation|assessment|development|testing|retainer|services", m.group(1)):
        put("scope", m.group(1).strip().capitalize(), m.group(0))
    m = re.search(r"(?:warranty)\D{0,20}(\d{1,3})\s*days", t, re.I)
    if m:
        put("warranty_days", int(m.group(1)), m.group(0))
    m = re.search(r"(?:scope|services?|project|engagement)\s*(?:is|are|:|covers?|include[s]?)\s*([^.]{15,200})\.", text, re.I)
    if m:
        put("scope", m.group(1).strip(), m.group(0))


SCHEMA = {
    "name": "fill_contract_form", "description": "Extract new-contract parameters from the user's notes. Omit anything not stated.",
    "input_schema": {"type": "object", "properties": {
        "template": {"type": "string", "enum": ["MSA", "SOW", "WO", "NDA", "SaaS", "DPA"]}, "vendor": {"type": "string"}, "title": {"type": "string"},
        "effective_date": {"type": "string", "description": "ISO date"}, "term_months": {"type": "integer"}, "owner": {"type": "string"}, "category": {"type": "string"},
        "scope": {"type": "string"}, "annual_fees": {"type": "number"}, "fixed_fee": {"type": "number"}, "payment_terms_days": {"type": "integer"},
        "auto_renew": {"type": "boolean"}, "notice_days": {"type": "integer"}, "governing_law": {"type": "string"}, "liability_cap": {"type": "number", "description": "multiple of annual fees"},
        "tfc_notice_days": {"type": "integer"}, "warranty_days": {"type": "integer"}, "insurance_cover_usd": {"type": "number"},
        "confidentiality_years": {"type": "integer"}, "sla": {"type": "number"}, "personal_data": {"type": "boolean"}, "subjects": {"type": "string"}}},
}


def read_brief(text: str, template: str | None = None) -> dict:
    """-> {template, params, found: [{field, value, source}], engine}"""
    found: dict[str, tuple[object, str]] = {}
    engine = "rules"
    if llm.available():
        try:
            out = llm.call_tool("brief", settings.model_extract, "You fill a contract form from the user's notes. Only use facts stated in the text.", text[:12000], SCHEMA)
            for k, v in out.items():
                c = _coerce(k, v)
                if c is not None:
                    found[k] = (c, "Claude")
            engine = "claude"
        except Exception:
            found = {}
    if not found:
        found = _structured(text)
        _free_text(text, found)
    tpl = template or (found.pop("template", (None, ""))[0] if "template" in found else None) or guess_template(text)
    found.pop("template", None)
    params = {k: v for k, (v, _) in found.items()}
    return {"template": tpl, "params": params, "engine": engine,
            "found": [{"field": k, "value": v, "source": src} for k, (v, src) in found.items()]}
