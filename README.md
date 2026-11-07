# ContractIQ — vendor contract intelligence for VMOs (POC)

Live-demo POC for **Arcadia Retail Inc.**'s Vendor Management Office, over an enterprise **IT-services portfolio in USD**:
a global systems integrator, a Big-4-style consultancy, an offshore IT services major, a web-infrastructure software
vendor and SaaS suppliers (all **fictional lookalikes** — no real company names). 32 documents: 6 standard templates,
27 executed contracts (MSA → SOW → Work Order, amendments, NDAs, DPAs, SaaS) and 5 vendor drafts. See `CLAUDE.md` for scope.

## Two corpora
* **Pilot corpus (recommended for evaluation)** — `make seed-pilot`: 36 realistic fictional contracts (MSAs, SOWs, work orders, amendments, NDAs, DPAs, SaaS, drafts) written
  in eight drafting styles and delivered as **PDF, Word and Markdown**, with signature tables in several layouts, short-form and unnumbered headings, number words and mixed
  date formats, no sidecar metadata. Source: `corpus/pilot/*.md` (date tokens), spec: `backend/app/docgen/pilot_spec.py`. Ground truth is computed from the spec
  (`data/labels_pilot.json`), never from the document text. `evals/pilot_eval.py` scores extraction; `evals/pilot_ask_eval.py` scores Ask.
* **Synthetic corpus** — `make seed` (the default below): 32 generated documents; deterministic, used by `make test` and `scripts/demo_walkthrough.js`.

Nothing in the product is tied to either: vendors, categories, obligations, SLA metrics, spend rules and risk points all come from the loaded documents and from
configuration (Admin → Values, Obligation rules, Thresholds, Risk scoring). Feed CSVs (invoices, SLA, obligation status) are generated *from the loaded contracts*.

## Run it
```bash
cp .env.example .env          # add ANTHROPIC_API_KEY for the live Claude path (optional, see below)
make dev                      # db + api + web  ->  http://localhost:5173  (api: :8000/health)
make seed                     # synthetic corpus into the inbox folder and run the pipeline (idempotent)
make seed-pilot               # the 36-document pilot corpus (PDF / Word / Markdown) instead
python -m app.seed --pilot    # same, outside Docker (set DATABASE_URL, DATA_DIR)
make eval                     # extraction, redline and Ask evals
make test                     # pytest
```
Dates in the documents are relative to the seed run, so **re-run `make seed` on the day of the demo** (and before each
walkthrough run: it creates a draft and edits admin settings, then restores them).

## How the data flows (one unified dataset)
```
data/inbox/**.md  ──►  pipeline  ──►  contracts · clauses · fields · values · checks · redlines  ──►  every screen + Ask
 (folder watch)        parse → classify clauses (KCC library) → extract fields (Claude / offline) → embed
                       → extract values & limits → compare to template → run the redline checklist
```
* **Folder pipelines** — anything dropped into `data/inbox/` (Markdown or text) is picked up and processed; vendor, type and
  parent are read from the document. A file is re-processed only when its content changes. There are two pipelines, each with
  its **own trigger** (Admin → Pipeline): *Executed contracts* (`contracts/`, `uploads/`; default **periodic, every 2 hours**) and
  *Draft review* (`drafts/`, `generated/`; default **dynamic: runs as soon as a new or changed file appears**). A trigger is
  periodic (any frequency), dynamic (on new/changed files, checked every 20 s) or manual, plus Run now. The seed uses the same path.
* **Admin** (⚙) configures what the platform identifies, extracts and checks — every change re-runs over all documents:
  * **Key clause library** — which clauses to identify (heading aliases + keywords), what the standard says, whether each shows
    in the matrix. Add any number; a new clause becomes a column in Key clauses and in Ask. *Preview matches* before saving.
  * **Values & limits** — the numbers to extract from a clause (regex → number/text): payment days, liability cap multiple,
    insurance cover, notice periods, uptime, governing law…
  * **Redline checklist** — rules run on a contract before signing: clause required / absent, value vs threshold, forbidden
    wording; severity, where it applies, suggested replacement wording.
  * **Pipeline** — frequency, run now, add a document, run history with per-document events.
* **Review queue (Redline)** — drafts from the drafts folder (or uploaded: `.docx`, `.md`, `.txt`) are redlined automatically and
  wait in a queue (To review / In review / Changes requested / Approved). Each opens as a **Word-style page with the redline as
  tracked changes** and margin comments: accept or reject each change, **apply accepted changes as a new version**, approve or
  request changes with a note. The checklist (rules live in Admin) sits on its own tab.
* **Online editor** — any draft opens in a Word/Docs-style editor (toolbar, page sheet, highlighted `[placeholders]`, word
  count) with a live checklist and **version history**; saving writes the file back and re-runs the pipeline. Executed
  contracts are read-only (change them by amendment).
* **New contract** — pick a template (MSA/SOW/Work Order/NDA/SaaS/DPA), or **paste/upload the deal details** (an email, term
  sheet, `key: value` lines, JSON, CSV, `.docx`) and the form is filled from them (Claude when a key is set, otherwise a
  rule-based reader). Choose which clauses go in (the template's, plus any of the 39 in the clause library), edit in the online
  editor with the live checklist, create: it is dropped into the folder, extracted, and appears everywhere.
* **Templates** — every template clause by clause with its deviation heatmap, and a coverage matrix of which clauses each
  template contains; "Create a contract from this template" jumps into New contract.
* **Chat** — Ask is a chat window: the **thinking trail streams live** (understood the question → SQL → composed the answer; with
  Claude also its reasoning text), then the answer is written out and the tables appear; **Stop** cancels. Follow-ups stay in
  the same conversation (Claude gets the earlier turns as context; the offline planner answers each question on its own).
  **Conversation history** on the left: reopen any past chat with its answers, tables and thinking, search, rename, delete.
  Re-seeding resets history (document ids change).
* **VMO depth** (what a vendor-management office runs on, beyond the contract text):
  * **Obligations & SLAs** — what each party must do, per contract: dated milestones, SLA targets, notice periods, payment, acceptance,
    insurance and audit duties, renewal-notice deadlines (rules over the extracted text; with Claude, extra duties such as reporting or
    certificates are added, tagged "found by Claude"). Status is tracked (open / overdue / done / waived; mark done in the UI). Monthly SLA
    actuals from monitoring feeds are charted against the contract target, with breaches and *estimated* service credits.
  * **Spend vs contract** — invoices (AP/ERP export) matched to contracts and checked: no contract on file, billed against an unsigned
    contract, before/after the term, duplicates, above the usual invoice, over the planned value, late payment (interest exposure).
    Contract utilisation shows billed vs planned vs share of term elapsed.
  * **Vendor risk scorecards** — 0–100 per vendor from five explainable components (contract terms, renewal exposure, performance,
    spend compliance, concentration), weights set in Admin → Risk scoring, every driver listed. **Term benchmarks** show each term across
    the portfolio against the median and our policy.
  * **Operational feeds** — a third pipeline loads CSVs from `data/feeds/` (`invoices*.csv`, `sla*.csv`, `obligation_status*.csv`) on its own
    trigger (default: when a file changes), or via upload in the UI. `make seed` writes believable fictional feeds with planted problems
    (unsigned work order billed, a hosting vendor with only a draft MSA, a duplicate invoice, SLA misses...). Replace them with real exports.
* **Ask** — *analytical* questions over the whole portfolio, or questions about **specific documents** chosen (search +
  select) in the panel on the right. Answers are tables; the SQL and steps are under a collapsed **Thinking** section.

### LLM engine: Claude subscription, API key, or offline
`LLM_PROVIDER=auto` (default) picks, in order: **`api`** (`ANTHROPIC_API_KEY` set) → **`claude_code`** (the `claude` CLI is installed and
logged in: everything runs on your **Claude subscription**, no key; run the API on the host, `pip install -e ".[claude-code]"`) →
**`offline`**. To move from the subscription to a key later, just set `ANTHROPIC_API_KEY` (or `LLM_PROVIDER=api`); nothing else changes.
If Claude is unavailable (e.g. the subscription's 5-hour limit), calls fall back to the offline engine and the header says so.

| | Claude (`api` / `claude_code`) | Offline engine |
|---|---|---|
| Extraction | Claude, forced JSON schema (cached on disk, so re-seeding is free) | regex extractor |
| Redline / deviations | Claude judges each changed clause vs the playbook | word diff + pattern library |
| Brief → new-contract form | Claude fills the schema | rule-based reader |
| Checklist, values, clause identification | rule engine (no LLM) | same |
| Ask | Claude tool-use loop (`run_sql`, `search_clauses`, `get_contract`), streamed live: reasoning, SQL steps, answer | scripted plans + rule-based planner |
| Embeddings | `sentence-transformers` if installed, else hashed bag-of-words | hashed bag-of-words |

Measured with Claude on the subscription (`make seed && make eval`): extraction **437/442 (98.9%)**, redline recall **18/18** (severity agreement
14/18: Claude grades severity differently from the planted labels), Ask **26/27** (the miss is clause *retrieval* ranking with the hashed embeddings).
Offline: 442/442, 18/18, 27/27. `make test` seeds offline first (the tests assert the deterministic offline data). Free-form (non-cached)
questions need **Demo mode off** to go live; with it on, preloaded questions are served from the cache that the seed generated with Claude.

The header badge shows the engine in use. Offline eval scores prove the plumbing and data, not Claude's quality; the Claude scores above do.

## Connectors, alerts, access (Admin)
* **Connectors** (Admin → Connectors): Google Drive (service-account key or OAuth refresh token), OneDrive and SharePoint (Microsoft Graph, app registration with
  `Files.Read.All`/`Sites.Read.All`). New and changed PDF / Word / Markdown / text files are copied into the inbox on a schedule (or *Sync now*), processed like any dropped file,
  and each contract keeps a link to the original. Secrets are encrypted (`SECRET_KEY` or `data/.secret_key`) and never shown again. Tested against local Drive/Graph stand-ins
  (auth flows, paging, redirects, Google-native export, changed/removed files); **not yet exercised against a live Google or Microsoft tenant**.
* **Alerts** (bell, `/alerts`; rules and channels in Admin → Alerts): 11 rules over the live data (renewal notice passed / due, expiring 30 / 90 days, obligation overdue / due,
  SLA breach, serious spend exception, vendor risk tier, draft waiting for review, connector failure). Each event is raised once; deliver to e-mail (SMTP), Slack, Teams or any webhook, with a
  minimum severity per channel. Review assignments (assignee, due date) live on the Redline screen.
* **Access** (Admin → Users & audit): `AUTH_MODE=off` (default, demo) is open; `AUTH_MODE=on` requires sign-in (first start creates the administrator), roles **viewer < reviewer < admin**,
  API tokens (`Authorization: Bearer ciq_…`, never outranking their owner), optional **OpenID Connect** (`OIDC_ISSUER`, `OIDC_AUDIENCE`, `OIDC_ROLES_CLAIM`; RS256/ES256 tokens verified against the issuer's JWKS),
  and an audit log of every change, sign-in and refusal. This is application-level access control; SSO provisioning (SCIM), MFA and per-tenant isolation are not built.
* **Word**: every draft / document exports to `.docx`; the redline exports with real tracked changes (`w:ins` / `w:del`) that Word shows as accept / reject.

## Demo without any ERP or DocuSign account (simulators)
Start the API with `SIMULATORS=1 PUBLIC_API_URL=http://localhost:8000` (the default in `.env.example` for demos). The app then contains stand-ins that speak the same APIs the real connectors use:
* **ERP** — Admin → Connectors → **Connect demo ERP**. Registers a simulated Coupa (OAuth client credentials, JSON, paging) and a simulated SAP S/4HANA (API key, OData v2, `/Date()/` values) and syncs them; the real
  connector code runs over HTTP. The invoices are generated from *your loaded contracts* (this month's fee per active SOW / SaaS, a resend, an over-run, a vendor with no contract, an unsigned contract), so Spend and Alerts
  change in front of the audience (e.g. 51 → 68 invoices, 12 → 20 exceptions on the pilot corpus). Demo credentials: Coupa `demo-client` / `demo-secret`, SAP key `demo-sap-key`.
* **E-signature** — open a draft in the editor → Signatures → provider *DocuSign* → Send. The DocuSign-compatible simulator returns the signing links (a real service e-mails them); open each in a browser, sign in order,
  and the simulator calls our Connect-style webhook; the draft gets a signature block, the signatories are extracted, and *Mark executed* turns it into an executed contract.
The simulators are clearly labelled, are not the vendors' services, and a real account is used the moment `DOCUSIGN_*` / a real connector is configured (`SIMULATORS=0` in production).

## Tests
`make test` (offline, synthetic corpus: 116 tests including connectors, alerts, access control, real PDF/Word ingestion). Outside Docker use a separate database and data folder
for tests (`DATABASE_URL=…/vmo_test DATA_DIR=./data_test LLM_PROVIDER=offline python -m app.seed && pytest`) so they never touch a demo database.
Pilot evals: `python evals/pilot_eval.py`, `python evals/pilot_ask_eval.py` (run with `LLM_PROVIDER=offline` or unset for Claude). Browser walkthrough over any corpus:
`NODE_PATH=$(npm root -g) node scripts/demo_pilot.js out/ "Claude mode"`.

## Demo script (~10 min)
1. **Dashboard (1m)** — USD; contracts expiring in the next 30 / 60 / 90 days with $ at stake; AdSpark's notice deadline has passed.
2. **Vendors (1m)** — Accentia / Delmont / Taraka / Nginova…: spend, next dates, risk flags; open Accentia: MSA → SOW → Work Order tree.
3. **Contract detail (1m)** — signatures, terms & limits, checklist, effective terms ("payment 45→30, overridden by Amendment No. 1"); Work Order inherits its MSA's terms.
4. **Key clauses (1m)** — every document × every key clause ✓/✗; hover for the citation; Work Order 2 is unsigned.
5. **Ask — portfolio (2m)** — "How many contracts are expiring in the next quarter?" · "Which contracts have payment terms below 45 days?" · "Which contracts fail the checklist?"; open **Thinking**.
6. **Ask — specific documents (1m)** — switch to *Selected documents*, search "delmont", tick the MSA: "Tell me about this contract", "What does the indemnity clause say?"; tick a draft: "Which checklist rules does it fail?".
7. **Review queue (1.5m)** — a vendor draft as a Word-style page with tracked changes; accept/reject, request changes, checklist tab; upload a `.docx`/`.md` and watch it join the queue; apply accepted changes → new version.
8. **New contract (1.5m)** — paste an email with the deal details → the SOW form fills itself (parent MSA picked) → add a clause from the library → the checklist flags 20-day payment → fix it in the editor → create → open it in the online editor, type, save v2.
9. **Templates (0.5m)** — clause coverage across the 6 templates; "Create a contract from this template".
10. **Admin (1.5m)** — each pipeline's trigger (periodic / dynamic / manual); add a key clause → new matrix column; tighten a threshold → everything re-checks.

`NODE_PATH=$(npm root -g) node scripts/demo_walkthrough.js` walks every screen above and records a captioned video.

## Notes
- Severity values are `low | medium | high | critical`. "Uncapped" means a liability clause that states liability is unlimited.
- Currency is USD throughout (documents, extraction, UI, Ask). Governing-law standard is New York.
- Drafts are ordinary documents with status `draft`: excluded from portfolio numbers (dashboard, vendors, Ask) but visible in
  the repository, key-clause matrix, Redline and scoped Ask.
- Catalogue metadata (category, owner, parent links) comes from an optional `.meta.json` next to a document, else is inferred
  from the document; `data/labels.json` is ground truth used only by the evals. Generated files under `data/` are git-ignored.
- The read-only role `vmo_readonly` backs `run_sql`; it cannot read embeddings, pipeline tables, `llm_calls` or `ask_cache`.
- Migrations 0003+ cannot be downgraded (recreate the database). The scheduler runs inside the API process (one worker).
