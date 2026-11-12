# ContractIQ

> **Branches.** This branch is the **VMO edition** (vendor management office, IT-services corpus). The hospitality version (hotel group, property level, hotel pack, new design shell, portfolio map) lives on the branch **`hotel-property-ops`**.

**Vendor contract intelligence for Vendor Management Offices (VMOs).**
Load your vendor contracts and drafts; ContractIQ reads them, keeps one unified dataset, and tells you what needs action:
which renewals have a notice deadline coming, where liability is uncapped, which drafts deviate from your playbook, what you
billed against what you signed, and the answer to any question about the portfolio, with the evidence to check it.

> **Status: proof of concept.** It runs end to end on a fictional corpus and on public real-world contracts, with simulated
> ERP, e-signature, cloud-drive and mailbox systems. It has not been used on a customer's real contracts or connected to
> real tenants. See [Known limits](#known-limits). The fictional customer is **Arcadia Retail**; every vendor, person and
> document in the demo data is fictional.

## What it does

| Area | What you get |
|---|---|
| **Portfolio** | KPI tiles, a decision queue sorted by the *last day to act* (expiry minus notice period), 30/60/90-day buckets with value at stake, expiries by month, vendor operations. |
| **Renewals** | A 12-month timeline (or list) of what expires, with the last day to act on each (expiry minus notice period), sorted by urgency. |
| **Portfolio map** | Every contract family (parent, schedules, amendments) on one timeline with the last day to act, and the problems it finds: a schedule that outlives its parent, an NDA that ends before its agreement, an SOW with no parent, no end date. |
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

The interface is an operations console (top navigation, dense tables, tabular mono numbers, blue for action, amber and red only for urgency, severity by shape, word and colour); the design boards are in `design/` (hotel edition) and on the VMO design canvas. Everything shown is derived from the loaded documents plus Admin configuration. Nothing is tied to a vendor or a document.

## Quick start

Requirements: Docker with Compose, or Python 3.12 + Node 20 + Postgres 16 with pgvector.

```bash
cp .env.example .env     # ANTHROPIC_API_KEY is optional, see "Demo and Live"
make dev                 # db + api + web   ->  http://localhost:5173   (API health: http://localhost:8000/health)
make seed-pilot          # load the 36-document pilot corpus (PDF, Word, Markdown) and run the pipeline
```

`make seed` loads the older 32-document synthetic corpus instead (deterministic; the test suite uses it). Dates inside the
documents are relative to the seed run, so re-seed on the day of a demo.

Without Docker: set `DATABASE_URL` and `DATA_DIR`, run `alembic upgrade head`, then `python -m app.seed --pilot`, then
`uvicorn app.main:app` in `backend/` and `npm run dev` in `frontend/`.

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

## Tests

* `make test`: backend suite (167 tests) against the offline-seeded synthetic corpus.
* Outside Docker, use a separate database and data folder so tests never touch demo data:
  `DATABASE_URL=…/vmo_test DATA_DIR=./data_test LLM_PROVIDER=offline python -m app.seed && pytest`.
* Browser walkthroughs: `scripts/demo_pilot.js` (any corpus) and `scripts/demo_walkthrough.js` (synthetic corpus).

## Repository layout

```
backend/app/         FastAPI app: pipeline, extraction, kcc (clause library), kcc_ai, deviations, ask*, routes_*,
                     connectors/, simulators/, collab, mode (Demo/Live), llm, embeddings
backend/alembic/     migrations (0001 to 0027; below 0005 cannot be downgraded)
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

**Verticals:** a hospitality version (property-level hierarchy across many sites, hotel-specific clauses such as food safety, guest data and
brand standards, rate cards per room-night or per kilo). It would use fictional data only and be built from public knowledge and customers'
own contracts, never from any employer's confidential material. The first decision is who the first buyer is.

## Known limits

1. Every external integration is verified only against simulators, never a live tenant.
2. Accuracy on real customer vendor contracts has not been measured; offline extraction is weaker on messy real wording than on the fictional corpus.
3. Claude-assisted clause tagging was tested with simulated Claude replies and not yet against real ones.
4. Co-editing shares presence, comments, suggestions and versions; there is no character-level simultaneous typing (no CRDT).
5. Not built: multi-tenancy, SOC 2 evidence, a penetration test. The Word add-in has not been tested in Word.
6. The Docker image and CI workflow were written but not run in the build environment.
7. OCR is tested on clean and noisy scans only; stamps, handwriting and low resolution will be worse.
8. The redesign in the design review is not yet implemented in the front end.

## Notes

* Severity values: `low | medium | high | critical`. "Uncapped" means a liability clause that states liability is unlimited.
* Currency is USD in the demo data. Drafts are documents with status `draft` and are excluded from portfolio numbers.
* Catalogue metadata (category, owner, parent links) comes from an optional `.meta.json` next to a document, else is inferred.
  `data/labels*.json` are ground truth used only by the evals.
