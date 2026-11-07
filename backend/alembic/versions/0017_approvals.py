"""Approval routing: rules (by document type, value, deviation severity) -> ordered approval steps per draft.

Revision ID: 0017
Revises: 0016
"""
from alembic import op

revision = "0017"
down_revision = "0016"


def upgrade() -> None:
    op.execute("""
CREATE TABLE approval_rules (
  id serial PRIMARY KEY, name text NOT NULL, doc_types text[] NOT NULL DEFAULT '{}', min_value numeric, min_severity text CHECK (min_severity IN ('low','medium','high','critical')),
  steps jsonb NOT NULL DEFAULT '[]', enabled boolean NOT NULL DEFAULT true, sort_order int NOT NULL DEFAULT 100, remind_after_days int NOT NULL DEFAULT 3);
CREATE TABLE approvals (
  id serial PRIMARY KEY, contract_id int NOT NULL REFERENCES contracts(id) ON DELETE CASCADE, rule_id int REFERENCES approval_rules(id) ON DELETE SET NULL, rule_name text,
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected','cancelled')), created_by text, created_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz);
CREATE TABLE approval_steps (
  id serial PRIMARY KEY, approval_id int NOT NULL REFERENCES approvals(id) ON DELETE CASCADE, seq int NOT NULL, label text NOT NULL, approvers text[] NOT NULL DEFAULT '{}',
  status text NOT NULL DEFAULT 'waiting' CHECK (status IN ('waiting','pending','approved','rejected')), activated_at timestamptz, decided_by text, decided_at timestamptz, comment text);
CREATE INDEX ix_approvals_contract ON approvals (contract_id, status);
""")


def downgrade() -> None:
    raise NotImplementedError("downgrade below 0005 is not supported: recreate the database")
