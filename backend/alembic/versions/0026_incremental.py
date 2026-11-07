"""Incremental runs: remember each file's size/mtime (cheap pre-filter; the hash stays the identity) and cache Claude clause tagging by content hash.

Revision ID: 0026
Revises: 0025
"""
from alembic import op

revision = "0026"
down_revision = "0025"


def upgrade() -> None:
    op.execute("ALTER TABLE contracts ADD COLUMN IF NOT EXISTS source_size bigint, ADD COLUMN IF NOT EXISTS source_mtime_ns bigint;")
    op.execute("""CREATE TABLE IF NOT EXISTS kcc_ai_cache (content_hash text NOT NULL, key text NOT NULL, def_hash text NOT NULL, result jsonb,
                  created_at timestamptz DEFAULT now(), PRIMARY KEY (content_hash, key, def_hash));""")


def downgrade() -> None:
    raise NotImplementedError("downgrade below 0005 is not supported: recreate the database")
