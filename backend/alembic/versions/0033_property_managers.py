"""Property managers: a user (and an alert channel) can be limited to one property; alerts record the properties they concern; service calls at a property
with their response times; supplier contacts per vendor and property.

Revision ID: 0033
Revises: 0032
"""
from alembic import op

revision = "0033"
down_revision = "0032"


def upgrade() -> None:
    op.execute("""
ALTER TABLE users ADD COLUMN IF NOT EXISTS property text;              -- NULL = every property
ALTER TABLE alert_channels ADD COLUMN IF NOT EXISTS property text;     -- NULL = every property
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS properties text[] NOT NULL DEFAULT '{}';     -- empty = group-wide
CREATE INDEX IF NOT EXISTS ix_alerts_properties ON alerts USING gin (properties);

CREATE TABLE IF NOT EXISTS service_events (
  id serial PRIMARY KEY,
  property text NOT NULL,
  vendor text NOT NULL,
  contract_id integer REFERENCES contracts(id) ON DELETE SET NULL,
  kind text NOT NULL DEFAULT 'fault' CHECK (kind IN ('fault', 'emergency', 'request', 'planned')),
  description text,
  reported_at timestamptz NOT NULL,
  attended_at timestamptz,
  resolved_at timestamptz,
  reported_by text,
  source text NOT NULL DEFAULT 'person',
  external_id text UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_service_events_property ON service_events (property, reported_at DESC);

CREATE TABLE IF NOT EXISTS vendor_contacts (
  id serial PRIMARY KEY,
  vendor text NOT NULL,
  property text,                        -- NULL = the vendor's contact for every property
  name text NOT NULL,
  role text,
  phone text,
  email text,
  note text,
  source text NOT NULL DEFAULT 'person',
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_vendor_contacts_vendor ON vendor_contacts (vendor);
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS owner text;        -- who asked (a property-limited account sees its own conversations only)
GRANT SELECT ON service_events, vendor_contacts TO vmo_readonly;
""")


def downgrade() -> None:
    raise NotImplementedError("downgrade below 0005 is not supported: recreate the database")
