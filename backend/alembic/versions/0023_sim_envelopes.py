"""Simulated e-signature service (demo / test): envelopes with recipients.

Revision ID: 0023
Revises: 0022
"""
from alembic import op

revision = "0023"
down_revision = "0022"


def upgrade() -> None:
    op.execute("""
CREATE TABLE sim_envelopes (
  id text PRIMARY KEY, account text NOT NULL, subject text, status text NOT NULL DEFAULT 'sent', doc_name text, doc_ext text, doc_b64 text, recipients jsonb NOT NULL DEFAULT '[]',
  webhook_url text, created_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz);
""")


def downgrade() -> None:
    raise NotImplementedError("downgrade below 0005 is not supported: recreate the database")
