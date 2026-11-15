"""Intake screen: a document goes through the normal pipeline and every step is reported as it happens; a reset removes what was added;
a 'what happens if...' question about one document is answered from its clauses."""
import base64
import json
from pathlib import Path

from sqlalchemy import text

from app import ask_nl, extract_rules, textutil
from app.db import SessionLocal

SAMPLES = Path(__file__).resolve().parents[2] / "data" / "realistic_hotel" / "docs"


def _events(r) -> list[dict]:
    return [json.loads(x) for x in r.text.splitlines() if x.strip()]


def test_intake_streams_each_step_and_reset_removes_it(client, clean_docs, monkeypatch):
    monkeypatch.setattr(extract_rules.settings, "customer_names", "Seabright")
    assert any(s["file"] == "prairie_waste_services.pdf" for s in client.get("/api/intake/samples").json())
    assert client.get("/api/intake/samples/prairie_waste_services.pdf").content[:4] == b"%PDF"
    r = client.post("/api/intake", json={"samples": ["prairie_waste_services.pdf"]})
    ev = _events(r)
    steps = [e["step"] for e in ev if e.get("doc") == "prairie_waste_services.pdf"]
    assert steps == ["queued", "start", "read", "structure", "extract", "index", "check", "done"], steps
    by = {e["step"]: e for e in ev}
    assert by["read"]["pages"] >= 5 and by["read"]["paged"] and by["structure"]["clauses"] > 10
    f = {x["field"]: x["value"] for x in by["extract"]["fields"]}
    assert f["expiry_date"] == "2026-11-30" and f["notice_period_days"] == "90" and f["customer_signatory"] == "Robert Nakamura"
    assert by["index"]["vectors"] == by["structure"]["clauses"] and by["index"]["dims"] > 0
    assert by["check"]["act_by"] == "2026-09-01" and by["check"]["failed_count"] >= 1
    s = by["summary"]
    assert s["contracts"] == 1 and s["uncapped"] == 1 and s["deadlines"][0]["notice_deadline"] == "2026-09-01"
    cid = by["done"]["contract_id"]
    assert client.get(f"/api/contracts/{cid}").status_code == 200
    assert client.delete("/api/intake").json()["removed"] == 1
    with SessionLocal() as s_:
        assert s_.execute(text("SELECT count(*) FROM contracts WHERE id = :c"), {"c": cid}).scalar() == 0


def test_intake_reads_an_uploaded_word_file_and_refuses_other_types(client, clean_docs):
    raw = (SAMPLES / "keystone_valet_parking.docx").read_bytes()
    ev = _events(client.post("/api/intake", json={"files": [{"filename": "valet.docx", "content_b64": base64.b64encode(raw).decode()}]}))
    by = {e["step"]: e for e in ev}
    assert by["read"]["format"] == "DOCX" and not by["read"]["paged"]        # a Word file has no fixed pages: none are invented
    assert by["done"]["title"].startswith("Valet Parking")
    assert client.post("/api/intake", json={"files": [{"filename": "x.exe", "content_b64": "AA=="}]}).status_code == 400
    assert client.post("/api/intake", json={}).status_code == 400
    client.delete("/api/intake")


def test_word_dollar_sign_and_how_questions():
    assert textutil.normalize(r"not to exceed US\$9,600") == "not to exceed USD 9,600"
    plan = ask_nl.parse("What happens if we end this contract early?", scope=[1])
    assert plan and plan["intent"] == "search"
    assert ask_nl.parse("Tell me about this contract", scope=[1])["intent"] == "card"


def test_a_folder_links_schedules_and_a_scanned_amendment_catches_a_duplicate_and_skips_a_second_run(client, clean_docs, monkeypatch):
    monkeypatch.setattr(extract_rules.settings, "customer_names", "Seabright")
    up = lambda name, as_=None: {"filename": as_ or name, "content_b64": base64.b64encode((SAMPLES / name).read_bytes()).decode()}  # noqa: E731
    files = [up("meridian_msa.pdf"), up("meridian_sow_harbor.pdf"), up("meridian_amendment_1_scan.pdf"), up("meridian_msa.pdf", "MSA signed copy.pdf")]
    done = {e["doc"]: e for e in _events(client.post("/api/intake", json={"files": files})) if e["step"] == "done"}
    msa, sow, amd, dup = done["meridian_msa.pdf"], done["meridian_sow_harbor.pdf"], done["meridian_amendment_1_scan.pdf"], done["MSA_signed_copy.pdf"]
    assert msa["action"] == "new" and msa["type"] == "MSA"
    assert sow["type"] == "SOW" and sow["parent_id"] == msa["contract_id"]
    assert amd["type"] == "Amendment" and amd["parent_id"] == msa["contract_id"] and set(amd["overrides"]) >= {"payment_terms_days", "expiry_date"}
    assert dup["action"] == "duplicate" and dup["contract_id"] == msa["contract_id"]
    with SessionLocal() as s:
        eff = s.execute(text("SELECT payment_terms_days, expiry_date FROM v_effective_terms WHERE contract_id = :c"), {"c": msa["contract_id"]}).first()
    assert eff[0] == 30 and str(eff[1]) == "2029-02-28"          # the scanned amendment's terms now govern the master agreement
    again = [e for e in _events(client.post("/api/intake", json={"files": files[:2]})) if e["step"] == "done"]
    assert [e["action"] for e in again] == ["unchanged", "unchanged"]
    client.delete("/api/intake")
