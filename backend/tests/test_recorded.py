"""Demo mode replays recorded results for the sample documents: their extracted terms (by content fingerprint) and the answers to recorded questions about
them (ids mapped to the running database); anything not recorded, and everything outside Demo mode, goes to the engine as usual."""
import base64
import hashlib
import json
import time
from pathlib import Path

from sqlalchemy import text

from app import ask, mode, recorded
from app.db import SessionLocal

DOC = Path(__file__).resolve().parents[2] / "data" / "realistic_hotel" / "docs" / "prairie_waste_services.pdf"


def _read(client) -> int:
    before = client.get("/api/admin/pipeline/live").json().get("run_id", 0)
    client.post("/api/admin/pipeline/files", json={"files": [{"filename": DOC.name, "content_b64": base64.b64encode(DOC.read_bytes()).decode()}]})
    for _ in range(600):
        live = client.get("/api/admin/pipeline/live").json()
        if live.get("run_id", 0) > before and live.get("status") == "completed":
            return next(iter(live["docs"].values()))
        time.sleep(0.5)
    raise AssertionError("no run")


def test_demo_mode_replays_recorded_terms_and_answers(client, clean_docs, monkeypatch, tmp_path):
    h = hashlib.sha256(DOC.read_bytes()).hexdigest()
    fields = {"governing_law": {"value": "Recorded State", "confidence": 0.99, "clause_type": "governing_law", "page": 5},
              "expiry_date": {"value": "2026-11-30", "confidence": 0.99, "clause_type": "renewal", "page": 3}}
    rec = {"engine": "Claude", "recorded_at": "2026-11-15T00:00:00+00:00",
           "documents": {h: {"file": DOC.name, "engine": "Claude", "fields": fields}},
           "answers": {recorded.key("What happens if we end this contract early?", [h]): {
               "engine": "Claude", "response": {"answer": "Liquidated damages of six months' charges.", "tool_calls": [],
                                                "citations": [{"contract_id": f"@doc:{h}", "heading": "Early Termination"}],
                                                "tables": [{"title": "Clauses", "columns": [], "rows": [{"_cid": f"@doc:{h}"}]}],
                                                "thinking": [{"title": "SQL", "sql": f"SELECT 1 WHERE contract_id IN (@doc:{h})"}]}}}}
    p = tmp_path / "recorded.json"
    p.write_text(json.dumps(rec))
    monkeypatch.setattr(recorded, "PATH", p)
    monkeypatch.setattr(recorded, "_cache", None)
    monkeypatch.setattr(mode, "demo_on", lambda: True)
    doc = _read(client)
    assert doc["extract"]["engine"].startswith("recorded (Claude")
    cid = doc["contract_id"]
    with SessionLocal() as s:
        assert s.execute(text("SELECT governing_law FROM contracts WHERE id = :c"), {"c": cid}).scalar() == "Recorded State"
    r = ask.answer("what happens if we end this contract early?", scope=[cid])
    assert r["source"] == "recorded" and r["recorded_engine"] == "Claude"
    assert r["citations"][0]["contract_id"] == cid and r["tables"][0]["rows"][0]["_cid"] == cid and f"IN ({cid})" in r["thinking"][0]["sql"]
    assert ask.answer("Who signed it?", scope=[cid])["source"] != "recorded"          # not recorded: the engine answers
    monkeypatch.setattr(mode, "demo_on", lambda: False)                                 # Live mode: nothing is replayed
    assert recorded.answer_for("What happens if we end this contract early?", [cid]) is None and recorded.fields_for(h) is None
