"""Everything the VMO features used to hardcode becomes configuration: obligation rules, thresholds (spend checks, risk points and tiers, SLA credit tiers),
and per-metric direction / SLA flags.

Revision ID: 0011
Revises: 0010
"""
from alembic import op

revision = "0011"
down_revision = "0010"


def upgrade() -> None:
    op.execute("""
CREATE TABLE obligation_rules (
  key text PRIMARY KEY, name text NOT NULL, metric_key text, kind text NOT NULL, party text NOT NULL DEFAULT 'Supplier', title_template text NOT NULL,
  frequency text NOT NULL DEFAULT 'event', unit text, annual boolean NOT NULL DEFAULT false, enabled boolean NOT NULL DEFAULT true, builtin boolean NOT NULL DEFAULT false, sort_order int NOT NULL DEFAULT 0);
CREATE TABLE config_items (
  grp text NOT NULL, key text NOT NULL, label text NOT NULL, description text, value jsonb NOT NULL, kind text NOT NULL DEFAULT 'number', sort_order int NOT NULL DEFAULT 0,
  PRIMARY KEY (grp, key));
ALTER TABLE metrics ADD COLUMN better text CHECK (better IN ('higher','lower')), ADD COLUMN sla boolean NOT NULL DEFAULT false;
""")


def downgrade() -> None:
    raise NotImplementedError("downgrade below 0005 is not supported: recreate the database")
