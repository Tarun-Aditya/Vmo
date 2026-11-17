# The document pipeline

The pipeline is the heart of the system: it turns contract files into rows that every screen, rule
and question reads. Code: `backend/app/pipeline.py` (`run_pipeline`, `ingest_file`, `derive`,
`link_parents`), with the steps in the modules named below.

## Where documents come from

| Source | How it arrives | Code |
|---|---|---|
| Watched folders | files in the data folder's inbox, grouped into pipelines (folders per pipeline in `pipeline_config`) | `pipeline.scan`, `scheduler.py` |
| Upload | Admin → Pipeline (one file or many), `POST /api/admin/pipeline/files`, `/upload` | `routes_admin.py` |
| Sample folder | Admin → Pipeline → sample folder (the ten realistic contracts in `data/realistic_hotel/`) | `routes_admin.py` |
| Cloud drives | Google Drive, OneDrive, SharePoint: new or changed files are downloaded into the inbox, then read | `connectors/service.py` |
| Mailbox | attachments of unread mail in one IMAP folder | `connectors/mailbox.py` |
| Signed copies | a completed e-signature re-enters as an executed contract | `routes_signatures.py` |

Operational documents (invoices, monthly service-level reports, certificates) and CSV feeds take a
separate path into their own tables: the `feeds` pipeline (`feeds.py`, `opsdocs.py`).

## Triggers

Each pipeline has its own trigger (`scheduler.py`, ticking every 20 seconds):
**periodic** (every N minutes), **on_change** (as soon as its folders hold a new or changed file),
or **manual** (only Run now). Uploads and connector syncs start a run for the files they bring.
One run at a time: a second request gets `busy` and the upload endpoints retry until the pipeline is
free.

## What happens to each file

```
file ──► identity ──► read ──► structure ──► extract ──► index ──► check and derive
          (hash)      (text,     (clauses,     (fields      (vectors)  (values, checks,
                       pages)     types,        with                    deviations,
                                  metadata)     sources)                redline, duties)
```

**1. Identity (incremental).** A file whose size and modified time match the last run is not
opened. Otherwise it is hashed (SHA-256 of its bytes):

- same hash as last time at that path → *unchanged*;
- same hash as another document → a *duplicate*, not stored again; if that document's file has gone,
  the record is *moved* to the new path instead;
- a new or changed hash → read; a changed document keeps its id and its derived rows are rebuilt.

A sidecar `.meta.json` with a different `status` (for example the executed copy of a draft) makes
identical text a separate record. `force` re-reads a file regardless.

**2. Read** (`docstruct.load_document`). PDF through `pdftotext` with layout (tables rebuilt row by
row), scans through Tesseract OCR (pages rendered by `pdftoppm`), Word (`.docx`) through pandoc or a
built-in reader, HTML, Markdown and text. The result is Markdown with `<!-- page: n -->` markers, so every
later step knows its page.

**3. Structure** (`parsing.parse_document`, `kcc.classify`, `kcc.detect_in_text`,
`meta_rules`). The text is split into clauses by its headings and numbering. Each clause gets a type
from the key-clause library (39 built-in types in `kcc.default_kcc`, the hospitality pack's
additions, and any added in Admin) by heading, keywords and sentences; clauses defined in Admin are also found by sentence anywhere in the text. Document
metadata is worked out: title, counterparty, type (MSA, SOW, Work Order, NDA, SaaS, DPA, Services,
Amendment), category, property, status, and the reference to a parent agreement.

**4. Extract** (`extraction.py`, `extract_rules.py`). The contract's key fields (dates, renewal and
notice, value, payment terms, liability cap, termination for convenience, governing law, personal
data and DPA, signatories and signing dates) with a confidence, source clause and page:

- **Claude:** a forced tool call against a JSON schema (`prompts/extract_fields.md`), cached on disk
  by content.
- **Offline:** rules over normalised text (number words, "thirty (30)", money, many date formats,
  signature blocks and tables).
- **Demo mode, sample documents:** the result recorded earlier for that exact file (`recorded.py`).

With Claude available, clauses added in Admin are also tagged by meaning (`kcc_ai.py`); the quote
must appear in the document word for word. A person's correction (`field_corrections`) replaces the
extracted value and survives every re-read. An amendment records which terms it overrides
(`contracts.overrides`).

**5. Index** (`embeddings.py`). Each clause is embedded (BGE-small through fastembed, 384
dimensions, running locally; or sentence-transformers; or hashed words offline) and stored with its
text, type and page in `clauses`, for semantic search in Ask.

**6. Check and derive** (`derive`, `kcc.py`, `deviations.py`, `obligations.py`):

- **values and limits** configured in Admin → Values (response times, insurance cover, rates) into
  `extracted_values`;
- **checklist** rules (required or forbidden clauses, thresholds, banned wording; optionally only
  for some vendor categories) into `check_results`, with severity;
- **deviations** from the standard template and playbook into `clause_deviations`, and for drafts a
  full **redline** (suggested wording) into `redlines`; Claude redlines drafts when available
  (`REDLINE_LLM_SCOPE`);
- **obligations**: dated duties derived from clauses and values by the obligation rules.

## After the files: linking and portfolio updates

When every file in the run is done:

1. **Parents are linked** (`link_parents`, `meta_rules.resolve_parent`): a schedule, NDA or
   amendment is attached to its master agreement from what it says about it (exact title, or type,
   date and number), then from the usual hierarchy for the same vendor. Order of arrival does not
   matter.
2. Contracts of a vendor with a DPA are marked as covered.
3. Properties named in documents get records (`properties.sync`), and the certificates each vendor's
   clauses require are derived (`certificates.sync`).
4. The run is recorded in `pipeline_runs`, with one `pipeline_events` row per file (hash, size,
   action, reason), shown on Admin → Pipeline.

Effective terms are not stored: the view `v_effective_terms` applies amendments over the original at
query time and records which document each current value comes from. Renewals (`v_renewals`) compute
the last day to act as expiry minus notice period.

## Watching a run

`GET /api/admin/pipeline/live` returns the run in progress (or the last one), document by document:
each step's result as it happens (pages and words, OCR, clause types, fields with pages, vectors, failed
checks, last day to act) and, at the end, the parent and overridden terms. Admin → Pipeline shows it
whatever started the run. A run started by a file watcher that changed nothing leaves no history.

## Failures and speed

One bad file never stops a run: it is recorded as *failed* and retried next time. With Claude,
up to four files are read in parallel (Claude calls dominate the time); offline, files are read one
after another, a few seconds each. Changing configuration in Admin re-derives step 6 for every
stored document from its stored clauses, without reading files again (`reprocess_all` re-reads them
when asked).

## Measured accuracy

See `HANDOVER.md` and the README's accuracy section: offline, 99.8% of fields on the hotel corpus,
all planted draft deviations found, and results on public real contracts (CUAD). Accuracy on a
customer's own contracts, with Claude switched on, has not been measured yet.
