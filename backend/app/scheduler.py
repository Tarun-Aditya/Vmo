"""Async scheduler. Each pipeline has its own trigger:
  periodic   - every N minutes (default 2 hours for executed contracts)
  on_change  - as soon as its folders hold a new or changed file (checked every tick)
  manual     - only when someone presses Run now."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app import pipeline
from app.db import SessionLocal

log = logging.getLogger("scheduler")
TICK_SECONDS = 20
TRIGGERS = ("periodic", "on_change", "manual")


def due(key: str = "contracts") -> bool:
    with SessionLocal() as s:
        row = s.execute(text("SELECT enabled, trigger_mode, next_run_at, folders, last_fingerprint FROM pipeline_config WHERE key=:k"), {"k": key}).first()
        if not row or not row[0] or row[1] == "manual":
            return False
        if row[1] == "on_change":
            files = pipeline.watched_files(s, key, [x for x in row[3].split(",") if x])
            return pipeline.fingerprint(files) != (row[4] or "")
    return row[2] is None or datetime.now(timezone.utc) >= row[2]


def set_interval(s, minutes: int, enabled: bool, key: str = "contracts", trigger_mode: str | None = None, folders: str | None = None) -> None:
    """Persist a pipeline's trigger and recompute the next run from the last one."""
    last = s.execute(text("SELECT last_run_at FROM pipeline_config WHERE key=:k"), {"k": key}).scalar()
    base = last or datetime.now(timezone.utc)
    s.execute(text("UPDATE pipeline_config SET interval_minutes=:m, enabled=:e, next_run_at=:n, trigger_mode=COALESCE(:t, trigger_mode), "
                   "folders=COALESCE(:f, folders) WHERE key=:k"),
              {"m": minutes, "e": enabled, "n": base + timedelta(minutes=minutes), "k": key, "t": trigger_mode, "f": folders})


def due_keys() -> list[str]:
    with SessionLocal() as s:
        keys = [r[0] for r in s.execute(text("SELECT key FROM pipeline_config ORDER BY id"))]
    return [k for k in keys if due(k)]


async def scheduler_loop() -> None:
    log.info("pipeline scheduler started")
    while True:
        await asyncio.sleep(TICK_SECONDS)
        try:
            from app.connectors import service as connectors

            for cid in await asyncio.to_thread(connectors.due):
                res = await asyncio.to_thread(connectors.sync, cid, "schedule")
                log.info("connector %s synced: %s", cid, res)
            from app import alerts

            await asyncio.to_thread(alerts.evaluate)
            from app import retention

            await asyncio.to_thread(retention.purge)
            for k in due_keys():
                with SessionLocal() as s:
                    mode = s.execute(text("SELECT trigger_mode FROM pipeline_config WHERE key=:k"), {"k": k}).scalar()
                res = await asyncio.to_thread(pipeline.run_pipeline, "watch" if mode == "on_change" else "schedule", pipeline_key=k)
                log.info("scheduled run of %s: %s", k, res)
        except Exception:  # keep the loop alive whatever happens
            log.exception("scheduled run failed")
