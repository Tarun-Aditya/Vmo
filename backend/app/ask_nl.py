"""Offline natural-language planner for aggregate questions ("how many contracts expire next
quarter?", "total annual value of SaaS contracts by vendor"). It turns a question into three real
SQL queries (headline aggregate, grouped breakdown, contract list) and writes the answer from the
results. The Claude path does this natively; this keeps the offline demo useful beyond the 15
scripted questions. It understands counts/sums/averages, group-by, time windows and common filters.
"""

from __future__ import annotations

import datetime as dt
import re

from sqlalchemy import text

from app.ask import execute_tool
from app.ask_scripted import money
from app.db import SessionLocal

BASE = "v_effective_terms"
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
TYPE_WORDS = {"msa": "MSA", "sow": "SOW", "nda": "NDA", "dpa": "DPA", "saas": "SaaS"}


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
        end = today + (
            dt.timedelta(days=n * (7 if unit == "week" else 1))
            if unit != "month"
            else dt.timedelta(days=30 * n)
        )
        return {
            "start": today,
            "end": end,
            "label": f"in the next {n} {unit}{'s' if n != 1 else ''} (to {end:%d %b %Y})",
        }
    for word, off in (("next", 1), ("this", 0), ("current", 0)):
        if re.search(rf"{word} quarter", q):
            a, b = _quarter_bounds(today, off)
            return {
                "start": a,
                "end": b,
                "label": f"{word if word != 'current' else 'this'} quarter ({_span(a, b)})",
            }
        if re.search(rf"{word} month", q):
            a, b = _month_bounds(today, off)
            return {
                "start": a,
                "end": b,
                "label": f"{word if word != 'current' else 'this'} month ({_span(a, b)})",
            }
        if re.search(rf"{word} (?:calendar )?year", q):
            y = today.year + off
            return {
                "start": dt.date(y, 1, 1),
                "end": dt.date(y, 12, 31),
                "label": f"{word if word != 'current' else 'this'} year ({y})",
            }
    if m := re.search(r"(?:in|by|before)\s+(\d{4})\b", q):
        y = int(m.group(1))
        return {"start": dt.date(y, 1, 1), "end": dt.date(y, 12, 31), "label": f"in {y}"}
    return None


def _distinct(col: str) -> list[str]:
    with SessionLocal() as s:
        return [
            r[0]
            for r in s.execute(
                text(f"SELECT DISTINCT {col} FROM contracts WHERE {col} IS NOT NULL")
            )
        ]


def parse(
    question: str, today: dt.date | None = None, cats=None, vendors=None, owners=None
) -> dict | None:
    q = question.lower().replace("’", "'")
    today = today or dt.date.today()
    cats = _distinct("category") if cats is None else cats
    vendors = _distinct("vendor") if vendors is None else vendors
    owners = _distinct("owner") if owners is None else owners
    notice = "notice" in q
    datecol = NOTICE if notice else "expiry_date"
    where, adj, suffix, notes = [], [], [], []

    win = parse_window(q, today)
    if win:
        where.append(f"{datecol} BETWEEN DATE '{win['start']}' AND DATE '{win['end']}'")
    # "without a DPA" / "has a DPA" talk about DPA status, not about the DPA contract type
    q_types = re.sub(r"(?:without|with|has|have|having|no)\s+(?:a\s+|an\s+|any\s+)?dpa", " ", q)
    types = [v for k, v in TYPE_WORDS.items() if re.search(rf"\b{k}s?\b", q_types)]
    if re.search(r"master services", q):
        types.append("MSA")
    if types:
        where.append("type IN (" + ", ".join(f"'{t}'" for t in sorted(set(types))) + ")")
        adj.append("/".join(sorted(set(types))))
    for c in cats:
        if c.lower() != "saas" and re.search(rf"\b{re.escape(c.lower())}\b", q):
            where.append(f"category = '{c}'")
            adj.append(c)
    for v in vendors:
        if re.search(rf"\b{re.escape(v.split()[0].lower())}\b", q):
            where.append(f"vendor = '{v}'")
            adj.append(v.split()[0])
    for o in owners:
        if re.search(rf"\b{re.escape(o.split()[0].lower())}\b", q):
            where.append(f"owner = '{o}'")
            suffix.append(f"owned by {o.split()[0]}")
    if re.search(r"auto[- ]?renew", q):
        where.append("auto_renew")
        adj.append("auto-renewing")
    if re.search(r"uncapped|unlimited liability", q):
        where.append("liability_uncapped")
        adj.append("uncapped-liability")
    if re.search(r"without (?:a )?dpa|no dpa", q):
        where.append("processes_personal_data AND NOT has_dpa")
        adj.append("personal-data-without-DPA")
    elif re.search(r"(?:with|has|have|having|covered by)\s+(?:a\s+|an\s+)?dpa", q):
        where.append("has_dpa")
        adj.append("DPA-covered")
    elif "personal data" in q:
        where.append("processes_personal_data")
        adj.append("personal-data")
    if re.search(
        r"(?:can't|cannot|can not|unable to) be terminated for convenience|no termination for convenience",
        q,
    ):
        where.append("termination_for_convenience = false")
        adj.append("non-terminable-for-convenience")

    metric = (
        "count"
        if re.search(r"how many|number of|\bcount\b", q)
        else (
            "sum"
            if re.search(r"\btotal\b|\bsum\b|worth|spend|how much", q)
            else "avg" if re.search(r"average|\bavg\b|mean", q) else "list"
        )
    )
    g = re.search(
        r"\bby (category|vendor|type|owner|status|month|quarter)\b|(?:each|per) (category|vendor|type|owner|status|month|quarter)",
        q,
    )
    group = (g.group(1) or g.group(2)) if g else None
    if metric == "list" and not (where or group):
        return None
    if metric == "list" and not re.search(r"contract|vendor|expir|renew|nda|sow|msa|dpa|saas", q):
        return None
    return dict(
        where=where,
        adj=adj,
        suffix=suffix,
        win=win,
        metric=metric,
        group=group,
        datecol=datecol,
        notice=notice,
        notes=notes,
    )


def build_sql(plan: dict) -> dict[str, str]:
    w = ("WHERE " + " AND ".join(plan["where"])) if plan["where"] else ""
    d = plan["datecol"]
    pinned_cat = any(x.startswith("category =") for x in plan["where"])
    dim = plan["group"] or ("type" if pinned_cat else "category")
    dim_sql = DIMS[dim].format(d=d)
    avg = ", ROUND(AVG(annual_value)) AS avg_annual_value" if plan["metric"] == "avg" else ""
    return {
        "aggregate": f"SELECT COUNT(*) AS contracts, COALESCE(SUM(annual_value), 0) AS total_annual_value{avg} "
        f"FROM {BASE} {w}",
        "breakdown": f"SELECT {dim_sql} AS {dim}, COUNT(*) AS contracts, COALESCE(SUM(annual_value), 0) AS total_annual_value "
        f"FROM {BASE} {w} GROUP BY 1 ORDER BY 2 DESC, 1",
        "list": f"SELECT title, vendor, category, type, expiry_date, {NOTICE} AS notice_deadline, annual_value "
        f"FROM {BASE} {w} ORDER BY {d}, title",
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


def run(plan: dict):
    sql = build_sql(plan)
    calls = []

    def go(name):
        out = execute_tool("run_sql", {"query": sql[name]})
        calls.append({"name": "run_sql", "input": {"query": sql[name]}, "output": out})
        if "error" in out:
            raise RuntimeError(out["error"])
        return [dict(zip(out["columns"], r)) for r in out["rows"]]

    agg = go("aggregate")[0]
    return sql, calls, agg, go


def answer(question: str, today: dt.date | None = None) -> dict | None:
    plan = parse(question, today)
    if not plan:
        return None
    sql, calls, agg, go = run(plan)
    n, total = agg["contracts"], float(agg["total_annual_value"] or 0)
    desc = describe(plan)
    if n == 0:
        return {"answer": f"No {desc} found.", "tool_calls": calls}
    if plan["metric"] == "sum":
        head = f"Total annual value of {desc} is {money(total)} across {n} contract{'s' if n != 1 else ''}"
    elif plan["metric"] == "avg":
        head = f"The average annual value of {desc} is {money(agg.get('avg_annual_value'))} ({n} contract{'s' if n != 1 else ''}, {money(total)} in total)"
    else:
        subject = subject_of(plan, n)
        verb = ""
        if plan["win"]:
            verb = (
                " has a notice deadline "
                if plan["notice"] and n == 1
                else (
                    " have a notice deadline "
                    if plan["notice"]
                    else (" expires " if n == 1 else " expire ")
                )
            ) + plan["win"]["label"]
        head = f"{n} {subject}{verb}"
        if total:
            head += f", carrying {money(total)} in annual value"
    parts = [head + "."]
    br = go("breakdown")
    dim = sql["dim"]
    if len(br) > 1 or plan["group"]:
        parts.append(
            f"By {dim}: "
            + "; ".join(
                (
                    f"{b[dim]} {b['contracts']} ({money(b['total_annual_value'])})"
                    if float(b["total_annual_value"] or 0)
                    else f"{b[dim]} {b['contracts']}"
                )
                for b in br
            )
            + "."
        )
    if not plan["group"]:
        items = go("list")
        shown = items[:12]
        lines = [
            f"• {i['title']} — "
            + (
                "notice by " + str(i["notice_deadline"])
                if plan["notice"]
                else "expires " + str(i["expiry_date"])
            )
            + (f" — {money(i['annual_value'])}" if i["annual_value"] else "")
            for i in shown
        ]
        if len(items) > 12:
            lines.append(f"• …and {len(items) - 12} more")
        parts.append("Contracts:\n" + "\n".join(lines))
    parts.append(
        "(Amendments are folded into their parent contract, so they are not counted separately.)"
    )
    return {"answer": "\n".join(parts), "tool_calls": calls}
