"""Chat history: conversations and their messages (question, answer payload with tables and thinking).

Revision ID: 0007
Revises: 0006
"""
from alembic import op

revision = "0007"
down_revision = "0006"


def upgrade() -> None:
    op.execute("""
CREATE TABLE conversations (
  id serial PRIMARY KEY, title text NOT NULL, scope jsonb, created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE chat_messages (
  id serial PRIMARY KEY, conversation_id int NOT NULL REFERENCES conversations ON DELETE CASCADE,
  role text NOT NULL CHECK (role IN ('user','assistant')), content text NOT NULL, payload jsonb,
  created_at timestamptz NOT NULL DEFAULT now());
CREATE INDEX ix_chat_messages_conv ON chat_messages (conversation_id, id);
""")


def downgrade() -> None:
    raise NotImplementedError("downgrade below 0005 is not supported: recreate the database")
