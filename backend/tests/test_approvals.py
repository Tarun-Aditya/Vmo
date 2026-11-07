"""Approval routing: rules choose the chain from type / value / severity, approvers decide in order, rejection sends the draft back, the last approval approves it (open threads block)."""
import pytest
from sqlalchemy import text

from app import alerts
from app.db import SessionLocal


@pytest.fixture()
def setup(client, seeded):
    cid = next(d["id"] for d in client.get("/api/contracts?status=draft").json() if client.get(f"/api/redline/{d['id']}").json().get("items"))
    with SessionLocal() as s:
        s.execute(text("DELETE FROM approval_rules"))
        for q in ("DELETE FROM approvals WHERE contract_id=:c", "DELETE FROM comment_threads WHERE contract_id=:c", "DELETE FROM contract_reviews WHERE contract_id=:c"):
            s.execute(text(q), {"c": cid})
        s.commit()
    yield cid
    with SessionLocal() as s:
        s.execute(text("DELETE FROM approval_rules"))
        for q in ("DELETE FROM approvals WHERE contract_id=:c", "DELETE FROM comment_threads WHERE contract_id=:c", "DELETE FROM contract_reviews WHERE contract_id=:c", "DELETE FROM alerts WHERE rule_key IN ('approval','approval_waiting')"):
            s.execute(text(q), {"c": cid})
        s.commit()


def rule(client, **kw):
    body = {"name": "Standard", "steps": [{"label": "Legal", "approvers": ["lena@arcadia.test"]}, {"label": "Finance", "approvers": ["fin@arcadia.test"]}], **kw}
    r = client.post("/api/admin/approval-rules", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_rules_are_validated_and_matched_by_type_value_and_severity(client, setup):
    cid = setup
    assert client.post("/api/admin/approval-rules", json={"name": "x", "steps": []}).status_code == 422
    assert client.post("/api/admin/approval-rules", json={"name": "x", "steps": [{"label": "a", "approvers": ["a@b.c"]}], "min_severity": "huge"}).status_code == 422
    assert client.post(f"/api/documents/{cid}/approval/start").status_code == 404                                    # no rule applies yet
    other = next(x for x in ("NDA", "SOW", "MSA") if x != client.get(f"/api/redline/{cid}").json()["type"])
    rule(client, name="Another document type only", doc_types=[other], sort_order=1)
    rule(client, name="Huge deals", min_value=10**12, sort_order=2)
    assert client.get(f"/api/documents/{cid}/approval").json()["matching_rule"] is None
    rule(client, name="Any deviation", min_severity="low", sort_order=3)
    m = client.get(f"/api/documents/{cid}/approval").json()["matching_rule"]
    assert m and m["name"] == "Any deviation"


def test_two_step_chain_notifications_and_final_approval(client, setup):
    cid = setup
    rule(client, min_severity="low")
    a = client.post(f"/api/documents/{cid}/approval/start").json()
    assert [s["status"] for s in a["steps"]] == ["pending", "waiting"] and client.post(f"/api/documents/{cid}/approval/start").status_code == 409
    inbox = client.get("/api/approvals/pending?approver=lena@arcadia.test").json()
    assert len(inbox) == 1 and inbox[0]["label"] == "Legal" and client.get("/api/approvals/pending?approver=fin@arcadia.test").json() == []
    assert client.post(f"/api/approvals/{a['id']}/steps/{a['steps'][1]['id']}/decide", json={"decision": "approve"}).status_code == 409        # out of order
    a = client.post(f"/api/approvals/{a['id']}/steps/{a['steps'][0]['id']}/decide", json={"decision": "approve", "comment": "ok"}).json()
    assert [s["status"] for s in a["steps"]] == ["approved", "pending"] and len(client.get("/api/approvals/pending?approver=fin@arcadia.test").json()) == 1
    client.post(f"/api/documents/{cid}/threads", json={"body": "one more thing"})
    assert client.post(f"/api/approvals/{a['id']}/steps/{a['steps'][1]['id']}/decide", json={"decision": "approve"}).status_code == 409             # open thread blocks the last step
    for t in client.get(f"/api/documents/{cid}/threads").json()["threads"]:
        client.put(f"/api/threads/{t['id']}", json={"status": "resolved"})
    a = client.post(f"/api/approvals/{a['id']}/steps/{a['steps'][1]['id']}/decide", json={"decision": "approve"}).json()
    assert a["status"] == "approved" and client.get(f"/api/redline/{cid}").json()["review"]["status"] == "approved"
    with SessionLocal() as s:
        assert s.execute(text("SELECT count(*) FROM alerts WHERE rule_key='approval'")).scalar() >= 2


def test_rejection_sends_the_draft_back_and_stalled_steps_raise_a_reminder(client, setup):
    cid = setup
    rule(client, min_severity="low", remind_after_days=1)
    a = client.post(f"/api/documents/{cid}/approval/start").json()
    with SessionLocal() as s:
        s.execute(text("UPDATE approval_steps SET activated_at = now() - interval '3 days' WHERE approval_id=:a AND seq=1"), {"a": a["id"]})
        s.commit()
    alerts.evaluate(deliver=False)
    with SessionLocal() as s:
        assert s.execute(text("SELECT count(*) FROM alerts WHERE rule_key='approval_waiting' AND contract_id=:c"), {"c": cid}).scalar() == 1
    r = client.post(f"/api/approvals/{a['id']}/steps/{a['steps'][0]['id']}/decide", json={"decision": "reject", "comment": "cap too high"}).json()
    assert r["status"] == "rejected" and client.get(f"/api/redline/{cid}").json()["review"]["status"] == "changes_requested"
    assert client.post(f"/api/approvals/{a['id']}/steps/{a['steps'][0]['id']}/decide", json={"decision": "approve"}).status_code == 409


def test_only_listed_approvers_can_decide_when_sign_in_is_on(client, setup, monkeypatch):
    cid = setup
    rule(client, min_severity="low")
    a = client.post(f"/api/documents/{cid}/approval/start").json()
    boot = client.post("/api/auth/bootstrap", json={"email": "lena@arcadia.test", "password": "correct-horse"})
    monkeypatch.setenv("AUTH_MODE", "on")
    try:
        tok = {"Authorization": f"Bearer {boot.json()['token']}"}
        assert client.post("/api/users", headers=tok, json={"email": "other@arcadia.test", "password": "password-1", "role": "reviewer"}).status_code == 200
        other = {"Authorization": "Bearer " + client.post("/api/auth/login", json={"email": "other@arcadia.test", "password": "password-1"}).json()["token"]}
        sid = a["steps"][0]["id"]
        assert client.post(f"/api/approvals/{a['id']}/steps/{sid}/decide", headers=other, json={"decision": "approve"}).status_code == 403
        assert client.post(f"/api/approvals/{a['id']}/steps/{sid}/decide", headers=tok, json={"decision": "approve"}).status_code == 200
    finally:
        monkeypatch.delenv("AUTH_MODE")
        with SessionLocal() as s:
            s.execute(text("DELETE FROM api_tokens"))
            s.execute(text("DELETE FROM users"))
            s.commit()
