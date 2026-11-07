"""Global switches stored server-side (demo mode: no Claude anywhere; off: every module is LLM-based).

Revision ID: 0027
Revises: 0026
"""
from alembic import op

revision = "0027"
down_revision = "0026"


def upgrade() -> None:
    op.execute("CREATE TABLE IF NOT EXISTS app_settings (key text PRIMARY KEY, value jsonb, updated_at timestamptz DEFAULT now(), updated_by text);")


def downgrade() -> None:
    raise NotImplementedError("downgrade below 0005 is not supported: recreate the database")
