"""Offline fallback for the Ask assistant: the 15 preloaded demo questions, each with a fixed plan
of real tool calls (real SQL against the DB, real pgvector search). Used only when there is no
ANTHROPIC_API_KEY, so the demo still runs. Free-form questions need the Claude path."""

from __future__ import annotations

import re

from app.ask import execute_tool, norm_key

QUESTIONS = {
    "notice_60": "Which contracts have a notice deadline in the next 60 days?",
    "quarter_by_category": "What is the total annual value of contracts expiring this quarter, by category?",
    "uncapped": "Which vendors have uncapped liability?",
    "saas_no_dpa": "Which SaaS vendors process personal data without a DPA?",
    "no_tfc": "Which contracts can't be terminated for convenience?",
    "bluepeak_payment": "What are the current effective payment terms on the {msa_vendor} MSA after amendments?",
    "top5_vendors": "Who are the top 5 vendors by annual value and what are their renewal dates?",
    "nda_before_msa": "Which NDAs expire before their related MSA?",
    "auto_renewals": "Which contracts auto-renew, and by when must we give notice?",
    "expire_30": "Which contracts expire in the next 30 days?",
    "total_value": "What is the total annual value of all active contracts?",
    "short_confidentiality": "Which contracts have a confidentiality period shorter than three years?",
    "vendor_owns_ip": "Which contracts give the vendor ownership of the deliverables we pay for?",
    "non_indian_law": "Which contracts are governed by a law other than New York law, and what does the clause say?",
    "uncapped_autorenew": "Which auto-renewing contracts have uncapped liability, and what does their liability clause say?",
    "off_contract_spend": "How much have we been invoiced by vendors with no contract on file?",
    "sla_breaches": "Which vendors missed their availability SLA in the last 6 months?",
    "duplicate_invoices": "Which vendors sent duplicate invoices?",
}


def msa_vendor() -> str:
    """The short name of a vendor whose MSA has been amended (read from the loaded contracts, nothing hardcoded)."""
    from sqlalchemy import text

    from app.db import SessionLocal

    with SessionLocal() as s:
        v = s.execute(text("""SELECT m.vendor FROM contracts m JOIN contracts a ON a.parent_id = m.id AND a.type = 'Amendment'
                              WHERE m.type = 'MSA' AND a.status <> 'draft' ORDER BY m.id LIMIT 1""")).scalar()
    return re.sub(r"\s+(?:Inc|LLC|LLP|Ltd|Limited|Corp|Corporation|Group)\.?$", "", v or "the").strip()


def questions() -> dict[str, str]:
    mv = msa_vendor()
    return {k: v.replace("{msa_vendor}", mv) for k, v in QUESTIONS.items()}


def sla_key() -> str:
    """The availability-type service level in the Values & limits configuration (a percentage SLA metric), not a fixed key."""
    from sqlalchemy import text

    from app.db import SessionLocal

    with SessionLocal() as s:
        return s.execute(text("SELECT key FROM metrics WHERE sla AND enabled ORDER BY (unit = '%') DESC, (name ILIKE '%availab%') DESC, key LIMIT 1")).scalar() or "sla_availability_pct"


def money(n) -> str:
    n = float(n or 0)
    if n >= 1e6:
        return f"${n / 1e6:.2f}M"
    if n >= 1e3:
        return f"${n / 1e3:.0f}K" if n % 1e3 == 0 else f"${n / 1e3:.1f}K"
    return f"${n:,.0f}"


class Run:
    def __init__(self):
        self.calls: list[dict] = []

    def sql(self, q: str) -> dict:
        out = execute_tool("run_sql", {"query": q})
        self.calls.append({"name": "run_sql", "input": {"query": q}, "output": out})
        return out

    def search(self, **kw) -> dict:
        out = execute_tool("search_clauses", kw)
        self.calls.append({"name": "search_clauses", "input": kw, "output": out})
        return out


def rows(out: dict) -> list[dict]:
    return [dict(zip(out["columns"], r)) for r in out.get("rows", [])]


def _list(items: list[str]) -> str:
    return "; ".join(items) if items else "none"


def _plan(key: str, r: Run) -> str:
    """Run the fixed tool calls for a demo question and return a short headline. The detail is
    shown as tables by the UI (see ask_present), so the text only summarises."""
    if key == "notice_60":
        d = rows(
            r.sql(
                """SELECT contract_id, title, vendor, notice_deadline, notice_days_left, auto_renew, annual_value
            FROM v_renewals WHERE notice_days_left BETWEEN 0 AND 60 ORDER BY notice_deadline"""
            )
        )
        return (
            f"{len(d)} contracts have a notice deadline in the next 60 days. For contracts without "
            "auto-renewal the deadline is the expiry date itself."
        )
    if key == "quarter_by_category":
        d = rows(
            r.sql(
                """SELECT category, COUNT(*) AS contracts, SUM(annual_value) AS total_annual_value
            FROM v_effective_terms WHERE status='active'
              AND expiry_date >= date_trunc('quarter', current_date)
              AND expiry_date < date_trunc('quarter', current_date) + interval '3 months'
            GROUP BY category ORDER BY 3 DESC NULLS LAST"""
            )
        )
        tot = sum(float(x["total_annual_value"] or 0) for x in d)
        return f"Contracts expiring this quarter carry {money(tot)} of annual value across {len(d)} categories."
    if key == "uncapped":
        d = rows(
            r.sql(
                """SELECT DISTINCT contract_id, vendor, title, liability_cap_text FROM v_effective_terms
            WHERE liability_uncapped ORDER BY vendor"""
            )
        )
        return f"{len(d)} vendors have uncapped liability."
    if key == "saas_no_dpa":
        d = rows(
            r.sql(
                """SELECT contract_id, vendor, title FROM v_effective_terms
            WHERE type='SaaS' AND processes_personal_data AND NOT has_dpa"""
            )
        )
        return f"{len(d)} SaaS vendor processes personal data without a DPA."
    if key == "no_tfc":
        d = rows(
            r.sql(
                """SELECT contract_id, title, vendor, termination_for_convenience FROM v_effective_terms
            WHERE termination_for_convenience = false"""
            )
        )
        return f"{len(d)} contracts cannot be terminated for convenience."
    if key == "bluepeak_payment":
        d = rows(
            r.sql(
                f"""SELECT e.contract_id, e.title, e.payment_terms_days AS effective_payment_terms_days,
              s.title AS set_by, s.type AS set_by_type
            FROM v_effective_terms e JOIN contracts s ON s.id = e.payment_terms_days_source
            WHERE e.type='MSA' AND e.vendor ILIKE '%{re.sub(r"[^A-Za-z0-9 ]", "", msa_vendor())}%'"""
            )
        )
        if not d:
            return "No amended MSA was found."
        x = d[0]
        return f"The effective payment term on {x['title']} is {x['effective_payment_terms_days']} days, set by {x['set_by']}."
    if key == "top5_vendors":
        d = rows(
            r.sql(
                """SELECT vendor, SUM(annual_value) AS total_annual_value,
              MIN(expiry_date) AS earliest_expiry, MIN(notice_deadline) AS earliest_notice_deadline
            FROM v_renewals WHERE annual_value IS NOT NULL GROUP BY vendor
            ORDER BY 2 DESC LIMIT 5"""
            )
        )
        return f"Top 5 vendors by annual value; the largest is {d[0]['vendor']} at {money(d[0]['total_annual_value'])}."
    if key == "nda_before_msa":
        d = rows(
            r.sql(
                """SELECT n.contract_id, n.title AS nda, n.expiry_date AS nda_expiry, m.title AS msa,
              m.expiry_date AS msa_effective_expiry
            FROM v_effective_terms n JOIN v_effective_terms m ON m.contract_id = n.parent_id
            WHERE n.type='NDA' AND m.type='MSA' AND n.expiry_date < m.expiry_date"""
            )
        )
        return f"{len(d)} NDAs expire before their related MSA."
    if key == "auto_renewals":
        d = rows(
            r.sql(
                """SELECT contract_id, title, vendor, expiry_date, notice_period_days, notice_deadline,
              notice_days_left FROM v_renewals WHERE auto_renew ORDER BY notice_deadline"""
            )
        )
        late = [x for x in d if x["notice_days_left"] < 0]
        return f"{len(d)} contracts auto-renew" + (
            f"; the notice deadline has already passed for {_list([x['title'] for x in late])}." if late else "."
        )
    if key == "expire_30":
        d = rows(
            r.sql(
                """SELECT contract_id, title, vendor, expiry_date, days_left, annual_value FROM v_renewals
            WHERE days_left BETWEEN 0 AND 30 ORDER BY expiry_date"""
            )
        )
        return f"{len(d)} contracts expire in the next 30 days."
    if key == "total_value":
        d = rows(
            r.sql(
                """SELECT SUM(annual_value) AS total_annual_value, COUNT(annual_value) AS contracts_with_value
            FROM v_effective_terms WHERE status='active'"""
            )
        )[0]
        return (
            f"Total annual value of active contracts is {money(d['total_annual_value'])} across "
            f"{d['contracts_with_value']} contracts that carry fees (MSAs and Work Orders carry no annual fee)."
        )
    if key == "short_confidentiality":
        h = r.search(
            query="keep Confidential Information confidential for 1 year after the agreement ends",
            clause_type="confidentiality",
            top_k=4,
        )["hits"]
        short = [x for x in h if re.search(r"\b1 year\b|one year", x["text"])]
        return (
            f"{len(short)} contract has a confidentiality tail shorter than the 3-year standard "
            "(top semantic matches shown; the first is the short one)."
        )
    if key == "vendor_owns_ip":
        h = r.search(
            query="the Supplier owns all deliverables and work product, Customer receives a limited licence",
            clause_type="ip_ownership",
            top_k=4,
        )["hits"]
        own = [x for x in h if x["text"].startswith("The Supplier owns")]
        return (
            f"{len(own)} contract gives the vendor ownership of deliverables; the standard position is "
            "that Arcadia owns bespoke deliverables."
        )
    if key == "non_indian_law":
        d = rows(
            r.sql(
                """SELECT contract_id, title, vendor, governing_law FROM v_effective_terms
            WHERE governing_law IS NOT NULL AND governing_law <> 'New York' ORDER BY title"""
            )
        )
        r.search(
            query="governed by the laws of England and Wales or Singapore, courts of London or Singapore",
            clause_type="governing_law",
            top_k=len(d) + 1,
        )
        return f"{len(d)} contracts use a non-New-York governing law; the clause wording is cited below."
    if key == "uncapped_autorenew":
        d = rows(
            r.sql(
                """SELECT contract_id, title, vendor, expiry_date, notice_deadline
            FROM v_renewals WHERE auto_renew AND liability_uncapped ORDER BY notice_deadline"""
            )
        )
        for x in d:
            r.search(
                query="limitation of liability",
                clause_type="liability_cap",
                vendor=x["vendor"].split()[0],
                top_k=1,
            )
        return f"{len(d)} auto-renewing contracts have uncapped liability; their liability clauses are cited below."
    if key == "off_contract_spend":
        r.sql("""SELECT COUNT(*) AS invoices, COALESCE(SUM(invoice_amount), 0) AS off_contract_spend FROM v_spend_exceptions WHERE kind = 'no_contract'""")
        d = rows(r.sql("""SELECT vendor, COUNT(*) AS invoices, SUM(invoice_amount) AS off_contract_spend FROM v_spend_exceptions WHERE kind = 'no_contract' GROUP BY vendor ORDER BY 3 DESC"""))
        tot = sum(float(x["off_contract_spend"] or 0) for x in d)
        return f"{money(tot)} was invoiced by {len(d)} vendors that have no contract on file: {_list([x['vendor'] for x in d])}."
    if key == "sla_breaches":
        d = rows(r.sql(f"""SELECT DISTINCT ON (vendor, period) vendor, title, period, actual, target, shortfall FROM v_sla
            WHERE breach AND metric_key = '{sla_key()}' AND period >= current_date - 183 ORDER BY vendor, period DESC"""))
        r.sql(f"""SELECT vendor, COUNT(*) AS breach_months, MIN(actual) AS worst_actual FROM v_sla WHERE breach AND metric_key = '{sla_key()}' AND period >= current_date - 183 GROUP BY vendor ORDER BY 2 DESC""")
        return f"{len({x['vendor'] for x in d})} vendors missed their availability target in the last 6 months."
    if key == "duplicate_invoices":
        d = rows(r.sql("""SELECT vendor, contract_title, invoice_no, invoice_date, invoice_amount, amount_at_risk FROM v_spend_exceptions WHERE kind = 'duplicate' ORDER BY invoice_date DESC"""))
        return f"{len(d)} duplicate invoice{'s' if len(d) != 1 else ''} found, {money(sum(float(x['amount_at_risk'] or 0) for x in d))} at risk."
    raise KeyError(key)


def match(question: str) -> str | None:
    q = set(norm_key(question).split())
    best, score = None, 0.0
    for k, t in questions().items():
        tt = set(norm_key(t).split())
        j = len(q & tt) / len(q | tt)
        if j > score:
            best, score = k, j
    return best if score >= 0.85 else None  # near-exact only; paraphrases go to the planner


def answer(question: str) -> dict | None:
    key = match(question)
    if not key:
        return None
    r = Run()
    headline = _plan(key, r)
    kinds = sorted({"SQL over the extracted contract data" if c["name"] == "run_sql" else "semantic clause search"
                    for c in r.calls})
    steps = [
        {
            "title": "Understood the question",
            "detail": "Matched it to a preloaded analysis (offline mode) and planned: " + " + ".join(kinds) + ".",
        }
    ]
    return {"answer": headline, "tool_calls": r.calls, "plan_steps": steps}
