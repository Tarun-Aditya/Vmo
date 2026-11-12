"""Property level: which hotel (site) a contract is for. Group-level agreements have none.

Revision ID: 0028
Revises: 0027
"""
from alembic import op

revision = "0028"
down_revision = "0027"


def upgrade() -> None:
    op.execute("ALTER TABLE contracts ADD COLUMN IF NOT EXISTS property text;")
    op.execute("CREATE INDEX IF NOT EXISTS ix_contracts_property ON contracts (property);")


def downgrade() -> None:
    raise NotImplementedError("downgrade below 0005 is not supported: recreate the database")
