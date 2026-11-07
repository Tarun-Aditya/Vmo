"""More connector types (mailbox, REST / Coupa / SAP / Ariba) and a 'feeds' target (invoice and report documents / rows go to the feeds pipeline).

Revision ID: 0020
Revises: 0019
"""
from alembic import op

revision = "0020"
down_revision = "0019"


def upgrade() -> None:
    op.execute("""
ALTER TABLE connectors DROP CONSTRAINT IF EXISTS connectors_type_check;
ALTER TABLE connectors ADD CONSTRAINT connectors_type_check CHECK (type IN ('gdrive','onedrive','sharepoint','imap','rest','coupa','sap','ariba'));
ALTER TABLE connectors DROP CONSTRAINT IF EXISTS connectors_target_check;
ALTER TABLE connectors ADD CONSTRAINT connectors_target_check CHECK (target IN ('contracts','drafts','feeds'));
""")


def downgrade() -> None:
    raise NotImplementedError("downgrade below 0005 is not supported: recreate the database")
