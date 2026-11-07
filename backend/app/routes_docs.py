"""Online document editing (versions), redline review queue (status, per-change decisions, apply), upload for redline."""
from __future__ import annotations

import base64
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import text

from app import docx_export, ingest_text, pipeline
from app.db import SessionLocal

router = APIRouter(prefix="/api")
REVIEW = ("pending", "in_review", "changes_requested", "approved")


def rows(sql: str, **p) -> list[dict]:
    with SessionLocal() as s:
        return [dict(r) for r in s.execute(text(sql), p).mappings().all()]


def one(sql: str, **p):
    r = rows(sql, **p)
    return r[0] if r else None


def _doc(cid: int) -> dict:
    d = one("SELECT id, title, vendor, type, status, body_md, source_path FROM contracts WHERE id=:i", i=cid)
    if not d:
        raise HTTPException(404, "document not found")
    return d


# ------------------------------------------------------------------ online editor
@router.get("/documents/{cid}/content")
def doc_content(cid: int):
    d = _doc(cid)
    vs = rows("SELECT version, note, created_at, length(body_md) AS chars FROM document_versions WHERE contract_id=:i ORDER BY version DESC", i=cid)
    return {"id": d["id"], "title": d["title"], "vendor": d["vendor"], "type": d["type"], "status": d["status"], "md": d["body_md"],
            "editable": d["status"] == "draft", "versions": vs, "version": vs[0]["version"] if vs else 1}


@router.get("/documents/{cid}/versions/{v}")
def doc_version(cid: int, v: int):
    r = one("SELECT version, note, created_at, body_md AS md FROM document_versions WHERE contract_id=:i AND version=:v", i=cid, v=v)
    if not r:
        raise HTTPException(404, "version not found")
    return r


class SaveIn(BaseModel):
    md: str
    note: str | None = None


def save_document(cid: int, md: str, note: str | None, trigger: str = "edit") -> dict:
    d = _doc(cid)
    if d["status"] != "draft":
        raise HTTPException(409, "only drafts can be edited; an executed contract is changed by amendment")
    if not md.strip():
        raise HTTPException(422, "the document is empty")
    md = md.rstrip() + "\n"
    with SessionLocal() as s:
        root = pipeline.inbox_path(s)
        path = root / d["source_path"]
        last = s.execute(text("SELECT max(version) FROM document_versions WHERE contract_id=:i"), {"i": cid}).scalar()
        if last is None:
            s.execute(text("INSERT INTO document_versions (contract_id, version, body_md, note) VALUES (:i,1,:b,'Original')"), {"i": cid, "b": d["body_md"]})
            last = 1
        s.execute(text("INSERT INTO document_versions (contract_id, version, body_md, note) VALUES (:i,:v,:b,:n)"),
                  {"i": cid, "v": last + 1, "b": md, "n": note or "Edited online"})
        s.commit()
    path.write_text(md)
    res = pipeline.run_pipeline(trigger, only=[path])
    if res.get("status") == "busy":
        raise HTTPException(409, "the pipeline is busy; try again in a moment")
    return {"saved": True, "version": last + 1, "run": res}


@router.put("/documents/{cid}/content")
def doc_save(cid: int, b: SaveIn):
    return save_document(cid, b.md, b.note)


# ------------------------------------------------------------------ review queue
class ReviewIn(BaseModel):
    status: str
    note: str | None = None
    reviewer: str | None = None


@router.put("/redline/{cid}/review")
def review_put(cid: int, r: ReviewIn):
    _doc(cid)
    if r.status not in REVIEW:
        raise HTTPException(422, f"status must be one of {', '.join(REVIEW)}")
    with SessionLocal() as s:
        s.execute(text("""INSERT INTO contract_reviews (contract_id, status, note, reviewer) VALUES (:i,:s,:n,:r)
                          ON CONFLICT (contract_id) DO UPDATE SET status=:s, note=COALESCE(:n, contract_reviews.note), reviewer=COALESCE(:r, contract_reviews.reviewer), updated_at=now()"""),
                  {"i": cid, "s": r.status, "n": r.note, "r": r.reviewer})
        s.commit()
    return review_get(cid)


def review_get(cid: int) -> dict:
    r = one("SELECT status, note, reviewer, updated_at FROM contract_reviews WHERE contract_id=:i", i=cid)
    dec = {x["clause_type"]: x["decision"] for x in rows("SELECT clause_type, decision FROM redline_decisions WHERE contract_id=:i", i=cid)}
    return {"review": r or {"status": "pending", "note": None, "reviewer": None, "updated_at": None}, "decisions": dec}


class DecisionIn(BaseModel):
    clause_type: str
    decision: str | None = None      # accepted | rejected | None (clear)


@router.put("/redline/{cid}/decision")
def decision_put(cid: int, d: DecisionIn):
    _doc(cid)
    with SessionLocal() as s:
        if d.decision is None:
            s.execute(text("DELETE FROM redline_decisions WHERE contract_id=:i AND clause_type=:c"), {"i": cid, "c": d.clause_type})
        elif d.decision in ("accepted", "rejected"):
            s.execute(text("""INSERT INTO redline_decisions (contract_id, clause_type, decision) VALUES (:i,:c,:d)
                              ON CONFLICT (contract_id, clause_type) DO UPDATE SET decision=:d, updated_at=now()"""), {"i": cid, "c": d.clause_type, "d": d.decision})
            s.execute(text("""INSERT INTO contract_reviews (contract_id, status) VALUES (:i,'in_review')
                              ON CONFLICT (contract_id) DO UPDATE SET status=CASE WHEN contract_reviews.status='pending' THEN 'in_review' ELSE contract_reviews.status END, updated_at=now()"""), {"i": cid})
        else:
            raise HTTPException(422, "decision must be accepted, rejected or null")
        s.commit()
    return review_get(cid)


def _norm(t: str) -> str:
    return " ".join(t.split())


def apply_accepted(md: str, items: list[dict], accepted: set[str]) -> tuple[str, int]:
    """Replace each accepted change's draft wording with the suggested wording; add accepted missing clauses."""
    n = 0
    for it in items:
        if it["clause_type"] not in accepted or not it.get("suggested_text"):
            continue
        if it["status"] == "changed" and it.get("draft_text"):
            old = it["draft_text"]
            if old in md:
                md = md.replace(old, it["suggested_text"], 1)
                n += 1
                continue
            m = re.search(r"\s+".join(re.escape(w) for w in old.split()), md)
            if m:
                md = md[:m.start()] + it["suggested_text"] + md[m.end():]
                n += 1
        elif it["status"] == "missing":
            nums = [int(x) for x in re.findall(r"^## (\d+)\.", md, re.M)]
            section = f"## {max(nums) + 1 if nums else 1}. {it['heading']}\n{it['suggested_text']}\n"
            m = re.search(r"^## \d+\.\s*(Execution|Signature)", md, re.M | re.I)    # keep the signature block last
            md = md[:m.start()] + section + "\n" + md[m.start():] if m else md.rstrip() + "\n\n" + section
            n += 1
    return md, n


@router.post("/redline/{cid}/apply")
def apply_decisions(cid: int):
    d = _doc(cid)
    red = one("SELECT items FROM redlines WHERE contract_id=:i", i=cid)
    dec = review_get(cid)["decisions"]
    accepted = {k for k, v in dec.items() if v == "accepted"}
    if not accepted:
        raise HTTPException(422, "accept at least one change first")
    md, n = apply_accepted(d["body_md"], (red or {}).get("items") or [], accepted)
    if n == 0:
        raise HTTPException(422, "the accepted changes could not be located in the text")
    out = save_document(cid, md, f"Applied {n} accepted redline change{'s' if n != 1 else ''}", trigger="redline")
    with SessionLocal() as s:
        s.execute(text("DELETE FROM redline_decisions WHERE contract_id=:i AND decision='accepted'"), {"i": cid})
        s.commit()
    return {**out, "applied": n}


# ------------------------------------------------------------------ upload a document for redline
class RedlineUpload(BaseModel):
    filename: str
    content: str | None = None
    content_b64: str | None = None
    owner: str | None = None
    category: str | None = None


@router.post("/redline/upload")
def redline_upload(u: RedlineUpload):
    try:
        md = u.content if u.content is not None else ingest_text.extract_text(u.filename, base64.b64decode(u.content_b64 or ""))
    except ValueError as e:
        raise HTTPException(422, str(e))
    if not md.strip():
        raise HTTPException(422, "the document is empty")
    if not re.search(r"^# ", md, re.M):
        md = f"# {re.sub(r'[_-]+', ' ', u.filename.rsplit('.', 1)[0]).strip().title()}\n\n{md}"
    name = re.sub(r"\.[A-Za-z0-9]+$", "", u.filename) + ".md"
    p = pipeline.add_document(name, md, {"status": "draft", "owner": u.owner, "category": u.category, "origin": "upload"}, subdir="drafts")
    res = pipeline.run_pipeline("upload", only=[p])
    with SessionLocal() as s:
        root = pipeline.inbox_path(s)
        cid = s.execute(text("SELECT id FROM contracts WHERE source_path=:p"), {"p": str(p.relative_to(root))}).scalar()
    return {"contract_id": cid, "saved_as": p.name, "run": res}


# ------------------------------------------------------------------ Word export
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _fname(title: str, suffix: str = "") -> str:
    import re

    return re.sub(r"[^A-Za-z0-9._ -]+", "", title)[:80].strip().replace(" ", "_") + suffix + ".docx"


@router.get("/documents/{cid}/export.docx")
def export_docx(cid: int):
    d = _doc(cid)
    try:
        data = docx_export.md_to_docx(d["body_md"])
    except RuntimeError as e:
        raise HTTPException(501, str(e))
    return Response(data, media_type=DOCX, headers={"Content-Disposition": f'attachment; filename="{_fname(d["title"])}"'})


@router.get("/redline/{cid}/export.docx")
def export_redline_docx(cid: int):
    """The document with every deviation as a tracked change (accepted ones inserted, rejected ones left out)."""
    d = _doc(cid)
    red = one("SELECT items FROM redlines WHERE contract_id=:i", i=cid)
    try:
        data, stats = docx_export.redline_docx(d["body_md"], (red or {}).get("items") or [], review_get(cid)["decisions"])
    except RuntimeError as e:
        raise HTTPException(501, str(e))
    return Response(data, media_type=DOCX, headers={"Content-Disposition": f'attachment; filename="{_fname(d["title"], "_redline")}"', "X-Tracked-Changes": str(stats["changes"] + stats["inserted_clauses"])})
