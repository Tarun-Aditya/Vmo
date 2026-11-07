"""Connectors (Google Drive, OneDrive, SharePoint): configuration, encrypted secrets, and the files synced from each.

Revision ID: 0010
Revises: 0009
"""
from alembic import op

revision = "0010"
down_revision = "0009"


def upgrade() -> None:
    op.execute("""
CREATE TABLE connectors (
  id serial PRIMARY KEY, name text NOT NULL UNIQUE, type text NOT NULL CHECK (type IN ('gdrive','onedrive','sharepoint')),
  config jsonb NOT NULL DEFAULT '{}', secrets_enc text, target text NOT NULL DEFAULT 'contracts' CHECK (target IN ('contracts','drafts')),
  enabled boolean NOT NULL DEFAULT true, trigger_mode text NOT NULL DEFAULT 'periodic' CHECK (trigger_mode IN ('periodic','manual')),
  interval_minutes int NOT NULL DEFAULT 60, last_sync_at timestamptz, next_sync_at timestamptz, last_status text, last_message text,
  created_at timestamptz NOT NULL DEFAULT now());
ALTER TABLE contracts ADD COLUMN source_url text;
CREATE TABLE connector_files (
  id serial PRIMARY KEY, connector_id int NOT NULL REFERENCES connectors ON DELETE CASCADE, remote_id text NOT NULL, path text NOT NULL, etag text,
  modified text, size bigint, web_url text, local_path text, status text NOT NULL DEFAULT 'synced', last_seen timestamptz NOT NULL DEFAULT now(),
  UNIQUE (connector_id, remote_id));
""")


def downgrade() -> None:
    raise NotImplementedError("downgrade below 0005 is not supported: recreate the database")
