# ContractIQ

> **Branches.** This branch is the **hotel / property operations edition** (fictional hotel group, property level, hospitality pack, portfolio map, new design shell). The **VMO edition** (vendor management office, IT-services corpus) lives on `claude/new-session-70au83`.

**Vendor contract intelligence for a hotel group's property operations.**
Load the group's vendor contracts and drafts; ContractIQ reads them, keeps one dataset, and tells the operations and procurement leads what needs action:
which renewals have a notice deadline coming, what each property really costs under contract, where the same vendor charges one hotel more than another,
which vendor certificates have lapsed, which drafts depart from the house standards, and the answer to any question about the portfolio, with the clause to check it.

> **Status: proof of concept.** It runs end to end on a fictional corpus and on public real-world contracts, with simulated
> ERP, e-signature, cloud-drive and mailbox systems. It has not been used on a customer's real contracts or connected to
> real tenants. See [Known limits](#known-limits). The fictional customer is **Seabright Hotels & Resorts** (six properties); every vendor,
> person and document in the demo data is fictional.

**Navigation.** Seven screens are always visible: Overview · Properties · Compare · Renewals · Contracts · Ask · Review. Everything else (vendors, portfolio map,
certificates, obligations, spend, risk, key clauses, templates, admin) is under **More**.

## What it does

| Area | What you get |
|---|---|
| **Portfolio** | KPI tiles, a decision queue sorted by the *last day to act* (expiry minus notice period), 30/60/90-day buckets with value at stake, expiries by month, vendor operations. |
| **Properties** | One record per property (rooms, city, kind). Each property's yearly cost is its own schedules **plus its share of group-level agreements** (by rooms), so the energy contract or the booking system is counted where it is used. Cost per room, what makes up the cost, what ends soon. |
| **Compare** | Where one vendor serves several properties: the rates and terms each property signed, side by side, with the gap between best and worst and an estimate of what the best rate is worth. |
| **Certificates** | The certificates each vendor's contract obliges it to hold (insurance, food safety, statutory inspections, payment-card attestation), with the expiry of the copy on file: expired, expiring, not on file. |
| **Contracts and hierarchy** | Repository with filters. Contract detail shows the text beside extracted fields (click a field to see its source passage, page and confidence), parent/child links (MSA → SOW → Work Order, amendments), and **effective terms** after amendments, with where each value comes from. |
| **Key clauses** | Matrix of every document × every key clause, with a citation for each tick and boxed gaps where the template requires a clause. The clause library is configurable in Admin. |
| **Ask** | Plain-English questions over the whole portfolio or chosen documents. Structured questions become read-only SQL; clause questions use semantic search; every answer shows its steps, SQL, result table and cited clauses. Conversation history, follow-ups, stop. |
| **Review and redline** | Vendor drafts are compared with the standard template and playbook. A review queue (status, assignee, due date), Word-style tracked changes, margin comments, accept/reject per change, apply accepted changes as a new version, export to `.docx` with real tracked changes. **Redlining is only for drafts**: executed contracts are read-only (change them by amendment). |
| **Online editor** | Word/Docs-style editing with Editing / Suggesting / Viewing, presence, comment threads (assign, resolve), version history, and guest **share links** (view / comment / edit) with an expiry. |
| **Approvals and e-signature** | Configurable approval routing with reminders; internal click-to-sign or a DocuSign-compatible flow; signed copies re-enter the pipeline as executed contracts. |
| **Templates** | Standard templates clause by clause, coverage matrix, and a deviation heatmap of executed contracts against each template. |
| **Obligations and SLAs** | Dated duties, SLA targets, notice periods, per-month actuals against the contract, breaches and estimated credits. |
| **Spend vs contract** | Invoices matched to contracts: off-contract, before/after term, duplicates, above rate, over planned value. Utilisation by contract. |
| **Vendor risk** | Explainable 0 to 100 scorecards (weights set in Admin) and portfolio benchmarks for terms such as liability cap and governing law. |
| **Alerts** | Rules over live data, an in-app centre, and delivery to e-mail, Slack, Teams or any webhook. |
| **Admin** | Pipelines, key-clause library, values and limits, checklist rules, thresholds, risk weights, obligation rules, connectors, alert channels, approval rules, users and audit log, quality and corrections, AI usage and cost. |

Everything shown is derived from the loaded documents plus Admin configuration. Nothing is tied to a vendor or a document.

## Quick start

Requirements: Docker with Compose, or Python 3.12 + Node 20 + Postgres 16 with pgvector.

```bash
cp .env.example .env     # ANTHROPIC_API_KEY is optional, see "Demo and Live"
make showcase            # db + api + web, migrate, seed the hotel corpus  ->  http://localhost:5173   (API health: http://localhost:8000/health)
```

Dates inside the documents are relative to the seed run, so re-seed (`make seed-hotel`) on the day of a demo. The hotel seed takes about eight minutes
(it renders Word and PDF files). `make seed` loads the older synthetic corpus the test suite uses.

Without Docker: see [Run it from a clean clone](#run-it-from-a-clean-clone-verified).

Other targets: `make eval`, `make test`, `make lint`, `make docs`, `make migrate`, `make down`.

## Demo and Live

One switch in the header controls the whole application and is saved on the server.

| | **Demo mode** (on) | **Live mode** (off) |
|---|---|---|
| Extraction, redline, clause tagging, Ask | Offline rule engine and cached results. **No Claude anywhere.** | Claude (API key, or the logged-in `claude` CLI on a subscription) |
| External systems | Built-in labelled simulators | Simulators until real tenants are configured |
| Good for | Fast, repeatable, works without internet | Real accuracy on real wording |

Stored documents keep the data of the engine that read them. After switching to Live, press **Admin → Pipeline → Re-extract all**
to read everything with Claude; people's manual field corrections are kept.

`LLM_PROVIDER=auto` picks `api` if a key is set, else `claude_code` if the CLI is available, else `offline`. If Claude hits a
limit, calls fall back to the offline engine and the header says so. The offline engine is a demo and fallback, not the
product's accuracy target.

## How documents flow through the system

```
folder / connector / upload / mailbox
        │  identify the file by SHA-256 of its content (not its name)
        ▼
  parse → split into clauses → tag key clauses (heading, keyword, sentence, optionally Claude)
        → extract fields (Claude or rules) → embed → derive values and limits
        → compare with template → run the checklist → obligations, risk, spend, alerts
        ▼
 one database  →  every screen and the Ask assistant
```

* **Incremental.** A run only touches the delta. A file whose size and modified time are unchanged is not even opened; a touched
  file is hashed and skipped if identical; a renamed file is recognised by its hash and recorded as *moved*; an identical
  copy is skipped as a duplicate; a changed hash updates the same record. Failed files are retried on the next run.
* **Audited.** Every run lists each file with its hash, size, action and reason (Admin → Pipeline).
* **Triggers.** Each pipeline runs on demand (**Run now**), on a schedule, or when files change.
* **Admin changes re-derive, they do not re-read.** Saving a key clause, value, checklist rule or threshold re-classifies the stored
  text and recomputes checks, deviations and redlines for every document. With Claude available, custom clauses are also tagged
  by meaning in any wording; the quote must appear verbatim in the document, and answers are cached by content hash.
* **Corrections stick.** A person's correction to a field survives re-extraction.

## Integrations and simulators

No sandboxes were available, so every external dependency has a stand-in that speaks the same API shape. The real connector
and client code runs against it over HTTP. Simulators are mounted only when `SIMULATORS=1` and are always labelled **Simulated**.

| System | Real code in the app | Stand-in used for the demo | Verified against a live tenant? |
|---|---|---|---|
| Coupa, SAP S/4HANA, SAP Ariba | OAuth / API-key connectors, paging, contracts and invoices | `/sim/coupa`, `/sim/sap`, `/sim/ariba` | No |
| DocuSign | Envelope, signing links, HMAC webhook | DocuSign-compatible simulator | No |
| Google Drive, OneDrive, SharePoint | Service account / Graph app, paging, change detection | Drive and Graph look-alikes | No |
| Mailbox intake | IMAP connector | Local IMAP server with contract attachments | No |
| Alerts | SMTP, Slack, Teams, webhook senders | Local sinks (`/sim/outbox`) | No |
| SSO | OpenID Connect (authorization code, JWKS) | Local identity provider | No |

Admin → Connectors has one-click "connect demo" buttons. Expect to debug permissions and consent on the first real connection.

## See it working: the end-to-end video

`reports/e2e/contractiq-e2e.mp4` (also `.webm`) is one recording of the whole product in Demo mode (no Claude, simulated external systems), driven by
`scripts/demo_e2e.js` against a fresh pilot seed: **22 of 22 feature steps passed**, no page errors (`reports/e2e/REPORT.md`, one screenshot per step).
It covers: dashboard, repository, contract detail with hierarchy and effective terms, vendors, key-clause matrix, an admin adding a clause that
every document is re-checked for, Ask (structured and clause questions), the review queue, uploading a draft and its tracked changes, the Word-style editor,
a guest share link, DocuSign-compatible signing through to an executed contract, the hash-based incremental pipeline run with its per-file audit, simulated
Coupa / SAP / Ariba / Drive / SharePoint / mailbox connectors, spend, obligations, risk, alerts, templates, admin configuration, the Demo/Live switch and security.
Re-record with `make video` (app running, `SIMULATORS=1`, pilot seeded).

## Data included in this repository (so a clone is self-contained)

| Path | What it is |
|---|---|
| `corpus/pilot/` and `backend/app/docgen/pilot_spec.py` | Source and spec of the 36 fictional pilot contracts |
| `data/inbox/` | The seeded folders the pipeline reads: contracts and drafts (PDF, Word, Markdown) |
| `data/feeds/` | Fixture invoices, SLA reports and acceptance certificates as **documents** (written for demos and tests; the product only reads files) |
| `data/labels*.json`, `data/manifest*.json` | Ground truth used only by the evals |
| `data/templates/` | The standard templates and playbook |
| `data/.cache/` | Cached Claude results, so Demo mode and re-seeding are instant and offline |
| `data/cuad/` | **CUAD v1**, 510 real public contracts as text with expert labels, plus our `index.csv` (agreement type and train/test split). CC BY 4.0, attributed in `data/cuad/README.md` |
| `reports/` | Eval outputs and recorded walkthrough videos and screenshots |
| `design/` | The full redesign: 39 boards and the generators that built them |

Not stored: the CUAD PDFs (`make cuad-full` downloads them) and generated test scratch data (`data_test/`).

One-command paths: `make showcase` (clone to running demo), `make cuad` (real-contract accuracy on the bundled text), `make eval`, `make test`, `make video` (records the end-to-end walkthrough into `reports/e2e/`).

## Accuracy: what has and has not been measured

* **Fictional pilot corpus** (36 documents, ground truth computed from the generating spec): extraction 98.9% offline, 98.2% with
  Claude; Ask checked against the page APIs, 60/60 offline, 57 to 60 of 60 with Claude (misses were answer-format only).
* **Public real contracts** (CUAD v1, 510 SEC-filed contracts with expert labels, 70/30 split by file-name hash; tuning used only
  the training split). On the 133-contract hold-out the offline engine reaches, for example, governing law 77%, effective
  date 76%, liability-cap clause F1 0.87, assignment F1 0.94; with Claude, on a 60-contract hold-out, governing law 98% and effective
  date 94%. Termination for convenience is the weakest area (offline recall about 0.63, Claude about 0.70).
  CUAD is not VMO-shaped (licences, distribution and similar), so read these as robustness on messy real text.
* **Semantic clause search** with the local `fastembed` model (BAAI/bge-small-en-v1.5) retrieves the right clause far more often than the
  hashed fallback (about 85% vs 40% on the retrieval eval).
* **Not measured:** accuracy on a customer's real vendor MSAs. That is the first thing to do with a pilot customer.

Reproduce: `python evals/pilot_eval.py`, `python evals/module_eval.py`, `python evals/retrieval_eval.py`, and for CUAD `make cuad`
(or `python evals/cuad_eval.py data/cuad/CUAD_v1 --split test`; `LLM_PROVIDER=offline` for rules, unset for Claude). Result files are in `reports/`; `HANDOVER.md` has the full tables.

## Security and operations

* `AUTH_MODE=off` (default for demos) is open. `AUTH_MODE=on` requires sign-in; first start creates the administrator. Roles
  viewer < reviewer < admin, API tokens, optional OIDC SSO, TOTP two-factor with recovery codes, lockout and password policy,
  SCIM user provisioning, and an audit log of changes, sign-ins and refusals. Connector secrets are stored encrypted.
* The Ask assistant's `run_sql` tool runs `SELECT` only, as a read-only Postgres role, with a statement timeout and an automatic
  `LIMIT 200`; the role cannot read embeddings or pipeline tables.
* Security headers, request ids, JSON logs, retention settings, metrics at `/api/ops/metrics`, `scripts/backup.sh`, a CI workflow.
  Details: [`docs/SECURITY.md`](docs/SECURITY.md).
* The scheduler runs inside the API process (one worker).

## Configuration

Set in `.env` (see `.env.example`):

| Variable | Purpose |
|---|---|
| `LLM_PROVIDER`, `ANTHROPIC_API_KEY`, `MODEL_EXTRACT`, `MODEL_ASK`, `MODEL_REDLINE` | Engine and models |
| `EMBEDDING_PROVIDER` | `auto`, `local` (fastembed) or `hash` |
| `DATABASE_URL`, `READONLY_DATABASE_URL`, `DATA_DIR` | Database and data folder |
| `AUTH_MODE`, `OIDC_ISSUER`, `OIDC_AUDIENCE`, `OIDC_ROLES_CLAIM`, `SECRET_KEY`, `CORS_ORIGINS` | Access and encryption |
| `SIMULATORS`, `PUBLIC_API_URL`, `SIM_IMAP_PORT`, `SIM_SMTP_PORT` | Demo stand-ins (set `SIMULATORS=0` in production) |
| `SCHEDULER_ENABLED` | Background pipeline scheduler (tests turn it off) |
| `CUSTOMER_NAMES` | How your own company is named in contracts (comma-separated; the hotel setup uses `Seabright`): needed so the other party is read as the vendor |
| `STANDARDS` | `hotel` gives the template library the hotel group's values and its own clauses |

## Tests

* `make test`: backend suite (178 tests) against the offline-seeded synthetic corpus.
* Outside Docker, use a separate database and data folder so tests never touch demo data:
  `DATABASE_URL=…/vmo_test DATA_DIR=./data_test LLM_PROVIDER=offline python -m app.seed && pytest`.
* Browser walkthroughs: `scripts/demo_pilot.js` (any corpus) and `scripts/demo_walkthrough.js` (synthetic corpus).

## Repository layout

```
backend/app/         FastAPI app: pipeline, extraction, kcc (clause library), kcc_ai, deviations, ask*, routes_*,
                     connectors/, simulators/, collab, mode (Demo/Live), llm, embeddings
backend/alembic/     migrations (0001 to 0029; below 0005 cannot be downgraded)
backend/tests/       pytest suite
frontend/src/        React + Vite + TypeScript + Tailwind + TanStack Query
evals/               extraction, redline, Ask, module, OCR, retrieval, CUAD and pilot evals
corpus/pilot/        source text of the 36 fictional pilot documents
data/                inbox, feeds, templates (generated files are git-ignored)
addin/               Word task-pane add-in (untested inside Word)
scripts/             seed, backup, demo walkthroughs
docs/, HANDOVER.md   security notes; handover with measured results and limits
CLAUDE.md            original scope and conventions
```

## Hotel edition: details

The fictional corpus: **Seabright Hotels & Resorts**, a hotel group with six properties and 32 vendor documents
(laundry and linen, security, lifts, HVAC, pest control, waste, food and beverage, housekeeping staffing, property and booking systems, payments, energy), with
group-level master agreements, per-property schedules, an amendment, NDAs, DPAs, and five vendor drafts (one clean control). It is written from the owner-operator's side;
all names are fictional.

* Sources: `backend/app/docgen/hotel_spec.py` (spec, ground truth, the properties' attributes, the certificates on file), `corpus/hotel/*.md` (contract text written by Claude
  from the spec), seeded files in `data/hotel/`.
* **Properties are records** (migration 0029): `properties` (rooms, city, kind) is filled from the documents and from `properties.json` in the data folder, and edited with
  `PATCH /api/properties/{id}`. View `v_property_contracts` attributes every contract to the properties it covers: a contract that names a property counts there in full; a
  group agreement with schedules counts at the properties its schedules name; a group agreement without schedules counts at every property; `PUT /api/contracts/{id}/coverage`
  records an exception. The share is by rooms. The six properties' costs add up to the portfolio's yearly value exactly.
* **Compare** (`/compare`, API `/api/properties/compare`): on the seeded data the same laundry supplier charges 1.42, 1.58 and 1.71 USD/kg at three hotels, a 20% gap worth
  about $60K a year at the best rate (an estimate: same volumes assumed). Cost per room is compared for every vendor that serves two or more properties.
* **Certificates** (`/certificates`, API `/api/certificates`): required certificates are derived from the clauses (a clause must actually oblige one); expiry dates come from
  `feeds/certificates.csv` or are recorded on the screen, never guessed from the contract. Seeded state: 2 expired, 2 expiring within 60 days, 4 not on file, 5 valid.
* **Hospitality pack** (`backend/app/hotel_pack.py`): ten key clauses, three values (laundry rate per kilogram, fault response hours, booking commission) and checklist rules,
  all ordinary Admin configuration.
* **House templates:** `STANDARDS=hotel` gives the template library the group's values (England and Wales law, 60-day exit notice) **and its own clauses**
  (`backend/app/docgen/hotel_house.py`): guest and staff injury, labour and wage compliance, exit on sale of a property and brand standards in the MSA, payment-card security in
  the SaaS template. Clauses that only suit one kind of supplier (food safety, statutory inspections) stay as key clauses and checklist rules.
* **Measured offline on this corpus** (`LABELS=labels_hotel.json python evals/pilot_eval.py`, `python evals/hotel_redline_eval.py`): **99.8% of fields (456/457), 98.4% of
  document metadata, 98.8% of values and limits; all 17 planted draft deviations found, none on the clean control, about 7 findings per draft.** The numbers rose from 98.2% and
  16/17 after fixes that also apply to real documents: tables in PDFs are rebuilt row by row, signature sentences wrapped over lines and signature tables with dates but no
  typed names are read as signed, and numbers above one hundred written in words are understood. Two security schedules had labels that contradicted their own text
  (they do handle CCTV and guest data); the labels now follow the documents.
* **Less noise:** the Overview counts only invoices worth querying (high and critical; late payments are listed as minor), personal data without a DPA is reported once per
  vendor, a contract misread as unsigned no longer raises a false critical exception, an invoice that quotes no agreement says how many agreements are on file, and Review
  shows critical and high findings first with the smaller differences folded away.
* **Ask** understands property: "which properties have the most contracts?", "contracts at Lakeside Resort", and "the laundry rate per kilogram at each property". The schema
  given to Claude now describes `properties`, `v_property_contracts` and `certificates` (it previously promised a `property` column that the view did not have).
* **Portfolio map** (`/map`): every contract family on one timeline with the last day to act, plus hierarchy problems.
* **End-to-end walkthrough** (`node scripts/demo_e2e.js`): all 22 steps pass on this build with no page errors. The committed video in `reports/e2e_hotel/` was recorded before
  the seven-screen navigation and the Properties, Compare and Certificates screens; re-record with `make video` after a fresh seed.
* Not yet done: the walkthrough does not visit Compare or Certificates; certificates are not yet read from uploaded certificate documents or raised as alerts; Claude-mode
  measurement has not been repeated since these changes; the new layout on Ask, Review and the Admin pages.

## Roadmap (future scope, not built)

**VMO depth** (what a mature vendor-management office runs beyond contracts):
1. Vendor performance reviews: quarterly business reviews with scores, actions and history per vendor.
2. Compliance certificates: insurance, security and other certificates with their own expiry dates and reminders.
3. Renewal and negotiation workflow: a recorded decision per renewal (renew, renegotiate, exit) with owner, deadline and outcome.
4. Savings tracking: cost avoided or reduced through renegotiation, reported per vendor and per category.
5. Vendor master data: duplicate vendors across business units, consolidation and tiering.
6. Onboarding and due diligence: questionnaires, financial-health and risk checks before signature.
7. Rate cards and resourcing for staffing and services vendors.
8. Exit and transition plans for critical vendors.

**Platform:** upload with OCR at scale, Word tracked-changes round trip from Word itself, character-level co-editing, ERP and procurement
connectors verified against real tenants (Coupa, SAP, Ariba), multi-tenancy, SSO provisioning at scale, SOC 2 evidence, audit export.

**Product:** port the redesign in `design/` to the front end, one headline demo path (renewals, portfolio map, Ask), and measured accuracy on a
design partner's own redacted contracts.

**Hospitality next:** management and franchise agreements, leases and distribution contracts alongside supplier contracts; rate cards per room-night;
certificates read from the certificate documents themselves. Fictional data only, built from public knowledge and customers' own contracts, never from any
employer's confidential material. The first decision is still who the first buyer is, and in which country.

## Known limits

1. Every external integration is verified only against simulators, never a live tenant.
2. Accuracy on real customer vendor contracts has not been measured; offline extraction is weaker on messy real wording than on the fictional corpus.
3. Claude-assisted clause tagging was tested with simulated Claude replies and not yet against real ones.
4. Co-editing shares presence, comments, suggestions and versions; there is no character-level simultaneous typing (no CRDT).
5. Not built: multi-tenancy, SOC 2 evidence, a penetration test. The Word add-in has not been tested in Word.
6. The Docker image and CI workflow were written but not run in the build environment.
7. OCR is tested on clean and noisy scans only; stamps, handwriting and low resolution will be worse.
8. The redesign in the design review is not yet implemented in the front end.
9. A property's share of a group agreement is an attribution by rooms, not a figure from the contract; the saving on Compare assumes unchanged volumes.

## Notes

* Severity values: `low | medium | high | critical`. "Uncapped" means a liability clause that states liability is unlimited.
* Currency is USD in the demo data. Drafts are documents with status `draft` and are excluded from portfolio numbers.
* Catalogue metadata (category, owner, parent links) comes from an optional `.meta.json` next to a document, else is inferred.
  `data/labels*.json` are ground truth used only by the evals.


## Run it from a clean clone (verified)

Everything the demo needs is committed: the documents, the labels, the rules and templates, the cached results and the fixtures. Nothing is downloaded and no API key is needed (the offline engine is the default; turn Demo mode off and set `LLM_PROVIDER` for Claude).

```
make showcase          # Docker: database + API + web, migrate, seed the hotel corpus
# or without Docker (Postgres 16 with pgvector, Python 3.12, Node 20; pandoc, LibreOffice, poppler and tesseract to render and read Word/PDF):
cd backend && pip install -e ".[dev]" && alembic upgrade head
DATA_DIR=../data/hotel STANDARDS=hotel CUSTOMER_NAMES=Seabright python -m app.seed --hotel
SIMULATORS=1 DATA_DIR=../data/hotel STANDARDS=hotel CUSTOMER_NAMES=Seabright uvicorn app.main:app --port 8000     # stand-in ERP and e-signature systems for the demo
cd ../frontend && npm ci && npm run dev                 # http://localhost:5173
```
Checked from an empty database: seed, evals (fields 99.8%, redline recall 17/17), 178 backend tests, type check, build and the 22-step walkthrough (`node scripts/demo_e2e.js`) all pass. Generated at first use and not committed: the connector encryption key (`.secret_key`).
