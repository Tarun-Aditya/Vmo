"""Recreate the effective-terms / renewals / key-clause views: 'uncapped' now recognises any wording of unlimited liability
(Claude copies the clause text, the offline extractor writes 'Unlimited').

Revision ID: 0008
Revises: 0007
"""
from alembic import op

from app.viewsql import effective_terms_sql, key_clauses_sql, renewals_sql

revision = "0008"
down_revision = "0007"


def upgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_key_clauses, v_renewals, v_effective_terms, v_document_terms")
    op.execute(effective_terms_sql())
    op.execute(effective_terms_sql("v_document_terms", drafts=True))
    op.execute(renewals_sql())
    op.execute(key_clauses_sql())
    op.execute("GRANT SELECT ON v_effective_terms, v_document_terms, v_renewals, v_key_clauses TO vmo_readonly")


def downgrade() -> None:
    raise NotImplementedError("downgrade below 0005 is not supported: recreate the database")
