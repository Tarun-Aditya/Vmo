# ContractIQ — vendor contract intelligence for VMOs (POC)

Live-demo POC for **Arcadia Retail Inc.**'s Vendor Management Office, over an enterprise **IT-services portfolio in USD**:
a global systems integrator, a Big-4-style consultancy, an offshore IT services major, a web-infrastructure software
vendor and SaaS suppliers (all **fictional lookalikes** — no real company names). 32 documents: 6 standard templates,
27 executed contracts (MSA → SOW → Work Order, amendments, NDAs, DPAs, SaaS) and 5 vendor drafts. See `CLAUDE.md` for scope.

## Run it
```bash
cp .env.example .env          # add ANTHROPIC_API_KEY for the live Claude path (optional, see below)
make dev                      # db + api + web  ->  http://localhost:5173  (api: :8000/health)
make seed                     # generate the corpus into the inbox folder and run the pipeline (idempotent)
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
* **Folder pipeline** — anything dropped into `data/inbox/` (Markdown or text) is picked up and processed; vendor, type and
  parent are read from the document. A file is re-processed only when its content changes. The **async scheduler** runs the
  pipeline on a configurable frequency (default every 2 hours; Admin → Pipeline) and on demand. The seed uses the same path.
* **Admin** (⚙) configures what the platform identifies, extracts and checks — every change re-runs over all documents:
  * **Key clause library** — which clauses to identify (heading aliases + keywords), what the standard says, whether each shows
    in the matrix. Add any number; a new clause becomes a column in Key clauses and in Ask. *Preview matches* before saving.
  * **Values & limits** — the numbers to extract from a clause (regex → number/text): payment days, liability cap multiple,
    insurance cover, notice periods, uptime, governing law…
  * **Redline checklist** — rules run on a contract before signing: clause required / absent, value vs threshold, forbidden
    wording; severity, where it applies, suggested replacement wording.
  * **Pipeline** — frequency, run now, add a document, run history with per-document events.
* **New contract** — pick a template (MSA/SOW/Work Order/NDA/SaaS/DPA), set the terms, edit the text with a live checklist,
  create the draft: it is dropped into the folder, extracted, and appears everywhere.
* **Ask** — *analytical* questions over the whole portfolio, or questions about **specific documents** chosen (search +
  select) in the panel on the right. Answers are tables; the SQL and steps are under a collapsed **Thinking** section.

### Two engines
| | With `ANTHROPIC_API_KEY` | Without (offline engine) |
|---|---|---|
| Extraction | Claude, forced tool call + JSON schema | regex extractor over the same text |
| Redline / deviations | Claude judges each changed clause vs playbook | word diff + pattern library |
| Checklist, values, clause identification | same (rule engine, no LLM needed) | same |
| Ask | Claude tool-use loop (`run_sql`, `search_clauses`, `get_contract`) over the extracted data | scripted plans for the demo questions + a planner for counts, totals, group-by, windows, filters, columns, thresholds, checklist, vendor-level and scoped questions |
| Embeddings | `sentence-transformers` if installed (`pip install -e ".[local-embeddings]"`) else hashed bag-of-words | hashed bag-of-words |

The header badge shows the engine. Offline eval scores prove the plumbing and data, not Claude's quality — run
`make seed && make eval` with a key to measure the real thing. **Demo mode** answers the preloaded questions from cache.

## Demo script (~10 min)
1. **Dashboard (1m)** — USD; contracts expiring in the next 30 / 60 / 90 days with $ at stake; AdSpark's notice deadline has passed.
2. **Vendors (1m)** — Accentia / Delmont / Taraka / Nginova…: spend, next dates, risk flags; open Accentia: MSA → SOW → Work Order tree.
3. **Contract detail (1m)** — signatures, terms & limits, checklist, effective terms ("payment 45→30, overridden by Amendment No. 1"); Work Order inherits its MSA's terms.
4. **Key clauses (1m)** — every document × every key clause ✓/✗; hover for the citation; Work Order 2 is unsigned.
5. **Ask — portfolio (2m)** — "How many contracts are expiring in the next quarter?" · "Which contracts have payment terms below 45 days?" · "Which contracts fail the checklist?"; open **Thinking**.
6. **Ask — specific documents (1m)** — switch to *Selected documents*, search "delmont", tick the MSA: "Tell me about this contract", "What does the indemnity clause say?"; tick a draft: "Which checklist rules does it fail?".
7. **Review before signing (1m)** — a vendor draft: checklist failures with the clause cited and suggested wording; the redline.
8. **New contract (1m)** — SOW from the template under the Accentia MSA with 20-day payment terms → the checklist flags it → edit → re-check → create.
9. **Admin (1.5m)** — pipeline schedule & add-a-document; add a key clause → new matrix column; tighten a threshold → everything re-checks.

`NODE_PATH=$(npm root -g) node scripts/demo_walkthrough.js` walks every screen above (≈85 assertions) and records a captioned video.

## Notes
- Severity values are `low | medium | high | critical`. "Uncapped" means a liability clause that states liability is unlimited.
- Currency is USD throughout (documents, extraction, UI, Ask). Governing-law standard is New York.
- Drafts are ordinary documents with status `draft`: excluded from portfolio numbers (dashboard, vendors, Ask) but visible in
  the repository, key-clause matrix, Redline and scoped Ask.
- Catalogue metadata (category, owner, parent links) comes from an optional `.meta.json` next to a document, else is inferred
  from the document; `data/labels.json` is ground truth used only by the evals. Generated files under `data/` are git-ignored.
- The read-only role `vmo_readonly` backs `run_sql`; it cannot read embeddings, pipeline tables, `llm_calls` or `ask_cache`.
- Migrations 0003+ cannot be downgraded (recreate the database). The scheduler runs inside the API process (one worker).
