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
    "bluepeak_payment": "What are the current effective payment terms on the Bluepeak MSA after amendments?",
    "top5_vendors": "Who are the top 5 vendors by annual value and what are their renewal dates?",
    "nda_before_msa": "Which NDAs expire before their related MSA?",
    "auto_renewals": "Which contracts auto-renew, and by when must we give notice?",
    "expire_30": "Which contracts expire in the next 30 days?",
    "total_value": "What is the total annual value of all active contracts?",
    "short_confidentiality": "Which contracts have a confidentiality period shorter than three years?",
    "vendor_owns_ip": "Which contracts give the vendor ownership of the deliverables we pay for?",
    "non_indian_law": "Which contracts are governed by a law other than Indian law, and what does the clause say?",
    "uncapped_autorenew": "Which auto-renewing contracts have uncapped liability, and what does their liability clause say?",
}


def money(n) -> str:
    n = float(n or 0)
    return f"₹{n / 1e7:.2f} crore" if n >= 1e7 else f"₹{n / 1e5:.1f} lakh"


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
    if key == "notice_60":
        d = rows(r.sql("""SELECT title, vendor, notice_deadline, notice_days_left, auto_renew, annual_value
            FROM v_renewals WHERE notice_days_left BETWEEN 0 AND 60 ORDER BY notice_deadline"""))
        return (f"{len(d)} contracts have a notice deadline in the next 60 days: " +
                _list([f"{x['title']} ({x['notice_deadline']}, {x['notice_days_left']} days)" for x in d]) +
                ". For contracts without auto-renewal the deadline is the expiry date itself.")
    if key == "quarter_by_category":
        d = rows(r.sql("""SELECT category, COUNT(*) AS contracts, SUM(annual_value) AS total_annual_value
            FROM v_effective_terms WHERE status='active'
              AND expiry_date >= date_trunc('quarter', current_date)
              AND expiry_date < date_trunc('quarter', current_date) + interval '3 months'
            GROUP BY category ORDER BY 3 DESC NULLS LAST"""))
        tot = sum(float(x["total_annual_value"] or 0) for x in d)
        return (f"Contracts expiring this quarter carry {money(tot)} of annual value: " +
                _list([f"{x['category']} {money(x['total_annual_value'])} ({x['contracts']} contract"
                       f"{'s' if x['contracts'] != 1 else ''})" for x in d]) + ".")
    if key == "uncapped":
        d = rows(r.sql("""SELECT DISTINCT vendor, title FROM v_effective_terms
            WHERE liability_uncapped ORDER BY vendor"""))
        return f"{len(d)} vendors have uncapped liability: " + _list([f"{x['vendor']} ({x['title']})" for x in d]) + "."
    if key == "saas_no_dpa":
        d = rows(r.sql("""SELECT vendor, title FROM v_effective_terms
            WHERE type='SaaS' AND processes_personal_data AND NOT has_dpa"""))
        return (f"{len(d)} SaaS vendor processes personal data without a DPA: " +
                _list([f"{x['vendor']} ({x['title']})" for x in d]) + ".")
    if key == "no_tfc":
        d = rows(r.sql("""SELECT title, vendor FROM v_effective_terms
            WHERE termination_for_convenience = false"""))
        return f"{len(d)} contracts cannot be terminated for convenience: " + _list([x["title"] for x in d]) + "."
    if key == "bluepeak_payment":
        d = rows(r.sql("""SELECT e.title, e.payment_terms_days AS effective_payment_terms_days,
              s.title AS set_by, s.type AS set_by_type
            FROM v_effective_terms e JOIN contracts s ON s.id = e.payment_terms_days_source
            WHERE e.type='MSA' AND e.vendor ILIKE '%Bluepeak%'"""))
        x = d[0]
        return (f"The effective payment term on {x['title']} is {x['effective_payment_terms_days']} days, "
                f"set by {x['set_by']} (the original MSA said 45).")
    if key == "top5_vendors":
        d = rows(r.sql("""SELECT vendor, SUM(annual_value) AS total_annual_value,
              MIN(expiry_date) AS earliest_expiry, MIN(notice_deadline) AS earliest_notice_deadline
            FROM v_renewals WHERE annual_value IS NOT NULL GROUP BY vendor
            ORDER BY 2 DESC LIMIT 5"""))
        return "Top 5 vendors by annual value: " + _list([
            f"{x['vendor']} {money(x['total_annual_value'])} (first expiry {x['earliest_expiry']})" for x in d]) + "."
    if key == "nda_before_msa":
        d = rows(r.sql("""SELECT n.title AS nda, n.expiry_date AS nda_expiry, m.title AS msa,
              m.expiry_date AS msa_effective_expiry
            FROM v_effective_terms n JOIN v_effective_terms m ON m.contract_id = n.parent_id
            WHERE n.type='NDA' AND m.type='MSA' AND n.expiry_date < m.expiry_date"""))
        return f"{len(d)} NDAs expire before their MSA: " + _list([
            f"{x['nda']} ends {x['nda_expiry']} vs MSA {x['msa_effective_expiry']}" for x in d]) + "."
    if key == "auto_renewals":
        d = rows(r.sql("""SELECT title, vendor, expiry_date, notice_period_days, notice_deadline,
              notice_days_left FROM v_renewals WHERE auto_renew ORDER BY notice_deadline"""))
        late = [x for x in d if x["notice_days_left"] < 0]
        return (f"{len(d)} contracts auto-renew. " +
                (f"The notice deadline has already passed for {_list([x['title'] for x in late])}. " if late else "") +
                "Deadlines: " + _list([f"{x['title']} {x['notice_deadline']}" for x in d]) + ".")
    if key == "expire_30":
        d = rows(r.sql("""SELECT title, vendor, expiry_date, days_left, annual_value FROM v_renewals
            WHERE days_left BETWEEN 0 AND 30 ORDER BY expiry_date"""))
        return f"{len(d)} contracts expire in the next 30 days: " + _list([
            f"{x['title']} ({x['days_left']} days)" for x in d]) + "."
    if key == "total_value":
        d = rows(r.sql("""SELECT SUM(annual_value) AS total_annual_value, COUNT(annual_value) AS contracts_with_value
            FROM v_effective_terms WHERE status='active'"""))[0]
        return (f"Total annual value of active contracts is {money(d['total_annual_value'])} across "
                f"{d['contracts_with_value']} contracts that carry fees (MSAs carry no fees themselves).")
    if key == "short_confidentiality":
        h = r.search(query="keep Confidential Information confidential for 1 year after the agreement ends",
                     clause_type="confidentiality", top_k=4)["hits"]
        short = [x for x in h if re.search(r"\b1 year\b|one year", x["text"])]
        return ("Found " + f"{len(short)} contract with a confidentiality tail shorter than the 3-year standard: " +
                _list([f"{x['title']} [{x['heading']}, p.{x['page']}]" for x in short]) +
                ". All other confidentiality clauses searched keep the 3-year standard.")
    if key == "vendor_owns_ip":
        h = r.search(query="the Supplier owns all deliverables and work product, Customer receives a limited licence",
                     clause_type="ip_ownership", top_k=4)["hits"]
        own = [x for x in h if x["text"].startswith("The Supplier owns")]
        return (f"{len(own)} contract gives the vendor ownership of deliverables: " +
                _list([f"{x['title']} [{x['heading']}, p.{x['page']}]" for x in own]) +
                ". The standard position is that Arcadia owns bespoke deliverables.")
    if key == "non_indian_law":
        d = rows(r.sql("""SELECT title, vendor, governing_law FROM v_effective_terms
            WHERE governing_law IS NOT NULL AND governing_law <> 'India' ORDER BY title"""))
        h = r.search(query="governed by the laws of England and Wales or Singapore, courts of London or Singapore",
                     clause_type="governing_law", top_k=len(d) + 1)["hits"]
        non_in = [x for x in h if "laws of India" not in x["text"]]
        return (f"{len(d)} contracts use a non-Indian governing law: " +
                _list([f"{x['title']} ({x['governing_law']})" for x in d]) + ". Clause wording: " +
                _list([f"{x['title']} [{x['heading']}, p.{x['page']}]" for x in non_in]) + ".")
    if key == "uncapped_autorenew":
        d = rows(r.sql("""SELECT contract_id, title, vendor, expiry_date, notice_deadline
            FROM v_renewals WHERE auto_renew AND liability_uncapped ORDER BY notice_deadline"""))
        parts = []
        for x in d:
            h = r.search(query="limitation of liability", clause_type="liability_cap",
                         vendor=x["vendor"].split()[0], top_k=1)["hits"]
            if h:
                parts.append(f"{x['title']}: \"{h[0]['text']}\" [{h[0]['heading']}, p.{h[0]['page']}]")
        return (f"{len(d)} auto-renewing contracts have uncapped liability. " + " ".join(parts))
    raise KeyError(key)


def match(question: str) -> str | None:
    q = set(norm_key(question).split())
    best, score = None, 0.0
    for k, t in QUESTIONS.items():
        tt = set(norm_key(t).split())
        j = len(q & tt) / len(q | tt)
        if j > score:
            best, score = k, j
    return best if score >= 0.6 else None


def answer(question: str) -> dict | None:
    key = match(question)
    if not key:
        return None
    r = Run()
    return {"answer": _plan(key, r), "tool_calls": r.calls}
