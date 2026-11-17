# Setup and running

How to get ContractIQ (hotel edition) running, load data, switch between the offline engine and
Claude, and run the tests and evaluations. For what the system does, start with the main
`README.md`; for how it is built, `docs/ARCHITECTURE.md`.

## Requirements

| | With Docker | Without Docker |
|---|---|---|
| Database | provided (`pgvector/pgvector:pg16`) | Postgres 16 with the `pgvector` extension |
| Backend | provided | Python 3.12 |
| Frontend | provided | Node 20 or later |
| Reading documents | provided in the API image | `poppler-utils` (PDF), `tesseract-ocr` (scans), `pandoc` (Word); LibreOffice only to render the sample corpora as Word and PDF |
| Claude (optional) | an `ANTHROPIC_API_KEY`, or the `claude` CLI logged in | same |

No API key is needed: the offline engine (rules and a local embedding model) is the default and
everything the demo needs is committed to the repository.

## Run with Docker

```bash
cp .env.example .env          # optional: edit models, keys and simulators
make showcase                 # build, start db + api + web, migrate, seed the hotel corpus
```

Then open http://localhost:5173 (the app) and http://localhost:8000/docs (the API). `make showcase`
is the one-command path; the pieces are:

| Command | What it does |
|---|---|
| `make up` / `make down` | start / stop the three containers (`db`, `api`, `web`) |
| `make dev` | start in the foreground with logs |
| `make migrate` | `alembic upgrade head` inside the API container |
| `make seed-hotel` | generate and read the Seabright hotel corpus (32 documents, 6 hotels) |
| `make seed-pilot` | the 36-document pilot corpus instead |
| `make seed` | the original synthetic VMO corpus (28 documents) |
| `make seed-offline` | `make seed` with the offline engine forced |

The API container mounts `./data/hotel` as its data folder and sets `STANDARDS=hotel` and
`CUSTOMER_NAMES=Seabright` (see `docker-compose.yml`).

## Run without Docker

```bash
# database: create the role and database, then the extension (as a superuser)
createuser -s vmo; createdb -O vmo vmo_hotel
psql -d vmo_hotel -c "ALTER USER vmo PASSWORD 'vmo'; CREATE EXTENSION IF NOT EXISTS vector;"

# backend
cd backend
pip install -e ".[dev]"
export DATABASE_URL=postgresql+psycopg://vmo:vmo@localhost:5432/vmo_hotel
export READONLY_DATABASE_URL=postgresql+psycopg://vmo_readonly:vmo_readonly@localhost:5432/vmo_hotel
export DATA_DIR=../data/hotel STANDARDS=hotel CUSTOMER_NAMES=Seabright SIMULATORS=1
alembic upgrade head          # also creates the read-only role used by Ask
python -m app.seed --hotel
uvicorn app.main:app --port 8000

# frontend (second terminal)
cd frontend && npm ci && npm run dev        # http://localhost:5173
```

Optional extras: `pip install -e ".[local-embeddings]"` for sentence-transformers (pulls PyTorch),
`pip install -e ".[claude-code]"` to run Claude through the Claude Code CLI.

## Configuration

Settings are read from the environment (and `.env`, through `backend/app/config.py`). The ones you
are likely to set:

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://vmo:vmo@localhost:5432/vmo` | main database |
| `READONLY_DATABASE_URL` | the `vmo_readonly` role on the same database | used by Ask's SQL tool (SELECT only) |
| `DATA_DIR` | `/data` (falls back to `./data`) | inbox, feeds, templates; `../data/hotel` for the hotel edition |
| `STANDARDS` | empty | `hotel` gives the template library the hotel group's house clauses and values |
| `CUSTOMER_NAMES` | `Arcadia` | comma-separated names our own company goes by in contracts (`Seabright`) |
| `LLM_PROVIDER` | `auto` | `auto` (API key, else Claude Code CLI, else offline), `api`, `claude_code`, `offline` |
| `ANTHROPIC_API_KEY` | empty | Claude through the API |
| `MODEL_EXTRACT`, `MODEL_ASK`, `MODEL_REDLINE` | `claude-sonnet-5-5` | model per task |
| `REDLINE_LLM_SCOPE` | `drafts` | which documents Claude redlines: `drafts`, `all`, `none` |
| `EMBEDDING_PROVIDER` | `auto` | `fastembed` (BGE-small, local), `local` (sentence-transformers), `hash` (offline) |
| `SIMULATORS` | `0` (`1` in Docker) | mount the stand-in ERP, e-signature, drive, mailbox and SSO systems under `/sim` |
| `SCHEDULER_ENABLED` | `1` | background pipeline runs and alert evaluation |
| `AUTH_MODE` | `off` | `on` enforces sign-in, roles and property limits |
| `SECRET_KEY` | generated file `data/.secret_key` | Fernet key for stored connector and MFA secrets |
| `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_AUDIENCE`, `OIDC_JWKS_URL`, `OIDC_ROLES_CLAIM`, `OIDC_DEFAULT_ROLE` | | single sign-on with OpenID Connect |
| `DOCUSIGN_*` | | a real DocuSign account instead of the simulator |
| `CORS_ORIGINS`, `PUBLIC_API_URL`, `WEB_URL` | localhost | addresses for links, callbacks and the browser |
| `HSTS`, `LOG_JSON` | `0` | HSTS header behind TLS; JSON logs |
| `AUDIT_RETENTION_DAYS`, `ALERT_RETENTION_DAYS` | `0` (keep) | retention of audit entries and finished alerts |
| `RECORDED_PATH` | `data/realistic_hotel/recorded.json` | recorded results replayed in Demo mode |

Everything about *what* is read and checked (key clauses, values, checklist rules, thresholds,
risk weights, obligation and alert rules, approval chains, connectors, pipelines) is configuration
in the database, edited on the Admin pages, not environment variables.

## Demo mode and Claude

The switch at the top of the app (stored in `app_settings.demo_mode`) decides the engine:

- **Demo mode on:** no Claude anywhere. Extraction, key-clause tagging, redline and Ask run on the
  offline engine and cached results; external systems are the simulators; the ten sample contracts
  in `data/realistic_hotel/` replay results recorded earlier. Fast and works without a network.
- **Demo mode off (Live):** every module uses Claude through `LLM_PROVIDER`. If Claude is
  unreachable or hits a limit, the module falls back to the offline engine and says so.

Every Claude call is logged in `llm_calls` (model, tokens, time, cost) and shown on Admin → AI usage.

## Loading your own documents

Drop PDF, Word, HTML, Markdown or text files into the data folder's inbox (or a watched pipeline
folder), use Admin → Pipeline (upload, sample folder, Run now), connect a drive or mailbox in
Admin → Connectors, or call `POST /api/admin/pipeline/files`. See `docs/PIPELINE.md`. The README's
"Measure it on your own contracts" section explains how to check accuracy on them.

## Tests

The suite needs its own database and data folder, because tests reseed:

```bash
createdb -O vmo vmo_test && psql -d vmo_test -c "CREATE EXTENSION IF NOT EXISTS vector;"
cd backend
export DATABASE_URL=postgresql+psycopg://vmo:vmo@localhost:5432/vmo_test
export READONLY_DATABASE_URL=postgresql+psycopg://vmo_readonly:vmo_readonly@localhost:5432/vmo_test
export DATA_DIR=../data_test
alembic upgrade head
mkdir -p ../data_test && cp -r ../data/templates ../data_test/ && python -m app.seed
pytest -q
```

`tests/conftest.py` forces the offline engine, disables the scheduler and recorded replay, and
mounts the simulators, so results do not depend on what is installed. The full suite takes more
than ten minutes; to split it, run part of it at a time, for example
`pytest -q tests/test_api.py tests/test_pipeline.py`. With Docker: `make test`.

Frontend: `cd frontend && npx tsc --noEmit && npm run build`. Lint: `make lint` (ruff and black).
CI (`.github/workflows/ci.yml`) runs the backend tests, two offline evaluations and the frontend
build.

## Evaluations

Accuracy is measured against ground-truth labels, never against the database:

| Command (from `backend/`) | Measures |
|---|---|
| `python ../evals/extraction_eval.py` | field accuracy on the synthetic corpus |
| `LABELS=labels_hotel.json python ../evals/pilot_eval.py` | fields, metadata and values on the hotel corpus |
| `python ../evals/hotel_redline_eval.py` | planted deviations found in the five hotel drafts |
| `QUESTIONS=questions_hotel.yaml LABELS=labels_hotel.json python ../evals/pilot_ask_eval.py` | the 13 owner questions in Ask |
| `python ../evals/module_eval.py`, `ops_eval.py`, `ocr_eval.py`, `retrieval_eval.py` | module answers, operational documents, scans, clause search |
| `make cuad` | public real contracts (CUAD) |

Results are kept in `reports/`; the numbers and their limits are summarised in `HANDOVER.md`.

## Regenerating the reference docs

`docs/reference/API.md` and `docs/reference/DATABASE.md` are generated. After changing endpoints or
migrations, with the database migrated:

```bash
cd backend && python ../scripts/gen_reference_docs.py      # or: make reference-docs (on the host, backend installed)
```

## Troubleshooting

- **`connection refused` on port 5432:** Postgres is not running. On Debian-style hosts:
  `pg_ctlcluster 16 main start`.
- **Ask fails with a permission or connection error:** check that `READONLY_DATABASE_URL` points to the
  same database as `DATABASE_URL`; the `vmo_readonly` role and its grants are created by the migrations.
- **A PDF or scan fails to read:** `pdftotext`, `pdftoppm` or `tesseract` is not installed on the machine
  running the API (the error says which). Word files fall back to a built-in reader without pandoc.
- **A pipeline run says "busy":** one run at a time; wait for it, or watch Admin → Pipeline.
- **Nothing changes after editing a rule:** rules re-derive stored text; a new document needs a
  pipeline run (Admin → Pipeline → Run now).
