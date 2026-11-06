"""Obligations: what each party must do under a contract, with dates and targets.
Rules read them from the extracted values and clauses (milestones with dates, SLA targets, notice periods, payment terms,
insurance, audit, renewal notice) so every engine produces them; with Claude, extra duties found in the clause text
(reporting, certificates, security duties) are added. Status edits made by people survive re-extraction."""
from __future__ import annotations

import re
from datetime import date, timedelta

from sqlalchemy import text

from app import llm

MONTHS = "january february march april may june july august september october november december".split()


def _date(s: str) -> date | None:
    m = re.match(r"\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", s)
    if not m or m.group(2).lower() not in MONTHS:
        return None
    return date(int(m.group(3)), MONTHS.index(m.group(2).lower()) + 1, int(m.group(1)))


def _anniversary(eff: date | None, today: date) -> date | None:
    if not eff:
        return None
    d = eff.replace(year=today.year) if not (eff.month == 2 and eff.day == 29) else date(today.year, 2, 28)
    return d if d >= today else d.replace(year=d.year + 1)


# metric -> (kind, party, title template, frequency, unit)
METRIC_OBLIGATIONS = {
    "sla_availability_pct": ("sla", "Supplier", "Keep service availability at or above {v:g}%", "monthly", "%"),
    "incident_notice_hours": ("notice", "Supplier", "Notify security incidents within {v:g} hours", "event", "hours"),
    "breach_notice_hours": ("notice", "Supplier", "Notify a personal-data breach within {v:g} hours", "event", "hours"),
    "payment_terms_days": ("payment", "Customer", "Pay undisputed invoices within {v:g} days", "event", "days"),
    "acceptance_days": ("acceptance", "Customer", "Accept or reject deliverables within {v:g} business days", "event", "business days"),
    "key_personnel_replacement_days": ("personnel", "Supplier", "Give {v:g} days' notice before replacing key personnel", "event", "days"),
    "cure_period_days": ("cure", "Both", "Remedy a material breach within {v:g} days of notice", "event", "days"),
    "audit_notice_days": ("audit", "Customer", "Give {v:g} days' notice before an audit", "event", "days"),
    "insurance_cover_usd": ("insurance", "Supplier", "Maintain insurance of at least ${v:,.0f} per claim and provide evidence annually", "annual", "USD"),
    "warranty_days": ("warranty", "Supplier", "Fix defects during the {v:g}-day warranty period", "event", "days"),
}


def rule_obligations(c: dict, clauses: list[dict], vals: list[dict], today: date) -> list[dict]:
    out: list[dict] = []
    by = {v["metric_key"]: v for v in vals if v.get("value_num") is not None}
    for mk, (kind, party, title, freq, unit) in METRIC_OBLIGATIONS.items():
        v = by.get(mk)
        if not v:
            continue
        due = _anniversary(c.get("effective_date"), today) if freq == "annual" else None
        out.append(dict(key=f"metric:{mk}", kind=kind, party=party, title=title.format(v=float(v["value_num"])), due_date=due, frequency=freq,
                        target_value=v["value_num"], target_unit=unit, metric_key=mk, page=v.get("page"), clause_type=None, detail=None))
    for cl in clauses:                       # dated milestones in the deliverables clause
        for n, desc, when in re.findall(r"Milestone (\d+): (.+?) by (\d{1,2} [A-Za-z]+ \d{4})", cl["text"]):
            d = _date(when)
            if d:
                out.append(dict(key=f"milestone:{n}", kind="milestone", party="Supplier", title=f"Milestone {n}: {desc.strip().rstrip('.')}", due_date=d,
                                frequency="once", target_value=None, target_unit=None, metric_key=None, page=cl.get("page"), clause_type=cl.get("clause_type"), detail=None))
    exp, notice = c.get("expiry_date"), c.get("notice_period_days")
    if c.get("auto_renew") and exp and notice:
        out.append(dict(key="renewal:notice", kind="renewal", party="Customer", title=f"Give non-renewal notice ({notice} days) or the contract renews automatically",
                        due_date=exp - timedelta(days=int(notice)), frequency="once", target_value=notice, target_unit="days", metric_key=None, page=None, clause_type="renewal", detail=None))
    return out


LLM_TOOL = {"name": "record_obligations", "description": "Record the contractual obligations found in the clauses.",
            "input_schema": {"type": "object", "properties": {"obligations": {"type": "array", "items": {"type": "object", "properties": {
                "party": {"type": "string", "enum": ["Supplier", "Customer", "Both"]},
                "title": {"type": "string", "description": "One short imperative sentence"},
                "kind": {"type": "string", "enum": ["reporting", "security", "certificate", "governance", "delivery", "other"]},
                "frequency": {"type": "string", "enum": ["once", "monthly", "quarterly", "annual", "event"]},
                "clause_heading": {"type": "string"}}, "required": ["party", "title", "kind", "frequency", "clause_heading"]}}}, "required": ["obligations"]}}


def llm_obligations(c: dict, clauses: list[dict]) -> list[dict]:
    """Additional duties that the rules cannot see (reporting, certificates, security programme...)."""
    body = "\n\n".join(f"## {x['heading']}\n{x['text']}" for x in clauses if x.get("clause_type") not in ("execution",))[:14000]
    if not body.strip() or c["type"] in ("Amendment", "NDA"):
        return []
    from app.config import settings

    res = llm.call_tool("obligations", settings.model_extract,
                        "You list the recurring or time-bound duties a contract puts on each party, for a vendor-management office. Only duties the text states "
                        "(reporting, certifications, security duties, governance meetings, deliveries). Skip payment, notice, SLA, insurance, audit, warranty, milestones "
                        "and renewal notice: they are captured elsewhere. Return an empty list if there are none.",
                        f"Contract: {c['title']} ({c['type']})\n\n{body}", LLM_TOOL, max_tokens=1500)
    by_head = {x["heading"].lower(): x for x in clauses}
    out = []
    for i, o in enumerate(res.get("obligations", [])[:8]):
        cl = by_head.get(o.get("clause_heading", "").lower().lstrip("0123456789. "))
        out.append(dict(key=f"llm:{i}:{re.sub(r'[^a-z0-9]+', '-', o['title'].lower())[:40]}", kind=o["kind"], party=o["party"], title=o["title"], due_date=None,
                        frequency=o["frequency"], target_value=None, target_unit=None, metric_key=None, page=cl["page"] if cl else None,
                        clause_type=cl.get("clause_type") if cl else None, detail=None, source="llm"))
    return out


def derive(s, contract, clauses: list[dict], vals: list[dict], today: date | None = None, use_llm: bool = True) -> int:
    """Recompute a contract's obligations. Keeps status / notes people set; drops stale open ones."""
    today = today or date.today()
    if contract.status == "draft" or contract.type == "Amendment":
        s.execute(text("DELETE FROM obligations WHERE contract_id=:c"), {"c": contract.id})
        return 0
    c = dict(title=contract.title, type=contract.type, effective_date=contract.effective_date, expiry_date=contract.expiry_date,
             notice_period_days=contract.notice_period_days, auto_renew=contract.auto_renew)
    items = rule_obligations(c, clauses, vals, today)
    if use_llm and llm.available():
        try:
            items += llm_obligations(c, clauses)
        except Exception as e:      # the rules still stand
            llm.note_failure(e)
    keys = []
    for o in items:
        keys.append(o["key"])
        s.execute(text("""INSERT INTO obligations (contract_id, key, kind, party, title, detail, due_date, frequency, target_value, target_unit, metric_key, clause_type, page, source)
                          VALUES (:c,:key,:kind,:party,:title,:detail,:due_date,:frequency,:target_value,:target_unit,:metric_key,:clause_type,:page,:source)
                          ON CONFLICT (contract_id, key) DO UPDATE SET kind=EXCLUDED.kind, party=EXCLUDED.party, title=EXCLUDED.title, due_date=EXCLUDED.due_date,
                            frequency=EXCLUDED.frequency, target_value=EXCLUDED.target_value, target_unit=EXCLUDED.target_unit, metric_key=EXCLUDED.metric_key,
                            clause_type=EXCLUDED.clause_type, page=EXCLUDED.page, source=EXCLUDED.source"""),
                  {"c": contract.id, "source": o.get("source", "rule"), **{k: o.get(k) for k in ("key", "kind", "party", "title", "detail", "due_date", "frequency", "target_value", "target_unit", "metric_key", "clause_type", "page")}})
    s.execute(text("DELETE FROM obligations WHERE contract_id=:c AND status='open' AND NOT (key = ANY(:k))"), {"c": contract.id, "k": keys})
    return len(items)
