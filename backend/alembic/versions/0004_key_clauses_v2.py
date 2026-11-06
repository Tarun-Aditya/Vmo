"""Recreate v_key_clauses: typical MSA/SOW/Work Order templates add key clauses.

Revision ID: 0004
Revises: 0003
"""
from alembic import op

from app.viewsql import key_clauses_sql

revision = "0004"
down_revision = "0003"


def upgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_key_clauses")
    op.execute(key_clauses_sql())
    op.execute("GRANT SELECT ON v_key_clauses TO vmo_readonly")


def downgrade() -> None:
    pass  # the view is derived from the clause library; nothing to restore
