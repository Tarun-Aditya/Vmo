"""Offline question -> SQL -> table planner (the Claude path does this natively).

Understands counts / totals / averages, group-by, time windows, filters (type, category, vendor,
owner, auto-renewing, uncapped, DPA, signed/unsigned, clause present/absent, drafts), which columns
to show (dates, signatories, any extracted value or limit), numeric thresholds ("payment terms below
45 days"), checklist questions ("which contracts fail the checklist?") and questions about a scope of
selected documents (a document card, its clauses, or the closest clauses). Every answer is real SQL
over the extracted data in Postgres, or a semantic clause search."""

from __future__ import annotations

import datetime as dt
import re

from sqlalchemy import text

from app.ask import execute_tool
from app.ask_present import label_of
from app.ask_scripted import money
from app.db import SessionLocal
from app.extract_rules import customer_markers

BASE = "v_effective_terms JOIN v_key_clauses USING (contract_id)"
BASE_ALL = "v_document_terms JOIN v_key_clauses USING (contract_id)"
NOTICE = "(expiry_date - COALESCE(notice_period_days, 0))"
DIMS = {"property": "COALESCE((SELECT c.property FROM contracts c WHERE c.id = contract_id), 'Group level')", "category": "category", "vendor": "vendor", "type": "type", "owner": "owner", "status": "status",
        "month": "to_char(date_trunc('month', {d}), 'YYYY-MM')", "quarter": "to_char(date_trunc('quarter', {d}), 'YYYY \"Q\"Q')"}
TYPE_WORDS = {"msa": "MSA", "sow": "SOW", "nda": "NDA", "dpa": "DPA", "saas": "SaaS", "work orders?": "Work Order", "wos?": "Work Order"}
SIG_COLS = ["customer_signatory", "customer_signed_date", "supplier_signatory", "supplier_signed_date", "fully_executed"]
ATTRS = [
    (r"start date|effective date|commenc|\bstarts?\b|\bstarting\b", ["effective_date"]),
    (r"end date|expir|renewal date|\bends?\b", ["expiry_date"]),
    (r"notice", ["notice_deadline"]),
    (r"annual value|\bvalue\b|worth|spend|\bcost|\bfees?\b", ["annual_value"]),
    (r"total value|fixed fee", ["total_value"]),
    (r"liability cap|cap on liability|how much liability|liability limit", ["liability_cap_text"]),
    (r"\bowners?\b", ["owner"]),
    (r"categor", ["category"]),
    (r"signature|signed|signator|execut|countersign|who signed", SIG_COLS),
    (r"auto[- ]?renew", ["auto_renew"]),
    (r"termination for convenience", ["termination_for_convenience"]),
]
DEFAULT_COLS = ["title", "vendor", "type", "effective_date", "expiry_date", "annual_value"]
CARD_COLS = ["title", "vendor", "type", "status", "category", "owner", "effective_date", "expiry_date", "annual_value", "total_value",
             "auto_renew", "notice_period_days", "liability_cap_text", "governing_law", "termination_for_convenience",
             "processes_personal_data", "has_dpa", "customer_signatory", "supplier_signatory", "fully_executed"]
LT = r"(?:below|under|less than|fewer than|lower than|shorter than|at most|no more than|up to|<=?)"
GT = r"(?:above|over|more than|greater than|higher than|longer than|at least|no less than|exceed(?:s|ing)?|>=?)"
NUM = r"\$?\s*(\d[\d,]*(?:\.\d+)?)\s*(k|thousand|m|mm|million|b|billion)?"
SEV_WORDS = ("critical", "high", "medium", "low")


def _a(word: str) -> str:
    w = word.lower()
    return ("an " if w[0] in "aeiou" else "a ") + w


def _quarter_bounds(today: dt.date, offset: int) -> tuple[dt.date, dt.date]:
    m = 3 * ((today.month - 1) // 3) + 1 + 3 * offset
    y, m = today.year + (m - 1) // 12, (m - 1) % 12 + 1
    start = dt.date(y, m, 1)
    ny, nm = (y + (m + 2) // 12, (m + 2) % 12 + 1)
    return start, dt.date(ny, nm, 1) - dt.timedelta(days=1)


def _month_bounds(today: dt.date, offset: int) -> tuple[dt.date, dt.date]:
    m0 = today.month - 1 + offset
    y, m = today.year + m0 // 12, m0 % 12 + 1
    ny, nm = y + m // 12, m % 12 + 1
    return dt.date(y, m, 1), dt.date(ny, nm, 1) - dt.timedelta(days=1)


def _span(a: dt.date, b: dt.date) -> str:
    return f"{a.day} {a:%b %Y} – {b.day} {b:%b %Y}"


def parse_window(q: str, today: dt.date) -> dict | None:
    if m := re.search(r"(?:next|within(?: the next)?|in the next|coming)\s+(\d+)\s+(day|week|month)s?", q):
        n, unit = int(m.group(1)), m.group(2)
        end = today + dt.timedelta(days=n * {"day": 1, "week": 7, "month": 30}[unit])
        return {"start": today, "end": end, "label": f"in the next {n} {unit}{'s' if n != 1 else ''} (to {end:%d %b %Y})"}
    for word, off in (("next", 1), ("this", 0), ("current", 0)):
        w = "this" if word == "current" else word
        if re.search(rf"{word} quarter", q):
            a, b = _quarter_bounds(today, off)
            return {"start": a, "end": b, "label": f"{w} quarter ({_span(a, b)})"}
        if re.search(rf"{word} month", q):
            a, b = _month_bounds(today, off)
            return {"start": a, "end": b, "label": f"{w} month ({_span(a, b)})"}
        if re.search(rf"{word} (?:calendar )?year", q):
            y = today.year + off
            return {"start": dt.date(y, 1, 1), "end": dt.date(y, 12, 31), "label": f"{w} year ({y})"}
    if m := re.search(r"(?:in|by|before)\s+(\d{4})\b", q):
        y = int(m.group(1))
        return {"start": dt.date(y, 1, 1), "end": dt.date(y, 12, 31), "label": f"in {y}"}
    return None


def _lit(v: str) -> str:
    """A SQL string literal for a value read from the data (a vendor called O'Brien must not break, or bend, the query)."""
    return "'" + str(v).replace("'", "''") + "'"


def _distinct(col: str) -> list[str]:
    with SessionLocal() as s:
        return [r[0] for r in s.execute(text(f"SELECT DISTINCT {col} FROM contracts WHERE {col} IS NOT NULL"))]


def _config() -> tuple[list[dict], list[dict]]:
    """(clause words, metrics) from the live admin configuration."""
    with SessionLocal() as s:
        k = [dict(r) for r in s.execute(text("SELECT key, name, keywords, heading_aliases FROM kcc_library WHERE enabled AND in_matrix")).mappings()]
        m = [dict(r) for r in s.execute(text("SELECT key, name, kind, unit FROM metrics WHERE enabled ORDER BY key")).mappings()]
        r = [dict(x) for x in s.execute(text("SELECT key, name FROM checklist_rules WHERE enabled")).mappings()]
    return k, m, r


def _num(v: str, suffix: str | None) -> float:
    x = float(v.replace(",", ""))
    mult = {"k": 1e3, "thousand": 1e3, "m": 1e6, "mm": 1e6, "million": 1e6, "b": 1e9, "billion": 1e9}.get((suffix or "").lower(), 1)
    return x * mult


def _clause_rx(k: dict) -> str:
    names = [re.escape(a.lower()) for a in (k["heading_aliases"] or [])] + [re.escape(k["name"].lower())]
    names = sorted(set(n for n in names if len(n) > 4), key=len, reverse=True)
    extra = {"liability_cap": r"liability cap|cap on liability|limitation of liability|liability clause", "ip_ownership": r"intellectual property|ip ownership",
             "data_return": r"return of data|data return", "sla": r"service levels?|\bsla\b", "indemnity": r"indemnit(?:y|ies)|indemnification",
             "audit_rights": r"audit rights?|audit clause", "warranties": r"warrant(?:y|ies)", "dispute_resolution": r"dispute resolution|arbitration",
             "order_of_precedence": r"order of precedence|precedence clause", "non_solicit": r"non-?solicit(?:ation)?"}
    return extra.get(k["key"]) or "|".join(names)


def parse(question: str, today=None, cats=None, vendors=None, owners=None, scope=None, cfg=None) -> dict | None:
    q = question.lower().replace("’", "'")
    today = today or dt.date.today()
    cats = _distinct("category") if cats is None else cats
    vendors = _distinct("vendor") if vendors is None else vendors
    owners = _distinct("owner") if owners is None else owners
    kccs, mets, rules = cfg if cfg is not None else _config()
    scope = list(scope or [])
    drafts = bool(re.search(r"\bdrafts?\b|not yet executed|under review|new contracts?\b", q))
    base = BASE_ALL if (drafts or scope) else BASE
    bname = "v_document_terms" if base == BASE_ALL else "v_effective_terms"
    notice = "notice" in q
    datecol = NOTICE if notice else "expiry_date"
    where, adj, suffix = [], [], []
    if scope:
        where.append("contract_id IN (" + ", ".join(str(int(i)) for i in scope) + ")")
    if drafts and not scope:
        where.append("status = 'draft'")
        suffix.append("that are drafts")

    win = parse_window(q, today)
    if win:
        where.append(f"{datecol} BETWEEN DATE '{win['start']}' AND DATE '{win['end']}'")
    q_types = re.sub(r"(?:without|with|has|have|having|no)\s+(?:a\s+|an\s+|any\s+)?dpa", " ", q)
    types = [v for k, v in TYPE_WORDS.items() if re.search(rf"\b(?:{k})(?:s)?\b", q_types)]
    if re.search(r"master services", q):
        types.append("MSA")
    if types and not scope:
        where.append("type IN (" + ", ".join(f"'{t}'" for t in sorted(set(types))) + ")")
        adj.append("/".join(sorted(set(types))))
    for c in cats:
        if c.lower() != "saas" and not scope and re.search(rf"\b{re.escape(c.lower())}\b", q):
            where.append(f"category = {_lit(c)}")
            adj.append(c)
    for pr in _distinct("property"):                                    # a hotel property named in the question
        toks = [w for w in re.findall(r"[a-z]+", pr.lower()) if w not in {*customer_markers(), "hotel", "hotels", "resort", "inn", "lodge", "suites", "boutique", "the", "and"}]
        if toks and not scope and all(re.search(rf"\b{t}\b", q) for t in toks):
            where.append(f"(SELECT c.property FROM contracts c WHERE c.id = contract_id) = {_lit(pr)}")
            adj.append(f"at {pr}")
    vendor_hit = False
    for v in vendors:
        if not scope and re.search(rf"\b{re.escape(v.split()[0].lower())}\b", q):
            where.append(f"vendor = {_lit(v)}")
            adj.append(v.split()[0])
            vendor_hit = True
    for o in owners:
        if not scope and re.search(rf"\b{re.escape(o.split()[0].lower())}\b", q):
            where.append(f"owner = {_lit(o)}")
            suffix.append(f"owned by {o.split()[0]}")
    if re.search(r"auto[- ]?renew", q):
        where.append("auto_renew")
        adj.append("auto-renewing")
    if re.search(r"uncapped|unlimited liability", q):
        where.append("liability_uncapped")
        suffix.append("with uncapped liability")
    if re.search(r"without (?:a )?dpa|no dpa", q):
        where.append("processes_personal_data AND NOT has_dpa")
        suffix.append("processing personal data without a DPA")
    elif re.search(r"(?:with|has|have|having|covered by)\s+(?:a\s+|an\s+)?dpa", q):
        where.append("has_dpa")
        suffix.append("covered by a DPA")
    elif "personal data" in q:
        where.append("processes_personal_data")
        suffix.append("processing personal data")
    if re.search(r"(?:can't|cannot|can not|unable to|not able to)\s+(?:we\s+|us\s+)?(?:be\s+)?terminat\w*\s+(?:\w+\s+)?for convenience|no termination for convenience|no (?:right|ability) to terminate for convenience", q):
        where.append("termination_for_convenience = false")
        suffix.append("that cannot be terminated for convenience")
    if re.search(r"unsigned|not (?:yet |fully )?signed|pending (?:signature|countersign)|not fully executed|awaiting signature|missing signature|not countersigned", q):
        where.append("NOT fully_executed")
        suffix.append("not fully signed")
    elif re.search(r"fully signed|fully executed|\bsigned by both", q):
        where.append("fully_executed")
        suffix.append("fully signed")

    want_cols: list[str] = []
    has_filter_clauses: list[str] = []
    for k in kccs:
        rx = _clause_rx(k)
        for m in re.finditer(rx, q) if rx else []:
            pre = q[max(0, m.start() - 28): m.start()]
            neg = re.search(r"(?:without|no|missing|lack(?:ing|s)?|absent|don't have|do not have|doesn't have|does not have|not have)\s+(?:an?\s+|any\s+|the\s+)?(?:\w+\s+)?$", pre)
            pos = re.search(r"(?:with|have|has|having|contain(?:s|ing)?|includ(?:e|es|ing))\s+(?:an?\s+|any\s+|the\s+)?(?:\w+\s+)?$", pre) and "clause" in q
            if neg:
                where.append(f"NOT has_{k['key']}")
                suffix.append(f"without {_a(k['name'])} clause")
                has_filter_clauses.append(k["key"])
            elif pos:
                where.append(f"has_{k['key']}")
                suffix.append(f"with {_a(k['name'])} clause")
                has_filter_clauses.append(k["key"])
            if neg or pos or "clause" in q or re.search(r"key clauses|all clauses", q):
                want_cols.append(f"has_{k['key']}")
            break
    for rx, cols in ATTRS:
        if re.search(rx, q):
            for c in cols:
                if c not in want_cols:
                    want_cols.append(c)

    # values & limits (admin-defined metrics) and numeric thresholds
    hit_metrics = []
    for m in mets:
        words = [w for w in re.findall(r"[a-z]+", m["name"].lower()) if len(w) > 2]

        def plural(ws):  # "payment terms" also matches "payment term"
            return r"\s+".join(re.escape(w.rstrip("s")) + "s?" for w in ws)

        mt_ = re.search(r"\b" + plural(re.findall(r"[a-z]+", m["name"].lower())) + r"\b", q) or (len(words) >= 2 and re.search(r"\b" + plural(words[:2]) + r"\b", q))
        if mt_:
            hit_metrics.append((mt_.start(), m))
    hit_metrics = [m for _, m in sorted(hit_metrics, key=lambda x: x[0])]        # columns follow the order of the question
    want_cols.extend("mv:" + m["key"] for m in hit_metrics)
    cmp_ = re.search(rf"({LT}|{GT})\s*{NUM}", q)
    if hit_metrics and not cmp_ and not scope and _distinct("property"):         # hotel groups: 'the laundry rate per kilogram (across properties)': only contracts that state it, with vendor and property beside the value
        where.append(f"EXISTS (SELECT 1 FROM extracted_values ev WHERE ev.contract_id = {bname}.contract_id AND ev.metric_key = '{hit_metrics[0]['key']}')")
        want_cols[:0] = [c for c in ("vendor", "property") if c not in want_cols]
        adj.append(f"stating {hit_metrics[0]['name'].lower()}")
    if cmp_ and hit_metrics:
        op_word, val, suf = cmp_.group(1), cmp_.group(2), cmp_.group(3)
        lt = re.fullmatch(LT, op_word) is not None
        op = ("<=" if re.search(r"at most|no more|up to|<=", op_word) else "<") if lt else (">=" if re.search(r"at least|no less|>=", op_word) else ">")
        mt = hit_metrics[0]
        col = "value_text" if mt["kind"] == "text" else "value_num"
        where.append(f"EXISTS (SELECT 1 FROM extracted_values ev WHERE ev.contract_id = {bname}.contract_id AND ev.metric_key = '{mt['key']}' AND ev.{col} {op} {_num(val, suf):g})")
        suffix.append(f"with {mt['name'].lower()} {op} {_num(val, suf):g}")
    elif cmp_ and "annual_value" in want_cols:
        op = "<" if re.fullmatch(LT, cmp_.group(1)) else ">"
        where.append(f"annual_value {op} {_num(cmp_.group(2), cmp_.group(3)):g}")
        suffix.append(f"with annual value {op} {money(_num(cmp_.group(2), cmp_.group(3)))}")

    gl = re.search(r"(?:other than|except|not governed by|outside of?)\s+(?:the\s+)?([a-z][a-z ]{2,24}?)(?:\s+law|\s+courts?|\?|$)", q) if re.search(r"govern|law|jurisdiction", q) else None
    if gl:
        where.append(f"governing_law IS NOT NULL AND governing_law NOT ILIKE '%{re.sub(r'[^a-z ]', '', gl.group(1)).strip()}%'")
        suffix.append(f"not governed by {gl.group(1).strip().title()} law")

    # checklist / policy questions
    checks = bool(re.search(r"\b(checklist|polic(?:y|ies)|non-?compliant|compliance|violat\w+|fail(?:s|ing|ed)?|redline|pass(?:es|ing)?)\b", q))
    rule_hits = [r["key"] for r in rules if r["name"].lower() in q]
    metric = ("count" if re.search(r"how many|number of|\bcount\b", q) else "sum" if re.search(r"\btotal\b(?! value)|\bsum\b|worth|spend|how much", q)
              else "avg" if re.search(r"average|\bavg\b|mean", q) else "list")
    g = re.search(r"\bby (category|vendor|type|owner|status|month|quarter|property)\b|(?:each|per) (category|vendor|type|owner|status|month|quarter|property)", q)
    group = (g.group(1) or g.group(2)) if g else None
    if not group and re.search(r"\b(?:which|what|how many) (?:properties|hotels)\b|\b(?:by|per|each) (?:hotel|site)\b|(?:properties|hotels) (?:with|have|has|by)", q):
        group = "property"
    topn = re.search(r"\btop\s+(\d+)\s+vendors?\b|\b(?:largest|biggest)\s+(\d+)\s+vendors?\b", q)
    top = int(topn.group(1) or topn.group(2)) if topn else None
    if top:
        group, metric = "vendor", "sum"
    vendor_level = bool(re.search(r"how many vendors|which vendors|what vendors|list (?:all )?(?:the )?vendors|vendors (?:with|that|having|who|have)", q))
    if vendor_level and not group:
        group = "vendor"
    if group == "property" and hit_metrics and metric in ("list", "count"):
        group = None                       # 'the laundry rate at each property' wants the values with the property beside them, not a count per property
    if group == "property" and metric == "list" and not hit_metrics:
        metric = "count"
        where.append("(SELECT c.property FROM contracts c WHERE c.id = contract_id) IS NOT NULL")
    all_clauses = bool(re.search(r"key clauses|all clauses|which clauses|clause (?:presence|checklist|coverage)", q))
    overview = bool(re.search(r"summar|overview|key terms|tell me about|describe|details|what is this|about this", q))

    doc_clauses = bool(re.search(r"\bclauses?\b|what does .* say|terms of|wording|says?\b", q) and (vendor_hit or types or scope) and not has_filter_clauses
                       and metric == "list" and not group and not (checks and not scope)) or (all_clauses and (vendor_hit or types or where) and metric == "list")
    if scope and want_cols and any(c.startswith("has_") for c in want_cols) and not has_filter_clauses and not cmp_ and not overview:
        doc_clauses = True  # "what does the indemnity clause say" on selected documents
    intent = "checks" if checks and not (doc_clauses and not checks) else "doc_clauses" if doc_clauses else "table"
    if intent == "table" and scope and len(scope) == 1 and metric == "list" and not group:
        intent = "card" if (overview or want_cols) else "search"
    if intent == "table" and metric == "list" and not (where or group or want_cols or all_clauses):
        if not scope:
            return None
        intent = "search"
    if intent == "table" and metric == "list" and not scope and not re.search(r"contract|vendor|expir|renew|nda|sow|msa|dpa|saas|work order|sign|clause|who|which|show|list|when|what|draft", q):
        return None

    cols = ["title", "type"] + [c for c in want_cols if c not in ("title", "type")]
    if all_clauses:
        cols = ["title", "type"] + ["has_" + k["key"] for k in kccs]
    elif not want_cols:
        cols = list(DEFAULT_COLS) + (["total_value"] if "Work Order" in " ".join(where) else [])
    if notice and "notice_deadline" not in cols:
        cols.append("notice_deadline")
    sev = [w for w in SEV_WORDS if re.search(rf"\b{w}\b", q)]
    return dict(where=where, adj=adj, suffix=suffix, win=win, metric=metric, group=group, datecol=datecol, notice=notice, cols=cols,
                doc_clauses=intent == "doc_clauses", all_clauses=all_clauses, want_cols=want_cols, has_filters=has_filter_clauses,
                vendor_level=vendor_level, top=top, intent=intent, base=base, bname=bname, scope=scope, mets=mets, overview=overview,
                severities=sev, rule_hits=rule_hits, only_pass=bool(re.search(r"\bpass(?:es|ing)?\b", q) and not re.search(r"\bfail", q)),
                drafts=drafts, clause_keys=[c[4:] for c in want_cols if c.startswith("has_")], question=question)


# ------------------------------------------------------------------ SQL
def _col_sql(c: str, plan: dict) -> str:
    if c == "notice_deadline":
        return f"{NOTICE} AS notice_deadline"
    if c == "property":
        return "COALESCE((SELECT c.property FROM contracts c WHERE c.id = contract_id), 'Group level') AS property"
    if c.startswith("mv:"):
        key = c[3:]
        m = next((x for x in plan["mets"] if x["key"] == key), {"kind": "number"})
        col = "value_text" if m["kind"] == "text" else "value_num"
        return f"(SELECT ev.{col} FROM extracted_values ev WHERE ev.contract_id = {plan['bname']}.contract_id AND ev.metric_key = '{key}') AS {key}"
    return c


def build_sql(plan: dict) -> dict[str, str]:
    w = ("WHERE " + " AND ".join(plan["where"])) if plan["where"] else ""
    d, base = plan["datecol"], plan["base"]
    pinned_cat = any(x.startswith("category =") for x in plan["where"])
    dim = plan["group"] or ("type" if pinned_cat else "category")
    dim_sql = DIMS[dim].format(d=d)
    avg = ", ROUND(AVG(annual_value)) AS avg_annual_value" if plan["metric"] == "avg" else ""
    nv = ", COUNT(DISTINCT vendor) AS vendors" if plan.get("vendor_level") else ""
    cols = ", ".join(["contract_id"] + [_col_sql(c, plan) for c in plan["cols"]])
    card_cols = plan["cols"] if plan["want_cols"] and not plan["overview"] else CARD_COLS + ["mv:" + m["key"] for m in plan["mets"]]
    card = ", ".join(["contract_id"] + [_col_sql(c, plan) for c in dict.fromkeys(["title"] + [c for c in card_cols if c != "type"] + (["type"] if not plan["want_cols"] or plan["overview"] else []))])
    cl_w = "WHERE " + " AND ".join(["cl.contract_id IN (" + ", ".join(str(i) for i in plan["scope"]) + ")"] if plan["scope"] else
                                    [x.replace("expiry_date", "e.expiry_date") for x in plan["where"]] or ["true"])
    if plan["clause_keys"] and plan["scope"]:
        cl_w += " AND cl.clause_type IN (" + ", ".join(f"'{k}'" for k in plan["clause_keys"]) + ")"
    doc_from = "v_document_terms" if plan["scope"] else "v_effective_terms"
    return {
        "aggregate": f"SELECT COUNT(*) AS contracts{nv}, COALESCE(SUM(annual_value), 0) AS total_annual_value{avg} FROM {base} {w}",
        "breakdown": f"SELECT {dim_sql} AS {dim}, COUNT(*) AS contracts, COALESCE(SUM(annual_value), 0) AS total_annual_value FROM {base} {w} GROUP BY 1 ORDER BY {'3 DESC, 1' if plan.get('top') else '2 DESC, 1'}{' LIMIT ' + str(int(plan['top'])) if plan.get('top') else ''}",
        "list": f"SELECT {cols} FROM {base} {w} ORDER BY {d}, title",
        "card": f"SELECT {card} FROM {base} {w}",
        "doc_clauses": ("SELECT e.contract_id, e.title, cl.heading AS clause, cl.page, cl.text FROM clauses cl "
                        f"JOIN {doc_from} e ON e.contract_id = cl.contract_id {cl_w} ORDER BY e.title, cl.id"),
        "dim": dim,
    }


def subject_of(plan: dict, n: int = 2) -> str:
    base = (" ".join(plan["adj"]) + " contracts") if plan["adj"] else "contracts"
    base = base.replace("contracts", "contract") if n == 1 else base
    return " ".join([base] + plan["suffix"])


def describe(plan: dict) -> str:
    subject = subject_of(plan)
    when = ""
    if plan["win"]:
        when = f" {'with a notice deadline' if plan['notice'] else 'expiring'} {plan['win']['label']}"
    return subject + when


def understood(plan: dict) -> dict:
    parts = [f"Intent: {plan['intent'].replace('_', ' ')}" + (f" · {plan['metric']}" if plan["metric"] != "list" else "")
             + (f" grouped by {plan['group']}" if plan["group"] else "")]
    parts.append("Scope: " + (f"{len(plan['scope'])} selected document(s)" if plan["scope"] else "whole portfolio" + (" (drafts)" if plan["drafts"] else "")))
    parts.append("Filters: " + (", ".join(plan["adj"] + plan["suffix"]) or "none"))
    if plan["win"]:
        parts.append(f"Time window: {'notice deadline' if plan['notice'] else 'end date'} {plan['win']['label']}")
    parts.append("Columns: " + ", ".join(label_of(c.replace("mv:", "")) if not c.startswith("mv:") else next((m["name"] for m in plan["mets"] if m["key"] == c[3:]), c) for c in plan["cols"][:8]) + ("…" if len(plan["cols"]) > 8 else ""))
    return {"title": "Understood the question", "detail": " · ".join(parts)}


def _run(sql: str, calls: list, label: str | None = None, display: bool = False, **flags) -> list[dict]:
    out = execute_tool("run_sql", {"query": sql})
    calls.append({"name": "run_sql", "input": {"query": sql}, "output": out, "label": label, "display": display, **flags})
    if "error" in out:
        raise RuntimeError(out["error"])
    return [dict(zip(out["columns"], r)) for r in out["rows"]]


def _answer_checks(plan: dict, steps: list) -> dict:
    where = ["result = " + ("'pass'" if plan["only_pass"] else "'fail'")]
    if plan["scope"]:
        where.append("contract_id IN (" + ", ".join(str(i) for i in plan["scope"]) + ")")
    if plan["drafts"] and not plan["scope"]:
        where.append("status = 'draft'")
    elif not plan["scope"]:
        for w_ in plan["where"]:
            if w_.startswith(("vendor =", "type IN", "category =")):
                where.append(w_)
    if plan["severities"]:
        where.append("severity IN (" + ", ".join(f"'{s}'" for s in plan["severities"]) + ")")
    if plan["rule_hits"]:
        where.append("rule_key IN (" + ", ".join(f"'{k}'" for k in plan["rule_hits"]) + ")")
    w = "WHERE " + " AND ".join(where)
    sev_order = "CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END"
    calls: list = []
    agg = _run(f"SELECT COUNT(*) AS results, COUNT(DISTINCT contract_id) AS documents FROM v_checks {w}", calls, "Headline numbers")[0]
    word = "passed" if plan["only_pass"] else "failed"
    if agg["results"] == 0:
        return {"answer": f"No checklist rules {word} for that selection.", "tool_calls": calls, "plan_steps": steps}
    _run(f"SELECT severity, COUNT(*) AS results, COUNT(DISTINCT contract_id) AS documents FROM v_checks {w} GROUP BY severity ORDER BY {sev_order}", calls, "By severity", True)
    _run(f"SELECT contract_id, title, type, status, rule, severity, actual, expected, page FROM v_checks {w} ORDER BY {sev_order}, title", calls, "Checklist results", True)
    head = f"{agg['results']} checklist rule{'s' if agg['results'] != 1 else ''} {word} across {agg['documents']} document{'s' if agg['documents'] != 1 else ''}."
    return {"answer": head, "tool_calls": calls, "plan_steps": steps}


def answer(question: str, today: dt.date | None = None, scope: list[int] | None = None) -> dict | None:
    plan = parse(question, today, scope=scope)
    if not plan:
        return None
    steps = [understood(plan)]
    sql, calls = build_sql(plan), []
    if plan["intent"] == "checks":
        return _answer_checks(plan, steps)
    if plan["intent"] == "search":
        res = execute_tool("search_clauses", {"query": question, "contract_ids": plan["scope"], "top_k": 5})
        calls.append({"name": "search_clauses", "input": {"query": question, "top_k": 5}, "output": res})
        hits = res.get("hits", [])
        return {"answer": f"The {len(hits)} closest clauses in the selected document{'s' if len(plan['scope']) != 1 else ''} for your question.",
                "tool_calls": calls, "plan_steps": steps}
    if plan["intent"] == "card":
        rows = _run(sql["card"], calls, "Document facts", True, vertical=True)
        if not rows:
            return {"answer": "That document has no extracted data yet.", "tool_calls": calls, "plan_steps": steps}
        t = rows[0]["title"] if "title" in rows[0] else "the selected document"
        return {"answer": f"{t}: its extracted terms, dates, signatories and limits.", "tool_calls": calls, "plan_steps": steps}
    if plan["doc_clauses"]:
        rows = _run(sql["doc_clauses"], calls, "Clauses found", True)
        docs = sorted({r["title"] for r in rows})
        if not rows:
            return {"answer": "No matching clauses found.", "tool_calls": calls, "plan_steps": steps}
        return {"answer": f"{len(rows)} clauses found in {len(docs)} document{'s' if len(docs) != 1 else ''}: " + "; ".join(docs[:3]) + ("…" if len(docs) > 3 else "") + ".",
                "tool_calls": calls, "plan_steps": steps}
    agg = _run(sql["aggregate"], calls, "Headline numbers")[0]
    if plan["metric"] == "list" and not plan.get("vendor_level"):
        calls[-1]["no_tiles"] = True
    n, total = agg["contracts"], float(agg["total_annual_value"] or 0)
    if n == 0:
        return {"answer": f"No {describe(plan)} found.", "tool_calls": calls, "plan_steps": steps}
    desc = describe(plan)
    if plan.get("vendor_level"):
        _run(sql["breakdown"], calls, "Vendors", True)
        nv = agg["vendors"]
        when = (" with a notice deadline " if plan["notice"] else " expiring ") + plan["win"]["label"] if plan["win"] else ""
        return {"answer": f"{nv} vendor{'s' if nv != 1 else ''} with {subject_of(plan)}{when}, {n} contract{'s' if n != 1 else ''} carrying {money(total)} in annual value.",
                "tool_calls": calls, "plan_steps": steps}
    if plan["metric"] == "sum":
        head = f"Total annual value of {desc} is {money(total)} across {n} contract{'s' if n != 1 else ''}."
    elif plan["metric"] == "avg":
        head = f"The average annual value of {desc} is {money(agg.get('avg_annual_value'))} ({n} contract{'s' if n != 1 else ''}, {money(total)} in total)."
    elif plan["metric"] == "count":
        verb = ""
        if plan["win"]:
            verb = (" has a notice deadline " if plan["notice"] and n == 1 else " have a notice deadline " if plan["notice"] else (" expires " if n == 1 else " expire ")) + plan["win"]["label"]
        head = f"{n} {subject_of(plan, n)}{verb}" + (f", carrying {money(total)} in annual value" if total else "") + "."
    else:
        head = f"{n} matching {'contract' if n == 1 else 'contracts'}"
        flt = plan["adj"] + plan["suffix"]
        if flt:
            head += " (" + ", ".join(flt) + ")"
        if plan["win"]:
            head += f", {'notice deadline' if plan['notice'] else 'ending'} {plan['win']['label']}"
        head += "."
    if plan["metric"] != "list" or plan["group"]:
        br = _run(sql["breakdown"], calls, f"Breakdown by {sql['dim']}", True)
        if plan["group"]:
            head += f" Split by {sql['dim']}: " + "; ".join(f"{b[sql['dim']]} {b['contracts']}" for b in br[:6]) + ("…" if len(br) > 6 else "") + "."
    if not plan["group"]:
        _run(sql["list"], calls, "Contracts", True)
    return {"answer": head, "tool_calls": calls, "plan_steps": steps}


__all__ = ["answer", "parse", "build_sql", "subject_of"]
