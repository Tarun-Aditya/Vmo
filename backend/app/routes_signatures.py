"""E-signature API: request signatures on a draft version, signers sign via personal links (no account), completion certificate, DocuSign provider, and 'mark executed'
(moves the signed draft into the executed-contracts folder so it is read as an executed contract)."""
from __future__ import annotations

import hashlib
import json
import secrets
import shutil

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text

from app import esign, pipeline
from app.db import SessionLocal
from app.routes_auth import me

router = APIRouter(prefix="/api")


def rows(sql: str, **p) -> list[dict]:
    with SessionLocal() as s:
        return [dict(r) for r in s.execute(text(sql), p).mappings().all()]


def _req(rid: int) -> dict:
    r = rows("SELECT * FROM signature_requests WHERE id=:i", i=rid)
    if not r:
        raise HTTPException(404, "signature request not found")
    return {**r[0], "signers": rows("SELECT id, seq, name, email, role, status, signed_at, typed_signature, decline_reason FROM signers WHERE request_id=:i ORDER BY seq", i=rid)}


class SignerIn(BaseModel):
    name: str
    email: str
    role: str = "other"


class RequestIn(BaseModel):
    signers: list[SignerIn]
    sequential: bool = True
    provider: str = "internal"


@router.post("/documents/{cid}/signatures")
def request_signatures(cid: int, b: RequestIn, request: Request):
    d = rows("SELECT id, title, body_md, status FROM contracts WHERE id=:i", i=cid)
    if not d:
        raise HTTPException(404, "document not found")
    d = d[0]
    if d["status"] != "draft":
        raise HTTPException(409, "only drafts are sent for signature")
    if not b.signers or any(s.role not in ("customer", "supplier", "other") or "@" not in s.email or not s.name.strip() for s in b.signers):
        raise HTTPException(422, "each signer needs a name, an e-mail and a role of customer, supplier or other")
    if b.provider not in ("internal", "docusign"):
        raise HTTPException(422, "provider must be internal or docusign")
    if rows("SELECT 1 FROM signature_requests WHERE contract_id=:c AND status='pending'", c=cid):
        raise HTTPException(409, "a signature request is already in progress for this draft")
    ver = rows("SELECT COALESCE(max(version), 1) AS v FROM document_versions WHERE contract_id=:c", c=cid)[0]["v"]
    tokens = []
    with SessionLocal() as s:
        rid = s.execute(text("INSERT INTO signature_requests (contract_id, title, version, doc_hash, provider, sequential, created_by) VALUES (:c,:t,:v,:h,:p,:q,:u) RETURNING id"),
                        {"c": cid, "t": d["title"], "v": ver, "h": esign.doc_hash(d["body_md"]), "p": b.provider, "q": b.sequential, "u": me(request)["email"]}).scalar()
        for i, sg in enumerate(b.signers):
            raw = "sig_" + secrets.token_urlsafe(24)
            tokens.append(raw)
            s.execute(text("INSERT INTO signers (request_id, seq, name, email, role, token_hash) VALUES (:r,:q,:n,:e,:ro,:h)"),
                      {"r": rid, "q": i + 1, "n": sg.name.strip(), "e": sg.email.strip(), "ro": sg.role, "h": hashlib.sha256(raw.encode()).hexdigest()})
        s.commit()
    if b.provider == "docusign":
        if not esign.DocuSign.configured():
            with SessionLocal() as s:
                s.execute(text("DELETE FROM signature_requests WHERE id=:i"), {"i": rid})
                s.commit()
            raise HTTPException(501, "DocuSign is not configured: set DOCUSIGN_ACCOUNT_ID and DOCUSIGN_ACCESS_TOKEN (or the JWT variables)")
        from app import docx_export

        try:
            ds = esign.DocuSign()
            eid, sim_links = ds.send(d["title"], docx_export.md_to_docx(d["body_md"]), "contract.docx", [s.model_dump() for s in b.signers])
        except (httpx.HTTPError, RuntimeError) as e:
            with SessionLocal() as s:
                s.execute(text("DELETE FROM signature_requests WHERE id=:i"), {"i": rid})
                s.commit()
            raise HTTPException(502, f"DocuSign refused the request: {str(e)[:160]}")
        with SessionLocal() as s:
            s.execute(text("UPDATE signature_requests SET external_id=:e WHERE id=:i"), {"e": eid, "i": rid})
            s.commit()
    links = [{"email": sg.email, "path": f"/sign/{tok}"} for sg, tok in zip(b.signers, tokens)] if b.provider == "internal" else [{"email": x["email"], "path": x["url"], "external": True} for x in locals().get("sim_links", [])]
    return {**_req(rid), "links": links}


@router.get("/documents/{cid}/signatures")
def list_requests(cid: int):
    return [_req(r["id"]) for r in rows("SELECT id FROM signature_requests WHERE contract_id=:c ORDER BY id DESC", c=cid)]


@router.delete("/signatures/{rid}")
def cancel(rid: int):
    with SessionLocal() as s:
        s.execute(text("UPDATE signature_requests SET status='cancelled' WHERE id=:i AND status='pending'"), {"i": rid})
        s.commit()
    return _req(rid)


@router.get("/signatures/{rid}/certificate")
def get_certificate(rid: int):
    r = _req(rid)
    if r["status"] != "completed":
        raise HTTPException(409, "the certificate exists once everyone has signed")
    return r["certificate"]


# ------------------------------------------------------------------ signer side (the personal link is the credential)
def _signer(token: str) -> tuple[dict, dict]:
    s = rows("SELECT * FROM signers WHERE token_hash=:h", h=hashlib.sha256(token.encode()).hexdigest())
    if not s:
        raise HTTPException(404, "This signing link is not valid")
    return s[0], _req(s[0]["request_id"])


@router.get("/sign/{token}")
def open_sign(token: str):
    sg, r = _signer(token)
    d = rows("SELECT body_md FROM document_versions WHERE contract_id=:c AND version=:v", c=r["contract_id"], v=r["version"]) or rows("SELECT body_md FROM contracts WHERE id=:c", c=r["contract_id"])
    md = d[0]["body_md"] if d else ""
    my_turn = r["status"] == "pending" and sg["status"] == "pending" and (not r["sequential"] or all(x["status"] == "signed" for x in r["signers"] if x["seq"] < sg["seq"]))
    return {"title": r["title"], "md": md, "signer": {"name": sg["name"], "email": sg["email"], "status": sg["status"], "role": sg["role"]}, "request_status": r["status"], "my_turn": my_turn,
            "doc_hash": r["doc_hash"], "hash_matches": esign.doc_hash(md) == r["doc_hash"], "others": [{"name": x["name"], "status": x["status"]} for x in r["signers"]]}


class SignIn(BaseModel):
    typed_name: str
    agree: bool


@router.post("/sign/{token}")
def sign(token: str, b: SignIn, request: Request):
    sg, r = _signer(token)
    if r["status"] != "pending" or sg["status"] != "pending":
        raise HTTPException(409, "this request is no longer waiting for your signature")
    if r["sequential"] and any(x["status"] != "signed" for x in r["signers"] if x["seq"] < sg["seq"]):
        raise HTTPException(409, "it is not your turn yet: an earlier signer has not signed")
    if not b.agree or len(b.typed_name.strip()) < 2:
        raise HTTPException(422, "type your full name and tick the agreement to sign")
    with SessionLocal() as s:
        s.execute(text("UPDATE signers SET status='signed', signed_at=now(), typed_signature=:t, ip=:ip, user_agent=:ua WHERE id=:i"),
                  {"t": b.typed_name.strip(), "ip": request.client.host if request.client else None, "ua": request.headers.get("user-agent", "")[:200], "i": sg["id"]})
        s.commit()
    r = _req(r["id"])
    if all(x["status"] == "signed" for x in r["signers"]):
        _complete(r)
    return {"signed": True, "request_status": _req(r["id"])["status"]}


@router.post("/sign/{token}/decline")
def decline(token: str, reason: str = ""):
    sg, r = _signer(token)
    with SessionLocal() as s:
        s.execute(text("UPDATE signers SET status='declined', decline_reason=:r WHERE id=:i AND status='pending'"), {"r": reason[:300], "i": sg["id"]})
        s.execute(text("UPDATE signature_requests SET status='declined' WHERE id=:i AND status='pending'"), {"i": r["id"]})
        s.commit()
    return {"declined": True}


def _complete(r: dict) -> None:
    """Everyone signed: certificate, signature block appended as a new version (so signatories and dates are extracted), request completed."""
    from app.routes_docs import save_document

    signers = rows("SELECT * FROM signers WHERE request_id=:i ORDER BY seq", i=r["id"])
    cert = esign.certificate(r, signers)
    cid = r["contract_id"]
    md = rows("SELECT body_md FROM contracts WHERE id=:c", c=cid)[0]["body_md"]
    if "Signed electronically" not in md:
        save_document(cid, md.rstrip() + esign.signature_block(signers), "Signed electronically", "esign")
    with SessionLocal() as s:
        s.execute(text("UPDATE signature_requests SET status='completed', completed_at=now(), certificate=CAST(:c AS jsonb) WHERE id=:i"), {"c": json.dumps(cert), "i": r["id"]})
        s.commit()


# ------------------------------------------------------------------ DocuSign status sync + executed
@router.post("/signatures/{rid}/sync")
def sync_docusign(rid: int):
    r = _req(rid)
    if r["provider"] != "docusign" or not r["external_id"]:
        raise HTTPException(409, "only DocuSign requests are synced")
    try:
        st = esign.DocuSign().status(r["external_id"])
    except httpx.HTTPError as e:
        raise HTTPException(502, f"DocuSign: {str(e)[:160]}")
    status = st.get("status")
    if status == "completed" and r["status"] == "pending":
        with SessionLocal() as s:
            s.execute(text("UPDATE signers SET status='signed', signed_at=now() WHERE request_id=:i AND status='pending'"), {"i": rid})
            s.commit()
        _complete(_req(rid))
    elif status in ("declined", "voided"):
        with SessionLocal() as s:
            s.execute(text("UPDATE signature_requests SET status='declined' WHERE id=:i"), {"i": rid})
            s.commit()
    return {"docusign_status": status, "request": _req(rid)["status"]}


@router.post("/signatures/webhook/docusign")
async def docusign_webhook(request: Request):
    """DocuSign Connect-style callback: verified with an HMAC of the body (DOCUSIGN_CONNECT_SECRET), then the request is synced."""
    import base64
    import hmac
    import os

    body = await request.body()
    secret = os.environ.get("DOCUSIGN_CONNECT_SECRET") or ("sim-secret" if esign.simulated() else "")
    want = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode() if secret else None
    if not want or not hmac.compare_digest(want, request.headers.get("x-docusign-signature-1", "")):
        raise HTTPException(401, "bad signature")
    env = (json.loads(body).get("data") or {}).get("envelopeId")
    r = rows("SELECT id FROM signature_requests WHERE external_id=:e", e=env)
    if not r:
        raise HTTPException(404, "unknown envelope")
    from starlette.concurrency import run_in_threadpool

    return await run_in_threadpool(sync_docusign, r[0]["id"])           # it calls DocuSign over HTTP: never block the event loop


@router.post("/documents/{cid}/execute")
def mark_executed(cid: int):
    """Move a fully signed draft into the executed-contracts folder and re-ingest it, so every screen treats it as an executed contract."""
    done = rows("SELECT id FROM signature_requests WHERE contract_id=:c AND status='completed' ORDER BY id DESC LIMIT 1", c=cid)
    if not done:        # a missed callback is recovered here: ask the signing service for the latest status before refusing
        pend = rows("SELECT id FROM signature_requests WHERE contract_id=:c AND status='pending' AND provider='docusign' ORDER BY id DESC LIMIT 1", c=cid)
        if pend:
            try:
                sync_docusign(pend[0]["id"])
            except HTTPException:
                pass
            done = rows("SELECT id FROM signature_requests WHERE contract_id=:c AND status='completed' ORDER BY id DESC LIMIT 1", c=cid)
    if not done:
        raise HTTPException(409, "the draft has no completed signature request")
    d = rows("SELECT id, source_path FROM contracts WHERE id=:c AND status='draft'", c=cid)
    if not d:
        raise HTTPException(409, "this document is already an executed contract")
    with SessionLocal() as s:
        root = pipeline.inbox_path(s)
    src = root / d[0]["source_path"]
    dst = root / "contracts" / src.name
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    meta = src.with_suffix(".meta.json")
    if meta.exists():
        data = json.loads(meta.read_text())
        data.pop("status", None)
        dst.with_suffix(".meta.json").write_text(json.dumps(data))
    res = pipeline.run_pipeline("execute", only=[dst])
    new = rows("SELECT id FROM contracts WHERE source_path=:p", p=str(dst.relative_to(root)))
    if not new:
        raise HTTPException(500, f"re-ingest failed: {res}")
    with SessionLocal() as s:
        s.execute(text("UPDATE signature_requests SET executed_contract_id=:n WHERE contract_id=:c"), {"n": new[0]["id"], "c": cid})
        s.execute(text("DELETE FROM contracts WHERE id=:c"), {"c": cid})
        s.commit()
    src.unlink(missing_ok=True)
    meta.unlink(missing_ok=True)
    return {"executed_contract_id": new[0]["id"]}
