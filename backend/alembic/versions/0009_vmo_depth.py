"""VMO depth: obligations & SLA tracking, invoices and spend exceptions, vendor risk scores (configurable weights).

Revision ID: 0009
Revises: 0008
"""
from alembic import op

revision = "0009"
down_revision = "0008"


def upgrade() -> None:
    op.execute("""
CREATE TABLE obligations (
  id serial PRIMARY KEY, contract_id int NOT NULL REFERENCES contracts ON DELETE CASCADE,
  key text NOT NULL, kind text NOT NULL, party text NOT NULL DEFAULT 'Supplier', title text NOT NULL, detail text,
  due_date date, frequency text NOT NULL DEFAULT 'once', target_value numeric, target_unit text, metric_key text,
  clause_type text, page int, source text NOT NULL DEFAULT 'rule',
  status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','done','waived')), completed_on date, note text,
  updated_at timestamptz NOT NULL DEFAULT now(), UNIQUE (contract_id, key));
CREATE INDEX ix_obligations_due ON obligations (due_date);

CREATE TABLE invoices (
  id serial PRIMARY KEY, external_id text NOT NULL UNIQUE, vendor text NOT NULL, contract_id int REFERENCES contracts ON DELETE SET NULL,
  contract_ref text, invoice_no text, invoice_date date NOT NULL, period_start date, period_end date, due_date date, paid_date date,
  amount numeric NOT NULL, currency text NOT NULL DEFAULT 'USD', description text, category text, source text NOT NULL DEFAULT 'feed');
CREATE INDEX ix_invoices_contract ON invoices (contract_id);
CREATE INDEX ix_invoices_vendor ON invoices (vendor);

CREATE TABLE spend_exceptions (
  id serial PRIMARY KEY, invoice_id int REFERENCES invoices ON DELETE CASCADE, contract_id int REFERENCES contracts ON DELETE CASCADE,
  vendor text NOT NULL, kind text NOT NULL, severity text NOT NULL, amount_at_risk numeric NOT NULL DEFAULT 0, detail text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now());

CREATE TABLE sla_measurements (
  id serial PRIMARY KEY, contract_id int NOT NULL REFERENCES contracts ON DELETE CASCADE, metric_key text NOT NULL,
  period date NOT NULL, actual numeric NOT NULL, incidents int NOT NULL DEFAULT 0, note text, source text NOT NULL DEFAULT 'feed',
  UNIQUE (contract_id, metric_key, period));

CREATE TABLE risk_weights (
  key text PRIMARY KEY, label text NOT NULL, description text, weight numeric NOT NULL, enabled boolean NOT NULL DEFAULT true, sort_order int NOT NULL DEFAULT 0);
INSERT INTO risk_weights (key, label, description, weight, sort_order) VALUES
 ('contract_risk','Contract terms','Uncapped liability, no termination for convenience, personal data without a DPA, unsigned documents, failing checklist rules',30,1),
 ('renewal_exposure','Renewal exposure','Auto-renewals whose notice deadline has passed or is near; contract value expiring in 90 days',15,2),
 ('performance','Performance','SLA breaches in the last 6 months and overdue obligations',20,3),
 ('spend_compliance','Spend compliance','Invoices without a contract, over budget, duplicates, late payment',20,4),
 ('concentration','Concentration','Share of the portfolio value held by one vendor',15,5);

INSERT INTO pipeline_config (id, key, name, description, folders, trigger_mode, interval_minutes) VALUES
 (3, 'feeds', 'Operational feeds', 'Invoices (ERP / AP export), SLA measurements and obligation status updates dropped as CSV in the feeds folder: load, match to contracts, check spend, refresh vendor risk scores.', 'feeds', 'on_change', 60)
 ON CONFLICT DO NOTHING;

CREATE TABLE vendor_scores (
  vendor text PRIMARY KEY, score numeric NOT NULL, tier text NOT NULL, components jsonb NOT NULL, computed_at timestamptz NOT NULL DEFAULT now());

CREATE VIEW v_obligations AS
SELECT o.id AS obligation_id, o.contract_id, c.title, c.vendor, c.type, c.status AS contract_status, o.kind, o.party, o.title AS obligation,
       o.detail, o.due_date, o.frequency, o.target_value, o.target_unit, o.metric_key, o.source,
       CASE WHEN o.status = 'open' AND o.due_date < CURRENT_DATE THEN 'overdue' ELSE o.status END AS status,
       o.completed_on, (o.due_date - CURRENT_DATE) AS days_left
FROM obligations o JOIN contracts c ON c.id = o.contract_id;

CREATE VIEW v_invoices AS
SELECT i.id AS invoice_id, i.external_id, i.vendor, i.contract_id, c.title AS contract_title, i.invoice_no, i.invoice_date, i.period_start, i.period_end,
       i.due_date, i.paid_date, i.amount, i.description, i.category,
       CASE WHEN i.paid_date IS NOT NULL THEN GREATEST(i.paid_date - i.due_date, 0) END AS days_paid_late
FROM invoices i LEFT JOIN contracts c ON c.id = i.contract_id;

CREATE VIEW v_contract_spend AS
WITH base AS (
  SELECT t.contract_id, t.title, t.vendor, t.type, t.category, t.effective_date, t.expiry_date, t.annual_value, t.total_value,
         CASE WHEN t.annual_value IS NOT NULL THEN t.annual_value * (t.expiry_date - t.effective_date) / 365.0 ELSE t.total_value END AS planned_value
  FROM v_effective_terms t WHERE t.status <> 'draft' AND (t.annual_value IS NOT NULL OR t.total_value IS NOT NULL)),
b AS (SELECT contract_id, sum(amount) AS billed, count(*) AS invoices, max(invoice_date) AS last_invoice FROM invoices WHERE contract_id IS NOT NULL GROUP BY 1)
SELECT base.*, COALESCE(b.billed, 0) AS billed, COALESCE(b.invoices, 0) AS invoices, b.last_invoice,
       LEAST(1, GREATEST(0, (CURRENT_DATE - base.effective_date)::numeric / NULLIF(base.expiry_date - base.effective_date, 0))) AS elapsed_pct,
       base.planned_value * LEAST(1, GREATEST(0, (CURRENT_DATE - base.effective_date)::numeric / NULLIF(base.expiry_date - base.effective_date, 0))) AS expected_to_date,
       COALESCE(b.billed, 0) / NULLIF(base.planned_value, 0) AS pct_of_planned
FROM base LEFT JOIN b USING (contract_id);

CREATE VIEW v_spend_exceptions AS
SELECT e.id AS exception_id, e.kind, e.severity, e.amount_at_risk, e.detail, e.vendor, e.contract_id, c.title AS contract_title,
       i.invoice_no, i.invoice_date, i.amount AS invoice_amount
FROM spend_exceptions e LEFT JOIN invoices i ON i.id = e.invoice_id LEFT JOIN contracts c ON c.id = e.contract_id;

CREATE VIEW v_sla AS
SELECT m.contract_id, c.title, c.vendor, m.metric_key, m.period, m.actual, v.value_num AS target, m.incidents,
       CASE WHEN m.metric_key = 'sla_availability_pct' THEN m.actual < v.value_num ELSE m.actual > v.value_num END AS breach,
       CASE WHEN m.metric_key = 'sla_availability_pct' THEN GREATEST(v.value_num - m.actual, 0) ELSE GREATEST(m.actual - v.value_num, 0) END AS shortfall
FROM sla_measurements m JOIN contracts c ON c.id = m.contract_id
LEFT JOIN extracted_values v ON v.contract_id = m.contract_id AND v.metric_key = m.metric_key;

CREATE VIEW v_vendor_scores AS
SELECT vendor, score, tier, computed_at,
       (components->'contract_risk'->>'score')::numeric AS contract_risk, (components->'renewal_exposure'->>'score')::numeric AS renewal_exposure,
       (components->'performance'->>'score')::numeric AS performance, (components->'spend_compliance'->>'score')::numeric AS spend_compliance,
       (components->'concentration'->>'score')::numeric AS concentration
FROM vendor_scores;

GRANT SELECT ON v_obligations, v_invoices, v_contract_spend, v_spend_exceptions, v_sla, v_vendor_scores TO vmo_readonly;
""")


def downgrade() -> None:
    raise NotImplementedError("downgrade below 0005 is not supported: recreate the database")
