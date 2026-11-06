"""Offline question -> SQL -> table planner (the Claude path does this natively).

Understands, in plain English: counts / totals / averages, group-by, time windows (next quarter,
next 60 days...), filters (type, category, vendor, owner, auto-renewing, uncapped, DPA status,
signed / unsigned, a clause present or absent) and WHICH COLUMNS to show (start/end dates,
signatories, payment terms, governing law, any key clause present/absent...). Questions about one
document ("key clauses in the Bluepeak MSA") return that document's clauses.
Every answer is real SQL over the extracted data in Postgres."""

from __future__ import annotations

import datetime as dt
import re

from sqlalchemy import text

from app.ask import execute_tool
from app.ask_present import label_of
from app.ask_scripted import money
from app.db import SessionLocal
from app.docgen.library import CLAUSES, KEY_CLAUSES

BASE = "v_effective_terms JOIN v_key_clauses USING (contract_id)"
NOTICE = "(expiry_date - COALESCE(notice_period_days, 0))"
DIMS = {
    "category": "category",
    "vendor": "vendor",
    "type": "type",
    "owner": "owner",
    "status": "status",
    "month": "to_char(date_trunc('month', {d}), 'YYYY-MM')",
    "quarter": "to_char(date_trunc('quarter', {d}), 'YYYY \"Q\"Q')",
}
TYPE_WORDS = {
    "msa": "MSA",
    "sow": "SOW",
    "nda": "NDA",
    "dpa": "DPA",
    "saas": "SaaS",
    "work orders?": "Work Order",
    "wos?": "Work Order",
}
SIG_COLS = [
    "customer_signatory",
    "customer_signed_date",
    "supplier_signatory",
    "supplier_signed_date",
    "fully_executed",
]
# words -> key clause (used both to filter "with/without X" and to add a presence column)
CLAUSE_WORDS = [
    (r"termination for convenience|terminate for convenience", "termination_for_convenience"),
    (r"termination for cause", "termination_for_cause"),
    (r"liability cap|cap on liability|limitation of liability|liability clause", "liability_cap"),
    (r"indemnit(?:y|ies)|indemnification", "indemnity"),
    (r"intellectual property|ip ownership|\bip\b", "ip_ownership"),
    (r"confidentiality|non-disclosure clause", "confidentiality"),
    (r"data protection", "data_protection"),
    (r"audit rights?|audit clause", "audit_rights"),
    (r"assignment", "assignment"),
    (r"non-?solicit(?:ation)?", "non_solicit"),
    (r"service levels?|\bsla\b", "sla"),
    (r"information security|security clause", "security"),
    (r"return of data|data return", "data_return"),
    (r"renewal clause", "renewal"),
    (r"payment clause", "payment"),
    (r"governing law clause", "governing_law"),
]
ATTRS = [  # question words -> columns to show
    (r"start date|effective date|commenc|\bstarts?\b|\bstarting\b", ["effective_date"]),
    (r"end date|expir|renewal date|\bends?\b", ["expiry_date"]),
    (r"notice", ["notice_deadline"]),
    (r"annual value|\bvalue\b|worth|spend|\bcost", ["annual_value"]),
    (r"total value|fixed fee", ["total_value"]),
    (r"payment terms?", ["payment_terms_days"]),
    (r"liability cap|cap on liability|how much liability", ["liability_cap_text"]),
    (r"governing law|jurisdiction", ["governing_law"]),
    (r"\bowners?\b", ["owner"]),
    (r"categor", ["category"]),
    (r"signature|signed|signator|execut|countersign|who signed", SIG_COLS),
    (r"auto[- ]?renew", ["auto_renew"]),
    (r"termination for convenience", ["termination_for_convenience"]),
]
DEFAULT_COLS = ["title", "vendor", "type", "effective_date", "expiry_date", "annual_value"]


# ------------------------------------------------------------------ date windows
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
    """Return {start, end, label} (inclusive dates) or None."""
    if m := re.search(
        r"(?:next|within(?: the next)?|in the next|coming)\s+(\d+)\s+(day|week|month)s?", q
    ):
        n, unit = int(m.group(1)), m.group(2)
        days = n * {"day": 1, "week": 7, "month": 30}[unit]
        end = today + dt.timedelta(days=days)
        return {
            "start": today,
            "end": end,
            "label": f"in the next {n} {unit}{'s' if n != 1 else ''} (to {end:%d %b %Y})",
        }
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
            return {
                "start": dt.date(y, 1, 1),
                "end": dt.date(y, 12, 31),
                "label": f"{w} year ({y})",
            }
    if m := re.search(r"(?:in|by|before)\s+(\d{4})\b", q):
        y = int(m.group(1))
        return {"start": dt.date(y, 1, 1), "end": dt.date(y, 12, 31), "label": f"in {y}"}
    return None


def _a(word: str) -> str:
    """a / an + lower-cased word."""
    w = word.lower()
    return ("an " if w[0] in "aeiou" else "a ") + w


def _distinct(col: str) -> list[str]:
    with SessionLocal() as s:
        return [
            r[0] for r in s.execute(text(f"SELECT DISTINCT {col} FROM contracts WHERE {col} IS NOT NULL"))
        ]


# ------------------------------------------------------------------ parsing
def parse(question: str, today=None, cats=None, vendors=None, owners=None) -> dict | None:
    q = question.lower().replace("’", "'")
    today = today or dt.date.today()
    cats = _distinct("category") if cats is None else cats
    vendors = _distinct("vendor") if vendors is None else vendors
    owners = _distinct("owner") if owners is None else owners
    notice = "notice" in q
    datecol = NOTICE if notice else "expiry_date"
    where, adj, suffix = [], [], []
    has_filter_clauses: list[str] = []

    win = parse_window(q, today)
    if win:
        where.append(f"{datecol} BETWEEN DATE '{win['start']}' AND DATE '{win['end']}'")

    # "without a DPA" / "has a DPA" talk about DPA status, not about the DPA contract type
    q_types = re.sub(r"(?:without|with|has|have|having|no)\s+(?:a\s+|an\s+|any\s+)?dpa", " ", q)
    types = [v for k, v in TYPE_WORDS.items() if re.search(rf"\b(?:{k})(?:s)?\b", q_types)]
    if re.search(r"master services", q):
        types.append("MSA")
    if types:
        where.append("type IN (" + ", ".join(f"'{t}'" for t in sorted(set(types))) + ")")
        adj.append("/".join(sorted(set(types))))
    for c in cats:
        if c.lower() != "saas" and re.search(rf"\b{re.escape(c.lower())}\b", q):
            where.append(f"category = '{c}'")
            adj.append(c)
    vendor_hit = False
    for v in vendors:
        if re.search(rf"\b{re.escape(v.split()[0].lower())}\b", q):
            where.append(f"vendor = '{v}'")
            adj.append(v.split()[0])
            vendor_hit = True
    for o in owners:
        if re.search(rf"\b{re.escape(o.split()[0].lower())}\b", q):
            where.append(f"owner = '{o}'")
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
    if re.search(
        r"(?:can't|cannot|can not|unable to) be terminated for convenience|no termination for convenience",
        q,
    ):
        where.append("termination_for_convenience = false")
        suffix.append("that cannot be terminated for convenience")
    if re.search(r"unsigned|not (?:yet |fully )?signed|pending (?:signature|countersign)|not fully executed|awaiting signature|missing signature|not countersigned", q):
        where.append("NOT fully_executed")
        suffix.append("not fully signed")
    elif re.search(r"fully signed|fully executed|\bsigned by both", q):
        where.append("fully_executed")
        suffix.append("fully signed")

    # clause present / absent filters, and clause columns
    want_cols: list[str] = []
    q_nowin = re.sub(r"termination for convenience", "tfc_", q)  # keep it from matching 'termination'
    for rx, ct in CLAUSE_WORDS:
        for m in re.finditer(rx, q):
            pre = q[max(0, m.start() - 28) : m.start()]
            if re.search(r"(?:without|no|missing|lack(?:ing|s)?|absent|don't have|do not have|doesn't have|does not have|not have)\s+(?:an?\s+|any\s+|the\s+)?(?:\w+\s+)?$", pre):
                where.append(f"NOT has_{ct}")
                suffix.append(f"without {_a(CLAUSES[ct].heading)} clause")
                has_filter_clauses.append(ct)
            elif re.search(r"(?:with|have|has|having|contain(?:s|ing)?|includ(?:e|es|ing))\s+(?:an?\s+|any\s+|the\s+)?(?:\w+\s+)?$", pre) and "clause" in q:
                where.append(f"has_{ct}")
                suffix.append(f"with {_a(CLAUSES[ct].heading)} clause")
                has_filter_clauses.append(ct)
            want_cols.append(f"has_{ct}")
            break
    del q_nowin

    for rx, cols in ATTRS:
        if re.search(rx, q):
            for c in cols:
                if c not in want_cols:
                    want_cols.append(c)
    all_clauses = bool(re.search(r"key clauses|all clauses|which clauses|clause (?:presence|checklist|coverage)", q))

    metric = (
        "count"
        if re.search(r"how many|number of|\bcount\b", q)
        else "sum"
        if re.search(r"\btotal\b(?! value)|\bsum\b|worth|spend|how much", q)
        else "avg"
        if re.search(r"average|\bavg\b|mean", q)
        else "list"
    )
    g = re.search(
        r"\bby (category|vendor|type|owner|status|month|quarter)\b|(?:each|per) (category|vendor|type|owner|status|month|quarter)",
        q,
    )
    group = (g.group(1) or g.group(2)) if g else None

    doc_clauses = bool(
        re.search(r"\bclauses?\b|what does .* say|terms of", q)
        and (vendor_hit or types)
        and not has_filter_clauses
        and metric == "list"
        and all_clauses is not False
        and not want_cols
    ) or (all_clauses and (vendor_hit or types or where) and metric == "list")

    if metric == "list" and not (where or group or want_cols or all_clauses):
        return None
    if metric == "list" and not re.search(
        r"contract|vendor|expir|renew|nda|sow|msa|dpa|saas|work order|sign|clause|who|which|show|list|when|what",
        q,
    ):
        return None
    cols = ["title", "type"] + [c for c in want_cols if c not in ("title", "type")]
    default = list(DEFAULT_COLS)
    if "Work Order" in " ".join(where):
        default.append("total_value")
    if all_clauses:
        cols = ["title", "type"] + [f"has_{c}" for c in KEY_CLAUSES]
    elif not want_cols:
        cols = default
    if notice and "notice_deadline" not in cols:
        cols.append("notice_deadline")
    return dict(
        where=where, adj=adj, suffix=suffix, win=win, metric=metric, group=group, datecol=datecol,
        notice=notice, cols=cols, doc_clauses=doc_clauses, all_clauses=all_clauses,
        want_cols=want_cols, has_filters=has_filter_clauses,
    )


# ------------------------------------------------------------------ SQL
def _col_sql(c: str) -> str:
    if c == "notice_deadline":
        return f"{NOTICE} AS notice_deadline"
    return c


def build_sql(plan: dict) -> dict[str, str]:
    w = ("WHERE " + " AND ".join(plan["where"])) if plan["where"] else ""
    d = plan["datecol"]
    pinned_cat = any(x.startswith("category =") for x in plan["where"])
    dim = plan["group"] or ("type" if pinned_cat else "category")
    dim_sql = DIMS[dim].format(d=d)
    avg = ", ROUND(AVG(annual_value)) AS avg_annual_value" if plan["metric"] == "avg" else ""
    cols = ", ".join(["contract_id"] + [_col_sql(c) for c in plan["cols"]])
    return {
        "aggregate": f"SELECT COUNT(*) AS contracts, COALESCE(SUM(annual_value), 0) AS total_annual_value{avg} FROM {BASE} {w}",
        "breakdown": f"SELECT {dim_sql} AS {dim}, COUNT(*) AS contracts, COALESCE(SUM(annual_value), 0) AS total_annual_value FROM {BASE} {w} GROUP BY 1 ORDER BY 2 DESC, 1",
        "list": f"SELECT {cols} FROM {BASE} {w} ORDER BY {d}, title",
        "doc_clauses": (
            "SELECT e.contract_id, e.title, cl.heading AS clause, cl.page, cl.text "
            "FROM clauses cl JOIN v_effective_terms e ON e.contract_id = cl.contract_id "
            + (w.replace("expiry_date", "e.expiry_date") if w else "")
            + " ORDER BY e.title, cl.id"
        ),
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
        verb = "with a notice deadline" if plan["notice"] else "expiring"
        when = f" {verb} {plan['win']['label']}"
    return subject + when


def understood(plan: dict) -> dict:
    parts = [
        f"Intent: {'count' if plan['metric'] == 'count' else 'total value' if plan['metric'] == 'sum' else 'average value' if plan['metric'] == 'avg' else 'list'}"
        + (f" grouped by {plan['group']}" if plan["group"] else "")
        + (" (one document's clauses)" if plan["doc_clauses"] else "")
    ]
    parts.append("Filters: " + (", ".join(plan["adj"] + plan["suffix"]) or "none"))
    if plan["win"]:
        parts.append(f"Time window: {'notice deadline' if plan['notice'] else 'end date'} {plan['win']['label']}")
    parts.append("Columns: " + ", ".join(label_of(c) for c in plan["cols"][:8]) + ("…" if len(plan["cols"]) > 8 else ""))
    return {"title": "Understood the question", "detail": " · ".join(parts)}


def _run(name: str, sql: str, calls: list, label: str | None = None, display: bool = False) -> list[dict]:
    out = execute_tool("run_sql", {"query": sql})
    calls.append({"name": "run_sql", "input": {"query": sql}, "output": out, "label": label, "display": display})
    if "error" in out:
        raise RuntimeError(out["error"])
    return [dict(zip(out["columns"], r)) for r in out["rows"]]


def answer(question: str, today: dt.date | None = None) -> dict | None:
    plan = parse(question, today)
    if not plan:
        return None
    sql, calls = build_sql(plan), []
    steps = [understood(plan)]
    if plan["doc_clauses"]:
        rows = _run("doc", sql["doc_clauses"], calls, "Clauses found", True)
        docs = sorted({r["title"] for r in rows})
        if not rows:
            return {"answer": "No matching document found.", "tool_calls": calls, "plan_steps": steps}
        return {
            "answer": f"{len(rows)} clauses found in {len(docs)} document{'s' if len(docs) != 1 else ''}: "
            + "; ".join(docs[:3]) + ("…" if len(docs) > 3 else "") + ".",
            "tool_calls": calls,
            "plan_steps": steps,
        }
    aggregate = plan["metric"] != "list" or plan["group"]
    agg = _run("agg", sql["aggregate"], calls, "Headline numbers")[0]
    if plan["metric"] == "list":
        calls[-1]["no_tiles"] = True  # a plain list needs a count in the text, not headline tiles
    n, total = agg["contracts"], float(agg["total_annual_value"] or 0)
    if n == 0:
        return {"answer": f"No {describe(plan)} found.", "tool_calls": calls, "plan_steps": steps}
    desc = describe(plan)
    if plan["metric"] == "sum":
        head = f"Total annual value of {desc} is {money(total)} across {n} contract{'s' if n != 1 else ''}."
    elif plan["metric"] == "avg":
        head = (f"The average annual value of {desc} is {money(agg.get('avg_annual_value'))} "
                f"({n} contract{'s' if n != 1 else ''}, {money(total)} in total).")
    else:
        verb = ""
        if plan["win"]:
            verb = (" has a notice deadline " if plan["notice"] and n == 1 else " have a notice deadline "
                    if plan["notice"] else (" expires " if n == 1 else " expire ")) + plan["win"]["label"]
        if plan["metric"] == "count":
            head = f"{n} {subject_of(plan, n)}{verb}"
            if total:
                head += f", carrying {money(total)} in annual value"
            head += "."
        else:
            head = f"{n} matching {'contract' if n == 1 else 'contracts'}"
            flt = plan["adj"] + plan["suffix"]
            if flt:
                head += " (" + ", ".join(flt) + ")"
            if plan["win"]:
                head += f", {'notice deadline' if plan['notice'] else 'ending'} {plan['win']['label']}"
            head += "."
    if plan["metric"] != "list" or plan["group"]:
        br = _run("br", sql["breakdown"], calls, f"Breakdown by {sql['dim']}", True)
        if plan["group"]:
            head += f" Split by {sql['dim']}: " + "; ".join(
                f"{b[sql['dim']]} {b['contracts']}" for b in br[:6]
            ) + ("…" if len(br) > 6 else "") + "."
    if not plan["group"]:
        _run("list", sql["list"], calls, "Contracts", True)
    del aggregate
    return {"answer": head, "tool_calls": calls, "plan_steps": steps}


__all__ = ["answer", "parse", "build_sql", "subject_of", "CLAUSES"]
