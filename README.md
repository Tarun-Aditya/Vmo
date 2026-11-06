# ContractIQ — vendor contract intelligence for VMOs (POC)

Live-demo POC over a fixed set of 28 fictional documents (5 templates, 18 executed contracts, 5 vendor
drafts) for the fictional customer **Arcadia Retail Ltd**. See `CLAUDE.md` for scope and conventions.

## Run it
```bash
cp .env.example .env          # add ANTHROPIC_API_KEY for the live Claude path (optional, see below)
make dev                      # db + api + web  ->  http://localhost:5173  (api: :8000/health)
make seed                     # generate docs, extract, embed, redline, cache demo answers (idempotent)
make eval                     # extraction, redline and 15-question Ask evals
make test                     # pytest
```
Dates in the documents are relative to the seed run, so **re-run `make seed` on the day of the demo.**

### Two engines
| | With `ANTHROPIC_API_KEY` | Without (offline engine) |
|---|---|---|
| Extraction | Claude, forced tool call + JSON schema, confidence + source clause | regex extractor over the same text |
| Redline / deviations | Claude judges each changed clause vs playbook | word diff + pattern library |
| Ask | Claude tool-use loop (`run_sql`, `search_clauses`, `get_contract`); aggregate questions answered headline → breakdown → list | scripted plans for the demo questions, plus an offline planner for counts / totals / group-by over time windows and filters (`ask_nl.py`) |
| Embeddings | `sentence-transformers` if installed (`pip install -e ".[local-embeddings]"`) else hashed bag-of-words | hashed bag-of-words |

LLM results are cached on disk (`data/.cache/llm`) so re-seeding is free. **Demo mode** (header toggle) answers
Ask from the `ask_cache` table filled at seed time, so the demo is instant and wifi-proof. The header badge
shows which engine is live. Offline-engine eval scores prove the plumbing and data, not Claude's quality:
run `make seed` + `make eval` with a key to measure the real thing.

## Demo script (~8 min)
1. **Problem (30s)** — "Arcadia's VMO tracks vendor contracts across Excel and SharePoint and missed 2 auto-renewals."
2. **Expiry dashboard (1m)** — three lanes: expiring in 0–30 / 31–60 / 61–90 days (4 / 1 / 3 contracts, ₹ at stake per lane).
   AdSpark is flagged "notice deadline passed"; the 12-month chart; uncapped liability; PulseHR processes personal data with no DPA.
3. **Repository + hierarchy (1m)** — Table: start / end dates, value, signature status, flags. Switch to **Hierarchy**:
   MSA → SOW → **Work Order**, with amendments, NDAs and DPAs under their agreement. Work Order 2 is ✗ pending (supplier has not countersigned).
4. **Contract detail (1m)** — signatures card; click "Payment terms" → source clause highlights; effective terms show 45→30 "Overridden by Amendment No. 1".
5. **Key clauses (1.5m)** — every document × every key clause, green ✓ / red ✗. Hover a ✓ for the citation (clause text + page); hover a ✗ for why it is absent.
   Boxed ✗ = the standard template requires it (a gap), e.g. the Quantum draft has no Return of Data clause.
6. **Ask (2.5m)** — answers are tables; the SQL is under a collapsed **Thinking** section.
   "Show start date, end date and signatures for all contracts" · "Which contracts are not fully signed?" ·
   "Which contracts do not have an audit rights clause?" · "Show the key clauses in the Bluepeak MSA" ·
   aggregate: "How many contracts are expiring in the next quarter?" (tiles → breakdown → list). Open **Thinking** to show the steps.
7. **Redline (1.5m)** — Zenith MSA: 5 deviations; the clean control: none. **Templates (1m)** — heatmap of where contracts drifted.
8. **Close (30s)** — roadmap: upload + OCR, alerts, integrations, multi-tenant.

`NODE_PATH=$(npm root -g) node scripts/demo_smoke.js` walks every screen and fails on any console error (run it twice before going on stage).

## Notes
- Severity values are `low | medium | high | critical`. "Uncapped" means a liability clause that states liability is unlimited
  (`v_effective_terms.liability_uncapped`); NDAs/SOWs/DPAs with no cap clause are not counted.
- Catalogue metadata (vendor, category, owner, parent links) comes from `data/manifest.json`; the 12 key fields are extracted from text.
  `data/labels.json` is ground truth used only by evals. Generated files under `data/` are git-ignored.
- Signatures are extracted from the Execution clause (signatory + date per party; `fully_executed` only when both signed).
- Migration 0003 adds Work Orders, signature columns and `v_key_clauses`; it cannot be downgraded (recreate the DB instead).
- Read-only role `vmo_readonly` (migration 0001/0002) backs `run_sql`; it cannot read embeddings, `llm_calls` or `ask_cache`.
