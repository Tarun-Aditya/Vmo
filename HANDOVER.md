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

## Demo simulators (ERP and e-signature)
`SIMULATORS=1`: Coupa- and SAP-shaped invoice APIs generated from the loaded contracts (`app/simulators/erp.py`) and a DocuSign-compatible envelope API with a signing page and webhook (`app/simulators/esign.py`).
Tested through the real connector and DocuSign client code over HTTP (`tests/test_simulators.py`). They prove the integration path and the demo story, **not** that a real Coupa / SAP / DocuSign tenant behaves identically:
field names and auth are modelled on their public documentation and must still be checked against a customer's sandbox.

## Real-contract benchmark (CUAD, 510 public contracts with expert labels)
`python evals/cuad_eval.py <CUAD_v1 folder> --n 150 --seed 7`. Held-out results: offline rules governing law 72%, effective date 55%, termination-for-convenience recall 33%; **Claude (60 contracts): governing law 98%,
effective date 96%, termination for convenience precision 0.76 / recall 0.81**. Clause detection (rules, both modes), held-out: audit rights recall 0.76, assignment 0.79, insurance 0.81, liability cap 0.52, termination for
convenience precision 0.46. Use Claude mode for real customer contracts. CUAD is mostly licence / distribution agreements, not vendor MSAs.

## Update: embeddings, live collaboration, simulated external systems, real-contract accuracy
**Real sentence embeddings** (`fastembed`, BAAI/bge-small-en-v1.5, ONNX, no torch; falls back to hashed vectors offline): clause-search top-3 accuracy on 20 plain-English questions 40% -> 85% (`evals/retrieval_eval.py`).

**Live collaboration** (WebSocket `/ws/documents/<id>`): presence, instant push of comments, suggestions and new versions; *Suggesting* mode (propose a replacement, others accept / reject, accepted text becomes a new version); a save made from an out-of-date version is
refused with a conflict instead of overwriting a colleague. **Not built: character-level simultaneous typing in the same text (needs a CRDT editor).**

**Simulated external systems** (`SIMULATORS=1`, `PUBLIC_API_URL`; every one is exercised end to end through the real connector / client code over HTTP, `tests/test_simulators.py`):
Coupa- and SAP-shaped invoice APIs generated from your loaded contracts; **contract pulls** from Coupa, SAP and Ariba (documents + metadata, cross-checked: dates / auto-renew read from each pulled document equal the ERP record);
DocuSign-compatible envelopes with signing page and webhook; Google Drive, OneDrive and SharePoint; an IMAP mailbox; SMTP / Slack / Teams / webhook sinks (`/sim/outbox`); an OpenID Connect identity provider with a real SSO login flow.
One-click buttons: Admin -> Connectors (ERP, cloud drives, mailbox), Admin -> Alerts (demo channels), login page (SSO). These prove our side of each integration, not that a real tenant behaves identically.

**Real-contract accuracy (CUAD, 510 public contracts; 70% train / 30% hold-out fixed by file-name hash, hold-out never tuned on).** Hold-out, offline rules (133 contracts):
termination-for-convenience F1 0.66 (was 0.54), liability cap 0.87 (was 0.65), audit rights 0.88 (0.82), assignment 0.94 (0.87), insurance 0.90 (0.79), IP ownership 0.72 (0.67), non-solicit 0.81 (0.67); governing law 77% (72%), effective date 76% (55%), termination-for-convenience as a field: precision 0.71 / recall 0.63 (was 0.33).
Hold-out, Claude (60 contracts): governing law 98%, effective date 94%, termination for convenience precision 0.88 / recall 0.70. Services / maintenance / outsourcing / hosting subset (42 hold-out contracts): liability cap F1 0.91, assignment 0.92, non-solicit 0.95; IP ownership precision stays low (0.44).
Fixes that mattered: text before the first heading is no longer dropped, clauses are also found by sentence (not only by heading), loosely matched clauses must pass a sentence check, governing law is read from the governing-law sentence, effective date from the first "This ... Agreement" sentence.
Remaining gaps: IP ownership precision (licence wording), termination for convenience recall, governing law with several jurisdictions, offline effective date on messy exhibits. **CUAD has no VMO templates; the VMO-type subset above is the closest proxy, and results on real vendor MSAs from your customer are still unmeasured.**

**Other:** Claude module eval 60/62 (misses are answer-format only), lint now enforces real defects (`ruff` F/B/I), 161 backend tests pass.

## Update: hotel / property-operations edition (branch `hotel-property-ops`)
Everything above describes the VMO edition and its pilot corpus; it still holds for the shared engine. This branch adds a fictional hotel group (Seabright, six properties, 32 documents) and:

**Property level.** `properties` (rooms, city, kind), `contract_coverage`, view `v_property_contracts`: every contract is attributed to the properties it covers, group agreements by rooms,
so a property's cost includes its share of the energy contract and the hotel systems. Screens: Properties (cost per room, what makes it up), Compare (one vendor's rates and terms across
properties; the seeded laundry rates of 1.42 / 1.58 / 1.71 USD/kg are worth about $60K a year at the best rate, same volumes assumed), Certificates (what each vendor must hold, expiry of
the copy on file, alerts).

**Measured on the hotel corpus, offline (2026-11-14):** fields 456/457 (99.8%), metadata 126/128, values 84/85, planted draft deviations 17/17, clean control 0, about 7 findings per draft.
Claude mode was last measured before these changes (98.7% fields, 16/17, about 17 findings per draft) and has not been repeated. These figures are scored against the spec the documents
were written from: they prove the pipeline, not accuracy on unseen contracts.

**Measured on real public contracts (CUAD hold-out, 133 contracts, offline, never tuned on):** governing law 89.1% (was 76.5%), effective date 75.7%, liability cap F1 0.87,
assignment 0.94, insurance 0.90, audit rights 0.88, non-solicit 0.81, IP ownership 0.72, termination for convenience F1 0.66 (`reports/cuad_offline_holdout.txt`).

**Reading fixes that apply to any document:** PDF tables are rebuilt row by row (wrapped cells joined); 'Signed for and on behalf of ... by NAME, TITLE' wrapped over lines, or with the date
on its own line, is read; a signature table with dates but no typed names counts as signed; numbers above one hundred in words ('one hundred and eighty (180) days'); a party's state of
incorporation is no longer taken as the governing law; a heading that contains two clause names goes to the longer one ('Data Protection and Payment-Card Security' is not a payment clause);
an admin-defined clause is located at the passage matching most of its keywords, not its first mention.

**Rules and alerts.** Checklist rules can be limited to vendor categories. Spend alerts are one per vendor and kind; an alert whose cause is gone is resolved automatically; certificate
expiry is an alert rule. Seeded hotel data: 24 open alerts (46 before).

**Known limits specific to this edition**
1. No real hotel contract has been read. The corpus is set in the United States (decided 2026-11-14) and written from the property owner's side.
2. A property's share of a group agreement is an attribution by rooms, not a contract term; the Compare saving assumes unchanged volumes.
3. Certificate expiry dates come from a CSV or a person; certificate documents themselves are not read.
4. The exit-on-sale rule fails on every seeded master agreement because none of the fictional contracts contains that clause: a true finding on this data, but check it against real paper.
5. The recorded walkthrough video predates Compare, Certificates and the grouped rail.
6. A few milestone names read from Word tables are still rough.

**Later the same day.** Corpus moved to a United States setting (US dollars, New York house law, US cities, American spelling, month-first dates). Added: the owner's sale view per property
(exit on sale / on notice / inherited by a buyer), certificates read from certificate documents in `feeds/`, three property steps in the recorded walkthrough. Reading fix: a party's legal form
('a Delaware corporation') is no longer taken as the vendor name. Services-type subset of the real-contract hold-out (42 agreements, offline): governing law 91.9%, liability cap F1 0.91.
Not done because it needs you: a real invoice export or sandbox credentials for one live integration; redacted real contracts for `evals/real_eval.py`.
