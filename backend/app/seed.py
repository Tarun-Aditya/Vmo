"""Seed = generate the fictional corpus into the inbox folder, then run the pipeline over it.
The seeded data therefore takes exactly the path a document dropped into the folder takes.
Idempotent: content tables are rebuilt; admin configuration (KCC / metrics / checklist) is kept."""
from __future__ import annotations

import csv
import json
import os
import shutil
import sys
import time
from datetime import date, timedelta

from sqlalchemy import text

from app import kcc, pipeline
from app.config import data_path
from app.db import SessionLocal
from app.docgen.generate import generate


def run(seed_date: date | None = None, extractor: str = "auto", redline_mode: str = "auto", log=print, corpus: str | None = None) -> dict:
    t0 = time.time()
    seed_date = seed_date or date.today()
    root = data_path()
    corpus = corpus or os.environ.get("CORPUS", "synthetic")
    if corpus in ("pilot", "hotel"):      # realistic contracts in their own formats (docx / pdf / md), written by Claude from a spec; hotel = a fictional hotel group
        from app.docgen import pilot

        pilot.use_pack(corpus)
        for sub in ("generated", "uploads"):
            shutil.rmtree(root / "inbox" / sub, ignore_errors=True)
        info = pilot.render(root, seed_date)
        log(f"pilot corpus: {info} into {root / 'inbox'} (seed date {seed_date})")
        if corpus == "hotel":            # what a contract never states: the properties' own attributes
            from app.docgen import hotel_spec

            (root / "properties.json").write_text(json.dumps(hotel_spec.PROPERTIES, indent=1))
    else:
        manifest = generate(root, seed_date)
        log(f"generated {len(manifest['templates'])} templates, {len(manifest['contracts'])} contracts, "
            f"{len(manifest['drafts'])} drafts into {root / 'inbox'} (seed date {seed_date})")
    with SessionLocal() as s:
        s.execute(text("TRUNCATE templates, template_clauses, contracts, clauses, field_extractions, clause_deviations, "
                       "extracted_values, check_results, redlines, ask_cache, pipeline_events, pipeline_runs, conversations, chat_messages, vendor_scores, properties, certificates, alerts RESTART IDENTITY CASCADE"))
        kcc.ensure_defaults(s)
        if corpus == "hotel":
            from app import hotel_pack

            log(f"hospitality pack: {hotel_pack.ensure(s)}")
        kcc.refresh_builtins(s)          # a seed starts from the code's built-in patterns
        s.execute(text("UPDATE pipeline_config SET inbox_path = NULL, last_run_at = NULL, next_run_at = NULL, last_fingerprint = NULL"))
        s.execute(text("UPDATE pipeline_config SET enabled = false, trigger_mode = 'periodic', interval_minutes = 120, folders = 'contracts,uploads' WHERE key = 'contracts'"))
        s.execute(text("UPDATE pipeline_config SET enabled = false, trigger_mode = 'on_change', interval_minutes = 15, folders = 'drafts,generated' WHERE key = 'drafts'"))
        s.execute(text("UPDATE pipeline_config SET enabled = false, trigger_mode = 'on_change', interval_minutes = 60, folders = 'feeds' WHERE key = 'feeds'"))
        s.commit()
    res = pipeline.run_pipeline("seed", extractor, log=lambda r: log(f"pipeline: {r}"))
    try:        # operational feeds: invoices, SLA measurements, obligation status -> spend exceptions, risk scores
        from app import feeds
        from app.docgen import ops_fixtures

        log(f"fixture documents written: {ops_fixtures.generate(seed_date)}")
        if corpus == "hotel":           # the certificates received so far, as a CSV export (written after the fixtures, which rebuild the feeds folder)
            from app.docgen import hotel_spec

            (root / "feeds").mkdir(parents=True, exist_ok=True)
            with (root / "feeds" / "certificates.csv").open("w", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(["vendor", "kind", "expiry_date", "received_on", "reference"])
                for vendor, kind, days, ref in hotel_spec.CERTIFICATES:
                    w.writerow([vendor, kind, seed_date + timedelta(days=days), seed_date + timedelta(days=days - 365), ref])

        log(f"feeds loaded: {feeds.run_feeds('seed')}")
    except Exception as e:
        log(f"feeds failed: {type(e).__name__}: {e}")
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
    run(d, corpus="hotel" if "--hotel" in args else "pilot" if "--pilot" in args else None)
