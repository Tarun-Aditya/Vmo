"""Quality loop for real contracts: correct an extracted field (it sticks through re-extraction), see how often each field needed correcting (a measured accuracy), and
export / import the extracted values as a review sheet so a customer can check 10-20 contracts in a spreadsheet and feed the answers back."""
from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import text

from app import feeds, pipeline
from app.db import SessionLocal
from app.routes_auth import me

router = APIRouter(prefix="/api")


def rows(sql: str, **p) -> list[dict]:
    with SessionLocal() as s:
        return [dict(r) for r in s.execute(text(sql), p).mappings().all()]


def apply_correction(cid: int, field: str, raw, by: str, note: str | None = None) -> dict:
    if field not in pipeline.EDITABLE:
        raise HTTPException(422, f"{field} cannot be corrected here")
    try:
        v = pipeline.coerce_input(field, raw)
    except (ValueError, TypeError) as e:
        raise HTTPException(422, f"not a valid value for {field}: {e}")
    c = rows("SELECT id, source_path FROM contracts WHERE id=:i", i=cid)
    if not c:
        raise HTTPException(404, "contract not found")
    with SessionLocal() as s:
        old = s.execute(text("SELECT value FROM field_extractions WHERE contract_id=:c AND field=:f ORDER BY id LIMIT 1"), {"c": cid, "f": field}).scalar()
        ex = s.execute(text("SELECT original_value FROM field_corrections WHERE source_path=:p AND field=:f"), {"p": c[0]["source_path"], "f": field}).scalar()
        orig = ex if ex is not None else old                      # the first machine value stays the 'original', however many times it is corrected
        s.execute(text("""INSERT INTO field_corrections (source_path, contract_id, field, original_value, corrected_value, corrected_by, note) VALUES (:p,:c,:f,:o,:v,:u,:n)
                          ON CONFLICT (source_path, field) DO UPDATE SET corrected_value=:v, corrected_by=:u, note=:n, created_at=now(), contract_id=:c"""),
                  {"p": c[0]["source_path"], "c": cid, "f": field, "o": orig, "v": None if v is None else str(v), "u": by, "n": note})
        s.execute(text(f"UPDATE contracts SET {field} = :v WHERE id=:c"), {"v": v, "c": cid})
        s.execute(text("DELETE FROM field_extractions WHERE contract_id=:c AND field=:f"), {"c": cid, "f": field})
        s.execute(text("INSERT INTO field_extractions (contract_id, field, value, confidence, source_page, corrected) VALUES (:c,:f,:v,1.0,1,true)"), {"c": cid, "f": field, "v": None if v is None else str(v)})
        s.commit()
    feeds.recompute()
    return {"field": field, "value": v, "original": orig}


class FixIn(BaseModel):
    value: str | None = None
    note: str | None = None


@router.put("/contracts/{cid}/fields/{field}")
def correct_field(cid: int, field: str, b: FixIn, request: Request):
    return apply_correction(cid, field, b.value, me(request)["email"], b.note)


@router.delete("/contracts/{cid}/fields/{field}")
def undo_correction(cid: int, field: str):
    """Drop a correction; the next processing of the document extracts the field again."""
    c = rows("SELECT source_path FROM contracts WHERE id=:i", i=cid)
    if not c:
        raise HTTPException(404, "contract not found")
    with SessionLocal() as s:
        s.execute(text("DELETE FROM field_corrections WHERE source_path=:p AND field=:f"), {"p": c[0]["source_path"], "f": field})
        s.commit()
    return {"ok": True, "note": "Re-run the pipeline (change the file or use Run now with a re-process) to extract the field again."}


@router.get("/quality/summary")
def summary():
    """Per field: values extracted, values a person had to correct, and the measured agreement (1 - corrected/extracted) over the corrected documents."""
    fx = rows("""SELECT f.field, count(*) AS extracted, count(*) FILTER (WHERE f.corrected) AS corrected
                 FROM field_extractions f JOIN contracts c ON c.id=f.contract_id
                 WHERE c.source_path IN (SELECT source_path FROM field_corrections) GROUP BY f.field ORDER BY f.field""")
    docs = rows("SELECT count(DISTINCT source_path) AS n FROM field_corrections")[0]["n"]
    out = [{**r, "agreement": round(1 - r["corrected"] / r["extracted"], 3) if r["extracted"] else None} for r in fx if r["field"] in pipeline.EDITABLE]
    tot_e, tot_c = sum(r["extracted"] for r in out), sum(r["corrected"] for r in out)
    return {"documents_reviewed": docs, "fields": out, "overall_agreement": round(1 - tot_c / tot_e, 3) if tot_e else None,
            "recent": rows("SELECT contract_id, field, original_value, corrected_value, corrected_by, created_at FROM field_corrections ORDER BY id DESC LIMIT 25")}


@router.get("/quality/review-sheet")
def review_sheet():
    """CSV of every extracted field of every executed contract: edit the 'correct_value' column where the extraction is wrong and import the file back."""
    data = rows("""SELECT c.id AS contract_id, c.source_path, c.title, f.field, f.value AS extracted_value, f.source_page
                   FROM field_extractions f JOIN contracts c ON c.id=f.contract_id WHERE c.status <> 'draft' ORDER BY c.id, f.field""")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["contract_id", "source_path", "title", "field", "extracted_value", "correct_value", "page"])
    for r in data:
        if r["field"] in pipeline.EDITABLE:
            w.writerow([r["contract_id"], r["source_path"], r["title"], r["field"], r["extracted_value"] or "", r["extracted_value"] or "", r["source_page"] or ""])
    return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="review_sheet.csv"'})


class SheetIn(BaseModel):
    content: str


@router.post("/quality/review-sheet")
def import_sheet(b: SheetIn, request: Request):
    """Apply the corrections in a returned review sheet (only rows whose correct_value differs from extracted_value)."""
    who, n, bad = me(request)["email"], 0, []
    for r in csv.DictReader(io.StringIO(b.content)):
        if (r.get("correct_value") or "").strip() == (r.get("extracted_value") or "").strip():
            continue
        try:
            apply_correction(int(r["contract_id"]), r["field"], r["correct_value"], who, "review sheet")
            n += 1
        except HTTPException as e:
            bad.append({"row": f"{r.get('contract_id')}/{r.get('field')}", "error": e.detail})
        except (KeyError, ValueError):
            bad.append({"row": str(r), "error": "unreadable row"})
    return {"applied": n, "rejected": bad}


@router.get("/quality/labels")
def labels():
    """Ground truth built from corrections: {source_path: {field: value}} for evals/real_eval.py (the corrected value where a person fixed it; fields nobody corrected are not listed)."""
    out: dict = {}
    for r in rows("SELECT source_path, field, corrected_value FROM field_corrections"):
        out.setdefault(r["source_path"], {})[r["field"]] = r["corrected_value"]
    return out
