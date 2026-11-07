"""Alerts API: notification centre (list / unread / acknowledge / resolve), rules, delivery channels (e-mail, Slack, Teams, webhook) and test-send."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from app import alerts
from app.connectors import crypto
from app.db import SessionLocal

router = APIRouter(prefix="/api")
SECRET_FIELDS = {"email": ["password"], "slack": ["url"], "teams": ["url"], "webhook": ["url"]}
CONFIG_FIELDS = {"email": ["host", "port", "from", "to", "username", "starttls", "ssl", "app_url"], "slack": [], "teams": [], "webhook": []}
SEVERITIES = ("low", "medium", "high", "critical")


def rows(sql: str, **p) -> list[dict]:
    with SessionLocal() as s:
        return [dict(r) for r in s.execute(text(sql), p).mappings().all()]


@router.get("/alerts")
def list_alerts(status: str = "open", limit: int = 100):
    where = "" if status == "all" else "WHERE status = :s" if status in ("open", "acknowledged", "resolved") else "WHERE status <> 'resolved'"
    items = rows(f"""SELECT id, rule_key, title, body, severity, link, contract_id, vendor, status, created_at, read_at, acknowledged_by, delivered FROM alerts {where}
                     ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, created_at DESC LIMIT :l""", s=status, l=min(limit, 500))
    return {"items": items, "unread": rows("SELECT count(*) AS n FROM alerts WHERE status='open' AND read_at IS NULL")[0]["n"]}


@router.get("/alerts/summary")
def summary():
    r = rows("SELECT count(*) FILTER (WHERE read_at IS NULL) AS unread, count(*) AS open, count(*) FILTER (WHERE severity='critical') AS critical FROM alerts WHERE status='open'")[0]
    return r


class StatusIn(BaseModel):
    status: str | None = None
    by: str | None = None


@router.put("/alerts/{aid}")
def update_alert(aid: int, b: StatusIn):
    if b.status not in (None, "open", "acknowledged", "resolved"):
        raise HTTPException(422, "status must be open, acknowledged or resolved")
    with SessionLocal() as s:
        n = s.execute(text("UPDATE alerts SET status=COALESCE(:st,status), read_at=COALESCE(read_at, now()), acknowledged_by=COALESCE(:by, acknowledged_by) WHERE id=:i"), {"st": b.status, "by": b.by, "i": aid}).rowcount
        s.commit()
    if not n:
        raise HTTPException(404, "alert not found")
    return rows("SELECT * FROM alerts WHERE id=:i", i=aid)[0]


@router.post("/alerts/read-all")
def read_all():
    with SessionLocal() as s:
        s.execute(text("UPDATE alerts SET read_at = now() WHERE read_at IS NULL"))
        s.commit()
    return summary()


@router.post("/alerts/evaluate")
def evaluate():
    return alerts.evaluate()


# ------------------------------------------------------------------ rules
@router.get("/admin/alert-rules")
def get_rules():
    with SessionLocal() as s:
        alerts.ensure_defaults(s)
        s.commit()
    return rows("""SELECT r.*, (SELECT count(*) FROM alerts a WHERE a.rule_key = r.key AND a.status = 'open') AS open_alerts FROM alert_rules r ORDER BY sort_order, key""")


class RuleIn(BaseModel):
    enabled: bool | None = None
    severity: str | None = None
    params: dict | None = None
    channels: list[str] | None = None


@router.put("/admin/alert-rules/{key}")
def put_rule(key: str, b: RuleIn):
    if b.severity is not None and b.severity not in SEVERITIES:
        raise HTTPException(422, "invalid severity")
    if b.channels is not None and not set(b.channels) <= {"in_app", "email", "chat"}:
        raise HTTPException(422, "channels must be in_app, email and/or chat")
    with SessionLocal() as s:
        n = s.execute(text("""UPDATE alert_rules SET enabled=COALESCE(:e,enabled), severity=COALESCE(:s,severity), params=COALESCE(CAST(:p AS jsonb),params), channels=COALESCE(:c,channels) WHERE key=:k"""),
                      {"e": b.enabled, "s": b.severity, "p": None if b.params is None else json.dumps(b.params), "c": b.channels, "k": key}).rowcount
        s.commit()
    if not n:
        raise HTTPException(404, "rule not found")
    return rows("SELECT * FROM alert_rules WHERE key=:k", k=key)[0]


# ------------------------------------------------------------------ channels
def _view(r: dict) -> dict:
    sec = crypto.decrypt(r.get("secrets_enc"))
    out = {k: v for k, v in r.items() if k != "secrets_enc"}
    out["secrets_set"] = {k: bool(sec.get(k)) for k in SECRET_FIELDS[r["kind"]]}
    return out


class ChannelIn(BaseModel):
    name: str
    kind: str
    config: dict = {}
    secrets: dict = {}
    enabled: bool = True
    min_severity: str = "medium"


def _check(c: ChannelIn) -> None:
    if c.kind not in SECRET_FIELDS or c.min_severity not in SEVERITIES or not c.name.strip():
        raise HTTPException(422, "invalid name, kind or minimum severity")
    if c.kind == "email" and not (c.config.get("host") and c.config.get("to")):
        raise HTTPException(422, "e-mail needs an SMTP host and a recipient")


def _clean(c: ChannelIn) -> dict:
    return {k: v for k, v in c.config.items() if k in CONFIG_FIELDS[c.kind]}


@router.get("/admin/alert-channels")
def list_channels():
    return [_view(r) for r in rows("SELECT * FROM alert_channels ORDER BY id")]


@router.post("/admin/alert-channels")
def create_channel(c: ChannelIn):
    _check(c)
    sec = {k: v for k, v in c.secrets.items() if k in SECRET_FIELDS[c.kind] and v}
    with SessionLocal() as s:
        try:
            cid = s.execute(text("""INSERT INTO alert_channels (name, kind, config, secrets_enc, enabled, min_severity) VALUES (:n,:k,CAST(:c AS jsonb),:s,:e,:m) RETURNING id"""),
                            {"n": c.name.strip(), "k": c.kind, "c": json.dumps(_clean(c)), "s": crypto.encrypt(sec) if sec else None, "e": c.enabled, "m": c.min_severity}).scalar()
            s.commit()
        except Exception:
            raise HTTPException(409, "a channel with that name already exists")
    return _view(rows("SELECT * FROM alert_channels WHERE id=:i", i=cid)[0])


@router.put("/admin/alert-channels/{cid}")
def update_channel(cid: int, c: ChannelIn):
    _check(c)
    cur = rows("SELECT * FROM alert_channels WHERE id=:i", i=cid)
    if not cur:
        raise HTTPException(404, "channel not found")
    sec = crypto.decrypt(cur[0]["secrets_enc"])
    sec.update({k: v for k, v in c.secrets.items() if k in SECRET_FIELDS[c.kind] and v})
    with SessionLocal() as s:
        s.execute(text("UPDATE alert_channels SET name=:n, kind=:k, config=CAST(:c AS jsonb), secrets_enc=:s, enabled=:e, min_severity=:m WHERE id=:i"),
                  {"n": c.name.strip(), "k": c.kind, "c": json.dumps(_clean(c)), "s": crypto.encrypt(sec) if sec else None, "e": c.enabled, "m": c.min_severity, "i": cid})
        s.commit()
    return _view(rows("SELECT * FROM alert_channels WHERE id=:i", i=cid)[0])


@router.delete("/admin/alert-channels/{cid}")
def delete_channel(cid: int):
    with SessionLocal() as s:
        s.execute(text("DELETE FROM alert_channels WHERE id=:i"), {"i": cid})
        s.commit()
    return {"ok": True}


@router.post("/admin/alert-channels/{cid}/test")
def test_channel(cid: int):
    cur = rows("SELECT * FROM alert_channels WHERE id=:i", i=cid)
    if not cur:
        raise HTTPException(404, "channel not found")
    return alerts.send(cur[0], {"title": "Test alert from ContractIQ", "body": "If you can read this, the channel works.", "severity": "low", "link": "/alerts", "vendor": None})


@router.post("/admin/alert-channels/demo")
def demo_channels():
    """Demo: channels that deliver to the built-in simulated Slack, Teams, webhook and SMTP sinks (see /sim/outbox). Needs SIMULATORS=1."""
    import os

    if os.environ.get("SIMULATORS", "0") != "1":
        raise HTTPException(409, "the simulators are switched off (set SIMULATORS=1)")
    base = os.environ.get("PUBLIC_API_URL", "http://localhost:8000").rstrip("/")
    spec = [("Slack #vmo-alerts (simulated)", "slack", {}, {"url": f"{base}/sim/hook/slack"}, "medium"), ("Teams VMO channel (simulated)", "teams", {}, {"url": f"{base}/sim/hook/teams"}, "high"),
            ("Webhook to ticketing (simulated)", "webhook", {}, {"url": f"{base}/sim/hook/ticketing"}, "high"),
            ("E-mail to the VMO (simulated)", "email", {"host": "127.0.0.1", "port": int(os.environ.get("SIM_SMTP_PORT", "2525")), "to": "vmo@arcadia.demo", "from": "contractiq@arcadia.demo"}, {}, "high")]
    made = []
    for name, kind, cfg, sec, sev in spec:
        if rows("SELECT 1 FROM alert_channels WHERE name=:n", n=name):
            continue
        with SessionLocal() as s:
            s.execute(text("INSERT INTO alert_channels (name, kind, config, secrets_enc, enabled, min_severity) VALUES (:n,:k,CAST(:c AS jsonb),:s,true,:m)"),
                      {"n": name, "k": kind, "c": json.dumps(cfg), "s": crypto.encrypt(sec) if sec else None, "m": sev})
            s.commit()
        made.append(name)
    return {"created": made}
