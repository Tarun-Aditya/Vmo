"""VMO depth: obligations, SLA, spend exceptions, vendor risk scores, benchmarks, feeds."""
from datetime import date

from sqlalchemy import text

from app import feeds, obligations, risk
from app.db import SessionLocal


def test_rule_obligations_read_milestones_slas_notices_and_renewal():
    clauses = [dict(heading="Deliverables", clause_type="deliverables", page=2,
                    text="Milestone 1: mobilisation and delivery plan by 16 February 2026. Milestone 2: core delivery by 3 May 2026.")]
    vals = [dict(metric_key="sla_availability_pct", value_num=99.9, page=3), dict(metric_key="payment_terms_days", value_num=45, page=2),
            dict(metric_key="insurance_cover_usd", value_num=5_000_000, page=4)]
    c = dict(title="x", type="SOW", effective_date=date(2026, 2, 2), expiry_date=date(2027, 2, 2), notice_period_days=60, auto_renew=True)
    out = {o["key"]: o for o in obligations.rule_obligations(c, clauses, vals, date(2026, 11, 6))}
    assert out["milestone:1"]["due_date"] == date(2026, 2, 16) and out["milestone:2"]["due_date"] == date(2026, 5, 3)
    assert out["metric:sla_availability_pct"]["target_value"] == 99.9 and out["metric:sla_availability_pct"]["party"] == "Supplier"
    assert out["metric:payment_terms_days"]["party"] == "Customer"
    assert out["metric:insurance_cover_usd"]["due_date"] == date(2027, 2, 2)          # next anniversary of the effective date
    assert out["renewal:notice"]["due_date"] == date(2026, 12, 4) and out["renewal:notice"]["kind"] == "renewal"


def test_obligations_api_statuses_and_marking_done(client):
    r = client.get("/api/obligations").json()
    assert r["summary"]["overdue"] == 3 and r["summary"]["done"] >= 10
    overdue = [o for o in r["rows"] if o["status"] == "overdue"]
    assert {o["kind"] for o in overdue} == {"milestone", "renewal"} and all(o["days_left"] < 0 for o in overdue)
    assert r["rows"][0]["status"] == "overdue"                                          # overdue first
    ms = next(o for o in overdue if o["kind"] == "milestone")
    try:
        done = client.patch(f"/api/obligations/{ms['obligation_id']}", json={"status": "done"}).json()
        assert done["status"] == "done" and client.get("/api/obligations").json()["summary"]["overdue"] == 2
    finally:
        client.patch(f"/api/obligations/{ms['obligation_id']}", json={"status": "open"})
    assert client.get("/api/obligations").json()["summary"]["overdue"] == 3
    assert client.patch("/api/obligations/999999", json={"status": "done"}).status_code == 404
    assert client.patch(f"/api/obligations/{ms['obligation_id']}", json={"status": "nope"}).status_code == 422


def test_spend_exceptions_find_every_planted_problem(client):
    ex = client.get("/api/spend/exceptions").json()
    kinds = {e["kind"] for e in ex}
    assert {"no_contract", "unsigned_contract", "duplicate", "above_run_rate", "billed_before_effective", "over_contract_value"} <= kinds
    assert ex[0]["severity"] == "critical" and "not fully signed" in ex[0]["detail"]
    off = [e for e in ex if e["kind"] == "no_contract"]
    import csv

    csv_off = sum(float(r["amount"]) for r in csv.DictReader((feeds.feeds_dir() / "invoices.csv").open()) if not r["contract_title"].strip())
    with SessionLocal() as s_:
        contracted = {r[0] for r in s_.execute(text("SELECT vendor FROM contracts WHERE status <> 'draft' AND type NOT IN ('NDA','DPA')"))}
    assert off and {e["vendor"] for e in off}.isdisjoint(contracted) and sum(e["amount_at_risk"] for e in off) == csv_off     # from the feed file, not hardcoded
    s = client.get("/api/spend/summary").json()
    assert s["off_contract"] == csv_off and s["exceptions"] == len(ex) and s["serious"] >= 4
    cs = {c["title"]: c for c in client.get("/api/spend/contracts").json()}
    assert any(c["pct_of_planned"] and c["pct_of_planned"] > 1.0 for c in cs.values())      # a contract billed above its planned value


def test_feed_loading_is_idempotent_and_upload_validates(client):
    csv_text = (feeds.feeds_dir() / "invoices.csv").read_text()
    again = feeds.load_csv("invoices.csv", csv_text)
    assert again["new"] == 0 and again["rows"] > 20
    assert client.post("/api/feeds/upload", json={"name": "notes.txt", "content": "x"}).status_code == 422
    with SessionLocal() as s:
        before = s.execute(text("SELECT count(*) FROM invoices")).scalar()
    extra = csv_text.splitlines()[0] + "\nINV-TEST-1,Testco Inc,,TST-1,2026-11-01,,,2026-12-16,,1000,Test,IT Services\n"
    try:
        r = client.post("/api/feeds/upload", json={"name": "invoices_test.csv", "content": extra}).json()
        assert r["status"] == "completed" and r["new_docs"] >= 1
        assert any(e["vendor"] == "Testco Inc" and e["kind"] == "no_contract" for e in client.get("/api/spend/exceptions").json())
    finally:
        (feeds.feeds_dir() / "invoices_test.csv").unlink(missing_ok=True)
        with SessionLocal() as s:
            s.execute(text("DELETE FROM invoices WHERE external_id='INV-TEST-1'"))
            s.commit()
        feeds.recompute()
        with SessionLocal() as s:
            assert s.execute(text("SELECT count(*) FROM invoices")).scalar() == before


def test_sla_series_breaches_and_manual_measurement(client):
    r = client.get("/api/sla").json()
    worst = next(s for s in r["series"] if s["metric_key"] == "sla_availability_pct")        # sorted: most breaches first
    assert worst["target"] and worst["breaches"] == 2 and worst["credit_usd"] > 0
    assert r["summary"]["breach_months"] >= 4
    cid = next(s["contract_id"] for s in r["series"] if s["breaches"] == 0 and s["metric_key"] == "sla_availability_pct")
    try:
        assert client.post("/api/sla/measurements", json={"contract_id": cid, "metric_key": "sla_availability_pct", "period": "2026-10-15", "actual": 97.0}).status_code == 200
        cirrus = next(s for s in client.get("/api/sla").json()["series"] if s["contract_id"] == cid and s["metric_key"] == "sla_availability_pct")
        assert cirrus["breaches"] == 1 and cirrus["points"][-1]["actual"] == 97.0
    finally:
        with SessionLocal() as s:
            s.execute(text("DELETE FROM sla_measurements WHERE contract_id=:c AND source='manual'"), {"c": cid})
            s.commit()
        feeds.recompute()
    assert client.post("/api/sla/measurements", json={"contract_id": cid, "metric_key": "nope", "period": "2026-10-01", "actual": 1}).status_code == 422


def test_risk_scores_are_ranked_explained_and_follow_the_weights(client):
    r = client.get("/api/risk/vendors").json()
    vs = {v["vendor"]: v for v in r["vendors"]}
    assert len(vs) == 9 and all(0 <= v["score"] <= 100 for v in vs.values())
    top = r["vendors"][0]
    assert top["tier"] in ("critical", "high") and [v["score"] for v in r["vendors"]] == sorted((v["score"] for v in r["vendors"]), reverse=True)
    assert risk.tier(55) == "critical" and risk.tier(10) == "low"
    with SessionLocal() as s_:
        uncapped_vendors = [x[0] for x in s_.execute(text("SELECT DISTINCT vendor FROM v_effective_terms WHERE liability_uncapped"))]
    assert uncapped_vendors and all(any("Uncapped liability" in d for d in vs[v]["components"]["contract_risk"]["drivers"]) for v in uncapped_vendors)   # derived from the contracts
    detail = client.get(f"/api/risk/vendors/{top['vendor']}").json()
    assert detail["score"] == top["score"]
    old = r["weights"]
    try:                                                                                # zero out concentration: Accentia drops
        w = [{"key": x["key"], "weight": 0 if x["key"] == "concentration" else x["weight"], "enabled": True} for x in old]
        new = client.put("/api/admin/risk-weights", json=w).json()
        assert next(v for v in new["vendors"] if v["vendor"] == top["vendor"])["score"] < top["score"]
    finally:
        client.put("/api/admin/risk-weights", json=[{"key": x["key"], "weight": x["weight"], "enabled": x["enabled"]} for x in old])
    assert client.get("/api/risk/vendors").json()["vendors"][0]["score"] == top["score"]
    assert client.get("/api/risk/vendors/Nobody").status_code == 404


def test_benchmarks_use_effective_values_and_flag_policy_breaches(client):
    b = client.get("/api/benchmarks").json()
    m = {x["metric_key"]: x for x in b["metrics"]}
    pay = m["payment_terms_days"]
    assert pay["median"] == 45 and all(v["type"] != "Amendment" for v in pay["values"])
    assert any(v["breaches_policy"] and v["value"] == 30 for v in pay["values"]) or pay["breaching"] >= 1
    ins = m["insurance_cover_usd"]
    low = [v for v in ins["values"] if v["breaches_policy"]]
    assert low and all(v["value"] < ins["policy"][0]["threshold"] for v in low)
    assert {c["cap"] for c in b["liability_caps"]} >= {"Unlimited"} and b["governing_law"]
