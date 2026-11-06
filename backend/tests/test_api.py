"""API smoke tests against the seeded DB (skipped when no DB / not seeded)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app


@pytest.fixture(scope="module")
def client(db):
    with db.connect() as c:
        if c.execute(text("select count(*) from contracts")).scalar() < 18:
            pytest.skip("database not seeded")
    return TestClient(app)


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "db": "ok", "pgvector": "ok"}


def test_filters_and_list(client):
    assert len(client.get("/api/contracts").json()) == 21
    assert {c["type"] for c in client.get("/api/contracts?category=SaaS").json()} == {"SaaS", "DPA"}


def test_detail_shows_amendment_provenance(client):
    msa = next(c for c in client.get("/api/contracts?type=MSA&search=Bluepeak").json())
    d = client.get(f"/api/contracts/{msa['id']}").json()
    pay = next(e for e in d["effective_terms"] if e["field"] == "payment_terms_days")
    assert pay["value"] == 30 and pay["overridden"] and "Amendment" in pay["source_title"]
    assert {c["type"] for c in d["hierarchy"]["children"]} == {"SOW", "Amendment", "NDA"}
    assert all(f["confidence"] is not None for f in d["fields"])


def test_dashboard_matches_planted_facts(client):
    d = client.get("/api/dashboard").json()
    assert d["kpis"]["contracts"] == 21 and d["kpis"]["uncapped"] == 3
    assert d["kpis"]["autorenew_notice_soon"] == 2 and d["kpis"]["expiring_90"] == 8
    lanes = {k: v["count"] for k, v in d["lanes"].items()}
    assert lanes == {"30": 4, "60": 1, "90": 3}  # by expiry date: 0-30 / 31-60 / 61-90 days
    adspark = next(i for i in d["lanes"]["30"]["items"] if "AdSpark" in i["title"])
    assert adspark["notice_passed"] and adspark["auto_renew"]
    assert len(d["monthly"]) == 12 and sum(m["count"] for m in d["monthly"]) >= 8


def test_sql_guard(client):
    from app.ask import run_sql

    assert "error" in run_sql("DELETE FROM contracts")
    assert "error" in run_sql("SELECT 1; SELECT 2")
    assert "error" in run_sql("SELECT embedding FROM clauses")  # column revoked from RO role
    assert run_sql("SELECT count(*) AS n FROM contracts WHERE title LIKE '%MSA%'")["rows"]


def test_redline_and_templates(client):
    drafts = client.get("/api/drafts").json()
    assert sorted(d["deviations"] for d in drafts) == [0, 3, 4, 5, 6]
    saas = next(t for t in client.get("/api/templates").json() if t["type"] == "SaaS")
    m = client.get(f"/api/templates/{saas['id']}").json()
    assert len(m["matrix"]) == 4 and any(c for r in m["matrix"] for c in r["cells"].values())


def test_hierarchy_msa_sow_work_order(client):
    rows = client.get("/api/contracts").json()
    by_id = {r["id"]: r for r in rows}
    wos = [r for r in rows if r["type"] == "Work Order"]
    assert len(wos) == 3
    for wo in wos:  # every Work Order hangs under a SOW, which hangs under an MSA
        sow = by_id[wo["parent_id"]]
        assert sow["type"] == "SOW" and by_id[sow["parent_id"]]["type"] == "MSA"
    d = client.get(f"/api/contracts/{wos[0]['id']}").json()
    assert d["hierarchy"]["type"] == "MSA"
    sow_node = next(c for c in d["hierarchy"]["children"] if c["children"])
    assert any(g["type"] == "Work Order" for g in sow_node["children"])


def test_signatures(client):
    rows = {r["title"]: r for r in client.get("/api/contracts").json()}
    wo2 = rows["Work Order 2 – Store Wi-Fi Refresh – Bluepeak Technologies"]
    assert not wo2["fully_executed"] and wo2["supplier_signatory"] is None
    d = client.get(f"/api/contracts/{wo2['id']}").json()["signatures"]
    assert d["customer_signatory"] == "Rohit Sharma" and d["supplier_signed_date"] is None
    assert sum(1 for r in rows.values() if not r["fully_executed"]) == 1


def test_clause_matrix_ticks_crosses_and_citations(client):
    m = client.get("/api/clause-matrix").json()
    assert len(m["columns"]) == 18 and [len(g["rows"]) for g in m["groups"]] == [19, 5]
    exe = {r["title"]: r for r in m["groups"][0]["rows"]}
    msa = exe["Master Services Agreement – Bluepeak Technologies"]["cells"]
    assert msa["liability_cap"]["present"] and msa["liability_cap"]["page"] == 3
    assert "liability" in msa["liability_cap"]["text"].lower()          # citation text
    nda = exe["NDA – Meridian Logistics"]["cells"]["payment"]
    assert not nda["present"] and not nda["expected"] and "not part of the standard" in nda["note"]
    wo2 = exe["Work Order 2 – Store Wi-Fi Refresh – Bluepeak Technologies"]["cells"]["execution"]
    assert not wo2["present"] and "Not fully signed" in wo2["note"]
    quantum = next(r for r in m["groups"][1]["rows"] if "Quantum" in r["title"])["cells"]["data_return"]
    assert not quantum["present"] and quantum["expected"] and "gap" in quantum["note"]  # draft gap
