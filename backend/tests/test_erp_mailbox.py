"""Procurement / ERP connectors (Coupa, SAP OData) against local stand-ins, and mailbox intake against a fake IMAP server."""
import email.message
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from sqlalchemy import text

from app import pipeline
from app.db import SessionLocal


@pytest.fixture()
def con(client, seeded):
    made, names = [], []

    def make(body):
        r = client.post("/api/connectors", json=body)
        assert r.status_code == 200, r.text
        made.append(r.json()["id"])
        names.append(body["name"])
        return r.json()

    yield make
    import shutil

    from app import feeds
    from app.connectors.service import slug

    for i in made:
        client.delete(f"/api/connectors/{i}")
    for n in names:                                                         # files a connector wrote are not part of the shared test data
        shutil.rmtree(feeds.feeds_dir() / slug(n), ignore_errors=True)
    with SessionLocal() as s:
        s.execute(text("DELETE FROM invoices WHERE external_id LIKE 'coupa:%' OR external_id LIKE 'sap:%'"))
        s.commit()


def server(handler):
    srv = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def a_contract():
    with SessionLocal() as s:
        return dict(s.execute(text("SELECT id, title, vendor FROM contracts WHERE status<>'draft' AND type='SaaS' LIMIT 1")).mappings().one())


def test_coupa_oauth_paging_and_matching(client, con):
    c = a_contract()
    calls = []
    inv = [{"id": i, "invoice-number": f"CP-{i}", "invoice-date": "2026-10-01", "payment-due-date": "2026-11-15", "total-with-taxes": f"{1000 * i:,}.50", "supplier": {"name": c["vendor"]}, "contract": {"name": c["title"]},
            "updated-at": f"2026-10-0{i}T10:00:00Z", "line-items": [{"description": f"Licence {i}"}]} for i in range(1, 4)]

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append(("token", self.rfile.read(int(self.headers["Content-Length"])).decode()))
            body = json.dumps({"access_token": "t0k", "expires_in": 86400}).encode()
            self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)  # noqa: E702

        def do_GET(self):
            calls.append(("get", self.path, self.headers.get("Authorization")))
            off = int(self.path.split("offset=")[-1].split("&")[0]) if "offset=" in self.path else 0
            body = json.dumps(inv[off:off + 2]).encode()
            self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)  # noqa: E702

        def log_message(self, *a):
            pass

    srv = server(H)
    try:
        r = con({"name": "Coupa test", "type": "coupa", "target": "feeds", "config": {"base_url": f"http://127.0.0.1:{srv.server_port}", "page_size": 2}, "secrets": {"client_id": "id1", "client_secret": "sec1"}})
        assert client.post(f"/api/connectors/{r['id']}/test").json()["ok"] is True
        res = client.post(f"/api/connectors/{r['id']}/sync?wait=true").json()
        assert res["status"] == "ok" and res["new"] == 3
        assert "grant_type=client_credentials" in calls[0][1] and "client_id=id1" in calls[0][1] and any(x[0] == "get" and x[2] == "Bearer t0k" for x in calls)
        assert sum(1 for x in calls if x[0] == "get" and "offset=" in x[1]) >= 2                                              # paged
        with SessionLocal() as s:
            rows = s.execute(text("SELECT invoice_no, amount, contract_id, vendor FROM invoices WHERE external_id LIKE 'coupa:%' ORDER BY invoice_no")).mappings().all()
        assert [r_["invoice_no"] for r_ in rows] == ["CP-1", "CP-2", "CP-3"] and [float(r_["amount"]) for r_ in rows] == [1000.5, 2000.5, 3000.5]
        assert all(r_["contract_id"] == c["id"] and r_["vendor"] == c["vendor"] for r_ in rows)                              # matched to the contract
        assert client.post(f"/api/connectors/{r['id']}/sync?wait=true").json()["unchanged"] == 3                              # idempotent
    finally:
        srv.shutdown()


def test_sap_odata_api_key_and_date_format(client, con):
    c = a_contract()
    seen = {}
    ms = 1_790_000_000_000
    body = json.dumps({"d": {"results": [{"SupplierInvoice": "5100000001", "InvoicingParty": c["vendor"], "SupplierInvoiceIDByInvcgParty": "S-77", "DocumentDate": f"/Date({ms})/",
                                           "PaymentDueDate": f"/Date({ms + 30 * 86400000})/", "InvoiceGrossAmount": "12500.00", "DocumentHeaderText": "Quarterly licence", "LastChangeDate": "20261001"}]}}).encode()

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            seen["key"], seen["path"] = self.headers.get("APIKey"), self.path
            self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)  # noqa: E702

        def log_message(self, *a):
            pass

    srv = server(H)
    try:
        r = con({"name": "SAP sandbox", "type": "sap", "target": "feeds", "config": {"base_url": f"http://127.0.0.1:{srv.server_port}"}, "secrets": {"api_key": "sandbox-key"}})
        assert client.post(f"/api/connectors/{r['id']}/sync?wait=true").json()["status"] == "ok"
        assert seen["key"] == "sandbox-key" and "API_SUPPLIERINVOICE_PROCESS_SRV/A_SupplierInvoice" in seen["path"] and "%24format=json" in seen["path"].replace("$", "%24")
        with SessionLocal() as s:
            row = s.execute(text("SELECT invoice_no, invoice_date, due_date, amount FROM invoices WHERE external_id='sap:5100000001'")).mappings().one()
        assert row["invoice_no"] == "S-77" and str(row["invoice_date"]) == "2026-09-21" and (row["due_date"] - row["invoice_date"]).days == 30 and float(row["amount"]) == 12500.0
    finally:
        srv.shutdown()


def test_bad_credentials_are_reported_not_raised(client, con):
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            self.send_response(401); self.send_header("Content-Length", "0"); self.end_headers()  # noqa: E702

        def log_message(self, *a):
            pass

    srv = server(H)
    try:
        r = con({"name": "Coupa bad", "type": "coupa", "target": "feeds", "config": {"base_url": f"http://127.0.0.1:{srv.server_port}"}, "secrets": {"client_id": "x", "client_secret": "y"}})
        res = client.post(f"/api/connectors/{r['id']}/sync?wait=true").json()
        assert res["status"] == "error" and "token request failed (401)" in res["message"]
    finally:
        srv.shutdown()


def test_mailbox_attachments_become_documents(client, con, monkeypatch):
    import imaplib

    nda = "# Mutual Non-Disclosure Agreement – Mailco Labs\n\n**Parties:** Arcadia Retail Inc. (the \"Customer\") and Mailco Labs Inc (the \"Supplier\")\n\n## Term\nThis Agreement commences on 1 December 2026 and continues for three (3) years.\n"
    msg = email.message.EmailMessage()
    msg["From"], msg["Subject"], msg["Message-ID"] = "Vera <vera@mailco.test>", "NDA for signature", "<m1@mailco.test>"
    msg.set_content("Please find attached.")
    msg.add_attachment(nda.encode(), maintype="text", subtype="markdown", filename="mailco_nda.md")
    msg.add_attachment(b"x", maintype="image", subtype="png", filename="logo.png")
    state = {"seen": []}

    class FakeIMAP:
        def __init__(self, host, port):
            assert host == "imap.test"

        def login(self, u, p):
            if p != "pw":
                raise imaplib.IMAP4.error("bad credentials")

        def select(self, folder):
            return "OK", [b"1"]

        def search(self, _c, q):
            return "OK", [b"" if state["seen"] else b"1"]

        def fetch(self, n, spec):
            return "OK", [(b"1 (BODY[] {n}", msg.as_bytes())]

        def store(self, n, op, flag):
            state["seen"].append(n)

        def logout(self):
            pass

    monkeypatch.setattr(imaplib, "IMAP4_SSL", FakeIMAP)
    r = con({"name": "Intake mailbox", "type": "imap", "target": "contracts", "config": {"host": "imap.test", "username": "intake@arcadia.test", "folder": "Contracts"}, "secrets": {"password": "pw"}})
    assert client.post(f"/api/connectors/{r['id']}/test").json()["ok"] is True
    res = client.post(f"/api/connectors/{r['id']}/sync?wait=true").json()
    assert res["status"] == "ok" and res["new"] == 1 and res["skipped"] == 0                                    # the .png never left the mailbox adapter
    assert state["seen"] == ["1"]                                                                              # marked read
    with SessionLocal() as s:
        row = s.execute(text("SELECT title, vendor, origin FROM contracts WHERE vendor ILIKE '%Mailco%'")).mappings().all()
        root = pipeline.inbox_path(s)
    assert len(row) == 1 and row[0]["origin"].startswith("connector:Intake mailbox")
    assert client.post(f"/api/connectors/{r['id']}/sync?wait=true").json()["new"] == 0                           # nothing new
    r2 = con({"name": "Bad mailbox", "type": "imap", "target": "contracts", "config": {"host": "imap.test", "username": "u"}, "secrets": {"password": "wrong"}})
    assert client.post(f"/api/connectors/{r2['id']}/test").json()["ok"] is False
    with SessionLocal() as s:
        s.execute(text("DELETE FROM contracts WHERE vendor ILIKE '%Mailco%'"))
        s.commit()
    import shutil

    shutil.rmtree(root / "contracts" / "intake-mailbox", ignore_errors=True)
