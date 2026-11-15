"""Continuous intake (Admin -> Pipeline): any number of files go into the inbox and through the normal pipeline; every run, whatever started it, reports each
document's steps in the live view; schedules and a scanned amendment link to their master agreement; a duplicate is caught; files already read are skipped.
Also: a 'what happens if...' question about one document is answered from its clauses."""
import base64
import time
from pathlib import Path

from sqlalchemy import text

from app import ask_nl, extract_rules, textutil
from app.db import SessionLocal

SAMPLES = Path(__file__).resolve().parents[2] / "data" / "realistic_hotel" / "docs"


def _up(name: str, as_: str | None = None) -> dict:
    return {"filename": as_ or name, "content_b64": base64.b64encode((SAMPLES / name).read_bytes()).decode()}


def _wait(client, run_after: int = 0, timeout: float = 300) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        live = client.get("/api/admin/pipeline/live").json()
        if live.get("run_id", 0) > run_after and live.get("status") in ("completed", "failed"):
            return live
        time.sleep(0.5)
    raise AssertionError("the run did not finish")


def _docs(live: dict) -> dict:
    return {d["name"]: d for d in (live["docs"][k] for k in live["order"])}


def test_files_are_read_live_linked_deduplicated_and_skipped_the_second_time(client, clean_docs, monkeypatch):
    monkeypatch.setattr(extract_rules.settings, "customer_names", "Seabright")
    before = client.get("/api/admin/pipeline/live").json().get("run_id", 0)
    files = [_up("meridian_msa.pdf"), _up("meridian_sow_harbor.pdf"), _up("meridian_amendment_1_scan.pdf"), _up("prairie_waste_services.pdf"), _up("meridian_msa.pdf", "MSA signed copy.pdf")]
    assert client.post("/api/admin/pipeline/files", json={"files": files}).json()["started"]
    live = _wait(client, before)
    d = _docs(live)
    msa, sow, amd, waste, dup = d["meridian_msa.pdf"], d["meridian_sow_harbor.pdf"], d["meridian_amendment_1_scan.pdf"], d["prairie_waste_services.pdf"], d["MSA_signed_copy.pdf"]
    for x in (msa, sow, amd, waste):                                           # every step reported, in the live view, for each document
        assert x["action"] == "new" and all(k in x for k in ("read", "structure", "extract", "index", "check")), x
    assert waste["read"]["pages"] >= 5 and waste["read"]["paged"] and waste["index"]["vectors"] == waste["structure"]["clauses"]
    f = {x["field"]: x["value"] for x in waste["extract"]["fields"]}
    assert f["expiry_date"] == "2026-11-30" and f["notice_period_days"] == "90" and f["customer_signatory"] == "Robert Nakamura"
    assert waste["check"]["act_by"] == "2026-09-01"
    assert sow["type"] == "SOW" and sow["parent_id"] == msa["contract_id"]
    assert amd["read"]["scanned"] and amd["type"] == "Amendment" and amd["parent_id"] == msa["contract_id"] and set(amd["overrides"]) >= {"payment_terms_days", "expiry_date"}
    assert dup["action"] == "duplicate" and dup["contract_id"] == msa["contract_id"]
    with SessionLocal() as s:
        eff = s.execute(text("SELECT payment_terms_days, expiry_date FROM v_effective_terms WHERE contract_id = :c"), {"c": msa["contract_id"]}).first()
    assert eff[0] == 30 and str(eff[1]) == "2029-02-28"                       # the scanned amendment's terms now govern the master agreement
    client.post("/api/admin/pipeline/files", json={"files": files[:2]})
    again = _docs(_wait(client, live["run_id"]))
    assert {x["action"] for x in again.values()} == {"unchanged"}            # the same files again: recognised and skipped


def test_upload_refuses_other_types_and_empty(client, clean_docs):
    assert client.post("/api/admin/pipeline/files", json={"files": [{"filename": "x.exe", "content_b64": "AA=="}]}).status_code == 400
    assert client.post("/api/admin/pipeline/files", json={"files": []}).status_code == 400


def test_the_demo_sample_folder_loads_and_is_removed(client, clean_docs, monkeypatch):
    monkeypatch.setattr(extract_rules.settings, "customer_names", "Seabright")
    info = client.get("/api/admin/pipeline/samples").json()
    assert len(info["files"]) >= 11
    before = client.get("/api/admin/pipeline/live").json().get("run_id", 0)
    client.post("/api/admin/pipeline/samples")
    live = _wait(client, before, timeout=600)
    acts = [x["action"] for x in _docs(live).values()]
    assert acts.count("duplicate") == 1 and acts.count("new") == len(acts) - 1
    assert client.get("/api/admin/pipeline/samples").json()["loaded"] == len(acts) - 1
    assert client.delete("/api/admin/pipeline/samples").json()["removed"] == len(acts) - 1


def test_word_dollar_sign_and_how_questions():
    assert textutil.normalize(r"not to exceed US\$9,600") == "not to exceed USD 9,600"
    plan = ask_nl.parse("What happens if we end this contract early?", scope=[1])
    assert plan and plan["intent"] == "search"
    assert ask_nl.parse("Tell me about this contract", scope=[1])["intent"] == "card"


def test_questions_about_ticked_documents():
    assert ask_nl.parse("What are the insurance requirements?", scope=[1, 2])["clause_keys"] == ["insurance"]
    assert ask_nl.parse("What are the termination terms?", scope=[1, 2])["intent"] == "search"
    assert "liability_uncapped" in ask_nl.parse("Which of these have no liability cap?", scope=[1, 2])["where"]
    assert ask_nl.parse("Show start date, end date and payment terms", scope=[1, 2])["intent"] == "table"
