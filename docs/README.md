# Documentation

ContractIQ reads contract documents (PDF, Word, scans) and turns them into structured, linked data:
clauses, key terms with their sources, values, checks, obligations and links between agreements.
Every screen, rule, alert and answer is computed from that one dataset.

## Where to start

| If you want to | Read |
|---|---|
| Know what it does and see it run | [`../README.md`](../README.md) |
| Install it, configure it, run tests and evaluations | [`SETUP.md`](SETUP.md) |
| Understand how it is built | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| Follow a document from file to rows | [`PIPELINE.md`](PIPELINE.md) |
| Understand the tables and views | [`DATA_MODEL.md`](DATA_MODEL.md) |
| Change the code | [`DEVELOPMENT.md`](DEVELOPMENT.md) |
| Look up an endpoint | [`reference/API.md`](reference/API.md) (generated) |
| Look up a table, column or index | [`reference/DATABASE.md`](reference/DATABASE.md) (generated) |
| Review security controls and gaps | [`SECURITY.md`](SECURITY.md) |
| Know what was measured, and the limits | [`../HANDOVER.md`](../HANDOVER.md) |
| Run the product demo | [`../DEMO.md`](../DEMO.md) |
| Present the idea to leadership | [`../reports/presentation/README.md`](../reports/presentation/README.md) |
| Know the original scope and conventions | [`../CLAUDE.md`](../CLAUDE.md) |

## In one picture

```
 sources                 pipeline (per file)                          one database          used by
 ───────                 ───────────────────                          ────────────          ───────
 folders, uploads   ─►   identity (hash) ─► read ─► structure ─►      contracts, clauses,   screens
 drives, mailbox         extract ─► index ─► check and derive    ─►   fields, values,   ─►  Ask
 ERP, feeds         ─────────────────────────────────────────────►   checks, duties,       alerts
                                                                      invoices, ...         rules
```

The reference pages are generated from the code and the database by
`scripts/gen_reference_docs.py`; the others are written by hand and should be updated with the
change that makes them out of date.
