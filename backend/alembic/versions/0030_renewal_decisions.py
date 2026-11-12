"""Renewal decisions: what the VMO decided for a contract that is coming up for renewal (renew, renegotiate, exit, extend), by whom and why.

Revision ID: 0030
Revises: 0028
"""
from alembic import op

revision = "0030"
down_revision = "0028"


def upgrade() -> None:
    op.execute("""CREATE TABLE IF NOT EXISTS renewal_decisions (
        id serial PRIMARY KEY, contract_id integer NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
        decision text NOT NULL CHECK (decision IN ('renew','renegotiate','exit','extend')), owner text, note text,
        decided_by text, decided_at timestamptz NOT NULL DEFAULT now());""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_renewal_decisions_contract ON renewal_decisions (contract_id, decided_at DESC);")
    op.execute("GRANT SELECT ON renewal_decisions TO vmo_readonly;")


def downgrade() -> None:
    raise NotImplementedError("downgrade below 0005 is not supported: recreate the database")
