"""Initial schema: tables, views, read-only role.

Revision ID: 0001
Revises:
"""
from alembic import op

revision = "0001"
down_revision = None

# Amendment-overridable contract columns (liability_cap_multiple included: NULL = uncapped).
OVERRIDABLE = [
    "expiry_date", "notice_period_days", "auto_renew", "annual_value", "total_value",
    "payment_terms_days", "liability_cap_multiple", "liability_cap_text",
    "termination_for_convenience", "governing_law",
]


def _effective_terms_sql() -> str:
    selects, joins = [], []
    for f in OVERRIDABLE:
        selects.append(f"CASE WHEN o_{f}.src IS NOT NULL THEN a_{f}.{f} ELSE c.{f} END AS {f}")
        selects.append(f"COALESCE(o_{f}.src, c.id) AS {f}_source")
        joins.append(
            f"LEFT JOIN latest_override o_{f} ON o_{f}.parent_id = c.id AND o_{f}.field = '{f}' "
            f"LEFT JOIN contracts a_{f} ON a_{f}.id = o_{f}.src"
        )
    return f"""
CREATE VIEW v_effective_terms AS
SELECT t.*,
       -- Uncapped = a cap clause says "Unlimited". NDAs/SOWs/DPAs with no cap clause are NOT uncapped.
       (t.liability_cap_multiple IS NULL AND t.liability_cap_text ILIKE 'unlimited%') AS liability_uncapped
FROM (
WITH latest_override AS (
  SELECT DISTINCT ON (a.parent_id, f.field) a.parent_id, f.field, a.id AS src
  FROM contracts a CROSS JOIN LATERAL unnest(a.overrides) AS f(field)
  WHERE a.type = 'Amendment' AND a.parent_id IS NOT NULL
  ORDER BY a.parent_id, f.field, a.effective_date DESC, a.id DESC
)
SELECT c.id AS contract_id, c.title, c.vendor, c.effective_date, c.category, c.type, c.parent_id, c.status,
       c.currency, c.processes_personal_data, c.has_dpa, c.owner,
       {", ".join(selects)}
FROM contracts c
{" ".join(joins)}
WHERE c.type <> 'Amendment'
) t
"""


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("""
CREATE TABLE templates (
  id serial PRIMARY KEY, name text UNIQUE NOT NULL, type text NOT NULL,
  version text NOT NULL DEFAULT '1.0', body_md text NOT NULL);
CREATE TABLE template_clauses (
  id serial PRIMARY KEY, template_id int NOT NULL REFERENCES templates ON DELETE CASCADE,
  clause_type text NOT NULL, standard_text text NOT NULL, playbook_position text,
  fallback_text text, severity_if_missing text NOT NULL DEFAULT 'medium');
CREATE TABLE contracts (
  id serial PRIMARY KEY, title text NOT NULL, vendor text NOT NULL, category text,
  type text NOT NULL CHECK (type IN ('MSA','SOW','NDA','SaaS','DPA','Services','Amendment')),
  template_id int REFERENCES templates, parent_id int REFERENCES contracts,
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','expired','draft')),
  effective_date date, expiry_date date, notice_period_days int,
  auto_renew boolean NOT NULL DEFAULT false,
  annual_value numeric(16,2), total_value numeric(16,2), currency text NOT NULL DEFAULT 'INR',
  payment_terms_days int,
  liability_cap_multiple numeric(6,2),  -- NULL = uncapped
  liability_cap_text text, termination_for_convenience boolean, governing_law text,
  processes_personal_data boolean NOT NULL DEFAULT false, has_dpa boolean NOT NULL DEFAULT false,
  owner text, overrides text[] NOT NULL DEFAULT '{}', body_md text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now());
CREATE INDEX ix_contracts_parent ON contracts(parent_id);
CREATE TABLE clauses (
  id serial PRIMARY KEY, contract_id int NOT NULL REFERENCES contracts ON DELETE CASCADE,
  clause_type text NOT NULL, heading text, text text NOT NULL, page int,
  embedding vector(384));
CREATE INDEX ix_clauses_contract ON clauses(contract_id);
CREATE TABLE field_extractions (
  id serial PRIMARY KEY, contract_id int NOT NULL REFERENCES contracts ON DELETE CASCADE,
  field text NOT NULL, value text, confidence numeric(4,3),
  source_clause_id int REFERENCES clauses ON DELETE SET NULL, source_page int,
  UNIQUE (contract_id, field));
CREATE TABLE clause_deviations (
  id serial PRIMARY KEY, contract_id int NOT NULL REFERENCES contracts ON DELETE CASCADE,
  template_clause_id int NOT NULL REFERENCES template_clauses ON DELETE CASCADE,
  deviation_summary text NOT NULL, severity text NOT NULL);
CREATE TABLE drafts (
  id serial PRIMARY KEY, title text NOT NULL, vendor text NOT NULL,
  template_id int NOT NULL REFERENCES templates, body_md text NOT NULL);
CREATE TABLE redline_results (
  draft_id int PRIMARY KEY REFERENCES drafts ON DELETE CASCADE,
  items jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE llm_calls (
  id serial PRIMARY KEY, purpose text NOT NULL, prompt_hash text NOT NULL, model text NOT NULL,
  input_tokens int NOT NULL DEFAULT 0, output_tokens int NOT NULL DEFAULT 0,
  latency_ms int NOT NULL DEFAULT 0, created_at timestamptz NOT NULL DEFAULT now());
""")
    # Clause vector index is added in the seed pipeline (needs data); exact search is fine at POC scale.
    op.execute(_effective_terms_sql())
    op.execute("""
CREATE VIEW v_renewals AS
SELECT contract_id, title, vendor, category, type, annual_value, currency, auto_renew,
       expiry_date, notice_period_days, owner, liability_uncapped, termination_for_convenience,
       (expiry_date - COALESCE(notice_period_days, 0)) AS notice_deadline,
       (expiry_date - CURRENT_DATE) AS days_left,
       ((expiry_date - COALESCE(notice_period_days, 0)) - CURRENT_DATE) AS notice_days_left,
       -- Bucket by the date action is needed: notice deadline for auto-renewals, else expiry.
       CASE
         WHEN d < 0 THEN 'overdue'
         WHEN d <= 30 THEN '30'
         WHEN d <= 60 THEN '60'
         WHEN d <= 90 THEN '90'
         ELSE 'later'
       END AS bucket
FROM (
  SELECT e.*, CASE WHEN e.auto_renew
                   THEN (e.expiry_date - COALESCE(e.notice_period_days, 0)) - CURRENT_DATE
                   ELSE e.expiry_date - CURRENT_DATE END AS d
  FROM v_effective_terms e WHERE e.status = 'active' AND e.expiry_date IS NOT NULL
) x
""")
    # Read-only role for the Ask assistant's run_sql tool (POC credentials; local use only).
    op.execute("""
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'vmo_readonly') THEN
    CREATE ROLE vmo_readonly LOGIN PASSWORD 'vmo_readonly';
  END IF;
END $$;
GRANT USAGE ON SCHEMA public TO vmo_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO vmo_readonly;
REVOKE ALL ON llm_calls FROM vmo_readonly;
ALTER ROLE vmo_readonly SET statement_timeout = '5s';
ALTER ROLE vmo_readonly SET default_transaction_read_only = on;
""")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_renewals, v_effective_terms")
    op.execute("DROP TABLE IF EXISTS llm_calls, redline_results, drafts, clause_deviations, "
               "field_extractions, clauses, contracts, template_clauses, templates CASCADE")
    op.execute("REVOKE ALL ON SCHEMA public FROM vmo_readonly")
    op.execute("DROP ROLE IF EXISTS vmo_readonly")
