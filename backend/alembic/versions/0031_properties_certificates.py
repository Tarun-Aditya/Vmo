"""Properties as records (rooms, city, kind), which contracts cover which property, and compliance certificates with their own expiry dates.

Revision ID: 0031
Revises: 0030
"""
from alembic import op

revision = "0031"
down_revision = "0030"


def upgrade() -> None:
    op.execute("""
CREATE TABLE IF NOT EXISTS properties (
  id serial PRIMARY KEY, name text NOT NULL UNIQUE, city text, country text, kind text, rooms integer, opened_year integer,
  created_at timestamptz NOT NULL DEFAULT now()
);
-- an explicit statement that a group-level agreement covers a property (when absent, coverage is derived: see v_property_contracts)
CREATE TABLE IF NOT EXISTS contract_coverage (
  contract_id integer NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
  property_id integer NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  PRIMARY KEY (contract_id, property_id)
);
CREATE TABLE IF NOT EXISTS certificates (
  id serial PRIMARY KEY, vendor text NOT NULL, kind text NOT NULL, name text NOT NULL,
  contract_id integer REFERENCES contracts(id) ON DELETE SET NULL, clause_type text, page integer,
  expiry_date date, received_on date, reference text, note text, source text NOT NULL DEFAULT 'derived',
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (vendor, kind)
);
DROP VIEW IF EXISTS v_property_contracts;
-- One row per (property, contract that applies there). basis: 'named' = the document names the property; 'stated' = coverage recorded by a person;
-- 'children' = a group agreement whose schedules name the property; 'group' = a group agreement with no schedules, taken to cover every property.
-- share = the part of the contract's yearly value attributed to the property (by rooms where known, else equally).
CREATE VIEW v_property_contracts AS
WITH base AS (
  SELECT c.id AS contract_id, c.vendor, c.category, c.type, c.title, c.property, c.parent_id,
         COALESCE(e.annual_value, c.annual_value) AS annual_value, COALESCE(e.expiry_date, c.expiry_date) AS expiry_date
  FROM contracts c LEFT JOIN v_effective_terms e ON e.contract_id = c.id
  WHERE c.status <> 'draft' AND c.type NOT IN ('Amendment', 'NDA', 'DPA')
), cover AS (
  SELECT b.contract_id, p.id AS property_id, 'named' AS basis FROM base b JOIN properties p ON p.name = b.property
  UNION ALL
  SELECT b.contract_id, cc.property_id, 'stated' FROM base b JOIN contract_coverage cc ON cc.contract_id = b.contract_id WHERE b.property IS NULL
  UNION ALL
  SELECT DISTINCT b.contract_id, p.id, 'children' FROM base b JOIN contracts ch ON ch.parent_id = b.contract_id AND ch.status <> 'draft' JOIN properties p ON p.name = ch.property
  WHERE b.property IS NULL AND NOT EXISTS (SELECT 1 FROM contract_coverage cc WHERE cc.contract_id = b.contract_id)
  UNION ALL
  SELECT b.contract_id, p.id, 'group' FROM base b CROSS JOIN properties p
  WHERE b.property IS NULL AND NOT EXISTS (SELECT 1 FROM contract_coverage cc WHERE cc.contract_id = b.contract_id)
    AND NOT EXISTS (SELECT 1 FROM contracts ch JOIN properties p2 ON p2.name = ch.property WHERE ch.parent_id = b.contract_id AND ch.status <> 'draft')
)
SELECT p.id AS property_id, p.name AS property, p.rooms, b.contract_id, b.title, b.vendor, b.category, b.type, b.expiry_date, k.basis,
       b.annual_value AS contract_annual_value,
       CASE WHEN k.basis = 'named' THEN 1.0
            WHEN bool_and(p.rooms IS NOT NULL) OVER w THEN p.rooms::numeric / NULLIF(sum(p.rooms) OVER w, 0)
            ELSE 1.0 / count(*) OVER w END AS share
FROM cover k JOIN base b USING (contract_id) JOIN properties p ON p.id = k.property_id
WINDOW w AS (PARTITION BY b.contract_id);
GRANT SELECT ON properties, contract_coverage, certificates, v_property_contracts TO vmo_readonly;
""")


def downgrade() -> None:
    raise NotImplementedError("downgrade below 0005 is not supported: recreate the database")
