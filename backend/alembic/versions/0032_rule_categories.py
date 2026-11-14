"""Checklist rules can be limited to vendor categories (food safety is asked of a food supplier, not of a lift contractor).

Revision ID: 0032
Revises: 0031
"""
from alembic import op

revision = "0032"
down_revision = "0031"


def upgrade() -> None:
    op.execute("ALTER TABLE checklist_rules ADD COLUMN IF NOT EXISTS categories text[] NOT NULL DEFAULT '{}';")


def downgrade() -> None:
    raise NotImplementedError("downgrade below 0005 is not supported: recreate the database")
