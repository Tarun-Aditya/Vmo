"""Async scheduler: runs the pipeline on the configured frequency (default every 2 hours)."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app import pipeline
from app.db import SessionLocal

log = logging.getLogger("scheduler")
TICK_SECONDS = 20


def due() -> bool:
    with SessionLocal() as s:
        row = s.execute(text("SELECT enabled, next_run_at FROM pipeline_config WHERE id = 1")).first()
    if not row or not row[0]:
        return False
    return row[1] is None or datetime.now(timezone.utc) >= row[1]


def set_interval(s, minutes: int, enabled: bool) -> None:
    """Persist the frequency and recompute the next run from the last one."""
    last = s.execute(text("SELECT last_run_at FROM pipeline_config WHERE id = 1")).scalar()
    base = last or datetime.now(timezone.utc)
    s.execute(text("UPDATE pipeline_config SET interval_minutes=:m, enabled=:e, next_run_at=:n WHERE id=1"),
              {"m": minutes, "e": enabled, "n": base + timedelta(minutes=minutes)})


async def scheduler_loop() -> None:
    log.info("pipeline scheduler started")
    while True:
        await asyncio.sleep(TICK_SECONDS)
        try:
            if due():
                res = await asyncio.to_thread(pipeline.run_pipeline, "schedule")
                log.info("scheduled run: %s", res)
        except Exception:  # keep the loop alive whatever happens
            log.exception("scheduled run failed")
