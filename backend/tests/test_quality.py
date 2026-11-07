"""Correction loop: a fixed field updates every screen, survives re-extraction, feeds a measured agreement, and a review sheet can be round-tripped."""
import csv
import io

import pytest
from sqlalchemy import text

from app import pipeline
from app.db import SessionLocal


@pytest.fixture()
def doc(client, seeded):
    c = next(x for x in client.get("/api/contracts").json() if x["type"] == "SaaS" and x["status"] != "draft")
    cols = sorted(pipeline.EDITABLE)
    with SessionLocal() as s:
        snap = dict(s.execute(text(f"SELECT {', '.join(cols)} FROM contracts WHERE id=:i"), {"i": c["id"]}).mappings().one())
        fx = [dict(r) for r in s.execute(text("SELECT field, value, confidence, source_clause_id, source_page FROM field_extractions WHERE contract_id=:i"), {"i": c["id"]}).mappings()]
        s.execute(text("DELETE FROM field_corrections"))
        s.commit()
    yield c
    with SessionLocal() as s:                      # put the shared test data back as it was
        s.execute(text("DELETE FROM field_corrections"))
        s.execute(text(f"UPDATE contracts SET {', '.join(f'{k} = :{k}' for k in cols)} WHERE id=:i"), {**snap, "i": c["id"]})
        s.execute(text("DELETE FROM field_extractions WHERE contract_id=:i"), {"i": c["id"]})
        for r in fx:
            s.execute(text("INSERT INTO field_extractions (contract_id, field, value, confidence, source_clause_id, source_page, corrected) VALUES (:i,:field,:value,:confidence,NULL,:source_page,false)"), {**r, "i": c["id"]})
        s.commit()


def test_correction_updates_the_contract_and_is_validated(client, doc):
    cid = doc["id"]
    r = client.put(f"/api/contracts/{cid}/fields/payment_terms_days", json={"value": "37"}).json()
    assert r["value"] == 37
    c = client.get(f"/api/contracts/{cid}").json()
    assert c["contract"]["payment_terms_days"] == 37
    f = next(x for x in c["fields"] if x["field"] == "payment_terms_days")
    assert f["value"] == "37" and float(f["confidence"]) == 1.0
    assert client.put(f"/api/contracts/{cid}/fields/payment_terms_days", json={"value": "abc"}).status_code == 422
    assert client.put(f"/api/contracts/{cid}/fields/auto_renew", json={"value": "maybe"}).status_code == 422
    assert client.put(f"/api/contracts/{cid}/fields/title", json={"value": "x"}).status_code == 422                        # not a correctable field
    assert client.put(f"/api/contracts/{cid}/fields/expiry_date", json={"value": "31/12/2030"}).status_code == 422
    assert client.put(f"/api/contracts/{cid}/fields/expiry_date", json={"value": "2030-12-31"}).json()["value"] == "2030-12-31"
    assert client.put("/api/contracts/999999/fields/auto_renew", json={"value": "yes"}).status_code == 404


def test_correction_survives_re_extraction_and_agreement_is_measured(client, doc):
    cid = doc["id"]
    orig = next(x for x in client.get(f"/api/contracts/{cid}").json()["fields"] if x["field"] == "payment_terms_days")["value"]
    client.put(f"/api/contracts/{cid}/fields/payment_terms_days", json={"value": "37"})
    client.put(f"/api/contracts/{cid}/fields/payment_terms_days", json={"value": "38"})
    with SessionLocal() as s:
        row = s.execute(text("SELECT original_value, corrected_value FROM field_corrections")).one()
        path = s.execute(text("SELECT source_path FROM contracts WHERE id=:i"), {"i": cid}).scalar()
        root = pipeline.inbox_path(s)
    assert row[0] == orig and row[1] == "38"                                                                               # the machine's first answer is kept as the original
    f = root / path
    f.write_text(f.read_text() + "\n")                                                                                    # the file changes: the pipeline extracts it again
    pipeline.run_pipeline("manual", only=[f])
    with SessionLocal() as s:
        again = s.execute(text("SELECT payment_terms_days FROM contracts WHERE source_path=:p"), {"p": path}).scalar()
    assert again == 38
    q = client.get("/api/quality/summary").json()
    assert q["documents_reviewed"] == 1 and any(x["field"] == "payment_terms_days" and x["corrected"] == 1 for x in q["fields"]) and 0 < q["overall_agreement"] < 1
    assert client.get("/api/quality/labels").json()[path]["payment_terms_days"] == "38"


def test_review_sheet_round_trip(client, doc):
    sheet = client.get("/api/quality/review-sheet").text
    rows = list(csv.DictReader(io.StringIO(sheet)))
    assert rows and {"contract_id", "field", "extracted_value", "correct_value"} <= set(rows[0])
    target = next(r for r in rows if r["contract_id"] == str(doc["id"]) and r["field"] == "governing_law")
    target["correct_value"] = "Ireland"
    bad = next(r for r in rows if r["contract_id"] == str(doc["id"]) and r["field"] == "payment_terms_days")
    bad["correct_value"] = "soon"
    buf = io.StringIO()
    w = csv.DictWriter(buf, rows[0].keys())
    w.writeheader()
    w.writerows([target, bad])
    res = client.post("/api/quality/review-sheet", json={"content": buf.getvalue()}).json()
    assert res["applied"] == 1 and len(res["rejected"]) == 1 and "payment_terms_days" in res["rejected"][0]["row"]
    assert client.get(f"/api/contracts/{doc['id']}").json()["contract"]["governing_law"] == "Ireland"
