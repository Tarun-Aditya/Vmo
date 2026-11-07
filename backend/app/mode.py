"""The global Demo / Live switch.

Demo mode ON  -> no Claude anywhere: every module (extraction, redline, key-clause tagging, Ask) runs on the offline engine
                 and cached results, and the external systems are the built-in simulators. Fast, deterministic, works without wifi.
Demo mode OFF -> Live: every module uses the LLM (Claude), whichever backend is configured."""
from __future__ import annotations

import time

from sqlalchemy import text

_cache: tuple[float, bool] | None = None


def demo_on() -> bool:
    global _cache
    if _cache and time.time() - _cache[0] < 2:
        return _cache[1]
    try:
        from app.db import SessionLocal

        with SessionLocal() as s:
            v = s.execute(text("SELECT value FROM app_settings WHERE key='demo_mode'")).scalar()
        on = bool(v)
    except Exception:
        on = False
    _cache = (time.time(), on)
    return on


def set_demo(on: bool, who: str | None = None) -> bool:
    global _cache
    from app.db import SessionLocal

    with SessionLocal() as s:
        s.execute(text("""INSERT INTO app_settings (key, value, updated_by) VALUES ('demo_mode', CAST(:v AS jsonb), :u)
                          ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=now(), updated_by=EXCLUDED.updated_by"""), {"v": "true" if on else "false", "u": who})
        s.commit()
    _cache = (time.time(), on)
    return on
