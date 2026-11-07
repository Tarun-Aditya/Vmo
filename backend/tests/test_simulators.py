"""The built-in ERP and e-signature simulators, used end to end through the REAL connector and DocuSign client code over HTTP."""
import re
import socket
import threading
import time

import httpx
import pytest
import uvicorn
from sqlalchemy import text

from app import pipeline
from app.db import SessionLocal
from app.main import app


@pytest.fixture(scope="module")
def live():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=srv.run, daemon=True).start()
    for _ in range(100):
        try:
            if httpx.get(f"http://127.0.0.1:{port}/health", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True


def test_simulated_erp_feeds_the_real_connectors_and_creates_findings(client, seeded, live, monkeypatch):
    monkeypatch.setenv("PUBLIC_API_URL", live)
    assert httpx.post(f"{live}/sim/coupa/oauth2/token", data={"grant_type": "client_credentials", "client_id": "x", "client_secret": "y"}).status_code == 401          # real auth rules apply
    assert httpx.get(f"{live}/sim/sap/sap/opu/odata/sap/API_SUPPLIERINVOICE_PROCESS_SRV/A_SupplierInvoice").status_code == 401
    r = client.post("/api/connectors/demo-erp").json()
    try:
        assert [c["status"] for c in r["connectors"]] == ["ok", "ok"] and all(c["new"] >= 1 for c in r["connectors"])
        with SessionLocal() as s:
            n_coupa = s.execute(text("SELECT count(*) FROM invoices WHERE external_id LIKE 'coupa:%'")).scalar()
            n_sap = s.execute(text("SELECT count(*) FROM invoices WHERE external_id LIKE 'sap:%'")).scalar()
            matched = s.execute(text("SELECT count(*) FROM invoices WHERE external_id LIKE 'coupa:%' AND contract_id IS NOT NULL")).scalar()
            kinds = {r_[0] for r_ in s.execute(text("SELECT kind FROM v_spend_exceptions WHERE invoice_no LIKE '%-S0%' OR invoice_no LIKE '%-CR' OR invoice_no LIKE '%-MOB' OR vendor IN (SELECT vendor FROM invoices WHERE external_id LIKE 'sap:%')"))}
        assert n_coupa >= 3 and n_sap >= 1 and matched >= n_coupa - 2                                  # amounts come from the loaded contracts; all but the no-contract vendor match
        assert {"duplicate", "above_run_rate"} & kinds                                           # the planted resend / over-run is found by the spend checks
        assert client.post("/api/connectors/demo-erp").json()["connectors"][0]["new"] == 0       # idempotent
    finally:
        with SessionLocal() as s:
            s.execute(text("DELETE FROM connectors WHERE name LIKE '%(simulated)'"))
            s.execute(text("DELETE FROM invoices WHERE external_id LIKE 'coupa:%' OR external_id LIKE 'sap:%'"))
            s.commit()
        import shutil

        from app import feeds

        for n in ("coupa-simulated", "sap-s-4hana-simulated"):
            shutil.rmtree(feeds.feeds_dir() / n, ignore_errors=True)
        feeds.recompute()


NDA = """# Mutual Non-Disclosure Agreement – Simco Labs

**Parties:** Arcadia Retail Inc. (the "Customer") and Simco Labs Inc (the "Supplier")
**Effective Date:** 1 December 2026

## Term
This Agreement commences on 1 December 2026 and continues for three (3) years.

## Governing Law
This Agreement is governed by the laws of New York.
"""


def test_simulated_docusign_send_sign_webhook_and_execute(client, seeded, live, monkeypatch):
    monkeypatch.setenv("PUBLIC_API_URL", live)
    cid = client.post("/api/redline/upload", json={"filename": "simco_nda.md", "content": NDA, "owner": "Legal", "category": "Legal"}).json()["contract_id"]
    try:
        r = client.post(f"/api/documents/{cid}/signatures", json={"provider": "docusign", "signers": [{"name": "Helena Cruz", "email": "helena@arcadia.test", "role": "customer"}, {"name": "Sam Lee", "email": "sam@simco.test", "role": "supplier"}]})
        assert r.status_code == 200, r.text
        r = r.json()
        assert r["external_id"] and len(r["links"]) == 2 and all(x["external"] for x in r["links"])
        l1, l2 = (x["path"] for x in r["links"])
        page = httpx.get(l1).text
        assert "Simulated e-signature service" in page and "Helena Cruz" in page and "Type your full name" in page
        assert "Waiting for an earlier signer" in httpx.get(l2).text
        assert httpx.post(l2, data={"name": "Sam Lee", "agree": "1"}).status_code == 409                                    # out of order
        assert "You signed" in httpx.post(l1, data={"name": "Helena Cruz", "agree": "1"}).text
        assert client.post(f"/api/signatures/{r['id']}/sync").json() == {"docusign_status": "sent", "request": "pending"}
        assert "You signed" in httpx.post(l2, data={"name": "Sam Lee", "agree": "1"}).text                                  # last signer: the simulator calls our webhook
        deadline = time.time() + 15
        while time.time() < deadline and client.get(f"/api/documents/{cid}/signatures").json()[0]["status"] != "completed":
            time.sleep(0.3)
        assert client.get(f"/api/documents/{cid}/signatures").json()[0]["status"] == "completed"
        assert "Signed electronically" in client.get(f"/api/documents/{cid}/content").json()["md"]
        assert httpx.post(f"{live}/api/signatures/webhook/docusign", content=b'{"data":{"envelopeId":"x"}}', headers={"x-docusign-signature-1": "bad"}).status_code == 401
        ex = client.post(f"/api/documents/{cid}/execute").json()
        assert client.get(f"/api/contracts/{ex['executed_contract_id']}").json()["contract"]["fully_executed"] is True
    finally:
        with SessionLocal() as s:
            root = pipeline.inbox_path(s)
            s.execute(text("DELETE FROM signature_requests WHERE title ILIKE '%Simco%'"))
            s.execute(text("DELETE FROM contracts WHERE vendor ILIKE '%Simco%'"))
            s.execute(text("DELETE FROM sim_envelopes"))
            s.commit()
        for f in list(root.rglob("simco_nda*")):
            f.unlink()
