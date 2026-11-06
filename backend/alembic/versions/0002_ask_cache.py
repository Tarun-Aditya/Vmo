"""Cache of Ask answers for demo mode.

Revision ID: 0002
Revises: 0001
"""
from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade() -> None:
    op.execute("""
CREATE TABLE ask_cache (
  question_key text PRIMARY KEY, question text NOT NULL, response jsonb NOT NULL,
  source text NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ask_cache")
