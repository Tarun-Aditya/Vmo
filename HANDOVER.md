# ContractIQ — handover

## What it is now
A VMO contract-intelligence POC that ingests real-format documents (PDF, Word, Markdown), extracts terms, obligations, SLA/spend/risk signals, answers questions
(Ask), redlines drafts (with Word tracked-changes export), alerts, syncs from Google Drive / OneDrive / SharePoint, and has role-based access with an audit log.
Everything is derived from the loaded documents plus admin configuration; nothing is tied to a particular vendor or document.

## Data provenance
| Data | Source |
|---|---|
| Contracts, clauses, extracted terms, obligations, redlines, checklist results | **Derived from the documents** (Claude or the offline rules) |
| Invoices, SLA measurements, obligation status (the "feeds") | **Synthetic**, generated from the loaded contracts to stand in for AP / monitoring exports. A real deployment loads CSV exports instead (Admin → Pipeline, or upload) |
| The 36 pilot documents | **Fictional**, written by Claude from a spec in eight drafting styles; not real redacted customer contracts |
| Thresholds, obligation rules, risk weights, key clauses, metrics | Admin configuration (defaults shipped, editable) |

## Parity: offline engine vs Claude (36-document pilot corpus, 2026-11-07)
| Eval | Offline | Claude (subscription) |
|---|---|---|
| Contract extraction vs spec labels (`evals/pilot_eval.py`, 783 fields) | 774 (98.9%) | 769 (98.2%) |
| Ask over portfolio, 8 questions (`evals/pilot_ask_eval.py`) | 8/8 | 8/8 |
| **Ask over every module, cross-validated against the page APIs** (`evals/module_eval.py`, 60 cases incl. 15 paraphrases, aggregate / group / list, whole portfolio and one document) | **60/60** | **57/60** |
| Invoices, SLA reports, acceptance certificates read from documents (`evals/ops_eval.py`, 573-589 fields, md/docx/pdf) | 100% | 100% |
| Scanned (OCR) contracts vs the digital original (`evals/ocr_eval.py`, 3 noisy scans x 10 fields) | 30/30 | 29/30 |
| Tests (`pytest`, synthetic corpus, offline) | all passing | – |

Claude's 3 module misses are answer-format cases, not wrong data: "Show critical alerts" returned the list (not a count), "highest risk score" returned the ranked list with the right vendor first,
and "longest warranty period" answered in text without a result table. The checker accepts only a matching number / set in a result table. The one OCR difference is `auto_renew` left empty by Claude on a scan.
Module questions are checked against what each page shows (obligations, SLA, spend, exceptions, risk, benchmarks, review queue, alerts, templates, dashboard, vendors, key clauses), not against Ask's own SQL.
Ask over modules uses views `v_obligations, v_sla, v_invoices, v_spend_exceptions, v_vendor_scores, v_alerts, v_reviews, v_deviations, v_values` (offline: `app/ask_modules.py`; Claude: `prompts/schema.md`).
Known gap: estimated service credits are computed by the SLA page from Admin thresholds and are not queryable in Ask.

Raw output: `reports/parity_offline_*.txt`, `reports/parity_claude_*.txt`; earlier walkthrough videos in `reports/walkthrough-*/` (recorded before the document-derived feeds and module Ask).

## Where data comes from (no static rows)
Contracts, clauses, terms, obligations, redlines and checklist results: the contract documents. Invoices, monthly SLA reports and milestone acceptance certificates: **documents in `data/feeds/`**
(PDF, Word, Markdown, scans; or CSV exports) read by `app/opsdocs.py` and matched to contracts by vendor and reference. Thresholds, rules, risk weights, metrics: Admin configuration.
The fictional invoices / reports in the demo are *fixture documents* written by `app/docgen/ops_fixtures.py` for demos and tests only; the product never reads fixture rows, only the files.
Real invoices and SLA actuals cannot be derived from contracts: they must come from the customer's documents, exports or connectors.

## Run
`make dev`, then `make seed-pilot` (or `make seed` for the synthetic corpus). Without Docker: see README "Tests"/"Two corpora".
Config: `.env` (`ANTHROPIC_API_KEY` optional, `AUTH_MODE`, `OIDC_*`, `SECRET_KEY`, `CORS_ORIGINS`, `SCHEDULER_ENABLED`).
Swapping the Claude subscription for an API key: set `ANTHROPIC_API_KEY`; nothing else changes.

## Known limits (be honest with the pilot customer)
1. **Connectors are verified only against local Google Drive / Microsoft Graph stand-ins**, never a live tenant. Expect to debug permissions (Drive sharing, Graph app consent) on first real connection.
2. **OCR** is tested here with tesseract on clean and noisy image-only PDFs (contracts and invoices). Real scans (stamps, handwriting, low resolution) will be worse; Docker image installs tesseract but was not built here.
3. **Docker changes** (apt packages, `corpus/` mount, `make seed-pilot`) were written but not run: there was no Docker in the build environment.
4. **Embeddings** are the hashed offline kind; install `sentence-transformers` (`pip install -e ".[local-embeddings]"`) for real semantic clause search. Not validated here.
5. The ~2% extraction misses are mostly: unusual NDA/DPA parent references, personal-data flags on SOWs, a draft whose vendor is named only in a table, and non-standard notice wording.
6. **Offline Ask** handles the common question shapes (filters, groups, top-N, negations, dates); unusual phrasing needs Claude. Claude's Ask is stronger on free-form questions.
7. **Access control** is application-level. Not built: MFA, SCIM provisioning, per-tenant isolation, SOC 2 evidence. OIDC verified against a local key server only.
8. Alerts: e-mail verified against a local SMTP server, Slack/Teams/webhook against a local HTTP receiver, not the real services.
9. Offline engine rebuilds obligations without Claude's extra duties; run the pipeline in Claude mode to restore them.
10. The older `scripts/demo_walkthrough.js` is tied to the synthetic corpus; `scripts/demo_pilot.js` works on any corpus.

## First steps with real contracts
1. Put 10–20 redacted PDFs/Word files in `data/inbox/contracts/` (drafts in `data/inbox/drafts/`) or configure a connector.
2. Run the pipeline (Admin → Pipeline → Run now). Check Contracts for vendor / type / parent resolution; fix by adding a `.meta.json` sidecar if needed.
3. Review Admin → Values & limits and Thresholds against the customer's policy; add obligation rules for their duty types.
4. Load their AP / SLA exports as CSV; set alert channels; turn on `AUTH_MODE=on`.

## Review collaboration (G1, built)
Threaded comments anchored to selected text (add, reply, assign with due date, resolve, reopen, @mention through the alerts engine), AI playbook findings opened as threads (idempotent),
approval blocked while threads are open (HTTP 409), and share links (view / comment / edit, expiry, revoke) that guests open without an account at `/shared/<token>`. Tests: `tests/test_comments.py`.
Not yet built: comments exported into / imported from `.docx` (Word margin comments), live multi-cursor co-editing (guests and users save whole versions), authoring-side "suggesting" mode, e-mail delivery of comment notifications beyond the alert channels.

## Ariba / Coupa / SAP: what is needed (checked 2026-11)
* **SAP Ariba:** a registered application in the Ariba Developer Portal (requested by the customer's Ariba administrator) gives an application key + OAuth client; the portal's sandbox / "try out" calls work without production approval. Real data needs the customer's realm and approval.
* **Coupa:** OAuth 2.0 client (client-credentials) created by the customer admin under Setup > OAuth2/OpenID Connect Clients; partner / demo instances are on coupacloud.com. I found no public free tier; sandbox access comes through a customer or Coupa's partner programme.
* **SAP S/4HANA:** the SAP Business Accelerator Hub offers a free read-only sandbox API key for exploring APIs; a free S/4HANA Cloud trial exists but is limited (about 30 days, shared tenant, reduced features).
Plan: build to files first (invoice / PO exports are already read), then a configurable REST connector with mock-server tests, then live tests with the pilot customer's sandbox credentials.

## The ten gaps: status (all code committed; tests: 150 backend, offline module eval 62/62)
| # | Gap | Status |
|---|---|---|
| 1 | Comments, share links, Word comments | Built: threads, AI findings as threads, approval gate, share links with guest access, comments exported to / imported from `.docx`. Not built: live multi-cursor co-editing, suggesting mode |
| 2 | Approval routing | Built: rules by type / value / severity, ordered steps, notifications, reminders, UI |
| 3 | E-signature | Built: personal signing links (ordered), certificate, signature block extracted as signatories, mark executed; DocuSign client tested against a stand-in |
| 4 | Real-contract proof | Built: corrections that survive re-extraction, measured agreement, review-sheet round trip, `evals/real_eval.py`. **Needs 10-20 real contracts from you to produce the actual number** |
| 5 | Live connectors, mailbox | Built: IMAP mailbox intake (tested against a fake IMAP). **Live Google / Microsoft / mailbox tests need credentials** |
| 6 | Coupa / SAP / Ariba | Built: configurable REST connector with presets, OAuth client-credentials and API-key auth, paging, OData dates; tested against stand-ins. **Field names are presets to verify against the customer's instance; Ariba reporting is the least certain** |
| 7 | Security | Built: MFA, lockout, password policy, SCIM, headers, retention (see `docs/SECURITY.md`). Not built: multi-tenancy, SOC 2, pen test |
| 8 | Word add-in | Scaffold: manifest + task pane (comments, insert suggested wording, comment on selection) served at `/addin/`. **Not tested inside Word** |
| 9 | Docker / CI / ops | Built: CI workflow, backup script, metrics, JSON logs. **Docker image and the CI workflow have not been run** (no Docker / GitHub runner here) |
| 10 | Ask gaps, market table | Built: service credits queryable, answer-format rules for Claude. Market table re-checked: LinkSquares has a Word add-in with playbook redlining (our old "Authoring in Word: No" for contract-AI tools was wrong for it); most comparison material found is vendor-authored |
