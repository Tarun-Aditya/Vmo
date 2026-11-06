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
v_renewals  -- active contracts with renewal maths. Columns: contract_id, title, vendor, category, type,
  annual_value, auto_renew, expiry_date, notice_period_days, owner, liability_uncapped,
  termination_for_convenience, notice_deadline (= expiry_date - notice_period_days; equals expiry when
  there is no notice period), days_left (to expiry), notice_days_left (to notice_deadline; negative =
  deadline passed), bucket ('overdue' | '30' | '60' | '90' | 'later') based on notice_deadline for
  auto-renewals and expiry_date otherwise.
contracts  -- raw rows incl. Amendment rows (type='Amendment', parent_id -> amended contract; the columns
  an amendment changes are listed in `overrides`). Raw values are NOT amendment-adjusted.
template_clauses(id, template_id, clause_type, standard_text, playbook_position, fallback_text,
  severity_if_missing); templates(id, name, type)
clause_deviations(contract_id, template_clause_id, deviation_summary, severity)  -- where an executed
  contract departs from its standard template (severity: low|medium|high|critical)
clauses(id, contract_id, clause_type, heading, text, page)  -- clause text of every contract
field_extractions(contract_id, field, value, confidence, source_clause_id, source_page)

Notes: all money is INR (1 lakh = 100,000; 1 crore = 10,000,000). MSAs carry no annual_value (their SOWs do),
so summing annual_value never double counts. contract `type` values: MSA, SOW, NDA, SaaS, DPA, Amendment.
clause_type values include: term, renewal, payment, termination_for_convenience, termination_for_cause,
liability_cap, indemnity, ip_ownership, confidentiality, data_protection, audit_rights, assignment,
non_solicit, governing_law, sla, security, data_return, acceptance, subprocessors, breach_notification,
cross_border. Do not SELECT the embedding column (not permitted).
