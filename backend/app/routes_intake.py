"""Intake: add contracts and watch them being read. Each document goes through the normal pipeline (the same code as the watched folder and the
connectors); this route only reports its steps as they happen: read the file, find its structure, extract the terms, index the clauses for search,
run the checks. Used by the Intake screen, which is also the first act of the demo (the five sample contracts in data/realistic_hotel)."""
from __future__ import annotations

import base64
import contextvars
import json
import queue
import re
import shutil
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text

from app import pipeline
from app.db import SessionLocal

router = APIRouter(prefix="/api/intake")
SAMPLES = Path(__file__).resolve().parents[2] / "data" / "realistic_hotel"
SUBDIR = "uploads/intake"
MAX_BYTES = 15 * 1024 * 1024
MEDIA = {".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".md": "text/markdown", ".txt": "text/plain"}


def _samples() -> list[dict]:
    if not (SAMPLES / "sources.json").exists():
        return []
    return [d for d in json.loads((SAMPLES / "sources.json").read_text()) if (SAMPLES / "docs" / d["file"]).exists()]


def _dest() -> Path:
    with SessionLocal() as s:
        d = pipeline.inbox_path(s) / SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _warm() -> None:
    try:
        from app import embeddings

        embeddings.embed(["warm up"])            # load the embedding model before the first document, so indexing is timed on its own
    except Exception:
        pass


@router.get("/samples")
def samples() -> list[dict]:
    threading.Thread(target=_warm, daemon=True).start()
    with SessionLocal() as s:
        loaded = {r[0].rsplit("/", 1)[-1]: r[1] for r in s.execute(text("SELECT source_path, id FROM contracts WHERE source_path LIKE :p"), {"p": SUBDIR + "/%"})}
    out = []
    for d in _samples():
        f = SAMPLES / "docs" / d["file"]
        out.append({"file": d["file"], "what": d["what"], "category": d.get("category"), "property": d.get("property"), "format": f.suffix.lstrip(".").upper(),
                    "size": f.stat().st_size, "contract_id": loaded.get(d["file"])})
    return out


@router.get("/samples/{name}")
def sample_file(name: str):
    """The original document, as a person would open it (a PDF opens in the browser; a Word file downloads)."""
    d = next((x for x in _samples() if x["file"] == name), None)
    if not d:
        raise HTTPException(404, "no such sample")
    f = SAMPLES / "docs" / d["file"]
    return FileResponse(f, media_type=MEDIA.get(f.suffix.lower(), "application/octet-stream"), filename=f.name,
                        content_disposition_type="inline" if f.suffix.lower() == ".pdf" else "attachment")


class UploadIn(BaseModel):
    filename: str
    content_b64: str


class IntakeIn(BaseModel):
    samples: list[str] = []
    files: list[UploadIn] = []


def _stage(body: IntakeIn) -> list[Path]:
    dest, out = _dest(), []
    by_name = {d["file"]: d for d in _samples()}
    for name in body.samples:
        d = by_name.get(name)
        if not d:
            raise HTTPException(404, f"no sample called {name}")
        f = dest / d["file"]
        shutil.copy2(SAMPLES / "docs" / d["file"], f)
        meta = {"category": d.get("category"), "owner": "Andrea Whitfield", "origin": "upload"}
        if d.get("property"):
            meta["property"] = d["property"]
        f.with_suffix(".meta.json").write_text(json.dumps(meta))
        out.append(f)
    for u in body.files:
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(u.filename).name) or "document"
        if Path(safe).suffix.lower() not in pipeline.SUPPORTED:
            raise HTTPException(400, f"{u.filename}: only {', '.join(sorted(pipeline.SUPPORTED))} files can be read")
        try:
            raw = base64.b64decode(u.content_b64, validate=True)
        except Exception:
            raise HTTPException(400, f"{u.filename}: the file could not be decoded") from None
        if len(raw) > MAX_BYTES:
            raise HTTPException(413, f"{u.filename}: larger than {MAX_BYTES // 1024 // 1024} MB")
        f = dest / safe
        f.write_bytes(raw)
        f.with_suffix(".meta.json").write_text(json.dumps({"origin": "upload"}))
        out.append(f)
    if not out:
        raise HTTPException(400, "choose at least one document")
    return out


def _summary(ids: list[int]) -> dict:
    if not ids:
        return {"contracts": 0}
    with SessionLocal() as s:
        q = lambda sql: s.execute(text(sql), {"ids": ids})  # noqa: E731
        c = q("""SELECT count(*) AS n, COALESCE(sum(annual_value), 0) AS annual, count(*) FILTER (WHERE liability_cap_multiple IS NULL) AS uncapped,
                        count(*) FILTER (WHERE processes_personal_data) AS personal, count(*) FILTER (WHERE auto_renew) AS auto_renew,
                        count(*) FILTER (WHERE NOT COALESCE(termination_for_convenience, false)) AS no_exit,
                        count(DISTINCT vendor) AS vendors FROM contracts WHERE id = ANY(:ids)""").mappings().one()
        acts = [dict(r) for r in q("""SELECT contract_id, title, vendor, notice_deadline, expiry_date, days_to_notice FROM (
                                        SELECT r.contract_id, r.title, r.vendor, r.notice_deadline, r.expiry_date, (r.notice_deadline - CURRENT_DATE) AS days_to_notice
                                        FROM v_renewals r WHERE r.contract_id = ANY(:ids)) x ORDER BY notice_deadline""").mappings()]
        fails = q("SELECT count(*) FILTER (WHERE severity IN ('critical','high')) FROM check_results WHERE contract_id = ANY(:ids) AND status = 'fail'").scalar()
        clauses = q("SELECT count(*) FROM clauses WHERE contract_id = ANY(:ids)").scalar()
        total = s.execute(text("SELECT count(*) FROM contracts WHERE status <> 'draft'")).scalar()
    for a in acts:
        for k in ("notice_deadline", "expiry_date"):
            a[k] = a[k].isoformat() if a[k] else None
    return {**{k: (float(v) if k == "annual" else v) for k, v in dict(c).items()}, "contracts": c["n"], "serious_failures": fails, "clauses": clauses,
            "portfolio_total": total, "deadlines": acts}


@router.post("")
def intake(body: IntakeIn):
    """Process the chosen documents one by one and stream what happens as newline-delimited JSON: {"doc", "step", ...} per step, then {"step": "summary"}."""
    files = _stage(body)
    q: queue.Queue = queue.Queue()
    END = object()

    def run() -> None:
        ids: list[int] = []
        try:
            for f in files:
                q.put({"doc": f.name, "step": "queued"})
            for f in files:
                tok = pipeline.PROGRESS.set(lambda step, data, _f=f.name: q.put({"doc": _f, "step": step, **data}))
                try:
                    r = pipeline.run_pipeline("intake", only=[f], force=True)
                finally:
                    pipeline.PROGRESS.reset(tok)
                if r.get("status") == "busy":
                    q.put({"doc": f.name, "step": "error", "message": "another pipeline run is in progress; try again in a moment"})
                    continue
                with SessionLocal() as s:
                    rel = str(f.relative_to(pipeline.inbox_path(s)))
                    row = s.execute(text("SELECT id, title FROM contracts WHERE source_path = :p"), {"p": rel}).first()
                    ev = s.execute(text("SELECT action, detail FROM pipeline_events WHERE run_id = :r ORDER BY id DESC LIMIT 1"), {"r": r.get("run_id")}).first()
                if row and (not ev or ev[0] != "failed"):
                    ids.append(row[0])
                    q.put({"doc": f.name, "step": "done", "contract_id": row[0], "title": row[1]})
                else:
                    q.put({"doc": f.name, "step": "error", "message": (ev[1] if ev else None) or "the document could not be read"})
            q.put({"step": "summary", **_summary(ids)})
        except Exception as e:  # report, never hang the stream
            q.put({"step": "error", "message": f"{type(e).__name__}: {e}"[:300]})
        finally:
            q.put(END)

    threading.Thread(target=contextvars.copy_context().run, args=(run,), daemon=True).start()

    def stream():
        yield json.dumps({"step": "engine", "engine": pipeline.llm.PROVIDER_LABEL.get(pipeline.llm.provider(), "Claude") if pipeline.llm.available() else "offline rules",
                          "documents": [f.name for f in files]}) + "\n"
        while True:
            item = q.get()
            if item is END:
                break
            yield json.dumps(item, default=str) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.delete("")
def reset() -> dict:
    """Remove every document added through Intake (contracts, clauses, values, checks and the files), so the demo can start again."""
    with SessionLocal() as s:
        n = s.execute(text("DELETE FROM contracts WHERE source_path LIKE :p"), {"p": SUBDIR + "/%"}).rowcount
        s.commit()
    d = _dest()
    for f in d.glob("*"):
        if f.is_file():
            f.unlink()
    return {"removed": n}
