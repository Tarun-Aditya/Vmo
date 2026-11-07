"""Files are identified by content hash, and every run records each file's hash and why it was (not) processed.

Revision ID: 0025
Revises: 0024
"""
from alembic import op

revision = "0025"
down_revision = "0024"


def upgrade() -> None:
    op.execute("ALTER TABLE pipeline_events ADD COLUMN IF NOT EXISTS content_hash text, ADD COLUMN IF NOT EXISTS size_bytes bigint, ADD COLUMN IF NOT EXISTS reason text;")
    op.execute("CREATE INDEX IF NOT EXISTS ix_contracts_content_hash ON contracts (content_hash);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_pipeline_events_hash ON pipeline_events (content_hash);")


def downgrade() -> None:
    raise NotImplementedError("downgrade below 0005 is not supported: recreate the database")
