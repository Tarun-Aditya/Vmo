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
| Ask | Claude tool-use loop (`run_sql`, `search_clauses`, `get_contract`) | scripted plans for the 15 demo questions only |
| Embeddings | `sentence-transformers` if installed (`pip install -e ".[local-embeddings]"`) else hashed bag-of-words | hashed bag-of-words |

LLM results are cached on disk (`data/.cache/llm`) so re-seeding is free. **Demo mode** (header toggle) answers
Ask from the `ask_cache` table filled at seed time, so the demo is instant and wifi-proof. The header badge
shows which engine is live. Offline-engine eval scores prove the plumbing and data, not Claude's quality:
run `make seed` + `make eval` with a key to measure the real thing.

## Demo script (~8 min)
1. **Problem (30s)** — "Arcadia's VMO tracks 18 vendor contracts across Excel and SharePoint and missed 2 auto-renewals."
2. **Dashboard (1m)** — 4 contracts expire within 30 days; AdSpark's non-renewal notice deadline already passed (red, ▲▲);
   ₹ value at stake per bucket; 3 uncapped-liability contracts; PulseHR processes personal data with no DPA.
3. **Contract detail (1m)** — open *MSA – Bluepeak*: click "Payment terms" → source clause highlights on page 2, confidence badge.
   *Effective terms* shows payment 45→**30**, liability 1×→**2×**, expiry extended — each "Overridden by Amendment No. 1". Hierarchy shows MSA → 3 SOWs → amendment → NDA.
4. **Ask (2m)** — (a) "Which vendors have uncapped liability?" → expand *How I got this* to show the SQL and rows.
   (b) "Which contracts give the vendor ownership of the deliverables we pay for?" → cited clause + page.
   (c) "Which auto-renewing contracts have uncapped liability, and what does their liability clause say?" → SQL + clause search.
5. **Redline (1.5m)** — *Draft MSA – Zenith*: 5 deviations (unlimited liability critical, one-way indemnity, no termination for
   convenience…) with struck-through original and inserted standard wording. Click **Re-run live**. Show the clean control: "No deviations".
6. **Templates (1m)** — SaaS template heatmap: every SaaS contract drifts on Renewal; AdSpark and PulseHR on liability.
7. **Close (30s)** — roadmap: upload + OCR, alerts, integrations, multi-tenant.

`NODE_PATH=$(npm root -g) node scripts/demo_smoke.js` walks every screen and fails on any console error (run it twice before going on stage).

## Notes
- Severity values are `low | medium | high | critical`. "Uncapped" means a liability clause that states liability is unlimited
  (`v_effective_terms.liability_uncapped`); NDAs/SOWs/DPAs with no cap clause are not counted.
- Catalogue metadata (vendor, category, owner, parent links) comes from `data/manifest.json`; the 12 key fields are extracted from text.
  `data/labels.json` is ground truth used only by evals. Generated files under `data/` are git-ignored.
- Read-only role `vmo_readonly` (migration 0001/0002) backs `run_sql`; it cannot read embeddings, `llm_calls` or `ask_cache`.
