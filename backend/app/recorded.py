"""Recorded outputs for the demo sample documents: what the engine (ideally Claude) produced for them, saved once and replayed in Demo mode.

Demo mode runs without Claude. For the dozen sample documents the demo uses, `scripts/record_demo.py` reads them once with the engine that is active
(Claude when Demo mode is off and Claude is reachable) and saves, in data/realistic_hotel/recorded.json:
  * the terms extracted from each document, keyed by the document's content fingerprint (sha256 of the file);
  * the answers to a list of questions about given sample documents (data/realistic_hotel/demo_questions.json), keyed by the question and the fingerprints
    of the documents it was asked about. Contract ids inside an answer are stored as fingerprints and mapped back to the ids of the running database.
In Demo mode the pipeline uses the recorded terms for a sample document and Ask the recorded answer for a recorded question; everything else (other
documents, other questions) goes to the offline engine as before. Recorded results say so (source "recorded", with the engine and date)."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from sqlalchemy import text

PATH = Path(os.environ.get("RECORDED_PATH") or Path(__file__).resolve().parents[2] / "data" / "realistic_hotel" / "recorded.json")
ID_KEYS = {"_cid", "contract_id", "cid", "source_id"}
DISABLED = False          # set by the recorder: never replay while recording
_cache: tuple[float, dict] | None = None
_capture: dict | None = None


def load() -> dict:
    global _cache
    try:
        m = PATH.stat().st_mtime
    except OSError:
        return {}
    if _cache and _cache[0] == m:
        return _cache[1]
    try:
        data = json.loads(PATH.read_text())
    except (OSError, ValueError):
        data = {}
    _cache = (m, data)
    return data


def active() -> bool:
    if DISABLED:
        return False
    from app import mode

    return mode.demo_on() and bool(load())


# ------------------------------------------------------------------ extraction
def fields_for(content_hash: str) -> tuple[dict, str] | None:
    """The recorded terms of a sample document, in Demo mode: (fields as extraction.extract returns them, engine label)."""
    if not active():
        return None
    d = load().get("documents", {}).get(content_hash)
    if not d:
        return None
    return json.loads(json.dumps(d["fields"])), f"recorded ({d.get('engine', load().get('engine', '?'))}, {load().get('recorded_at', '')[:10]})"


def start_capture() -> None:
    global _capture, DISABLED
    DISABLED, _capture = True, {}


def observe(content_hash: str, fields: dict, mode: str, file: str) -> None:
    if _capture is not None:
        _capture[content_hash] = {"file": file, "engine": mode, "fields": json.loads(json.dumps(fields, default=str))}


def captured() -> dict:
    return dict(_capture or {})


# ------------------------------------------------------------------ answers
def _hashes(s, ids: list[int]) -> dict[int, str]:
    return {r[0]: r[1] for r in s.execute(text("SELECT id, content_hash FROM contracts WHERE id = ANY(:ids) AND content_hash IS NOT NULL"), {"ids": list(ids)})}


def key(question: str, hashes: list[str]) -> str:
    from app.ask import norm_key

    return norm_key(question) + "|" + ",".join(sorted(set(hashes)))


def _swap(o, ints: dict, strs: dict):
    """Replace contract ids (ints under ID_KEYS, in contract_ids lists, and inside 'IN (...)' / '/contracts/N' in strings) using the given maps."""
    if isinstance(o, dict):
        return {k: (ints.get(v, v) if k in ID_KEYS and isinstance(v, (int, str)) and not isinstance(v, bool)
                    else [ints.get(x, x) for x in v] if k == "contract_ids" and isinstance(v, list) else _swap(v, ints, strs)) for k, v in o.items()}
    if isinstance(o, list):
        return [_swap(x, ints, strs) for x in o]
    if isinstance(o, str) and strs:
        o = re.sub(r"IN \(([^)]*)\)", lambda m: "IN (" + ", ".join(strs.get(x.strip(), x.strip()) for x in m.group(1).split(",")) + ")", o)
        return re.sub(r"/contracts/(\w+)", lambda m: "/contracts/" + strs.get(m.group(1), m.group(1)), o)
    return o


def to_portable(s, res: dict, scope: list[int]) -> dict:
    """An answer with the ids of documents it mentions replaced by their fingerprints ('@doc:<hash>')."""
    ids = set(scope)

    def collect(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ID_KEYS and isinstance(v, int) and not isinstance(v, bool):
                    ids.add(v)
                collect(v)
        elif isinstance(o, list):
            for x in o:
                collect(x)
    collect(res)
    h = _hashes(s, list(ids))
    ints = {i: f"@doc:{x}" for i, x in h.items()}
    return _swap(res, ints, {str(i): v for i, v in ints.items()})


def answer_for(question: str, scope: list[int] | None) -> dict | None:
    """The recorded answer to this question about these documents, in Demo mode, with ids mapped to this database; None if not recorded."""
    if not active() or not scope:
        return None
    from app.db import SessionLocal

    with SessionLocal() as s:
        h = _hashes(s, scope)
        if len(h) != len(set(scope)):
            return None
        rec = load().get("answers", {}).get(key(question, list(h.values())))
        if not rec:
            return None
        back = {f"@doc:{x}": i for i, x in h.items()}
        want = set(re.findall(r"@doc:[0-9a-f]+", json.dumps(rec["response"])))
        missing = [w for w in want if w not in back]
        if missing:
            more = {f"@doc:{r[1]}": r[0] for r in s.execute(text("SELECT id, content_hash FROM contracts WHERE content_hash = ANY(:h) AND status <> 'draft'"),
                                                           {"h": [m[5:] for m in missing]})}
            back.update(more)
            if any(w not in back for w in want):
                return None
    res = _swap(rec["response"], back, {k: str(v) for k, v in back.items()})
    res.update(source="recorded", recorded_engine=rec.get("engine"), recorded_at=load().get("recorded_at"))
    return res
