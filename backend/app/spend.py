"""Spend vs contract: every invoice is checked against the contract it claims to bill, and each contract's billing is checked against its value.
Exceptions land in spend_exceptions (read by the Spend screen, the risk score and Ask)."""
from __future__ import annotations

import statistics
from datetime import date

from sqlalchemy import text

INTEREST_PER_MONTH = 0.01          # the standard MSA caps late-payment interest at 1% per month
RUN_RATE_TOLERANCE = 1.10          # an invoice more than 10% above the contract's usual invoice is flagged


def compute_exceptions(s, today: date | None = None) -> int:
    today = today or date.today()
    s.execute(text("DELETE FROM spend_exceptions"))
    contracts = {r["contract_id"]: dict(r) for r in s.execute(text(
        "SELECT contract_id, title, vendor, effective_date, expiry_date, fully_executed, planned_value FROM v_contract_spend "
        "JOIN (SELECT id, fully_executed FROM contracts) c ON c.id = contract_id")).mappings()}
    drafts = {r[0]: r[1] for r in s.execute(text("SELECT vendor, min(title) FROM contracts WHERE status='draft' GROUP BY vendor"))}
    invs = [dict(r) for r in s.execute(text("SELECT id, vendor, contract_id, invoice_no, invoice_date, due_date, paid_date, amount FROM invoices ORDER BY invoice_date, id")).mappings()]
    typical: dict[int, float] = {}
    for cid in {i["contract_id"] for i in invs if i["contract_id"]}:
        amts = [float(i["amount"]) for i in invs if i["contract_id"] == cid]
        if len(amts) >= 3:
            typical[cid] = statistics.median(amts)
    seen: dict[tuple, int] = {}
    n = 0

    def add(inv_id, cid, vendor, kind, sev, risk, detail):
        nonlocal n
        s.execute(text("INSERT INTO spend_exceptions (invoice_id, contract_id, vendor, kind, severity, amount_at_risk, detail) VALUES (:i,:c,:v,:k,:s,:r,:d)"),
                  {"i": inv_id, "c": cid, "v": vendor, "k": kind, "s": sev, "r": round(float(risk), 2), "d": detail})
        n += 1

    for i in invs:
        c, amt, label = contracts.get(i["contract_id"]), float(i["amount"]), f"Invoice {i['invoice_no']}"
        if not c:
            why = f"only a draft ({drafts[i['vendor']]}) is on file" if i["vendor"] in drafts else "no agreement of any kind is on file"
            add(i["id"], None, i["vendor"], "no_contract", "high", amt, f"{label} for ${amt:,.0f} from {i['vendor']}: {why}.")
            continue
        if not c["fully_executed"]:
            add(i["id"], i["contract_id"], i["vendor"], "unsigned_contract", "critical", amt, f"{label} (${amt:,.0f}) is billed against {c['title']}, which is not fully signed.")
        if c["effective_date"] and i["invoice_date"] < c["effective_date"]:
            add(i["id"], i["contract_id"], i["vendor"], "billed_before_effective", "medium", amt, f"{label} is dated {i['invoice_date']:%d %b %Y}, before the contract starts on {c['effective_date']:%d %b %Y}.")
        if c["expiry_date"] and i["invoice_date"] > c["expiry_date"]:
            add(i["id"], i["contract_id"], i["vendor"], "billed_after_expiry", "high", amt, f"{label} is dated after the contract ended on {c['expiry_date']:%d %b %Y}.")
        key = (i["contract_id"], i["invoice_no"], amt)
        if key in seen:
            add(i["id"], i["contract_id"], i["vendor"], "duplicate", "high", amt, f"{label} (${amt:,.0f}) repeats an invoice already received for {c['title']}.")
        else:
            seen[key] = i["id"]
        t = typical.get(i["contract_id"])
        if t and amt > t * RUN_RATE_TOLERANCE:
            add(i["id"], i["contract_id"], i["vendor"], "above_run_rate", "medium", amt - t, f"{label} is ${amt:,.0f}, {amt / t - 1:.0%} above the usual ${t:,.0f} for {c['title']}.")
        if i["due_date"]:
            paid = i["paid_date"] or today
            late = (paid - i["due_date"]).days
            if late > 5:                  # five days' grace
                add(i["id"], i["contract_id"], i["vendor"], "late_payment", "medium" if late > 30 else "low", amt * INTEREST_PER_MONTH * late / 30,
                    f"{label} was {'paid' if i['paid_date'] else 'still unpaid'} {late} days after the due date; interest exposure at 1% a month.")
    for cid, c in contracts.items():          # the contract's total billing against its planned value
        billed = float(s.execute(text("SELECT COALESCE(sum(amount),0) FROM invoices WHERE contract_id=:c"), {"c": cid}).scalar())
        plan = float(c["planned_value"] or 0)
        if plan and billed > plan * 1.001:
            add(None, cid, c["vendor"], "over_contract_value", "high", billed - plan,
                f"${billed:,.0f} has been billed against {c['title']}, ${billed - plan:,.0f} ({billed / plan - 1:.0%}) more than its planned value of ${plan:,.0f}.")
    return n
