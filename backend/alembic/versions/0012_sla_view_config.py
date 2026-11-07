"""v_sla reads each metric's direction from the metrics table (no hardcoded metric names).

Revision ID: 0012
Revises: 0011
"""
from alembic import op

revision = "0012"
down_revision = "0011"


def upgrade() -> None:
    op.execute("""
DROP VIEW IF EXISTS v_sla;
CREATE VIEW v_sla AS
SELECT m.contract_id, c.title, c.vendor, m.metric_key, m.period, m.actual, v.value_num AS target, m.incidents,
       CASE WHEN mt.better = 'lower' THEN m.actual > v.value_num ELSE m.actual < v.value_num END AS breach,
       CASE WHEN mt.better = 'lower' THEN GREATEST(m.actual - v.value_num, 0) ELSE GREATEST(v.value_num - m.actual, 0) END AS shortfall
FROM sla_measurements m JOIN contracts c ON c.id = m.contract_id JOIN metrics mt ON mt.key = m.metric_key
LEFT JOIN extracted_values v ON v.contract_id = m.contract_id AND v.metric_key = m.metric_key;
GRANT SELECT ON v_sla TO vmo_readonly;
""")


def downgrade() -> None:
    raise NotImplementedError("downgrade below 0005 is not supported: recreate the database")
