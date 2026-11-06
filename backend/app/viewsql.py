"""SQL for the reporting views, shared by migrations (so a later migration can recreate them)."""
from __future__ import annotations

from app.docgen.library import KEY_CLAUSES

# Amendment-overridable contract columns (liability_cap_multiple: NULL = uncapped).
OVERRIDABLE = [
    "expiry_date", "notice_period_days", "auto_renew", "annual_value", "total_value",
    "payment_terms_days", "liability_cap_multiple", "liability_cap_text",
    "termination_for_convenience", "governing_law",
]


def effective_terms_sql(name: str = "v_effective_terms", drafts: bool = False) -> str:
    """One row per non-amendment contract with amendments applied, plus provenance
    (<field>_source = id of the contract whose text set the value) and signature status."""
    selects, joins = [], []
    for f in OVERRIDABLE:
        selects.append(f"CASE WHEN o_{f}.src IS NOT NULL THEN a_{f}.{f} ELSE c.{f} END AS {f}")
        selects.append(f"COALESCE(o_{f}.src, c.id) AS {f}_source")
        joins.append(
            f"LEFT JOIN latest_override o_{f} ON o_{f}.parent_id = c.id AND o_{f}.field = '{f}' "
            f"LEFT JOIN contracts a_{f} ON a_{f}.id = o_{f}.src"
        )
    return f"""
CREATE VIEW {name} AS
SELECT t.*,
       -- Uncapped = a cap clause says "Unlimited". Docs with no cap clause are NOT uncapped.
       (t.liability_cap_multiple IS NULL AND t.liability_cap_text ~* 'unlimited|uncapped') AS liability_uncapped
FROM (
WITH latest_override AS (
  SELECT DISTINCT ON (a.parent_id, f.field) a.parent_id, f.field, a.id AS src
  FROM contracts a CROSS JOIN LATERAL unnest(a.overrides) AS f(field)
  WHERE a.type = 'Amendment' AND a.parent_id IS NOT NULL
  ORDER BY a.parent_id, f.field, a.effective_date DESC, a.id DESC
)
SELECT c.id AS contract_id, c.title, c.vendor, c.effective_date, c.category, c.type, c.parent_id,
       c.status, c.currency, c.processes_personal_data, c.has_dpa, c.owner,
       c.customer_signatory, c.customer_signed_date, c.supplier_signatory,
       c.supplier_signed_date, c.fully_executed,
       {", ".join(selects)}
FROM contracts c
{" ".join(joins)}
WHERE c.type <> 'Amendment' {'' if drafts else "AND c.status <> 'draft'"}
) t
"""


def renewals_sql() -> str:
    return """
CREATE VIEW v_renewals AS
SELECT contract_id, title, vendor, category, type, annual_value, currency, auto_renew,
       expiry_date, notice_period_days, owner, liability_uncapped, termination_for_convenience,
       fully_executed,
       (expiry_date - COALESCE(notice_period_days, 0)) AS notice_deadline,
       (expiry_date - CURRENT_DATE) AS days_left,
       ((expiry_date - COALESCE(notice_period_days, 0)) - CURRENT_DATE) AS notice_days_left,
       -- Bucket by the date action is needed: notice deadline for auto-renewals, else expiry.
       CASE
         WHEN d < 0 THEN 'overdue'
         WHEN d <= 30 THEN '30'
         WHEN d <= 60 THEN '60'
         WHEN d <= 90 THEN '90'
         ELSE 'later'
       END AS bucket
FROM (
  SELECT e.*, CASE WHEN e.auto_renew
                   THEN (e.expiry_date - COALESCE(e.notice_period_days, 0)) - CURRENT_DATE
                   ELSE e.expiry_date - CURRENT_DATE END AS d
  FROM v_effective_terms e WHERE e.status = 'active' AND e.expiry_date IS NOT NULL
) x
"""


def key_clauses_sql(keys: list[str] | None = None) -> str:
    """One boolean per key clause: does the document contain it? (has_execution = fully signed.)"""
    keys = keys or KEY_CLAUSES
    cols = [
        f"COALESCE(bool_or(cl.clause_type = '{c}'), false) AS has_{c}"
        for c in keys
        if c != "execution"
    ]
    return f"""
CREATE VIEW v_key_clauses AS
SELECT c.id AS contract_id, {", ".join(cols)}{', c.fully_executed AS has_execution' if 'execution' in keys else ''}
FROM contracts c LEFT JOIN clauses cl ON cl.contract_id = c.id
WHERE c.type <> 'Amendment'
GROUP BY c.id, c.fully_executed
"""
