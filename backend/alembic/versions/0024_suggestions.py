"""Suggestions (proposed text replacements) are comment threads with a proposed change.

Revision ID: 0024
Revises: 0023
"""
from alembic import op

revision = "0024"
down_revision = "0023"


def upgrade() -> None:
    op.execute("ALTER TABLE comment_threads ADD COLUMN suggestion jsonb;")


def downgrade() -> None:
    raise NotImplementedError("downgrade below 0005 is not supported: recreate the database")
