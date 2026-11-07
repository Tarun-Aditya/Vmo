"""E-signature: signature requests, signers (token links), completion certificate; provider internal or DocuSign.

Revision ID: 0018
Revises: 0017
"""
from alembic import op

revision = "0018"
down_revision = "0017"


def upgrade() -> None:
    op.execute("""
CREATE TABLE signature_requests (
  id serial PRIMARY KEY, contract_id int REFERENCES contracts(id) ON DELETE SET NULL, title text NOT NULL, version int, doc_hash text NOT NULL,
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','completed','declined','cancelled')), provider text NOT NULL DEFAULT 'internal', external_id text,
  sequential boolean NOT NULL DEFAULT true, created_by text, created_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz, executed_contract_id int, certificate jsonb);
CREATE TABLE signers (
  id serial PRIMARY KEY, request_id int NOT NULL REFERENCES signature_requests(id) ON DELETE CASCADE, seq int NOT NULL, name text NOT NULL, email text NOT NULL,
  role text NOT NULL DEFAULT 'other' CHECK (role IN ('customer','supplier','other')), token_hash text NOT NULL UNIQUE,
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','signed','declined')), signed_at timestamptz, typed_signature text, ip text, user_agent text, decline_reason text);
""")


def downgrade() -> None:
    raise NotImplementedError("downgrade below 0005 is not supported: recreate the database")
