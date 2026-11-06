Tables and views (PostgreSQL). Prefer the VIEWS for any question about current terms or dates.

v_effective_terms  -- one row per non-amendment contract, with amendments already applied.
  contract_id, title, vendor, category, type, parent_id, status, currency, owner, effective_date,
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
  metric, unit, value_num, value_text, page. metric_key values: payment_terms_days, liability_cap_multiple, tfc_notice_days,
  renewal_notice_days, insurance_cover_usd, warranty_days, confidentiality_years, sla_availability_pct, incident_notice_hours,
  breach_notice_hours, cure_period_days, key_personnel_replacement_days, acceptance_days, audit_notice_days,
  force_majeure_termination_days, governing_law_text. USE THIS for any threshold question ("shorter than", "below", "at least",
  "more than") on those numbers, e.g. `WHERE metric_key='confidentiality_years' AND value_num < 3`.
v_checks  -- pre-signature checklist results, one row per (document, rule): contract_id, title, vendor, type, status, rule_key, rule,
  result ('pass'|'fail'|'na'), severity (low|medium|high|critical), actual, expected, page. Use it for "which contracts fail ...".
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
