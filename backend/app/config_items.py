"""Configuration that used to be hardcoded in the VMO features: obligation rules, spend-check thresholds, risk points and tiers, SLA credit tiers.
`ensure_defaults` inserts what is missing (never overwrites admin edits); `get` reads a value with a fallback."""
from __future__ import annotations

import json

from sqlalchemy import text

# (group, key, label, description, value, kind)
ITEMS: list[tuple] = [
    ("spend", "run_rate_tolerance", "Invoice above the usual (multiple)", "An invoice larger than this multiple of the contract's median invoice is flagged.", 1.10, "number"),
    ("spend", "late_grace_days", "Late-payment grace (days)", "Payment this many days after the due date is not flagged.", 5, "number"),
    ("spend", "interest_per_month", "Late-payment interest per month", "Used to estimate the exposure on late payments (the standard MSA caps it at 1%).", 0.01, "number"),
    ("spend", "over_value_tolerance", "Over-contract-value tolerance", "Billing is flagged when it exceeds the planned value by more than this share.", 0.001, "number"),
    ("spend", "late_medium_days", "Late payment is 'medium' after (days)", "Below this it is 'low'.", 30, "number"),
    ("risk", "tier_critical", "Critical tier from score", "A vendor's score at or above this is 'critical'.", 50, "number"),
    ("risk", "tier_high", "High tier from score", "", 30, "number"),
    ("risk", "tier_medium", "Medium tier from score", "", 15, "number"),
    ("risk", "k_contract", "Contract-terms saturation", "Points at which the component reaches ~63. Lower = more sensitive.", 60, "number"),
    ("risk", "k_renewal", "Renewal-exposure saturation", "", 60, "number"),
    ("risk", "k_performance", "Performance saturation", "", 50, "number"),
    ("risk", "k_spend", "Spend-compliance saturation", "", 70, "number"),
    ("risk", "conc_low", "Concentration starts at (share)", "Share of the portfolio value below which concentration scores 0.", 0.10, "number"),
    ("risk", "conc_high", "Concentration maxes at (share)", "Share at which concentration scores 100.", 0.40, "number"),
    ("risk_points", "uncapped_liability", "Uncapped liability (per contract)", "", 30, "number"),
    ("risk_points", "no_tfc", "No termination for convenience (per MSA / SaaS)", "", 8, "number"),
    ("risk_points", "personal_data_no_dpa", "Personal data without a DPA", "", 25, "number"),
    ("risk_points", "not_fully_signed", "Executed contract not fully signed", "", 25, "number"),
    ("risk_points", "check_critical", "Failing checklist rule: critical", "", 12, "number"),
    ("risk_points", "check_high", "Failing checklist rule: high", "", 6, "number"),
    ("risk_points", "check_medium", "Failing checklist rule: medium", "", 2, "number"),
    ("risk_points", "check_low", "Failing checklist rule: low", "", 0.5, "number"),
    ("risk_points", "renewal_notice_passed", "Auto-renewal notice deadline passed", "", 50, "number"),
    ("risk_points", "renewal_notice_soon", "Auto-renewal notice due within 30 days", "", 30, "number"),
    ("risk_points", "expiring_90", "Expires within 90 days", "", 12, "number"),
    ("risk_points", "sla_breach", "SLA breach (per month, plus shortfall)", "", 12, "number"),
    ("risk_points", "overdue_milestone", "Overdue supplier milestone", "", 15, "number"),
    ("risk_points", "overdue_other", "Other overdue supplier obligation", "", 8, "number"),
    ("risk_points", "spend_critical", "Spend exception: critical", "", 40, "number"),
    ("risk_points", "spend_high", "Spend exception: high", "", 25, "number"),
    ("risk_points", "spend_medium", "Spend exception: medium", "", 10, "number"),
    ("risk_points", "spend_low", "Spend exception: low", "", 3, "number"),
    ("sla", "credit_tiers", "Service-credit tiers", "[[shortfall in points below target, share of the monthly fee], ...]; the last tier has no upper bound (null). Used for the estimated credits.", [[0.5, 0.05], [1.0, 0.10], [None, 0.20]], "json"),
    ("sla", "window_months", "Months of SLA history counted in risk", "", 6, "number"),
]

OBLIGATION_RULES = [
    ("sla", "SLA target", "sla_availability_pct", "sla", "Supplier", "Keep service availability at or above {v:g}%", "monthly", "%", False),
    ("incident", "Incident notice", "incident_notice_hours", "notice", "Supplier", "Notify security incidents within {v:g} hours", "event", "hours", False),
    ("breach", "Breach notice", "breach_notice_hours", "notice", "Supplier", "Notify a personal-data breach within {v:g} hours", "event", "hours", False),
    ("payment", "Payment terms", "payment_terms_days", "payment", "Customer", "Pay undisputed invoices within {v:g} days", "event", "days", False),
    ("acceptance", "Acceptance window", "acceptance_days", "acceptance", "Customer", "Accept or reject deliverables within {v:g} business days", "event", "business days", False),
    ("personnel", "Key personnel", "key_personnel_replacement_days", "personnel", "Supplier", "Give {v:g} days' notice before replacing key personnel", "event", "days", False),
    ("cure", "Breach cure", "cure_period_days", "cure", "Both", "Remedy a material breach within {v:g} days of notice", "event", "days", False),
    ("audit", "Audit notice", "audit_notice_days", "audit", "Customer", "Give {v:g} days' notice before an audit", "event", "days", False),
    ("insurance", "Insurance", "insurance_cover_usd", "insurance", "Supplier", "Maintain insurance of at least ${v:,.0f} per claim and provide evidence annually", "annual", "USD", True),
    ("warranty", "Warranty", "warranty_days", "warranty", "Supplier", "Fix defects during the {v:g}-day warranty period", "event", "days", False),
]

METRIC_FLAGS = {"sla_availability_pct": ("higher", True), "incident_notice_hours": ("lower", True), "breach_notice_hours": ("lower", False), "payment_terms_days": ("higher", False),
                "liability_cap_multiple": ("higher", False), "insurance_cover_usd": ("higher", False), "warranty_days": ("higher", False), "confidentiality_years": ("higher", False),
                "renewal_notice_days": ("higher", False), "tfc_notice_days": ("lower", False), "cure_period_days": ("lower", False), "acceptance_days": ("lower", False),
                "audit_notice_days": ("lower", False), "key_personnel_replacement_days": ("lower", False)}


def ensure_defaults(s) -> None:
    for i, (g, k, label, desc, v, kind) in enumerate(ITEMS):
        s.execute(text("INSERT INTO config_items (grp, key, label, description, value, kind, sort_order) VALUES (:g,:k,:l,:d,CAST(:v AS jsonb),:kd,:o) ON CONFLICT DO NOTHING"),
                  {"g": g, "k": k, "l": label, "d": desc, "v": json.dumps(v), "kd": kind, "o": i})
    for i, (key, name, mk, kind, party, tpl, freq, unit, annual) in enumerate(OBLIGATION_RULES):
        s.execute(text("""INSERT INTO obligation_rules (key, name, metric_key, kind, party, title_template, frequency, unit, annual, builtin, sort_order)
                          VALUES (:k,:n,:m,:kd,:p,:t,:f,:u,:a,true,:o) ON CONFLICT DO NOTHING"""), {"k": key, "n": name, "m": mk, "kd": kind, "p": party, "t": tpl, "f": freq, "u": unit, "a": annual, "o": i})
    for mk, (better, sla) in METRIC_FLAGS.items():
        s.execute(text("UPDATE metrics SET better=:b, sla=:s WHERE key=:k AND better IS NULL AND NOT sla"), {"b": better, "s": sla, "k": mk})


def group(s, grp: str) -> dict:
    return {r[0]: r[1] for r in s.execute(text("SELECT key, value FROM config_items WHERE grp=:g"), {"g": grp})}


def get(s, grp: str, key: str, default=None):
    r = s.execute(text("SELECT value FROM config_items WHERE grp=:g AND key=:k"), {"g": grp, "k": key}).first()
    return r[0] if r else default
