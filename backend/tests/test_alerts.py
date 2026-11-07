"""Alerts: rules raise each event once, the notification centre works, and delivery reaches a real SMTP server and a webhook."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from aiosmtpd.controller import Controller
from sqlalchemy import text

from app import alerts
from app.db import SessionLocal


class Inbox:
    def __init__(self):
        self.msgs = []

    async def handle_DATA(self, server, session, envelope):
        self.msgs.append(envelope.content.decode("utf8", "replace"))
        return "250 OK"


@pytest.fixture()
def clean(seeded):
    with SessionLocal() as s:
        s.execute(text("DELETE FROM alert_channels"))
        s.commit()
    yield
    with SessionLocal() as s:
        s.execute(text("DELETE FROM alert_channels"))
        s.execute(text("UPDATE alert_rules SET enabled = true"))
        s.execute(text("DELETE FROM alerts"))          # drop what the test delivered, then re-raise the real ones quietly
        s.commit()
    alerts.evaluate(deliver=False)


def test_evaluate_is_idempotent_and_matches_the_data(client, clean):
    alerts.evaluate(deliver=False)
    again = alerts.evaluate(deliver=False)
    assert again["new"] == 0                                                    # every event is raised once
    open_ = client.get("/api/alerts?status=all").json()["items"]
    keys = {a["rule_key"] for a in open_}
    assert {"renewal_notice_passed", "contract_expiring_30"} & keys
    n30 = client.get("/api/alerts?status=all&limit=500").json()["items"]
    expiring = [a for a in n30 if a["rule_key"] == "contract_expiring_30"]
    with SessionLocal() as s:
        want = s.execute(text("SELECT count(*) FROM v_renewals WHERE days_left BETWEEN 0 AND 30")).scalar()
    assert len(expiring) == want


def test_ack_resolve_and_unread(client, clean):
    alerts.evaluate(deliver=False)
    a = client.get("/api/alerts").json()["items"][0]
    u0 = client.get("/api/alerts/summary").json()["unread"]
    r = client.put(f"/api/alerts/{a['id']}", json={"status": "acknowledged", "by": "priya"}).json()
    assert r["status"] == "acknowledged" and r["acknowledged_by"] == "priya"
    assert client.get("/api/alerts/summary").json()["open"] >= 0
    assert client.get(f"/api/alerts?status=acknowledged").json()["items"][0]["id"] == a["id"]
    assert client.put("/api/alerts/999999", json={"status": "resolved"}).status_code == 404
    assert client.put(f"/api/alerts/{a['id']}", json={"status": "nope"}).status_code == 422
    client.post("/api/alerts/read-all")
    assert client.get("/api/alerts/summary").json()["unread"] == 0 <= u0
    client.put(f"/api/alerts/{a['id']}", json={"status": "open"})


def test_rule_toggle_and_validation(client, clean):
    r = client.put("/api/admin/alert-rules/sla_breach", json={"enabled": False, "severity": "low", "params": {"months": 1}}).json()
    assert r["enabled"] is False and r["severity"] == "low" and r["params"] == {"months": 1}
    assert client.put("/api/admin/alert-rules/sla_breach", json={"severity": "urgent"}).status_code == 422
    assert client.put("/api/admin/alert-rules/nope", json={"enabled": True}).status_code == 404
    client.put("/api/admin/alert-rules/sla_breach", json={"enabled": True, "severity": "high", "params": {"months": 2}})


def test_email_and_webhook_delivery(client, clean):
    import socket

    with socket.socket() as so:
        so.bind(("127.0.0.1", 0))
        port = so.getsockname()[1]
    box = Inbox()
    ctl = Controller(box, hostname="127.0.0.1", port=port)
    ctl.start()
    hits: list[dict] = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            hits.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        em = client.post("/api/admin/alert-channels", json={"name": "ops mail", "kind": "email", "min_severity": "high",
                                                           "config": {"host": "127.0.0.1", "port": port, "to": "vmo@arcadia.test", "app_url": "https://iq.test"}}).json()
        wh = client.post("/api/admin/alert-channels", json={"name": "slack", "kind": "slack", "secrets": {"url": f"http://127.0.0.1:{srv.server_port}/hook"}}).json()
        assert wh["secrets_set"] == {"url": True} and "secrets_enc" not in wh
        assert client.post(f"/api/admin/alert-channels/{em['id']}/test").json()["ok"] is True
        assert client.post(f"/api/admin/alert-channels/{wh['id']}/test").json()["ok"] is True
        assert "Test alert from ContractIQ" in box.msgs[0] and hits[0]["text"].startswith("*LOW*")
        # real delivery of freshly raised alerts
        with SessionLocal() as s:
            s.execute(text("DELETE FROM alerts"))
            s.commit()
        res = alerts.evaluate()
        assert res["new"] > 0 and res["delivered"] > 0
        assert len(hits) > 1 and any("high" in m.lower() or "critical" in m.lower() for m in box.msgs[1:])
        assert all("[ContractIQ · low]" not in m for m in box.msgs[1:])        # min severity honoured on the email channel
        ch = {c["name"]: c for c in client.get("/api/admin/alert-channels").json()}
        assert ch["ops mail"]["last_status"] == "ok"
        assert client.post("/api/admin/alert-channels", json={"name": "ops mail", "kind": "slack"}).status_code == 409
    finally:
        ctl.stop()
        srv.shutdown()


def test_failing_channel_is_reported_not_raised(client, clean):
    ch = client.post("/api/admin/alert-channels", json={"name": "dead", "kind": "webhook", "secrets": {"url": "http://127.0.0.1:9/x"}}).json()
    r = client.post(f"/api/admin/alert-channels/{ch['id']}/test").json()
    assert r["ok"] is False and r["error"]
    assert client.get("/api/admin/alert-channels").json()[0]["last_status"] == "error"


def test_review_assignment(client, seeded):
    d = next(r for r in client.get("/api/redline").json() if r["status"] == "draft") if isinstance(client.get("/api/redline").json(), list) else None
    cid = d["id"] if d else client.get("/api/contracts?status=draft").json()[0]["id"]
    r = client.put(f"/api/redline/{cid}/review", json={"status": "in_review", "assignee": "meera", "due_date": "2026-12-01"}).json()
    assert r["review"]["assignee"] == "meera" and r["review"]["due_date"] == "2026-12-01"
