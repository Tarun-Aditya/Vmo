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
        assert [c["status"] for c in r["connectors"]] == ["ok"] * 5 and all(c["new"] >= 1 for c in r["connectors"][:2])
        with SessionLocal() as s:
            n_coupa = s.execute(text("SELECT count(*) FROM invoices WHERE external_id LIKE 'coupa:%'")).scalar()
            n_sap = s.execute(text("SELECT count(*) FROM invoices WHERE external_id LIKE 'sap:%'")).scalar()
            matched = s.execute(text("SELECT count(*) FROM invoices WHERE external_id LIKE 'coupa:%' AND contract_id IS NOT NULL")).scalar()
            kinds = {r_[0] for r_ in s.execute(text("SELECT kind FROM v_spend_exceptions WHERE invoice_no LIKE '%-S0%' OR invoice_no LIKE '%-CR' OR invoice_no LIKE '%-MOB' OR vendor IN (SELECT vendor FROM invoices WHERE external_id LIKE 'sap:%')"))}
        assert n_coupa >= 3 and n_sap >= 1 and matched >= n_coupa - 2                                  # amounts come from the loaded contracts; all but the no-contract vendor match
        assert {"duplicate", "above_run_rate"} & kinds                                           # the planted resend / over-run is found by the spend checks
        second = client.post("/api/connectors/demo-erp").json()["connectors"]
        assert all(c["new"] == 0 for c in second[2:])                                            # documents already pulled are not pulled again
        # (the ERP now also bills the contracts that were just pulled, so a second invoice sync can legitimately bring new invoices)
    finally:
        with SessionLocal() as s:
            s.execute(text("DELETE FROM connectors WHERE name LIKE '%(simulated)'"))
            s.execute(text("DELETE FROM contracts WHERE origin LIKE 'connector:%(simulated)'"))
            s.execute(text("DELETE FROM invoices WHERE external_id LIKE 'coupa:%' OR external_id LIKE 'sap:%'"))
            root = pipeline.inbox_path(s)
            s.commit()
        import shutil

        from app import feeds

        for n in ("coupa-contracts-simulated", "sap-contracts-simulated", "ariba-contracts-simulated"):
            shutil.rmtree(root / "contracts" / n, ignore_errors=True)
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


def test_contract_pulls_from_all_three_systems_match_the_erp_records(client, seeded, live, monkeypatch):
    """Coupa, SAP and Ariba each hold contract documents; the real connectors pull them; the pipeline reads each document; what it reads must equal what the ERP record says."""
    import shutil
    from datetime import date

    from app.simulators import erp_contracts

    monkeypatch.setenv("PUBLIC_API_URL", live)
    r = client.post("/api/connectors/demo-erp").json()
    try:
        by = {c["name"]: c for c in r["connectors"]}
        assert all(by[n]["status"] == "ok" and by[n]["new"] >= 2 for n in ("Coupa contracts (simulated)", "SAP contracts (simulated)", "Ariba contracts (simulated)")), by
        want = {(c["vendor"], c["kind"]): c for c in erp_contracts.erp_contracts()}
        with SessionLocal() as s:
            got = {(row["vendor"], row["type"]): dict(row) for row in s.execute(text("SELECT vendor, type, effective_date, expiry_date, auto_renew, payment_terms_days, governing_law, source_url, origin FROM contracts WHERE origin LIKE 'connector:%contracts%'")).mappings()}
        assert set(want) <= set(got)                                                                       # every contract the systems hold arrived
        for v, w in want.items():
            g = got[v]
            assert g["effective_date"] == w["start"] and g["expiry_date"] == w["end"], (v, g["effective_date"], w["start"])        # the document says what the ERP record says
            assert bool(g["auto_renew"]) == w["auto_renew"] and g["source_url"].startswith(live) and "/contracts/" in g["source_url"]
        assert got[("Brightwave Logistics Ltd", "SaaS")]["governing_law"] == "New York" and got[("Pinecrest Facilities Services LLC", "MSA")]["governing_law"] == "Texas"
        assert client.post("/api/connectors/demo-erp").json()["connectors"][2]["new"] == 0                 # idempotent
    finally:
        with SessionLocal() as s:
            s.execute(text("DELETE FROM connectors WHERE name LIKE '%(simulated)'"))
            s.execute(text("DELETE FROM contracts WHERE origin LIKE 'connector:%(simulated)'"))
            s.execute(text("DELETE FROM invoices WHERE external_id LIKE 'coupa:%' OR external_id LIKE 'sap:%'"))
            root = pipeline.inbox_path(s)
            s.commit()
        from app import feeds

        for n in ("coupa-contracts-simulated", "sap-contracts-simulated", "ariba-contracts-simulated"):
            shutil.rmtree(root / "contracts" / n, ignore_errors=True)
        for n in ("coupa-simulated", "sap-s-4hana-simulated"):
            shutil.rmtree(feeds.feeds_dir() / n, ignore_errors=True)
        feeds.recompute()


def test_simulated_google_drive_onedrive_and_sharepoint(client, seeded, live, monkeypatch):
    """The demo cloud-storage stand-ins, mounted in the app, feed the real Drive and Microsoft Graph connectors."""
    import shutil

    monkeypatch.setenv("PUBLIC_API_URL", live)
    # the live server was started with the default public address: rebuild its state for this address
    r = httpx.post(f"{live}/api/connectors/demo-cloud", timeout=120)
    assert r.status_code == 200, r.text
    try:
        by = {c["name"]: c for c in r.json()["connectors"]}
        assert by["Google Drive (simulated)"]["status"] == "ok" and by["Google Drive (simulated)"]["new"] == 2
        assert by["OneDrive (simulated)"]["new"] == 1 and by["SharePoint (simulated)"]["new"] == 1
        with SessionLocal() as s:
            rows_ = {x["vendor"]: dict(x) for x in s.execute(text("SELECT vendor, type, status, origin FROM contracts WHERE origin LIKE 'connector:%(simulated)'")).mappings()}
        assert {"Lumenfield Software Inc", "Cobalt Ridge Partners LLC", "Westbay Cleaning Services Ltd", "Ironvale Networks Inc"} <= set(rows_)
        assert rows_["Ironvale Networks Inc"]["status"] == "draft" and rows_["Lumenfield Software Inc"]["status"] != "draft"          # SharePoint feeds the draft review queue
        assert all(c["new"] == 0 for c in httpx.post(f"{live}/api/connectors/demo-cloud", timeout=120).json()["connectors"])
    finally:
        with SessionLocal() as s:
            s.execute(text("DELETE FROM connectors WHERE name LIKE '%(simulated)'"))
            s.execute(text("DELETE FROM contracts WHERE origin LIKE 'connector:%(simulated)'"))
            root = pipeline.inbox_path(s)
            s.commit()
        for d in ("contracts", "drafts"):
            for n in ("google-drive-simulated", "onedrive-simulated", "sharepoint-simulated"):
                shutil.rmtree(root / d / n, ignore_errors=True)


def test_simulated_mailbox_intake_with_the_real_imap_connector(client, seeded, live):
    """A real imaplib session against the simulated mailbox: attachments become contracts, mail is marked read, a second sync finds nothing."""
    import shutil

    r = client.post("/api/connectors/demo-mailbox")
    assert r.status_code == 200, r.text
    try:
        c = r.json()["connectors"][0]
        assert c["status"] == "ok" and c["new"] == 2, c
        with SessionLocal() as s:
            vendors = {x[0] for x in s.execute(text("SELECT vendor FROM contracts WHERE origin LIKE 'connector:Mailbox intake%'"))}
            root = pipeline.inbox_path(s)
        assert {"Foxglove Marketing Ltd", "Redwood Biotech Inc"} <= vendors
        assert client.post("/api/connectors/demo-mailbox").json()["connectors"][0]["new"] == 0
    finally:
        with SessionLocal() as s:
            s.execute(text("DELETE FROM connectors WHERE name LIKE 'Mailbox intake%'"))
            s.execute(text("DELETE FROM contracts WHERE origin LIKE 'connector:Mailbox intake%'"))
            s.commit()
        shutil.rmtree(root / "contracts" / "mailbox-intake-simulated", ignore_errors=True)


def test_alerts_reach_the_simulated_slack_teams_webhook_and_smtp(client, seeded, live, monkeypatch):
    from app import alerts
    from app.simulators import mail as sim_mail

    monkeypatch.setenv("PUBLIC_API_URL", live)
    sim_mail.OUTBOX.clear()
    with SessionLocal() as s:
        s.execute(text("DELETE FROM alert_channels"))
        s.execute(text("DELETE FROM alerts"))
        s.commit()
    try:
        assert len(client.post("/api/admin/alert-channels/demo").json()["created"]) == 4
        res = alerts.evaluate()
        assert res["new"] > 0 and res["delivered"] > 0
        kinds = {m["channel"] for m in sim_mail.OUTBOX}
        assert {"slack", "teams", "ticketing"} <= kinds and "email" in kinds                                              # the SMTP sink is part of the same outbox
        assert any(m["kind"] == "email" and "vmo@arcadia.demo" in m["to"] for m in sim_mail.OUTBOX)
        assert httpx.get(f"{live}/sim/outbox").json()[0]["channel"]
    finally:
        with SessionLocal() as s:
            s.execute(text("DELETE FROM alert_channels"))
            s.execute(text("DELETE FROM alerts"))
            s.commit()
        alerts.evaluate(deliver=False)


def test_single_sign_on_through_the_simulated_identity_provider(client, seeded, live, monkeypatch):
    monkeypatch.setenv("PUBLIC_API_URL", live)
    monkeypatch.setenv("WEB_URL", "http://web.test")
    from app import auth

    auth._jwks.update(keys=None)
    assert client.get("/api/auth/config").json()["oidc"] is True                                                         # demo mode advertises SSO
    c = httpx.Client(follow_redirects=False, timeout=30)
    r = c.get(f"{live}/api/auth/oidc/login")
    assert r.status_code == 302 and "/sim/idp/authorize" in r.headers["location"]
    page = c.get(r.headers["location"]).text
    assert "Simulated identity provider" in page and "Meera Shah" in page
    q = httpx.URL(r.headers["location"]).params
    r2 = c.post(f"{live}/sim/idp/authorize", data={"redirect_uri": q["redirect_uri"], "state": q["state"], "nonce": q["nonce"], "user": "meera@arcadia.demo"})
    assert r2.status_code == 303
    r3 = c.get(r2.headers["location"])
    assert r3.status_code == 302 and r3.headers["location"].startswith("http://web.test/?sso_token=")
    tok = r3.headers["location"].split("sso_token=")[1]
    monkeypatch.setenv("AUTH_MODE", "on")
    try:
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"}).json()
        assert me["email"] == "meera@arcadia.demo" and me["role"] == "reviewer" and me["auth_required"] is True      # the role came from the identity provider's claim
        assert client.get("/api/users", headers={"Authorization": f"Bearer {tok}"}).status_code == 403
        assert c.post(f"{live}/sim/idp/token", data={"grant_type": "authorization_code", "code": "stolen", "client_id": "contractiq-demo", "client_secret": "demo-sso-secret"}).status_code == 400
    finally:
        monkeypatch.delenv("AUTH_MODE")
        with SessionLocal() as s:
            s.execute(text("DELETE FROM users"))
            s.execute(text("DELETE FROM audit_log"))
            s.commit()
