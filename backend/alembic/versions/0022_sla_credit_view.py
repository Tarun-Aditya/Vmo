"""v_sla_credit: monthly SLA actuals with the estimated service credit (tiers from Admin -> Thresholds, share of the monthly fee), so Ask can total credits.

Revision ID: 0022
Revises: 0021
"""
from alembic import op

revision = "0022"
down_revision = "0021"


def upgrade() -> None:
    op.execute("""
CREATE OR REPLACE VIEW v_sla_credit AS
SELECT s.*, COALESCE(CASE WHEN s.breach AND COALESCE(m.better, 'higher') <> 'lower' THEN
    (SELECT (t.elem ->> 1)::numeric FROM config_items ci, LATERAL jsonb_array_elements(ci.value) WITH ORDINALITY AS t(elem, n)
      WHERE ci.grp = 'sla' AND ci.key = 'credit_tiers' AND (t.elem ->> 0 IS NULL OR s.shortfall < (t.elem ->> 0)::numeric) ORDER BY t.n LIMIT 1)
    * COALESCE(e.annual_value, 0) / 12 END, 0) AS credit_usd
FROM v_sla s LEFT JOIN metrics m ON m.key = s.metric_key LEFT JOIN v_effective_terms e ON e.contract_id = s.contract_id;
GRANT SELECT ON v_sla_credit TO vmo_readonly;
""")


def downgrade() -> None:
    raise NotImplementedError("downgrade below 0005 is not supported: recreate the database")
