Tables and views (PostgreSQL). Prefer the VIEWS for any question about current terms or dates.

v_effective_terms  -- one row per non-amendment contract, with amendments already applied.
  contract_id, title, vendor, category, type, parent_id, status, currency, owner, property, effective_date,
  expiry_date, notice_period_days, auto_renew, annual_value, total_value, payment_terms_days,
  liability_cap_multiple, liability_cap_text, termination_for_convenience, governing_law,
  processes_personal_data, has_dpa,
  liability_uncapped  -- true only when the contract states liability is unlimited (use this, NOT
                         "liability_cap_multiple IS NULL": NDAs/SOWs/DPAs have no cap clause)
  <field>_source      -- contract id whose text set the effective value of <field> (the contract
                         itself, or the latest amendment that overrode it); join contracts for its title.
  Also: customer_signatory, customer_signed_date, supplier_signatory, supplier_signed_date, fully_executed
  (true only when both parties signed; false = e.g. supplier countersignature pending).
v_key_clauses  -- one row per non-amendment contract (join USING (contract_id)) with a boolean per key clause:
  has_term, has_renewal, has_payment, has_termination_for_convenience, has_termination_for_cause,
  has_liability_cap, has_indemnity, has_ip_ownership, has_confidentiality, has_data_protection,
  has_audit_rights, has_assignment, has_non_solicit, has_governing_law, has_sla, has_security,
  has_data_return, has_order_of_precedence, has_warranties, has_insurance, has_force_majeure,
  has_dispute_resolution, has_execution (= fully signed). false = the clause is absent from that document.
v_renewals  -- active contracts with renewal maths. Columns: contract_id, title, vendor, category, type,
  annual_value, auto_renew, expiry_date, notice_period_days, owner, liability_uncapped,
  termination_for_convenience, notice_deadline (= expiry_date - notice_period_days; equals expiry when
  there is no notice period), days_left (to expiry), notice_days_left (to notice_deadline; negative =
  deadline passed), bucket ('overdue' | '30' | '60' | '90' | 'later') based on notice_deadline for
  auto-renewals and expiry_date otherwise.
v_document_terms  -- same columns as v_effective_terms but INCLUDING vendor drafts (status='draft'). Use it for questions about
  drafts or about specific selected documents.
v_values  -- extracted terms & limits, one row per (document, metric): contract_id, title, vendor, type, status, metric_key,
  metric, unit, value_num, value_text, page. metric_key values are the rows of the `metrics` table (key, name, unit; configured in Admin → Values & limits): SELECT key, name, unit FROM metrics to see them. USE THIS for any threshold question ("shorter than", "below", "at least",
  "more than") on those numbers, e.g. `WHERE metric_key='confidentiality_years' AND value_num < 3`.
v_checks  -- pre-signature checklist results, one row per (document, rule): contract_id, title, vendor, type, status, rule_key, rule,
  result ('pass'|'fail'|'na'), severity (low|medium|high|critical), actual, expected, page. Use it for "which contracts fail ...".
v_obligations  -- what each party must do: obligation_id, contract_id, title (contract), vendor, type, contract_status, kind (milestone | sla | notice |
  payment | acceptance | personnel | cure | audit | renewal | warranty | insurance | reporting | security | certificate | governance | delivery | other), party
  (Supplier | Customer | Both), obligation (text), due_date, frequency, target_value, target_unit, status ('open' | 'overdue' | 'done' | 'waived'; overdue =
  open and past due_date), completed_on, days_left. Exclude drafts with contract_status <> 'draft'.
v_invoices  -- invoices from the AP feed: invoice_id, vendor, contract_id (NULL = no contract matched), contract_title, invoice_no, invoice_date, due_date,
  paid_date, amount, description, days_paid_late.
v_contract_spend  -- per contract with a value: contract_id, title, vendor, type, planned_value (value over the term), billed, invoices, expected_to_date,
  pct_of_planned (billed / planned_value), elapsed_pct (share of the term gone).
v_spend_exceptions  -- invoices/contracts that break a rule: exception_id, kind (no_contract | unsigned_contract | billed_before_effective | billed_after_expiry |
  duplicate | above_run_rate | over_contract_value | late_payment), severity, amount_at_risk, detail, vendor, contract_id, contract_title, invoice_no, invoice_date,
  invoice_amount. "Spend with vendors that have no contract on file" = SUM(invoice_amount) WHERE kind = 'no_contract'.
v_sla  -- monthly SLA actuals vs the contract target: contract_id, title, vendor, metric_key (any SLA metric in the `metrics` table: sla = true), period (month start),
  actual, target, breach (true when the target was missed), shortfall, incidents.
v_sla_credit  -- v_sla plus credit_usd: the estimated service credit for a breached month (tier share of the monthly fee, tiers from Admin → Thresholds). SUM(credit_usd) = 'service credits'.
v_vendor_scores  -- vendor risk (0-100, higher = riskier): vendor, score, tier (low | medium | high | critical), contract_risk, renewal_exposure, performance,
  spend_compliance, concentration (each 0-100).
v_alerts  -- the notification centre: alert_id, rule_key, title, body, severity (low|medium|high|critical), status ('open' | 'acknowledged' | 'resolved'), vendor, contract_id, created_at.
v_reviews  -- the vendor-draft review queue (one row per draft): contract_id, title, vendor, type, review_status ('pending' | 'in_review' | 'changes_requested' | 'approved'),
  assignee, due_date, reviewer, deviations (changes vs the standard template), checks_failed (checklist rules failed), days_waiting.
v_deviations  -- where documents depart from their standard template, one row per (document, clause): contract_id, title, vendor, type, status, template, clause_type, severity, deviation_summary.
Benchmarks (median / min / max of a term across the portfolio): aggregate v_values, e.g. percentile_cont(0.5) WITHIN GROUP (ORDER BY value_num) WHERE metric_key = '...' AND status <> 'draft'.
Templates: `templates` (name, type) and `template_clauses` (the clauses of each standard template).
contracts  -- raw rows incl. Amendment rows (type='Amendment', parent_id -> amended contract; the columns
  an amendment changes are listed in `overrides`). Raw values are NOT amendment-adjusted.
template_clauses(id, template_id, clause_type, standard_text, playbook_position, fallback_text,
  severity_if_missing); templates(id, name, type)
clause_deviations(contract_id, template_clause_id, deviation_summary, severity)  -- where an executed
  contract departs from its standard template (severity: low|medium|high|critical)
clauses(id, contract_id, clause_type, heading, text, page)  -- clause text of every contract
field_extractions(contract_id, field, value, confidence, source_clause_id, source_page)

Meaning of flags: termination_for_convenience is true (customer may terminate without cause), false (the contract bars it) or NULL
(not addressed, e.g. NDAs). "Cannot be terminated for convenience" means = false only. has_dpa is true when a signed DPA covers the
vendor (a DPA document for the same vendor, or one referenced by the contract). A SaaS vendor "without a DPA" has
processes_personal_data AND NOT has_dpa. When asked what a clause SAYS, also call search_clauses (use the vendor / clause_type
filters) so the wording is cited, in addition to any SQL.

Notes: all money is USD. MSAs carry no annual_value (their SOWs do),
so summing annual_value never double counts; Work Orders carry total_value only (fixed fee). Hierarchy: MSA ->
SOW -> Work Order via parent_id; amendments, NDAs and DPAs also point at their parent. contract `type` values: MSA,
SOW, Work Order, NDA, SaaS, DPA, Amendment.
clause_type values include: term, renewal, payment, termination_for_convenience, termination_for_cause,
liability_cap, indemnity, ip_ownership, confidentiality, data_protection, audit_rights, assignment,
non_solicit, governing_law, sla, security, data_return, acceptance, subprocessors, breach_notification,
cross_border, execution. Do not SELECT the embedding column (not permitted).
