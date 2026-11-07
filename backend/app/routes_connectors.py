"""Connectors API: configure Google Drive / OneDrive / SharePoint, test the connection, sync now, see what was synced."""
from __future__ import annotations

import json
import threading

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text

from app.connectors import crypto, service
from app.connectors.base import ConnectorError
from app.db import SessionLocal

router = APIRouter(prefix="/api")
# api_base / token_url / login_base: advanced overrides (sovereign clouds such as graph.microsoft.us, proxies, test servers)
CONFIG_FIELDS = {"gdrive": ["folder", "recursive", "api_base", "token_url"], "onedrive": ["tenant_id", "user", "drive_id", "folder", "recursive", "api_base", "login_base"],
                 "sharepoint": ["tenant_id", "site_url", "library", "folder", "recursive", "api_base", "login_base"],
                 "imap": ["host", "port", "ssl", "username", "folder", "from_filter", "subject_filter"],
                 **{k: ["base_url", "token_url", "token_path", "scope", "path", "items_path", "params", "mapping", "page_param", "page_size", "auth", "etag", "mode", "files_path", "file_name", "file_url", "id", "supplier"] for k in ("coupa", "sap", "ariba", "rest")}}


def rows(sql: str, **p) -> list[dict]:
    with SessionLocal() as s:
        return [dict(r) for r in s.execute(text(sql), p).mappings().all()]


def view(r: dict) -> dict:
    sec = crypto.decrypt(r.get("secrets_enc"))
    out = {k: v for k, v in r.items() if k != "secrets_enc"}
    out["type_label"] = service.TYPES[r["type"]]
    out["secrets_set"] = {k: bool(sec.get(k)) for k in service.SECRET_FIELDS[r["type"]]}
    out["files"] = rows("SELECT count(*) AS n FROM connector_files WHERE connector_id=:c AND status='synced'", c=r["id"])[0]["n"]
    return out


class ConnectorIn(BaseModel):
    name: str
    type: str
    config: dict = {}
    secrets: dict = {}              # only the secrets being (re)set; blanks keep the stored value
    target: str = "contracts"
    enabled: bool = True
    trigger_mode: str = "periodic"
    interval_minutes: int = 60


def _validate(c: ConnectorIn) -> None:
    if c.type not in service.TYPES:
        raise HTTPException(422, "unknown connector type")
    if c.target not in ("contracts", "drafts", "feeds") or c.trigger_mode not in ("periodic", "manual") or not 1 <= c.interval_minutes <= 60 * 24 * 7:
        raise HTTPException(422, "invalid target, trigger or interval")
    if not c.name.strip():
        raise HTTPException(422, "give the connector a name")


@router.get("/connectors")
def list_connectors():
    return {"connectors": [view(r) for r in rows("SELECT * FROM connectors ORDER BY id")], "types": service.TYPES}


@router.post("/connectors")
def create(c: ConnectorIn):
    _validate(c)
    cfg = {k: v for k, v in c.config.items() if k in CONFIG_FIELDS[c.type]}
    sec = {k: v for k, v in c.secrets.items() if k in service.SECRET_FIELDS[c.type] and v}
    try:
        with SessionLocal() as s:
            cid = s.execute(text("""INSERT INTO connectors (name, type, config, secrets_enc, target, enabled, trigger_mode, interval_minutes, next_sync_at)
                                    VALUES (:n,:t,CAST(:c AS jsonb),:s,:tg,:e,:tm,:i, now()) RETURNING id"""),
                            {"n": c.name.strip(), "t": c.type, "c": json.dumps(cfg), "s": crypto.encrypt(sec), "tg": c.target, "e": c.enabled, "tm": c.trigger_mode, "i": c.interval_minutes}).scalar()
            s.commit()
    except Exception as e:
        raise HTTPException(409, f"could not save: {str(e)[:120]}")
    return view(rows("SELECT * FROM connectors WHERE id=:i", i=cid)[0])


@router.put("/connectors/{cid}")
def update(cid: int, c: ConnectorIn):
    _validate(c)
    old = service.load(cid)
    cfg = {k: v for k, v in c.config.items() if k in CONFIG_FIELDS[c.type]}
    sec = crypto.decrypt(old["secrets_enc"])
    sec.update({k: v for k, v in c.secrets.items() if k in service.SECRET_FIELDS[c.type] and v})
    with SessionLocal() as s:
        s.execute(text("UPDATE connectors SET name=:n, config=CAST(:c AS jsonb), secrets_enc=:s, target=:tg, enabled=:e, trigger_mode=:tm, interval_minutes=:i WHERE id=:id"),
                  {"n": c.name.strip(), "c": json.dumps({**(old["config"] or {}), **cfg}), "s": crypto.encrypt(sec), "tg": c.target, "e": c.enabled, "tm": c.trigger_mode, "i": c.interval_minutes, "id": cid})
        s.commit()
    return view(rows("SELECT * FROM connectors WHERE id=:i", i=cid)[0])


@router.delete("/connectors/{cid}")
def delete(cid: int):
    with SessionLocal() as s:
        s.execute(text("DELETE FROM connectors WHERE id=:i"), {"i": cid})
        s.commit()
    return {"deleted": cid}


@router.post("/connectors/{cid}/test")
def test(cid: int):
    try:
        return service.instance(service.load(cid)).test()
    except ConnectorError as e:
        return {"ok": False, "detail": str(e)}
    except Exception as e:
        return {"ok": False, "detail": f"{type(e).__name__}: {e}"[:300]}


@router.post("/connectors/{cid}/sync")
def sync_now(cid: int, wait: bool = False):
    service.load(cid)
    if wait:
        return service.sync(cid, "manual")
    threading.Thread(target=service.sync, args=(cid, "manual"), daemon=True).start()
    return {"started": True}


@router.get("/connectors/{cid}/files")
def files(cid: int):
    return rows("SELECT path, status, modified, size, web_url, last_seen FROM connector_files WHERE connector_id=:c ORDER BY path", c=cid)


@router.post("/connectors/demo-erp")
def connect_demo_erp():
    """Demo: register the built-in simulated Coupa and SAP systems as connectors (the real connector code talks to them over HTTP) and sync once. Needs SIMULATORS=1."""
    import os

    if os.environ.get("SIMULATORS", "0") != "1":
        raise HTTPException(409, "the simulators are switched off (set SIMULATORS=1)")
    base = os.environ.get("PUBLIC_API_URL", "http://localhost:8000").rstrip("/")
    spec = [("Coupa (simulated)", "coupa", {"base_url": f"{base}/sim/coupa", "page_size": 50}, {"client_id": "demo-client", "client_secret": "demo-secret"}, "feeds"),
            ("SAP S/4HANA (simulated)", "sap", {"base_url": f"{base}/sim/sap"}, {"api_key": "demo-sap-key"}, "feeds"),
            ("Coupa contracts (simulated)", "coupa", {"base_url": f"{base}/sim/coupa", "mode": "contracts"}, {"client_id": "demo-client", "client_secret": "demo-secret"}, "contracts"),
            ("SAP contracts (simulated)", "sap", {"base_url": f"{base}/sim/sap", "mode": "contracts"}, {"api_key": "demo-sap-key"}, "contracts"),
            ("Ariba contracts (simulated)", "ariba", {"base_url": f"{base}/sim/ariba", "mode": "contracts"}, {"client_id": "demo-ariba-key", "client_secret": "demo-ariba-secret"}, "contracts")]
    out = []
    for name, kind, cfg, sec, target in spec:
        ex = rows("SELECT id FROM connectors WHERE name=:n", n=name)
        if ex:
            cid = ex[0]["id"]
        else:
            with SessionLocal() as s:
                cid = s.execute(text("""INSERT INTO connectors (name, type, config, secrets_enc, target, enabled, trigger_mode, interval_minutes, next_sync_at)
                                        VALUES (:n,:t,CAST(:c AS jsonb),:s,:tg,true,'manual',60, now()) RETURNING id"""), {"n": name, "t": kind, "c": json.dumps(cfg), "s": crypto.encrypt(sec), "tg": target}).scalar()
                s.commit()
        out.append({"name": name, "id": cid, **service.sync(cid, "demo")})
    return {"connectors": out}


@router.post("/connectors/demo-cloud")
def connect_demo_cloud(request: Request):
    """Demo: register simulated Google Drive, OneDrive and SharePoint (built into this app, same API shapes as the real services) as connectors and sync once. Needs SIMULATORS=1."""
    import os

    if os.environ.get("SIMULATORS", "0") != "1":
        raise HTTPException(409, "the simulators are switched off (set SIMULATORS=1)")
    base = os.environ.get("PUBLIC_API_URL", "http://localhost:8000").rstrip("/")
    from app.simulators import cloud as sim_cloud

    try:
        sa = sim_cloud.demo(base)[2]
    except Exception as e:                     # the demo documents need pandoc
        raise HTTPException(409, f"the cloud simulators could not start: {e}")
    spec = [("Google Drive (simulated)", "gdrive", "contracts", {"folder": "root1", "api_base": f"{base}/sim/gdrive/drive/v3", "token_url": f"{base}/sim/gdrive/token"}, {"service_account_json": sa}),
            ("OneDrive (simulated)", "onedrive", "contracts", {"tenant_id": "demo-tenant", "user": "legal@arcadia.demo", "folder": "Contracts", "api_base": f"{base}/sim/graph/v1.0", "login_base": f"{base}/sim/graph"},
             {"client_id": "demo-app", "client_secret": "demo-secret"}),
            ("SharePoint (simulated)", "sharepoint", "drafts", {"tenant_id": "demo-tenant", "site_url": "https://arcadia.sharepoint.demo/sites/Legal", "library": "Documents", "folder": "Vendor Agreements",
                                                                 "api_base": f"{base}/sim/graph/v1.0", "login_base": f"{base}/sim/graph"}, {"client_id": "demo-app", "client_secret": "demo-secret"})]
    out = []
    for name, kind, target, cfg, sec in spec:
        ex = rows("SELECT id FROM connectors WHERE name=:n", n=name)
        if ex:
            cid = ex[0]["id"]
        else:
            with SessionLocal() as s:
                cid = s.execute(text("""INSERT INTO connectors (name, type, config, secrets_enc, target, enabled, trigger_mode, interval_minutes, next_sync_at)
                                        VALUES (:n,:t,CAST(:c AS jsonb),:s,:tg,true,'manual',60, now()) RETURNING id"""), {"n": name, "t": kind, "c": json.dumps(cfg), "s": crypto.encrypt(sec), "tg": target}).scalar()
                s.commit()
        out.append({"name": name, "id": cid, **service.sync(cid, "demo")})
    return {"connectors": out}


@router.post("/connectors/demo-mailbox")
def connect_demo_mailbox():
    """Demo: register the simulated IMAP mailbox (two unread mails with contract attachments) as an intake connector and sync it."""
    import os

    if os.environ.get("SIMULATORS", "0") != "1":
        raise HTTPException(409, "the simulators are switched off (set SIMULATORS=1)")
    from app.simulators import mail as sim_mail

    name = "Mailbox intake (simulated)"
    cfg = {"host": "127.0.0.1", "port": int(os.environ.get("SIM_IMAP_PORT", "1143")), "ssl": False, "username": sim_mail.DEMO_USER, "folder": "INBOX"}
    ex = rows("SELECT id FROM connectors WHERE name=:n", n=name)
    if ex:
        cid = ex[0]["id"]
    else:
        with SessionLocal() as s:
            cid = s.execute(text("""INSERT INTO connectors (name, type, config, secrets_enc, target, enabled, trigger_mode, interval_minutes, next_sync_at)
                                    VALUES (:n,'imap',CAST(:c AS jsonb),:s,'contracts',true,'manual',60, now()) RETURNING id"""), {"n": name, "c": json.dumps(cfg), "s": crypto.encrypt({"password": sim_mail.DEMO_PASS})}).scalar()
            s.commit()
    return {"connectors": [{"name": name, "id": cid, **service.sync(cid, "demo")}]}
