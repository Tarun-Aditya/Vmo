"""Alerts (rules, notifications, delivery channels) and review workflow fields (assignee, due date).

Revision ID: 0013
Revises: 0012
"""
from alembic import op

revision = "0013"
down_revision = "0012"


def upgrade() -> None:
    op.execute("""
CREATE TABLE alert_rules (
  key text PRIMARY KEY, name text NOT NULL, description text, kind text NOT NULL, severity text NOT NULL DEFAULT 'medium', params jsonb NOT NULL DEFAULT '{}',
  channels text[] NOT NULL DEFAULT '{in_app}', enabled boolean NOT NULL DEFAULT true, builtin boolean NOT NULL DEFAULT false, sort_order int NOT NULL DEFAULT 0);
CREATE TABLE alerts (
  id serial PRIMARY KEY, rule_key text NOT NULL, dedupe_key text NOT NULL UNIQUE, title text NOT NULL, body text, severity text NOT NULL, link text, contract_id int, vendor text,
  status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','acknowledged','resolved')), created_at timestamptz NOT NULL DEFAULT now(), read_at timestamptz, acknowledged_by text,
  delivered jsonb NOT NULL DEFAULT '{}');
CREATE INDEX ix_alerts_status ON alerts (status, created_at DESC);
CREATE TABLE alert_channels (
  id serial PRIMARY KEY, name text NOT NULL UNIQUE, kind text NOT NULL CHECK (kind IN ('email','slack','teams','webhook')), config jsonb NOT NULL DEFAULT '{}', secrets_enc text,
  enabled boolean NOT NULL DEFAULT true, min_severity text NOT NULL DEFAULT 'medium', last_status text, last_message text, last_sent_at timestamptz);
ALTER TABLE contract_reviews ADD COLUMN assignee text, ADD COLUMN due_date date;
""")


def downgrade() -> None:
    raise NotImplementedError("downgrade below 0005 is not supported: recreate the database")
