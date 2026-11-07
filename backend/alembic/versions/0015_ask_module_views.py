"""Views so Ask can answer questions about every module: alerts, the draft review queue, template deviations.

Revision ID: 0015
Revises: 0014
"""
from alembic import op

revision = "0015"
down_revision = "0014"


def upgrade() -> None:
    op.execute("""
CREATE OR REPLACE VIEW v_alerts AS
  SELECT id AS alert_id, rule_key, title, body, severity, status, vendor, contract_id, created_at FROM alerts;
CREATE OR REPLACE VIEW v_reviews AS
  SELECT c.id AS contract_id, c.title, c.vendor, c.type, COALESCE(r.status, 'pending') AS review_status, r.assignee, r.due_date, r.reviewer, r.note,
         jsonb_array_length(COALESCE(x.items, '[]'::jsonb)) AS deviations,
         (SELECT count(*) FROM check_results k WHERE k.contract_id = c.id AND k.status = 'fail') AS checks_failed,
         c.ingested_at AS received_at, (CURRENT_DATE - c.ingested_at::date) AS days_waiting
  FROM contracts c LEFT JOIN contract_reviews r ON r.contract_id = c.id LEFT JOIN redlines x ON x.contract_id = c.id WHERE c.status = 'draft';
CREATE OR REPLACE VIEW v_deviations AS
  SELECT d.contract_id, c.title, c.vendor, c.type, c.status, t.name AS template, tc.clause_type, d.severity, d.deviation_summary
  FROM clause_deviations d JOIN contracts c ON c.id = d.contract_id JOIN template_clauses tc ON tc.id = d.template_clause_id JOIN templates t ON t.id = tc.template_id;
GRANT SELECT ON v_alerts, v_reviews, v_deviations TO vmo_readonly;
""")


def downgrade() -> None:
    raise NotImplementedError("downgrade below 0005 is not supported: recreate the database")
