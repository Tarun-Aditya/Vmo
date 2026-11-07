"""A simulated e-signature service speaking the part of the DocuSign eSignature REST API v2.1 that ContractIQ uses (create envelope, get envelope, download the combined document),
plus a neutral signing page and Connect-style webhook, so the whole send -> sign -> completed -> executed flow can be demonstrated with no account.
This is a stand-in for demos and tests, not DocuSign and not a legally binding signing service. Enabled with SIMULATORS=1. Demo token: sim-token, account: sim-account."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timezone
from html import escape

import httpx
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import text

from app.db import SessionLocal

router = APIRouter(prefix="/sim/docusign")
TOKEN, ACCOUNT = "sim-token", "sim-account"
SECRET = os.environ.get("DOCUSIGN_CONNECT_SECRET", "sim-secret")


def _auth(request: Request) -> None:
    if request.headers.get("authorization") != f"Bearer {TOKEN}":
        raise HTTPException(401, "AUTHORIZATION_INVALID_TOKEN")


def _public(request: Request) -> str:
    return os.environ.get("PUBLIC_API_URL") or str(request.base_url).rstrip("/")


def _get(eid: str) -> dict:
    with SessionLocal() as s:
        r = s.execute(text("SELECT * FROM sim_envelopes WHERE id=:i"), {"i": eid}).mappings().first()
    if not r:
        raise HTTPException(404, "ENVELOPE_DOES_NOT_EXIST")
    return dict(r)


@router.post("/restapi/v2.1/accounts/{account}/envelopes")
async def create(account: str, request: Request):
    from starlette.concurrency import run_in_threadpool

    _auth(request)
    b = await request.json()
    return await run_in_threadpool(_create, account, request, b)


def _create(account: str, request: Request, b: dict):
    docs, signers = b.get("documents") or [], (b.get("recipients") or {}).get("signers") or []
    if not docs or not signers:
        raise HTTPException(400, "INVALID_REQUEST_BODY: documents and signers are required")
    eid = secrets.token_hex(8)
    rec = [{"recipientId": s.get("recipientId"), "name": s["name"], "email": s["email"], "routingOrder": int(s.get("routingOrder") or i + 1), "status": "sent", "token": secrets.token_urlsafe(12), "signedAt": None, "signature": None}
           for i, s in enumerate(signers)]
    with SessionLocal() as s:
        s.execute(text("INSERT INTO sim_envelopes (id, account, subject, doc_name, doc_ext, doc_b64, recipients, webhook_url) VALUES (:i,:a,:s,:n,:e,:d,CAST(:r AS jsonb),:w)"),
                  {"i": eid, "a": account, "s": b.get("emailSubject"), "n": docs[0].get("name"), "e": docs[0].get("fileExtension") or "docx", "d": docs[0]["documentBase64"], "r": json.dumps(rec),
                   "w": (b.get("eventNotification") or {}).get("url")})
        s.commit()
    base = _public(request)
    return {"envelopeId": eid, "status": "sent", "uri": f"/envelopes/{eid}",
            "simulator": {"note": "Stand-in for DocuSign. Real DocuSign e-mails each signer; here the signing links are returned so the demo can open them.",
                          "signing_links": [{"name": r["name"], "email": r["email"], "url": f"{base}/sim/docusign/sign/{eid}/{r['token']}"} for r in rec]}}


@router.get("/restapi/v2.1/accounts/{account}/envelopes/{eid}")
def status(account: str, eid: str, request: Request):
    _auth(request)
    e = _get(eid)
    return {"envelopeId": eid, "status": e["status"], "emailSubject": e["subject"], "completedDateTime": e["completed_at"].isoformat() if e["completed_at"] else None,
            "recipients": {"signers": [{k: v for k, v in r.items() if k != "token"} for r in e["recipients"]]}}


@router.get("/restapi/v2.1/accounts/{account}/envelopes/{eid}/documents/combined")
def combined(account: str, eid: str, request: Request):
    _auth(request)
    e = _get(eid)
    return Response(base64.b64decode(e["doc_b64"]), media_type="application/octet-stream", headers={"Content-Disposition": f'attachment; filename="{e["doc_name"]}.{e["doc_ext"]}"'})


PAGE = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>E-sign simulator</title>
<style>body{{font:15px system-ui,sans-serif;max-width:560px;margin:40px auto;padding:0 16px;color:#1e293b}}.b{{border:1px solid #cbd5e1;border-radius:8px;padding:16px;margin:12px 0}}
.sim{{background:#fef3c7;border:1px solid #f59e0b;border-radius:6px;padding:6px 10px;font-size:12px}}input[type=text]{{width:100%;padding:8px;font-size:16px;box-sizing:border-box}}
button{{background:#4f46e5;color:#fff;border:0;border-radius:6px;padding:10px 16px;font-size:15px;cursor:pointer}}</style></head><body>
<p class="sim">Simulated e-signature service for demonstration. Not DocuSign; not a legally binding signature.</p><h1>{subject}</h1>
<div class="b"><p>Recipient: <b>{name}</b> ({email})</p><p><a href="{doc}">Review the document ({docname})</a></p>{body}</div></body></html>"""


@router.get("/sign/{eid}/{token}", response_class=HTMLResponse)
def sign_page(eid: str, token: str, request: Request):
    e = _get(eid)
    r = next((x for x in e["recipients"] if x["token"] == token), None)
    if not r:
        raise HTTPException(404, "invalid signing link")
    if r["status"] == "completed":
        body = f"<p>✓ You signed on {escape(str(r['signedAt']))[:19]}.</p>"
    elif e["status"] != "sent":
        body = f"<p>This envelope is {escape(e['status'])}.</p>"
    elif any(x["status"] != "completed" for x in e["recipients"] if x["routingOrder"] < r["routingOrder"]):
        body = "<p>Waiting for an earlier signer. Come back to this link later.</p>"
    else:
        body = (f'<form method="post" action="{_public(request)}/sim/docusign/sign/{eid}/{token}"><p><label>Type your full name to sign<br><input type="text" name="name" required minlength="2"></label></p>'
                '<p><label><input type="checkbox" name="agree" value="1" required> I have read the document and agree to sign it electronically.</label></p><button type="submit">Sign</button> '
                f'<button type="submit" formaction="{_public(request)}/sim/docusign/decline/{eid}/{token}" formnovalidate style="background:#64748b">Decline</button></form>')
    return PAGE.format(subject=escape(e["subject"] or "Please sign"), name=escape(r["name"]), email=escape(r["email"]), doc=f"{_public(request)}/sim/docusign/doc/{eid}/{token}", docname=escape(f"{e['doc_name']}.{e['doc_ext']}"), body=body)


@router.get("/doc/{eid}/{token}")
def doc(eid: str, token: str):
    e = _get(eid)
    if not any(x["token"] == token for x in e["recipients"]):
        raise HTTPException(404, "invalid link")
    return Response(base64.b64decode(e["doc_b64"]), media_type="application/octet-stream", headers={"Content-Disposition": f'attachment; filename="{e["doc_name"]}.{e["doc_ext"]}"'})


def _save(eid: str, rec: list, status: str, done: bool) -> None:
    with SessionLocal() as s:
        s.execute(text("UPDATE sim_envelopes SET recipients=CAST(:r AS jsonb), status=:st, completed_at=CASE WHEN :d THEN now() ELSE completed_at END WHERE id=:i"), {"r": json.dumps(rec), "st": status, "d": done, "i": eid})
        s.commit()


def _webhook(e: dict, status_: str) -> None:
    if not e.get("webhook_url"):
        return
    body = json.dumps({"event": f"envelope-{status_}", "data": {"envelopeId": e["id"], "status": status_}}).encode()
    def post():
      try:
        httpx.post(e["webhook_url"], content=body, headers={"Content-Type": "application/json", "X-DocuSign-Signature-1": base64.b64encode(hmac.new(SECRET.encode(), body, hashlib.sha256).digest()).decode()}, timeout=60)
      except httpx.HTTPError:
        pass                                                        # a missed webhook is recovered by the status check

    import threading

    threading.Thread(target=post, daemon=True).start()               # like the real service, the callback does not hold up the signer's page


@router.post("/sign/{eid}/{token}", response_class=HTMLResponse)
def sign(eid: str, token: str, request: Request, name: str = Form(...), agree: str = Form("")):
    e = _get(eid)
    rec = e["recipients"]
    r = next((x for x in rec if x["token"] == token), None)
    if not r or not agree or e["status"] != "sent" or r["status"] == "completed":
        raise HTTPException(400, "cannot sign")
    if any(x["status"] != "completed" for x in rec if x["routingOrder"] < r["routingOrder"]):
        raise HTTPException(409, "an earlier signer has not signed")
    r.update(status="completed", signedAt=datetime.now(timezone.utc).isoformat(), signature=name.strip())
    done = all(x["status"] == "completed" for x in rec)
    _save(eid, rec, "completed" if done else "sent", done)
    if done:
        _webhook(e, "completed")
    return sign_page(eid, token, request)


@router.post("/decline/{eid}/{token}", response_class=HTMLResponse)
def decline(eid: str, token: str, request: Request):
    e = _get(eid)
    rec = e["recipients"]
    r = next((x for x in rec if x["token"] == token), None)
    if not r or e["status"] != "sent":
        raise HTTPException(400, "cannot decline")
    r["status"] = "declined"
    _save(eid, rec, "declined", False)
    _webhook(e, "declined")
    return sign_page(eid, token, request)
