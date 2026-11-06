"""Seed = generate the fictional corpus into the inbox folder, then run the pipeline over it.
The seeded data therefore takes exactly the path a document dropped into the folder takes.
Idempotent: content tables are rebuilt; admin configuration (KCC / metrics / checklist) is kept."""
from __future__ import annotations

import json
import sys
import time
from datetime import date

from sqlalchemy import text

from app import kcc, pipeline
from app.config import data_path
from app.db import SessionLocal
from app.docgen.generate import generate


def run(seed_date: date | None = None, extractor: str = "auto", redline_mode: str = "auto", log=print) -> dict:
    t0 = time.time()
    seed_date = seed_date or date.today()
    root = data_path()
    manifest = generate(root, seed_date)
    log(f"generated {len(manifest['templates'])} templates, {len(manifest['contracts'])} contracts, "
        f"{len(manifest['drafts'])} drafts into {root / 'inbox'} (seed date {seed_date})")
    with SessionLocal() as s:
        s.execute(text("TRUNCATE templates, template_clauses, contracts, clauses, field_extractions, clause_deviations, "
                       "extracted_values, check_results, redlines, ask_cache, pipeline_events, pipeline_runs, conversations, chat_messages RESTART IDENTITY CASCADE"))
        kcc.ensure_defaults(s)
        s.execute(text("UPDATE pipeline_config SET inbox_path = NULL, last_run_at = NULL, next_run_at = NULL, last_fingerprint = NULL"))
        s.execute(text("UPDATE pipeline_config SET enabled = false, trigger_mode = 'periodic', interval_minutes = 120, folders = 'contracts,uploads' WHERE key = 'contracts'"))
        s.execute(text("UPDATE pipeline_config SET enabled = false, trigger_mode = 'on_change', interval_minutes = 15, folders = 'drafts,generated' WHERE key = 'drafts'"))
        s.commit()
    res = pipeline.run_pipeline("seed", extractor, log=lambda r: log(f"pipeline: {r}"))
    with SessionLocal() as s:       # pipelines were paused while seeding so a running API scheduler cannot race the seed
        s.execute(text("UPDATE pipeline_config SET enabled = true"))
        s.commit()
    stats = dict(pipeline=res)
    try:
        from app import ask

        stats["ask_cached"] = ask.precompute_demo_answers(log=log)
    except ImportError:
        pass
    stats["seconds"] = round(time.time() - t0, 1)
    log("seed complete: " + json.dumps(stats, default=str))
    return stats


if __name__ == "__main__":
    args = sys.argv[1:]
    d = date.fromisoformat(args[0]) if args and args[0][0].isdigit() else None
    run(d)
