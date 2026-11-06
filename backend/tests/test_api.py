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
    assert len(client.get("/api/contracts").json()) == 18
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
    assert d["kpis"]["contracts"] == 18 and d["kpis"]["uncapped"] == 3
    assert d["kpis"]["autorenew_notice_soon"] == 2 and d["kpis"]["expiring_90"] == 8
    b = {x["bucket"]: x["count"] for x in d["buckets"]}
    assert b["30"] == 4 and b["overdue"] == 1


def test_sql_guard(client):
    from app.ask import run_sql

    assert "error" in run_sql("DELETE FROM contracts")
    assert "error" in run_sql("SELECT 1; SELECT 2")
    assert "error" in run_sql("SELECT embedding FROM clauses")          # column revoked from RO role
    assert run_sql("SELECT count(*) AS n FROM contracts WHERE title LIKE '%MSA%'")["rows"]


def test_redline_and_templates(client):
    drafts = client.get("/api/drafts").json()
    assert sorted(d["deviations"] for d in drafts) == [0, 3, 4, 5, 6]
    saas = next(t for t in client.get("/api/templates").json() if t["type"] == "SaaS")
    m = client.get(f"/api/templates/{saas['id']}").json()
    assert len(m["matrix"]) == 4 and any(c for r in m["matrix"] for c in r["cells"].values())
