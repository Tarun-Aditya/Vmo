# CLAUDE.md: VMO Contract AI (POC)

Working name: **ContractIQ**. Change it freely.

## 1. Context

- I'm building a product for **Vendor Management Offices (VMOs)**: the internal teams that manage an enterprise's vendor contracts, renewals, spend and risk.
- This repo is the **POC**. Its only job is a reliable 5–10 minute **live demo** that shows every feature.
- I'm solo. **You (Claude Code) write the code; I review and test.** Stop at the end of each phase for my review.
- The full product (upload, multi-tenant, SSO, integrations) comes later. Don't build it now, but don't paint us into a corner either.

### Why this product
Commercial CLMs (Icertis, Ironclad, SirionLabs) are expensive, slow to implement, and built for legal teams. VMOs care about **renewals, spend, SLA and risk across the whole vendor portfolio**. Our edge: *"Ask any question about your vendor portfolio"*. Structured SQL-style questions and clause questions both work, with answers you can verify.

## 2. POC scope

The POC works over a **fixed, preloaded set of 28 documents**.
**There is no upload, no creating new templates and no creating new documents in the POC.** All AI extraction runs **once at seed time**, so the demo reads from the DB and is fast and deterministic on stage.

### Features (all over the preloaded set)
1. **Contract repository**: list with filters (vendor, category, type, owner, status) and a detail view. Extracted fields sit beside the document text, and clicking a field highlights its source passage. Each field shows a confidence badge.
2. **Renewal dashboard**: KPI tiles (contracts, annual value, expiring in 90 days, auto-renewals with notice deadlines soon, uncapped liability). A timeline/list of upcoming **notice deadlines** (expiry minus notice period), not just expiry dates. 30/60/90-day buckets with value at stake. Severity chips.
3. **Ask assistant**: plain-English questions over the whole portfolio.
   - Structured questions → **text-to-SQL**. Always show the generated SQL and the result table.
   - Clause questions → **semantic search over clauses** (pgvector). Answers cite contract + clause + page.
   - A **router** (an LLM tool-use loop) picks SQL, clause search, or both.
4. **Redline**: pick one of the preloaded vendor drafts, compare it to its standard template + playbook, and list deviations with severity, our standard position and suggested wording. Render it as a redline view (strikethrough original, inserted suggestion).
5. **Template library**: browse the 5 standard templates clause by clause. For each template, show which executed contracts deviate and where (a clause-level deviation heatmap or list).
6. **Contract hierarchy**: MSA → SOWs → amendments. An amendment overrides earlier terms, and the "effective terms" view shows the current values with provenance.

### Out of scope (later version)
Upload, OCR, new templates/documents, auth/SSO, multi-tenancy, email/Teams alerts, ERP/procurement integrations, Word tracked-changes export, billing.

## 3. Preloaded document set (28 docs, all fictional)

All company and vendor names are **fictional**. Don't use real company names or real contract text.
Our fictional customer: **"Arcadia Retail Ltd"** (India HQ, INR values).

- **5 standard templates**: MSA, SOW, NDA, SaaS Subscription, DPA (Data Processing Agreement).
- **18 executed contracts** derived from the templates:
  - 2 MSAs, each with 2–3 SOWs and 1 amendment (shows the parent/child + amendment-override logic)
  - 4 SaaS, 3 NDAs, 2 DPAs, the rest services
  - Expiries relative to the seed date: 4 within 30 days, 4 in 31–90 days, the rest over 12 months
  - 5 auto-renewals, 2 of them with notice deadlines already close or passed
  - Planted risks: 3 uncapped liability, 2 with no termination for convenience, 1 SaaS vendor processing personal data with **no DPA**
  - Spread across categories: IT Services, SaaS, Facilities, Logistics, Staffing, Telecom, Security, Marketing
- **5 vendor drafts** for redlining, each with 3–6 planted deviations from its template. One draft is clean (the control).

Store the source docs as Markdown (or DOCX/PDF generated from Markdown) under `data/docs/`, with page markers so citations can show page numbers.

**Ground truth:** `data/labels.json` holds the correct fields for every executed contract and the planted deviations for every draft. The eval scripts score against it.

**Dates:** generate dates **relative to the seed run date** so the dashboard always looks current.

## 4. Tech stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2 + Alembic, Pydantic v2
- **DB:** Postgres 16 + pgvector (structured fields and clause embeddings in one DB)
- **AI:** Anthropic API (Claude) for extraction, routing, SQL generation, answers and redlining. Embeddings via a hosted embedding API or a local sentence-transformers model, configurable.
- **Frontend:** React + Vite + TypeScript + Tailwind, TanStack Query, Recharts for charts
- **Run:** Docker Compose (`db`, `api`, `web`). `make seed`, `make eval`, `make dev`.
- **Config:** `.env` (`ANTHROPIC_API_KEY`, `DATABASE_URL`, model names). Never commit secrets.

## 5. Data model (starting point)

```
templates(id, name, type, version, body_md)
template_clauses(id, template_id, clause_type, standard_text, playbook_position, fallback_text, severity_if_missing)

contracts(id, title, vendor, category, type[MSA|SOW|NDA|SaaS|DPA|Services|Amendment],
          template_id, parent_id, status[active|expired|draft],
          effective_date, expiry_date, notice_period_days, auto_renew,
          annual_value, total_value, currency, payment_terms_days,
          liability_cap_multiple NULL,  -- NULL = uncapped
          liability_cap_text, termination_for_convenience, governing_law,
          processes_personal_data, has_dpa, owner, body_md, created_at)

field_extractions(contract_id, field, value, confidence, source_clause_id, source_page)
clauses(id, contract_id, clause_type, text, page, embedding vector)
clause_deviations(contract_id, template_clause_id, deviation_summary, severity)

drafts(id, title, vendor, template_id, body_md)
redline_results(draft_id, items jsonb, created_at)   -- cached for demo reliability

v_effective_terms  -- view applying amendments over the parent contract
v_renewals         -- view: notice_deadline = expiry_date - notice_period_days, days_left, bucket
```

Use the **CUAD clause taxonomy** as the reference for `clause_type` values (term, renewal, termination for convenience, cap on liability, uncapped liability, indemnity, IP ownership, confidentiality, governing law, payment, SLA, audit rights, data protection, assignment, non-solicit, and so on).

## 6. Architecture notes

- **Seed pipeline** (`scripts/seed.py`): generate docs → parse → split into clauses → LLM extracts fields as structured JSON (forced tool call / JSON schema) with confidence + source clause → embed clauses → compute template deviations → precompute redlines for the 5 drafts → load the DB. It must be idempotent.
- **Ask assistant**: a Claude tool-use loop with tools:
  - `run_sql(query)`: SELECT-only, executed as a **read-only Postgres role**, with `statement_timeout` and an auto `LIMIT 200`. Schema + view descriptions + sample values go in the system prompt.
  - `search_clauses(query, clause_type?, vendor?, top_k)`: pgvector search
  - `get_contract(id)`: fields + effective terms
  - Return the final answer + every tool call (SQL, rows, citations) so the UI can show its work.
  - On a SQL error, feed the error back once and retry.
- **Redline**: clause-align the draft to its template → per-clause LLM comparison against the playbook → JSON `{clause_type, draft_text, standard_position, deviation, severity[low|med|high|critical], suggested_text}`. Cache the results, with a "Re-run live" button for the demo.
- **Log** every LLM call (prompt hash, model, tokens, latency) to a table. Show the token/cost total on an admin page.

## 7. Phases (stop for review after each)

| Phase | Deliverable | Done when |
|---|---|---|
| P1 | Repo scaffold, Docker Compose, DB schema + migrations, CLAUDE.md conventions | `docker compose up` works and `/health` is green |
| P2 | Fictional document set (28) + `labels.json` + seed pipeline | `make seed` loads everything; extraction eval ≥ 90% on key fields |
| P3 | Repository + contract detail + hierarchy/effective terms | MSA→SOW→amendment shows overridden values with provenance |
| P4 | Renewal dashboard | KPIs and notice-deadline buckets match `labels.json` |
| P5 | Ask assistant (router, SQL, clause search, citations) | 15/15 demo questions correct in `make eval` |
| P6 | Redline + template library + deviation view | All planted deviations found in 4 drafts; the clean draft shows none at high/critical severity |
| P7 | Polish, demo mode, README with demo script | Full demo runs end to end with no errors, twice in a row |

## 8. Evals

- `evals/extraction_eval.py`: per-field accuracy vs `labels.json` (dates exact, money ±1%, booleans exact).
- `evals/questions.yaml`: 15 demo questions with expected answers. Examples:
  - Which contracts have a notice deadline in the next 60 days?
  - Total annual value of contracts expiring this quarter, by category?
  - Which vendors have uncapped liability?
  - Which SaaS vendors process personal data without a DPA?
  - Which contracts can't be terminated for convenience?
  - What are the current effective payment terms on the Bluepeak MSA after amendments?
  - Top 5 vendors by annual value and their renewal dates?
  - Which NDAs expire before their related MSA?
- `evals/redline_eval.py`: recall of the planted deviations per draft.

## 9. UI and UX

- Navigation: Dashboard · Contracts · Ask · Redline · Templates
- Clean, professional enterprise look. Light + dark themes. Tabular numbers, INR formatting (₹ lakh/crore).
- Encode severity in form (chips/stripes), not only in colour.
- Ask page: answer first, then expandable "How I got this" (SQL, result rows, cited clauses linking to the contract detail).
- **Demo mode** toggle: uses cached LLM results where available, so the demo is fast and the wifi can't break it.

## 10. Conventions

- Small, reviewable commits per phase. Conventional commit messages.
- Type hints everywhere; ruff + black; pytest for backend logic (renewal date math, effective-terms resolution).
- Keep prompts in `backend/app/prompts/*.md`, not inline strings.
- Don't add libraries without saying why.
- Ask me before any decision that is hard to reverse.

## 11. Demo script (target)

1. **Problem (30s):** "Arcadia's VMO tracks 18 vendor contracts across Excel and SharePoint. Last year it missed 2 auto-renewals."
2. **Dashboard (1m):** 4 notice deadlines in 30 days, ₹ value at stake, 3 uncapped liabilities.
3. **Contract detail (1m):** fields with source highlights; MSA → SOW → amendment effective terms.
4. **Ask (2m):** a structured question (show the SQL), a clause question (show citations), then a mixed question.
5. **Redline (1.5m):** pick a vendor draft and see deviations, severity and suggested wording in seconds.
6. **Templates (1m):** where executed contracts drifted from the standard templates.
7. **Close (30s):** roadmap for upload, alerts, integrations and multi-tenant.

## 12. Later version (not now)

Upload + OCR, creating contracts from templates, Word tracked-changes export, email/Teams alerts, obligation tracking, invoice-vs-contract rate matching, renewal briefs, SSO, multi-tenancy, Ariba/Coupa/SAP integrations, audit trail, SOC 2 readiness.
