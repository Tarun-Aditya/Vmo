"""Work Order type, signature columns, v_key_clauses; recreate the reporting views.

Revision ID: 0003
Revises: 0002
"""
from alembic import op

from app.viewsql import effective_terms_sql, key_clauses_sql, renewals_sql

revision = "0003"
down_revision = "0002"

TYPES_NEW = "('MSA','SOW','Work Order','NDA','SaaS','DPA','Services','Amendment')"


def upgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_renewals, v_effective_terms")
    op.execute(f"""
ALTER TABLE contracts DROP CONSTRAINT IF EXISTS contracts_type_check;
ALTER TABLE contracts ADD CONSTRAINT contracts_type_check CHECK (type IN {TYPES_NEW});
ALTER TABLE contracts
  ADD COLUMN customer_signatory text, ADD COLUMN customer_signed_date date,
  ADD COLUMN supplier_signatory text, ADD COLUMN supplier_signed_date date,
  ADD COLUMN fully_executed boolean NOT NULL DEFAULT false;
""")
    op.execute(effective_terms_sql())
    op.execute(renewals_sql())
    op.execute(key_clauses_sql())
    op.execute("GRANT SELECT ON v_effective_terms, v_renewals, v_key_clauses TO vmo_readonly")


def downgrade() -> None:
    # The pre-0003 views lived inline in 0001; rebuild the dev database instead of downgrading.
    raise NotImplementedError("downgrade below 0003 is not supported: recreate the database")
