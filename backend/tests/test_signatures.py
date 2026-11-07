"""E-signature: personal signing links (ordered), certificate, signature block extracted as signatories, mark executed, and the DocuSign provider against a local stand-in."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from sqlalchemy import text

from app import pipeline
from app.db import SessionLocal

NDA = """# Mutual Non-Disclosure Agreement – Signco Labs

**Parties:** Arcadia Retail Inc. (the "Customer") and Signco Labs Inc (the "Supplier")
**Effective Date:** 1 December 2026

## Term
This Agreement commences on 1 December 2026 and continues for three (3) years.

## Confidentiality
Each party shall keep the other's Confidential Information confidential and survive for 3 years after this Agreement ends.

## Governing Law
This Agreement is governed by the laws of New York.
"""


@pytest.fixture()
def draft(client, seeded):
    cid = client.post("/api/redline/upload", json={"filename": "signco_nda.md", "content": NDA, "owner": "Legal", "category": "Legal"}).json()["contract_id"]
    assert cid
    yield cid
    with SessionLocal() as s:
        root = pipeline.inbox_path(s)
        s.execute(text("DELETE FROM signature_requests WHERE title ILIKE '%Signco%'"))
        s.execute(text("DELETE FROM contracts WHERE vendor ILIKE '%Signco%'"))
        s.commit()
    for f in list(root.rglob("signco_nda*")):
        f.unlink()


def test_internal_signing_in_order_with_certificate_and_execution(client, draft):
    r = client.post(f"/api/documents/{draft}/signatures", json={"signers": [{"name": "Helena Cruz", "email": "helena@arcadia.test", "role": "customer"}, {"name": "Sam Lee", "email": "sam@signco.test", "role": "supplier"}]}).json()
    assert r["status"] == "pending" and len(r["links"]) == 2 and client.post(f"/api/documents/{draft}/signatures", json={"signers": [{"name": "A B", "email": "a@b.c"}]}).status_code == 409
    t1, t2 = (x["path"].split("/")[-1] for x in r["links"])
    assert client.get(f"/api/sign/{t1}").json()["my_turn"] is True and client.get(f"/api/sign/{t2}").json()["my_turn"] is False
    assert client.post(f"/api/sign/{t2}", json={"typed_name": "Sam Lee", "agree": True}).status_code == 409                    # not his turn
    assert client.post(f"/api/sign/{t1}", json={"typed_name": "H", "agree": False}).status_code == 422
    assert client.post(f"/api/sign/{t1}", json={"typed_name": "Helena Cruz", "agree": True}).json()["request_status"] == "pending"
    assert client.post(f"/api/sign/{t1}", json={"typed_name": "Helena Cruz", "agree": True}).status_code == 409                  # only once
    assert client.get(f"/api/documents/{draft}/signatures").json()[0]["signers"][0]["status"] == "signed"
    assert client.get(f"/api/signatures/{r['id']}/certificate").status_code == 409
    assert client.post(f"/api/sign/{t2}", json={"typed_name": "Sam Lee", "agree": True}).json()["request_status"] == "completed"
    cert = client.get(f"/api/signatures/{r['id']}/certificate").json()
    assert [s["name"] for s in cert["signers"]] == ["Helena Cruz", "Sam Lee"] and len(cert["sha256"]) == 64 and all(s["ip"] for s in cert["signers"])
    md = client.get(f"/api/documents/{draft}/content").json()["md"]
    assert "Signed electronically" in md and "Helena Cruz" in md and "Sam Lee" in md
    ex = client.post(f"/api/documents/{draft}/execute").json()
    c = client.get(f"/api/contracts/{ex['executed_contract_id']}").json()["contract"]
    assert c["status"] != "draft" and c["fully_executed"] is True and c["customer_signatory"] == "Helena Cruz" and c["supplier_signatory"] == "Sam Lee"
    assert client.get(f"/api/documents/{draft}/content").status_code == 404                                                       # the draft became the executed contract


def test_decline_and_bad_inputs(client, draft):
    assert client.post(f"/api/documents/{draft}/signatures", json={"signers": []}).status_code == 422
    assert client.post(f"/api/documents/{draft}/signatures", json={"signers": [{"name": "A B", "email": "nope"}]}).status_code == 422
    r = client.post(f"/api/documents/{draft}/signatures", json={"signers": [{"name": "Sam Lee", "email": "sam@signco.test", "role": "supplier"}]}).json()
    tok = r["links"][0]["path"].split("/")[-1]
    assert client.post(f"/api/sign/{tok}/decline?reason=terms").json()["declined"] and client.get(f"/api/documents/{draft}/signatures").json()[0]["status"] == "declined"
    assert client.post(f"/api/sign/{tok}", json={"typed_name": "Sam Lee", "agree": True}).status_code == 409
    assert client.get("/api/sign/sig_nonsense").status_code == 404
    assert client.post(f"/api/documents/{draft}/execute").status_code == 409                                                       # nothing completed


def test_docusign_provider_against_a_stand_in(client, draft, monkeypatch):
    seen = {}

    class H(BaseHTTPRequestHandler):
        def _send(self, body, ctype="application/json"):
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            seen["auth"] = self.headers.get("Authorization")
            seen["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self._send(json.dumps({"envelopeId": "env-123", "status": "sent"}).encode())

        def do_GET(self):
            self._send(json.dumps({"envelopeId": "env-123", "status": seen.get("status", "sent")}).encode())

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    body = {"provider": "docusign", "signers": [{"name": "Helena Cruz", "email": "helena@arcadia.test", "role": "customer"}, {"name": "Sam Lee", "email": "sam@signco.test", "role": "supplier"}]}
    try:
        assert client.post(f"/api/documents/{draft}/signatures", json=body).status_code == 501                                    # not configured
        monkeypatch.setenv("DOCUSIGN_BASE_URI", f"http://127.0.0.1:{srv.server_port}")
        monkeypatch.setenv("DOCUSIGN_ACCOUNT_ID", "acct-1")
        monkeypatch.setenv("DOCUSIGN_ACCESS_TOKEN", "tok-abc")
        r = client.post(f"/api/documents/{draft}/signatures", json=body).json()
        assert r["external_id"] == "env-123" and r["links"] == [] and seen["auth"] == "Bearer tok-abc"
        assert [x["routingOrder"] for x in seen["body"]["recipients"]["signers"]] == ["1", "2"] and seen["body"]["documents"][0]["fileExtension"] == "docx"
        assert client.post(f"/api/signatures/{r['id']}/sync").json() == {"docusign_status": "sent", "request": "pending"}
        seen["status"] = "completed"
        assert client.post(f"/api/signatures/{r['id']}/sync").json()["request"] == "completed"
        assert "Signed electronically" in client.get(f"/api/documents/{draft}/content").json()["md"]
    finally:
        srv.shutdown()
