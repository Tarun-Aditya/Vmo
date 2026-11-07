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

## Measured results (36-document pilot corpus, 2026-11-07)
| | Offline engine | Claude (subscription) |
|---|---|---|
| Extraction vs spec labels (`evals/pilot_eval.py`) | 774/783 (98.9%) | 769/783 (98.2%) |
| Ask, 8 portfolio questions (`evals/pilot_ask_eval.py`) | 8/8 | 8/8 |
| Browser walkthrough (`scripts/demo_pilot.js`) | 10/10 checks | 11/11 checks |
| Backend tests (synthetic corpus, offline) | 116 passed | – |

Raw output: `reports/pilot_eval_*.txt`, `reports/pilot_ask_claude.txt`; videos and screenshots: `reports/walkthrough-claude/`, `reports/walkthrough-offline/`; UI screenshots of alerts and access: `reports/shots/`.
Claude numbers on extraction were produced partly from the on-disk result cache (same prompts, same documents); the Ask run was live.
The Claude extraction score was last measured before the total-fee extraction fix and the hybrid gap-fill landed in the *rules*; re-run `python evals/pilot_eval.py` to refresh.

## Run
`make dev`, then `make seed-pilot` (or `make seed` for the synthetic corpus). Without Docker: see README "Tests"/"Two corpora".
Config: `.env` (`ANTHROPIC_API_KEY` optional, `AUTH_MODE`, `OIDC_*`, `SECRET_KEY`, `CORS_ORIGINS`, `SCHEDULER_ENABLED`).
Swapping the Claude subscription for an API key: set `ANTHROPIC_API_KEY`; nothing else changes.

## Known limits (be honest with the pilot customer)
1. **Connectors are verified only against local Google Drive / Microsoft Graph stand-ins**, never a live tenant. Expect to debug permissions (Drive sharing, Graph app consent) on first real connection.
2. **OCR** for scanned PDFs is implemented (needs `tesseract` + `pdftoppm`); not exercised here because tesseract is not installed in this sandbox. The Docker image now installs it, untested.
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
