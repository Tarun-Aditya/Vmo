"""Threaded comments on documents (anchored to text, assignable, resolvable) and share links (view / comment / edit).

Revision ID: 0016
Revises: 0015
"""
from alembic import op

revision = "0016"
down_revision = "0015"


def upgrade() -> None:
    op.execute("""
CREATE TABLE comment_threads (
  id serial PRIMARY KEY, contract_id int NOT NULL REFERENCES contracts(id) ON DELETE CASCADE, version int, anchor_text text, anchor_start int, anchor_end int, clause_type text,
  status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','resolved')), source text NOT NULL DEFAULT 'user' CHECK (source IN ('user','ai','guest')), severity text,
  created_by text NOT NULL, assignee text, due_date date, resolved_by text, resolved_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(),
  ai_key text, UNIQUE (contract_id, ai_key));
CREATE INDEX ix_threads_contract ON comment_threads (contract_id, status);
CREATE TABLE comments (
  id serial PRIMARY KEY, thread_id int NOT NULL REFERENCES comment_threads(id) ON DELETE CASCADE, author text NOT NULL, body text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), edited_at timestamptz);
CREATE TABLE share_links (
  id serial PRIMARY KEY, contract_id int NOT NULL REFERENCES contracts(id) ON DELETE CASCADE, token_hash text NOT NULL UNIQUE, prefix text NOT NULL, level text NOT NULL CHECK (level IN ('view','comment','edit')),
  label text, expires_at timestamptz, created_by text, created_at timestamptz NOT NULL DEFAULT now(), revoked boolean NOT NULL DEFAULT false, last_used_at timestamptz, uses int NOT NULL DEFAULT 0);
""")


def downgrade() -> None:
    raise NotImplementedError("downgrade below 0005 is not supported: recreate the database")
