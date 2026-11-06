"""Several pipelines with their own trigger (periodic / on new or changed files / manual) and folders,
redline review queue (status + per-change decisions), document versions for the online editor.

Revision ID: 0006
Revises: 0005
"""
from alembic import op

revision = "0006"
down_revision = "0005"


def upgrade() -> None:
    op.execute("""
ALTER TABLE pipeline_config DROP CONSTRAINT IF EXISTS pipeline_config_id_check;
ALTER TABLE pipeline_config ADD COLUMN key text, ADD COLUMN name text, ADD COLUMN description text,
  ADD COLUMN folders text NOT NULL DEFAULT '', ADD COLUMN trigger_mode text NOT NULL DEFAULT 'periodic',
  ADD COLUMN last_fingerprint text;
UPDATE pipeline_config SET key='contracts', name='Executed contracts',
  description='Signed agreements dropped into the contracts / uploads folders: extract, classify, check and index.',
  folders='contracts,uploads', trigger_mode='periodic' WHERE id=1;
INSERT INTO pipeline_config (id, key, name, description, folders, trigger_mode, interval_minutes)
  VALUES (2, 'drafts', 'Draft review (redline)',
  'Vendor drafts dropped into the drafts folder (or created from a template): extract, run the checklist and redline against the standard, then queue for review.',
  'drafts,generated', 'on_change', 15);
ALTER TABLE pipeline_config ALTER COLUMN key SET NOT NULL;
CREATE UNIQUE INDEX pipeline_config_key ON pipeline_config (key);

ALTER TABLE pipeline_runs ADD COLUMN pipeline text NOT NULL DEFAULT 'all';

CREATE TABLE contract_reviews (
  contract_id int PRIMARY KEY REFERENCES contracts ON DELETE CASCADE,
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','in_review','changes_requested','approved')),
  note text, reviewer text, updated_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE redline_decisions (
  contract_id int NOT NULL REFERENCES contracts ON DELETE CASCADE, clause_type text NOT NULL,
  decision text NOT NULL CHECK (decision IN ('accepted','rejected')), updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (contract_id, clause_type));
CREATE TABLE document_versions (
  id serial PRIMARY KEY, contract_id int NOT NULL REFERENCES contracts ON DELETE CASCADE, version int NOT NULL,
  body_md text NOT NULL, note text, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE (contract_id, version));
""")


def downgrade() -> None:
    raise NotImplementedError("downgrade below 0005 is not supported: recreate the database")
