"""Users (local accounts with roles), API tokens, audit log.

Revision ID: 0014
Revises: 0013
"""
from alembic import op

revision = "0014"
down_revision = "0013"


def upgrade() -> None:
    op.execute("""
CREATE TABLE users (
  id serial PRIMARY KEY, email text NOT NULL UNIQUE, name text, role text NOT NULL DEFAULT 'viewer' CHECK (role IN ('admin','reviewer','viewer')),
  password_hash text, source text NOT NULL DEFAULT 'local', active boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now(), last_login_at timestamptz);
CREATE TABLE api_tokens (
  id serial PRIMARY KEY, user_id int NOT NULL REFERENCES users(id) ON DELETE CASCADE, name text NOT NULL, token_hash text NOT NULL UNIQUE, prefix text NOT NULL,
  role text NOT NULL CHECK (role IN ('admin','reviewer','viewer')), created_at timestamptz NOT NULL DEFAULT now(), last_used_at timestamptz, revoked boolean NOT NULL DEFAULT false);
CREATE TABLE audit_log (
  id bigserial PRIMARY KEY, ts timestamptz NOT NULL DEFAULT now(), user_email text, role text, method text, path text, status int, ip text, event text, detail jsonb NOT NULL DEFAULT '{}');
CREATE INDEX ix_audit_ts ON audit_log (ts DESC);
""")


def downgrade() -> None:
    raise NotImplementedError("downgrade below 0005 is not supported: recreate the database")
