"""Connector registry and sync: list the remote folder, download what is new or changed into the inbox, record it, run the pipeline on it."""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import text

from app import pipeline
from app.connectors import crypto
from app.connectors.base import SUPPORTED_EXT, Connector, ConnectorError, RemoteFile
from app.connectors.gdrive import GoogleDrive
from app.connectors.mailbox import Mailbox
from app.connectors.msgraph import MicrosoftGraph
from app.connectors.rest import RestFeed
from app.db import SessionLocal

TYPES = {"gdrive": "Google Drive", "onedrive": "OneDrive", "sharepoint": "SharePoint", "imap": "Mailbox (IMAP)", "coupa": "Coupa", "sap": "SAP S/4HANA", "ariba": "SAP Ariba", "rest": "Generic REST (JSON)"}
SECRET_FIELDS = {"gdrive": ["service_account_json", "client_id", "client_secret", "refresh_token"], "onedrive": ["client_id", "client_secret"], "sharepoint": ["client_id", "client_secret"],
                 "imap": ["password"], "coupa": ["client_id", "client_secret"], "ariba": ["client_id", "client_secret"], "sap": ["api_key"], "rest": ["token", "api_key", "client_id", "client_secret"]}


def build(kind: str, config: dict, secrets: dict) -> Connector:
    if kind == "gdrive":
        return GoogleDrive(config, secrets)
    if kind in ("onedrive", "sharepoint"):
        return MicrosoftGraph(config, secrets, kind)
    if kind == "imap":
        return Mailbox(config, secrets)
    if kind in ("coupa", "sap", "ariba", "rest"):
        return RestFeed(config, secrets, kind)
    raise ConnectorError(f"unknown connector type {kind}")


def load(cid: int) -> dict:
    with SessionLocal() as s:
        r = s.execute(text("SELECT * FROM connectors WHERE id=:i"), {"i": cid}).mappings().first()
    if not r:
        raise ConnectorError("connector not found")
    return dict(r)


def instance(row: dict) -> Connector:
    return build(row["type"], row["config"] or {}, crypto.decrypt(row["secrets_enc"]))


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "connector"


def safe_rel(path: str) -> str:
    parts = [re.sub(r"[^\w.\- ()]+", "_", p) for p in path.split("/") if p not in ("", ".", "..")]
    return "/".join(parts)


def sync(cid: int, trigger: str = "manual", run_pipeline: bool = True) -> dict:
    row = load(cid)
    t0 = time.time()
    res = dict(new=0, updated=0, unchanged=0, removed=0, failed=0, skipped=0)
    events: list[tuple[str, str, str]] = []
    paths: list[Path] = []
    try:
        con = instance(row)
        with SessionLocal() as s:
            root = pipeline.inbox_path(s)
            known = {r["remote_id"]: dict(r) for r in s.execute(text("SELECT * FROM connector_files WHERE connector_id=:c"), {"c": cid}).mappings()}
        from app import feeds

        base = (feeds.feeds_dir() if row["target"] == "feeds" else root / row["target"]) / slug(row["name"])
        seen: set[str] = set()
        for f in con.list_files():
            if not f.name.lower().endswith(SUPPORTED_EXT + ((".csv",) if row["target"] == "feeds" else ())):
                res["skipped"] += 1
                continue
            seen.add(f.id)
            old = known.get(f.id)
            if old and old["etag"] == f.etag and old["status"] == "synced" and old["local_path"] and Path(old["local_path"]).exists():
                res["unchanged"] += 1
                with SessionLocal() as s:
                    s.execute(text("UPDATE connector_files SET last_seen=now() WHERE id=:i"), {"i": old["id"]})
                    s.commit()
                continue
            try:
                data = con.download(f)
                dest = base / safe_rel(f.path)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
                dest.with_suffix(".meta.json").write_text(json.dumps({"origin": f"connector:{row['name']}", "source_url": f.web_url, "remote_path": f.path, "remote_modified": f.modified,
                                                                      **({"status": "draft"} if row["target"] == "drafts" else {})})) if row["target"] != "feeds" else None
                with SessionLocal() as s:
                    s.execute(text("""INSERT INTO connector_files (connector_id, remote_id, path, etag, modified, size, web_url, local_path, status, last_seen)
                                      VALUES (:c,:r,:p,:e,:m,:z,:u,:l,'synced',now())
                                      ON CONFLICT (connector_id, remote_id) DO UPDATE SET path=:p, etag=:e, modified=:m, size=:z, web_url=:u, local_path=:l, status='synced', last_seen=now()"""),
                              {"c": cid, "r": f.id, "p": f.path, "e": f.etag, "m": f.modified, "z": len(data), "u": f.web_url, "l": str(dest)})
                    s.commit()
                res["updated" if old else "new"] += 1
                events.append(("updated" if old else "new", f.path, f"{len(data):,} bytes"))
                paths.append(dest)
            except Exception as e:
                res["failed"] += 1
                events.append(("failed", f.path, f"{type(e).__name__}: {e}"[:300]))
        for rid, old in known.items():
            if rid not in seen and old["status"] == "synced":
                res["removed"] += 1
                events.append(("removed", old["path"], "no longer in the folder (the contract is kept)"))
                with SessionLocal() as s:
                    s.execute(text("UPDATE connector_files SET status='removed-upstream' WHERE id=:i"), {"i": old["id"]})
                    s.commit()
        proc = None
        if paths and run_pipeline and row["target"] == "feeds":
            proc = feeds.run_feeds("connector")
        elif paths and run_pipeline:
            proc = pipeline.run_pipeline("connector", only=paths)
            if proc.get("status") == "busy":
                events.append(("queued", "", "the pipeline is busy; the folder pipeline will pick the files up"))
        status = "error" if res["failed"] and not (res["new"] + res["updated"]) else "ok"
        msg = f"{res['new']} new, {res['updated']} updated, {res['unchanged']} unchanged, {res['removed']} removed upstream" + (f", {res['failed']} failed" if res["failed"] else "")
    except Exception as e:
        status, msg = "error", f"{type(e).__name__}: {e}"[:400]
        res["failed"] += 1
        events.append(("failed", "", msg))
    with SessionLocal() as s:
        s.execute(text("UPDATE connectors SET last_sync_at=now(), last_status=:s, last_message=:m, next_sync_at=now() + make_interval(mins => interval_minutes) WHERE id=:i"), {"s": status, "m": msg, "i": cid})
        rid = s.execute(text("INSERT INTO pipeline_runs (trigger, pipeline, status, scanned, new_docs, updated, unchanged, failed, message, finished_at) VALUES (:t,:p,:st,:a,:b,:c,:d,:e,:m, now()) RETURNING id"),
                        {"t": trigger, "p": f"connector:{row['name']}", "st": "completed" if status == "ok" else "failed", "a": res["new"] + res["updated"] + res["unchanged"], "b": res["new"],
                         "c": res["updated"], "d": res["unchanged"], "e": res["failed"], "m": msg}).scalar()
        for act, p, d in events:
            s.execute(text("INSERT INTO pipeline_events (run_id, path, action, detail) VALUES (:r,:p,:a,:d)"), {"r": rid, "p": p, "a": act, "d": d})
        s.commit()
    return {"status": status, "message": msg, "seconds": round(time.time() - t0, 2), **res}


def due() -> list[int]:
    with SessionLocal() as s:
        return [r[0] for r in s.execute(text("SELECT id FROM connectors WHERE enabled AND trigger_mode='periodic' AND (next_sync_at IS NULL OR next_sync_at <= now()) ORDER BY id"))]


_ = (datetime, timedelta, timezone, RemoteFile)
