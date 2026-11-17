# Development guide

How to work on the code: conventions, the common changes and how to test them. Setup is in
`docs/SETUP.md`, the structure in `docs/ARCHITECTURE.md`.

## Conventions

- **Python:** 3.12, type hints, `ruff` and `black` (`make lint`; config in `backend/pyproject.toml`,
  line length 160, ruff checks real defects and import order).
- **TypeScript:** strict, checked by `npx tsc --noEmit`; Tailwind for styling; TanStack Query for
  every server call (through `api()` in `frontend/src/lib.ts`).
- **Prompts** live in `backend/app/prompts/*.md` and are loaded by name (`llm.py`), never inline.
- **Schema changes** go in a new Alembic migration, never in the ORM models alone. Migrations are
  plain SQL through `op.execute`, written to be re-runnable (`IF NOT EXISTS`). View SQL lives in
  `app/viewsql.py` so a later migration can recreate a view after changing its columns.
- **Configuration over code:** a new rule, value or clause type should be a row a person can edit
  in Admin, with defaults in code (`kcc.default_*`, `hotel_pack.py`, `config_items.py`).
- **Offline counterpart:** anything that calls Claude needs a deterministic offline path, used in
  Demo mode, in the tests and as the fallback.
- **New libraries:** say why in the commit; prefer the standard library or what is already installed.
- **Commits:** small, conventional messages (`feat(ask): ...`, `fix(pipeline): ...`,
  `docs: ...`).
- **Fictional data only** in the repository: no real company names or contract text.

## Common changes

**Add a field the pipeline extracts**

1. Migration: add the column to `contracts` (and to `OVERRIDABLE` in `viewsql.py` and
   `pipeline.py` if an amendment can change it; recreate `v_effective_terms`).
2. `extraction.py`: add it to the schema; describe it in `prompts/extract_fields.md`.
3. `extract_rules.py`: the offline rule.
4. `pipeline.ingest_file`: map it into the contract's attributes.
5. Ground truth in the labels files and a check in `evals/`; describe it in `prompts/schema.md` so
   Ask can query it.

**Add a key clause, value or checklist rule.** Normally in Admin. To ship it as a default, add it to
`kcc.default_kcc`, `default_metrics` or `default_rules` (or `hotel_pack.py`); `kcc.ensure_defaults`
brings stored defaults up to date without touching what admins added.

**Add an endpoint.** In the matching `routes_*.py`, with a one-line docstring (it becomes the
summary in `docs/reference/API.md` and Swagger). If property managers should reach it, add it to the
allow-list in `app/scope.py`; every other path is refused to them by default. Regenerate the
reference (`make reference-docs`).

**Add a screen.** A file in `frontend/src/pages/`, its route in `main.tsx`, a link in `ui.tsx`
(the rail or **More**) or in `pages/admin/AdminLayout.tsx` for Admin.

**Add a table or view.** A migration; then regenerate `docs/reference/DATABASE.md` and, if Ask
should use it, describe it in `prompts/schema.md` and, for property-limited users, in `scope.py`.

**Add a connector.** A class in `connectors/` following `connectors/base.py`, registered in
`connectors/service.py`; a simulator in `simulators/` with the same API shape for tests and demos.

## Tests

`backend/tests/` (pytest, 33 test files) runs against a real Postgres with a seeded corpus;
`conftest.py` forces the offline engine and disables the scheduler and recorded replay. Put pure
logic (date maths, effective terms, rules) in unit tests that need no database; put API behaviour in
tests that use the `seeded` fixture. Run a single file while working:

```bash
cd backend && pytest -q tests/test_pipeline.py
```

Areas and their tests: pipeline and reading (`test_pipeline`, `test_realdocs`, `test_ocr`,
`test_intake`, `test_realistic_contracts`, `test_recorded`), clauses and rules (`test_kcc`,
`test_deviations`), Ask (`test_ask_loop`, `test_ask_nl`), views (`test_views`), hotel and property
managers (`test_hotel`, `test_property_manager`), security (`test_auth`, `test_security`), review
and signing (`test_review_editor`, `test_comments`, `test_approvals`, `test_signatures`),
integrations (`test_connectors`, `test_erp_mailbox`, `test_simulators`).

## Evaluations

Accuracy is measured against ground truth in `data/**/labels*.json` and `evals/questions*.yaml`,
never against the database (see `docs/SETUP.md` for the commands). When fixing an extraction or Ask
bug, add the case to the labels or questions so it stays fixed, and record the new numbers in
`HANDOVER.md`.

## Documentation

| File | Keep up to date when |
|---|---|
| `README.md` | features, setup or limits change |
| `docs/ARCHITECTURE.md`, `PIPELINE.md`, `DATA_MODEL.md` | modules, pipeline steps or core tables change |
| `docs/reference/API.md`, `DATABASE.md` | regenerate after any endpoint or migration (`make reference-docs`) |
| `HANDOVER.md` | measured results or known limits change |
| `DEMO.md`, `reports/presentation/` | the demo story changes |
