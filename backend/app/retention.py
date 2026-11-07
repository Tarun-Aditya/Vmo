"""Data retention: delete audit entries and finished alerts older than the configured number of days (AUDIT_RETENTION_DAYS, ALERT_RETENTION_DAYS; 0 or unset = keep)."""
from __future__ import annotations

import os

from sqlalchemy import text

from app.db import SessionLocal


def purge() -> dict:
    out = {"audit": 0, "alerts": 0}
    with SessionLocal() as s:
        a, b = int(os.environ.get("AUDIT_RETENTION_DAYS", "0") or 0), int(os.environ.get("ALERT_RETENTION_DAYS", "0") or 0)
        if a > 0:
            out["audit"] = s.execute(text("DELETE FROM audit_log WHERE ts < now() - make_interval(days => :d)"), {"d": a}).rowcount
        if b > 0:
            out["alerts"] = s.execute(text("DELETE FROM alerts WHERE status = 'resolved' AND created_at < now() - make_interval(days => :d)"), {"d": b}).rowcount
        s.commit()
    return out
