"""Human corrections of extracted fields (kept across re-extraction) and the accuracy report built from them.

Revision ID: 0019
Revises: 0018
"""
from alembic import op

revision = "0019"
down_revision = "0018"


def upgrade() -> None:
    op.execute("""
CREATE TABLE field_corrections (
  id serial PRIMARY KEY, source_path text NOT NULL, contract_id int REFERENCES contracts(id) ON DELETE SET NULL, field text NOT NULL, original_value text, corrected_value text,
  corrected_by text, note text, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE (source_path, field));
ALTER TABLE field_extractions ADD COLUMN corrected boolean NOT NULL DEFAULT false;
""")


def downgrade() -> None:
    raise NotImplementedError("downgrade below 0005 is not supported: recreate the database")
