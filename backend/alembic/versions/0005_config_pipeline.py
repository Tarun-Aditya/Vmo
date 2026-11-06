"""Configurable KCC library / metrics / checklist, extracted values and check results, pipeline
tables, unified redlines (drafts become contracts with status='draft'), source tracking.

Revision ID: 0005
Revises: 0004
"""
from alembic import op

from app.viewsql import effective_terms_sql, key_clauses_sql, renewals_sql

revision = "0005"
down_revision = "0004"


def upgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_key_clauses, v_renewals, v_effective_terms, v_document_terms")
    op.execute("""
ALTER TABLE contracts
  ADD COLUMN source_path text, ADD COLUMN content_hash text, ADD COLUMN ingested_at timestamptz,
  ADD COLUMN origin text NOT NULL DEFAULT 'seed';
ALTER TABLE contracts ALTER COLUMN currency SET DEFAULT 'USD';
CREATE UNIQUE INDEX ix_contracts_source_path ON contracts(source_path) WHERE source_path IS NOT NULL;

CREATE TABLE kcc_library (
  key text PRIMARY KEY, name text NOT NULL, description text, category text,
  keywords text[] NOT NULL DEFAULT '{}', heading_aliases text[] NOT NULL DEFAULT '{}',
  standard_text text, playbook_position text, fallback_text text,
  severity_if_missing text NOT NULL DEFAULT 'medium', applies_to text[] NOT NULL DEFAULT '{}',
  in_matrix boolean NOT NULL DEFAULT true, enabled boolean NOT NULL DEFAULT true,
  sort_order int NOT NULL DEFAULT 0, builtin boolean NOT NULL DEFAULT false);
CREATE TABLE metrics (
  key text PRIMARY KEY, name text NOT NULL, description text, kcc_key text, pattern text NOT NULL,
  kind text NOT NULL DEFAULT 'number', unit text, scale numeric NOT NULL DEFAULT 1,
  enabled boolean NOT NULL DEFAULT true, builtin boolean NOT NULL DEFAULT false);
CREATE TABLE checklist_rules (
  key text PRIMARY KEY, name text NOT NULL, description text,
  rule_type text NOT NULL CHECK (rule_type IN ('clause_required','clause_forbidden','metric_threshold','text_forbidden')),
  kcc_key text, metric_key text, operator text, threshold numeric, threshold_text text, phrase text,
  severity text NOT NULL DEFAULT 'medium', applies_to text[] NOT NULL DEFAULT '{}',
  stage text NOT NULL DEFAULT 'any', suggested_text text, enabled boolean NOT NULL DEFAULT true,
  sort_order int NOT NULL DEFAULT 0, builtin boolean NOT NULL DEFAULT false);
CREATE TABLE extracted_values (
  id serial PRIMARY KEY, contract_id int NOT NULL REFERENCES contracts ON DELETE CASCADE,
  metric_key text NOT NULL, value_num numeric, value_text text,
  clause_id int REFERENCES clauses ON DELETE SET NULL, page int, confidence numeric(4,3),
  UNIQUE (contract_id, metric_key));
CREATE TABLE check_results (
  id serial PRIMARY KEY, contract_id int NOT NULL REFERENCES contracts ON DELETE CASCADE,
  rule_key text NOT NULL, status text NOT NULL, actual text, expected text, severity text,
  clause_id int REFERENCES clauses ON DELETE SET NULL, page int, excerpt text,
  UNIQUE (contract_id, rule_key));
CREATE TABLE pipeline_config (
  id int PRIMARY KEY DEFAULT 1 CHECK (id = 1), enabled boolean NOT NULL DEFAULT true,
  interval_minutes int NOT NULL DEFAULT 120, inbox_path text, last_run_at timestamptz, next_run_at timestamptz);
CREATE TABLE pipeline_runs (
  id serial PRIMARY KEY, started_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz,
  trigger text NOT NULL, status text NOT NULL DEFAULT 'running', scanned int NOT NULL DEFAULT 0,
  new_docs int NOT NULL DEFAULT 0, updated int NOT NULL DEFAULT 0, unchanged int NOT NULL DEFAULT 0,
  failed int NOT NULL DEFAULT 0, message text);
CREATE TABLE pipeline_events (
  id serial PRIMARY KEY, run_id int NOT NULL REFERENCES pipeline_runs ON DELETE CASCADE,
  path text, contract_id int, action text NOT NULL, detail text, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE redlines (
  contract_id int PRIMARY KEY REFERENCES contracts ON DELETE CASCADE, items jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now());
DROP TABLE IF EXISTS redline_results, drafts CASCADE;
""")
    op.execute(effective_terms_sql())
    op.execute(effective_terms_sql("v_document_terms", drafts=True))  # includes drafts (scoped Ask)
    op.execute(renewals_sql())
    op.execute(key_clauses_sql())
    op.execute("""
CREATE VIEW v_values AS
SELECT ev.contract_id, c.title, c.vendor, c.type, c.status, ev.metric_key, m.name AS metric, m.unit,
       ev.value_num, ev.value_text, ev.page
FROM extracted_values ev JOIN contracts c ON c.id = ev.contract_id JOIN metrics m ON m.key = ev.metric_key;
CREATE VIEW v_checks AS
SELECT cr.contract_id, c.title, c.vendor, c.type, c.status, cr.rule_key, r.name AS rule, cr.status AS result,
       cr.severity, cr.actual, cr.expected, cr.page
FROM check_results cr JOIN contracts c ON c.id = cr.contract_id JOIN checklist_rules r ON r.key = cr.rule_key;
GRANT SELECT ON v_effective_terms, v_document_terms, v_renewals, v_key_clauses, v_values, v_checks, kcc_library, metrics,
  checklist_rules, extracted_values, check_results TO vmo_readonly;
""")


def downgrade() -> None:
    raise NotImplementedError("downgrade below 0005 is not supported: recreate the database")
