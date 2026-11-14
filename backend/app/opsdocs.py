"""Operational documents -> feed rows. Invoices, monthly service-level reports and milestone acceptance certificates (PDF, Word, Markdown, text, or scans via OCR)
are read from data/feeds/ and become rows of the invoices / SLA / obligation-status tables. Nothing here knows a vendor, contract or metric: metric names come from the
Values & limits configuration, contracts are matched through the loaded contracts, and values are read from the text. Rules read the common layouts; when Claude is
available it also fills whatever the rules could not find (never overriding a value the rules read)."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from sqlalchemy import text

from app import docstruct, llm
from app import textutil as tu
from app.config import settings
from app.db import SessionLocal
from app.extract_rules import COMPANY_RX, customer_markers

PARSER_VERSION = "7"        # bump when the readers change: parsed results are cached by content hash + this
DOC_EXT = {".pdf", ".docx", ".md", ".txt"}
AMT = r"(?:USD|US\$|\$)\s*([\d]{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)"
DATE_RX = r"(?:\d{1,2}[ \-/][A-Za-z]{3,9}[ \-/,]*\d{4}|[A-Za-z]{3,9}\.? \d{1,2},? \d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})"


def kind_of(t: str) -> str | None:
    head = t[:600].lower()
    if re.search(r"acceptance (?:certificate|notice)|certificate of acceptance|milestone acceptance|sign-?off certificate", head):
        return "acceptance"
    if re.search(r"service[- ]level (?:report|performance)|sla (?:report|performance)|monthly service report|service performance report", head):
        return "sla_report"
    if re.search(r"\binvoice\b|tax invoice|credit note", head):
        return "invoice"
    if re.search(r"certificate of (?:liability )?insurance|insurance certificate|evidence of insurance|haccp|food[- ]safety certificat|attestation of compliance|"
                 r"certificate of (?:\w+ )?inspection|inspection certificate|certificate of compliance", head):
        return "certificate"
    return None


def _after(label: str, t: str, rx: str, span: int = 60) -> str | None:
    m = re.search(rf"(?:{label})\W{{0,6}}({rx})", t[:], re.I) or re.search(rf"(?:{label})[^\n]{{0,{span}}}?({rx})", t, re.I)
    return m.group(1) if m else None


def _date(label: str, t: str) -> date | None:
    for m in re.finditer(rf"(?:{label})", t, re.I):
        d = tu.find_dates(t[m.end():m.end() + 45])
        if d and d[0][0] <= 22:
            return d[0][1]
    return None


def _clean(t: str) -> str:
    t = re.sub(r"<!--.*?-->", " ", t)
    t = re.sub(r"[*_`#]+", "", t)
    return re.sub(r"[ \t]+", " ", t.replace("\\", ""))


def _company(s: str):
    """The first company name in s, including a legal suffix that follows a 'Group' / 'Co.' ('Quill Staffing Group Ltd')."""
    m = COMPANY_RX.search(s)
    if not m:
        return None
    ext = re.match(r"\s+(?:Pte\s+Ltd|Ltd\.?|Limited|Inc\.?|LLC|LLP|Corp\.?|PLC|GmbH)(?![\w])", s[m.end():])
    return s[m.start():m.end() + (ext.end() if ext else 0)].strip()


def _vendor(t: str) -> str | None:
    cm = customer_markers()
    m = re.search(r"(?:from|supplier|issued by|vendor|remit(?:tance)? to|billed by|prepared by|provider)\s*[:|]\s*([^\n|]{3,80})", t, re.I)
    if m:
        c = _company(m.group(1))
        if c and not any(k in c.lower() for k in cm):
            return c
    for line in t[:1800].splitlines():              # a company name never spans lines; 'TAX INVOICE' above it is not part of it
        c = _company(re.sub(r"^\W*(?:tax\s+)?(?:invoice|statement|credit note)\W*", "", line, flags=re.I))
        if c and not any(k in c.lower() for k in cm):
            return c
    return None


def _reference(t: str) -> str | None:
    """The agreement / SOW / work order a document refers to, from a labelled line ('Agreement: X', '| Reference | X |', or 'Agreement X' once a Word table has lost its separators)."""
    m = re.search(r"(?:^|\n)[\s|]*(?:agreement|contract|sow|statement of work|work order|your ref(?:erence)?|our ref(?:erence)?|reference|re)\b[^:|\n]{0,20}?\s*[:|]\s*([^\n|]{6,160})", t, re.I)
    if not m:
        m = re.search(r"(?:^|\n)[\s|]*(?i:agreement|contract|your ref(?:erence)?|reference)\s+([A-Z][^\n|]{5,159})", t)
    return m.group(1).strip(" .|") if m else None


def parse_invoice(t: str) -> dict:
    r = {"vendor": _vendor(t), "contract_title": _reference(t)}
    m = re.search(r"(?:invoice\s*(?:no\.?|number|#|ref(?:erence)?)|tax invoice\s*(?:no\.?|number))\W{0,6}([A-Z0-9][A-Z0-9\-/]{3,})", t, re.I)
    r["invoice_no"] = m.group(1) if m else None
    r["invoice_date"] = _date(r"invoice date|date of issue|issue date|issued(?: on)?|dated", t)
    r["due_date"] = _date(r"due date|payment due(?: by| on| date)?|due on|pay(?:able)? by|due", t)
    r["paid_date"] = _date(r"paid on|date paid|payment received(?: on)?|settled on|remittance date", t)
    pm = re.search(rf"(?:service period|billing period|period|for the period|services? (?:from|rendered))\W{{0,4}}({DATE_RX})\s*(?:–|—|-|to|until)\s*({DATE_RX})", t, re.I)
    r["period_start"], r["period_end"] = (tu.first_date(pm.group(1)), tu.first_date(pm.group(2))) if pm else (None, None)
    am = re.search(rf"(?:total (?:amount )?due|amount (?:due|payable)|total payable|grand total|balance due|total (?:invoice )?amount|total)\W{{0,10}}{AMT}", t, re.I)
    if am:
        r["amount"] = float(am.group(1).replace(",", ""))
    else:
        allv = [float(x.replace(",", "")) for x in re.findall(AMT, t)]
        r["amount"] = max(allv) if allv else None
    dm = re.search(r"(?:description|particulars|details|for)\W{0,4}\n?\s*([^\n|]{8,120})", t, re.I)
    r["description"] = dm.group(1).strip(" .|") if dm else None
    if not r["invoice_date"]:
        ds = tu.find_dates(t[:700])
        r["invoice_date"] = ds[0][1] if ds else None
    return r


def parse_sla(t: str, metrics: list[dict]) -> dict:
    r = {"vendor": _vendor(t), "contract_title": _reference(t), "period": None, "rows": []}
    pm = re.search(rf"(?:reporting period|period|month|for)\W{{0,4}}((?:[A-Za-z]{{3,9}}\.? ?\d{{4}})|{DATE_RX})", t, re.I)
    if pm:
        d = tu.first_date(pm.group(1)) or tu.first_date("1 " + pm.group(1))
        r["period"] = date(d.year, d.month, 1) if d else None
    metric_words = {m["key"]: {w[:5] for w in re.findall(r"[a-z]{4,}", m["name"].lower())} for m in metrics if m.get("sla")}
    lines = t.splitlines()
    start = next((i for i, ln in enumerate(lines) if re.search(r"\bactual\b", ln, re.I) and re.search(r"target|incident|service level|metric|measure", ln, re.I)), None)
    has_inc = start is not None and bool(re.search(r"incident", lines[start], re.I))
    rows: list[dict] = []
    gap = False
    for ln in lines[(start + 1) if start is not None else 0:]:
        s = ln.replace("|", "  ").strip()
        if not s or re.fullmatch(r"[-=_ ]+", s):
            if rows and s:                               # the closing rule of the table
                break
            gap = True
            continue
        nums = list(re.finditer(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(?:%|hours?|hrs?|h|minutes?|min|days?)?(?![\w])", s))
        if not nums:                                     # a wrapped cell: more of the previous row's name
            if rows and len(s.split()) <= 4 and not gap:
                rows[-1]["name"] += " " + s
            continue
        gap = False
        name = re.split(r"\s+(?:per contract|n/?a|–|—|-{1,2})\s+|\s\d", s)[0]
        vals = [float(m.group(1)) for m in nums]
        rows.append(dict(name=name, vals=vals, line=s))
    for x in rows:
        words = {w[:5] for w in re.findall(r"[a-z]{4,}", x["name"].lower())}
        best = max(metric_words, key=lambda k: len(words & metric_words[k]) / max(len(metric_words[k]), 1), default=None)
        if not best or len(words & metric_words[best]) / len(metric_words[best]) < 0.6:
            continue
        v = x["vals"]
        actual, inc = (v[-2], int(v[-1])) if has_inc and len(v) >= 2 else (v[-1], 0)
        note = re.sub(r"^.*?\d[\d.]*\s*(?:%|hours?)?\s*(?:\d+\s*)?", "", x["line"]).strip()
        r["rows"].append(dict(metric_key=best, actual=actual, incidents=inc, note="" if re.fullmatch(r"(?i)no issues?|none|–|-", note) else note))
    return r


def parse_acceptance(t: str) -> dict:
    r = {"vendor": _vendor(t), "contract_title": _reference(t)}
    m = re.search(r"milestone\W{0,6}([^\n|]{5,160})", t, re.I)
    r["milestone"] = re.sub(r"\(?(?:due|planned)[^)\n]*\)?", "", m.group(1)).strip(" .:|-") if m else None
    r["due"] = _date(r"(?:due|planned|scheduled)(?: date| for)?", t)
    r["completed_on"] = _date(r"accepted on|date of acceptance|acceptance date|signed off on|accepted", t)
    n = re.search(r"(?:comments?|note|remarks)\W{0,4}([^\n|]{4,120})", t, re.I)
    r["note"] = n.group(1).strip() if n else None
    return r


CERT_KIND = [("payment_card_data", r"pci[- ]dss|attestation of compliance|payment[- ]card"), ("food_safety", r"haccp|food[- ]safety"),
             ("inspection_certificates", r"certificate of (?:\w+ )?inspection|inspection certificate|elevator|boiler|state[- ]mandated"), ("insurance", r"insurance|insured|policy")]


def parse_certificate(t: str) -> dict:
    """A vendor's compliance certificate: who holds it, what kind it is, when it runs out. The holder is the insured / certified company, never us."""
    cm = customer_markers()
    vendor = None
    m = re.search(r"(?:insured|named insured|issued to|certified (?:company|entity|organi[sz]ation)|merchant|service provider|contractor|supplier|holder of this certificate)\s*[:|]\s*([^\n|]{3,90})", t, re.I)
    if m:
        c = _company(m.group(1))
        vendor = c if c and not any(k in c.lower() for k in cm) else None
    head = t[:700].lower()
    kind = next((k for k, rx in CERT_KIND if re.search(rx, head)), None)
    ref = re.search(r"(?:certificate|policy|reference|report|attestation)\s*(?:no\.?|number|#|id|ref(?:erence)?)\s*[:|]?\s*([A-Z0-9][A-Z0-9\-/]{3,30})", t, re.I)
    return {"vendor": vendor or _vendor(t), "kind": kind, "expiry_date": _date(r"expir(?:y|es|ation)(?: date)?|valid (?:until|through|to)|policy period[^\n]{0,40}?\bto\b|next inspection due|good through", t),
            "received_on": _date(r"issued(?: on)?|date of issue|issue date|effective(?: date)?|inspection date|dated", t), "reference": ref.group(1) if ref else None}


# ------------------------------------------------------------------ Claude gap filler
def _tool(kind: str) -> dict:
    props = {"invoice": {"vendor": "string", "contract_title": "string (the agreement / SOW / work order the invoice refers to, as written)", "invoice_no": "string", "invoice_date": "YYYY-MM-DD",
                         "due_date": "YYYY-MM-DD or null", "paid_date": "YYYY-MM-DD or null", "period_start": "YYYY-MM-DD or null", "period_end": "YYYY-MM-DD or null",
                         "amount": "number, the total payable", "description": "string"},
             "acceptance": {"vendor": "string", "contract_title": "string", "milestone": "string", "due": "YYYY-MM-DD or null", "completed_on": "YYYY-MM-DD", "note": "string"}}[kind]
    return {"name": "record", "description": f"Record the fields of this {kind} document. Use null when the document does not say.",
            "input_schema": {"type": "object", "properties": {k: {"type": ["string", "number", "null"], "description": v} for k, v in props.items()}}}


def _fill(kind: str, t: str, row: dict) -> dict:
    need = {"invoice": ("invoice_no", "amount", "invoice_date", "vendor"), "acceptance": ("completed_on", "milestone")}.get(kind, ())
    if not llm.available() or all(row.get(k) for k in need):
        return row
    try:
        got = llm.call_tool("ops_document", settings.model_extract, "You read business documents precisely and never guess.", t[:6000], _tool(kind), max_tokens=900)
    except Exception as e:
        llm.note_failure(e)
        return row
    for k, v in (got or {}).items():
        if row.get(k) in (None, "") and v not in (None, ""):
            row[k] = tu.first_date(v) if k.endswith(("date", "_on", "start", "end")) or k == "due" else v
    return row


# ------------------------------------------------------------------ entry point
def read(path: Path) -> tuple[str | None, list[dict]]:
    """(kind, feed rows) for one document; rows use the feed column names. Raises ValueError when the document is none of the known kinds."""
    t = _clean(docstruct.load_document(path))
    kind = kind_of(t)
    if not kind:
        raise ValueError("not recognised as an invoice, service-level report, acceptance certificate or compliance certificate")
    if kind == "invoice":
        row = _fill("invoice", t, parse_invoice(t))
        if not (row.get("amount") and row.get("invoice_date")):
            raise ValueError("invoice without a readable amount or date")
        row["external_id"] = path.name
        return kind, [row]
    if kind == "sla_report":
        with SessionLocal() as s:
            metrics = [dict(m) for m in s.execute(text("SELECT key, name, sla FROM metrics")).mappings()]
        r = parse_sla(t, metrics)
        if not r["period"] or not r["rows"]:
            raise ValueError("service-level report without a period or recognised service levels")
        return kind, [dict(contract_title=r["contract_title"], vendor=r["vendor"], period=r["period"], **x) for x in r["rows"]]
    if kind == "certificate":
        row = parse_certificate(t)
        if not (row.get("vendor") and row.get("kind") and row.get("expiry_date")):
            raise ValueError("certificate without a readable holder, kind or expiry date")
        return kind, [row]
    row = _fill("acceptance", t, parse_acceptance(t))
    if not (row.get("completed_on") and row.get("milestone")):
        raise ValueError("acceptance certificate without a milestone or date")
    return kind, [{**row, "status": "done"}]
