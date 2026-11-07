"""Security: MFA (TOTP + recovery codes), login lockout counters.

Revision ID: 0021
Revises: 0020
"""
from alembic import op

revision = "0021"
down_revision = "0020"


def upgrade() -> None:
    op.execute("""
ALTER TABLE users ADD COLUMN mfa_secret_enc text, ADD COLUMN mfa_enabled boolean NOT NULL DEFAULT false, ADD COLUMN recovery_hashes text[] NOT NULL DEFAULT '{}',
  ADD COLUMN failed_logins int NOT NULL DEFAULT 0, ADD COLUMN locked_until timestamptz, ADD COLUMN external_id text;
""")


def downgrade() -> None:
    raise NotImplementedError("downgrade below 0005 is not supported: recreate the database")
