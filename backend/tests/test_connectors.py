"""Connectors against local Google Drive / Microsoft Graph stand-ins: auth flows, recursion, paging, redirects, Google-native export,
unchanged / changed / removed files, secrets handling, the API and the scheduler's due-logic."""
import json
import shutil
import subprocess
import tempfile
from datetime import date
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import text

from app import pipeline
from app.connectors import crypto, service
from app.connectors.base import ConnectorError
from app.db import SessionLocal
from app.docgen import pilot

from . import mock_cloud as mc

NDA = pilot.fill((pilot.CORPUS_DIR / "quill_nda.md").read_text(), pilot.spec_by_key()["quill_nda"], date(2026, 11, 7)).encode()
SOW = pilot.fill((pilot.CORPUS_DIR / "helix_sow1.md").read_text(), pilot.spec_by_key()["helix_sow1"], date(2026, 11, 7)).encode()


def docx_of(md: bytes) -> bytes:
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "a.md").write_bytes(md)
        subprocess.run(["pandoc", str(Path(td) / "a.md"), "-o", str(Path(td) / "a.docx")], check=True)
        return (Path(td) / "a.docx").read_bytes()


@pytest.fixture(scope="module")
def pdf_bytes():
    if not shutil.which("soffice"):
        pytest.skip("libreoffice not installed")
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "a.docx").write_bytes(docx_of(SOW))
        subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", td, str(Path(td) / "a.docx")], check=True, capture_output=True, timeout=180)
        return (Path(td) / "a.pdf").read_bytes()


@pytest.fixture
def keys():
    k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    pub = k.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return priv, pub


@pytest.fixture
def cleanup(seeded):
    yield
    with SessionLocal() as s:
        s.execute(text("DELETE FROM contracts WHERE origin LIKE 'connector:%'"))
        s.execute(text("DELETE FROM connectors WHERE name LIKE 'pytest-%'"))
        s.commit()


def make(kind, name, config, secrets, target="contracts"):
    from app.routes_connectors import ConnectorIn, create

    return create(ConnectorIn(name=name, type=kind, config=config, secrets=secrets, target=target))["id"]


def contracts_of(name):
    with SessionLocal() as s:
        return [dict(r) for r in s.execute(text("SELECT id, title, vendor, type, status, origin, source_url, source_path FROM contracts WHERE origin = :o ORDER BY id"), {"o": f"connector:{name}"}).mappings()]


def test_secrets_are_encrypted_and_masked(seeded):
    enc = crypto.encrypt({"client_secret": "s3cret"})
    assert "s3cret" not in enc and crypto.decrypt(enc) == {"client_secret": "s3cret"} and crypto.mask({"a": "x", "b": ""}) == {"a": "••••••••", "b": ""}


def test_google_drive_service_account_sync_recursion_export_change_and_removal(tmp_inbox, keys, cleanup, pdf_bytes):
    priv, pub = keys
    st = mc.DriveState(pub, "svc@proj.iam.gserviceaccount.com")
    st.add_file("f-nda", "Quill NDA.md", "root1", NDA, "text/markdown")
    st.add_folder("sub1", "Statements of Work", "root1")
    st.add_file("f-sow", "Helix SOW 1.docx", "sub1", docx_of(SOW))
    st.add_file("f-pdf", "Helix SOW scan.pdf", "sub1", pdf_bytes, "application/pdf")
    st.add_file("f-gdoc", "Draft memo", "sub1", docx_of(NDA), "application/vnd.google-apps.document")
    st.add_file("f-img", "logo.png", "root1", b"\x89PNG", "image/png")
    with mc.serve(lambda base: mc.google_app(st, base)) as base:
        sa = {"client_email": "svc@proj.iam.gserviceaccount.com", "private_key": priv}
        cid = make("gdrive", "pytest-gd", {"folder": "https://drive.google.com/drive/folders/root1?usp=sharing", "api_base": base + "/drive/v3", "token_url": base + "/token"},
                   {"service_account_json": json.dumps(sa)})
        ok = service.instance(service.load(cid)).test()
        assert ok["ok"] and "Contracts" in ok["detail"] and "4 supported" in ok["detail"]
        r = service.sync(cid, "manual")
        assert r["status"] == "ok" and r["new"] == 4 and r["skipped"] == 1 and r["failed"] == 0                 # the .png is skipped, the Google Doc is exported to .docx
        cons = contracts_of("pytest-gd")
        assert len(cons) == 4 and all(c["source_url"].startswith("https://drive.google.com") for c in cons)
        assert {c["type"] for c in cons} >= {"NDA", "SOW"} and "export" in st.calls
        again = service.sync(cid, "manual")
        assert (again["new"], again["updated"], again["unchanged"]) == (0, 0, 4)                                    # nothing changed: nothing downloaded
        st.files["f-nda"]["content"] = NDA.replace(b"Quill Staffing Group Ltd", b"Quill Staffing Group Limited")
        st.files["f-nda"]["md5"] = "changed"
        upd = service.sync(cid, "manual")
        assert upd["updated"] == 1 and upd["unchanged"] == 3
        del st.files["f-img"], st.files["f-sow"]
        gone = service.sync(cid, "manual")
        assert gone["removed"] == 1 and len(contracts_of("pytest-gd")) == 4                                        # the contract is kept
        with SessionLocal() as s:
            assert s.execute(text("SELECT status FROM connector_files WHERE connector_id=:c AND remote_id='f-sow'"), {"c": cid}).scalar() == "removed-upstream"


def test_google_oauth_refresh_token_and_bad_credentials(tmp_inbox, keys, cleanup):
    _, pub = keys
    st = mc.DriveState(pub, "x@y")
    st.add_file("f1", "n.md", "root1", NDA)
    with mc.serve(lambda base: mc.google_app(st, base)) as base:
        good = make("gdrive", "pytest-gd-oauth", {"folder": "root1", "api_base": base + "/drive/v3", "token_url": base + "/token"}, {"client_id": "cid", "client_secret": "good-secret", "refresh_token": "good-refresh"})
        assert service.instance(service.load(good)).test()["ok"]
        bad = make("gdrive", "pytest-gd-bad", {"folder": "root1", "api_base": base + "/drive/v3", "token_url": base + "/token"}, {"client_id": "cid", "client_secret": "wrong", "refresh_token": "good-refresh"})
        with pytest.raises(ConnectorError, match="Google sign-in"):
            service.instance(service.load(bad)).test()
        r = service.sync(bad)
        assert r["status"] == "error" and "sign-in" in r["message"]


def graph_state():
    st = mc.GraphState("tenant-1", "app-secret")
    st.drive("d-od", "OneDrive")
    st.users["jordan@arcadia.test"] = "d-od"
    st.folder("d-od", "fo-con", "Contracts")
    st.folder("d-od", "fo-ven", "Vendors", "fo-con")
    st.file("d-od", "i1", "Quill NDA.md", "fo-con", NDA)
    st.file("d-od", "i2", "Helix SOW 1.docx", "fo-ven", docx_of(SOW))
    st.file("d-od", "i3", "notes.xlsx", "fo-ven", b"PK")
    st.file("d-od", "i4", "Second NDA.md", "fo-ven", NDA.replace(b"Quill Staffing Group Ltd", b"Orbit Staffing Ltd"))
    st.drive("d-sp", "Documents")
    st.drive("d-sp2", "Archive")
    st.sites["contoso.sharepoint.com:/sites/Legal"] = {"id": "site-1", "drives": ["d-sp2", "d-sp"]}
    st.folder("d-sp", "sp-f", "Vendor Agreements")
    st.file("d-sp", "s1", "Helix SOW 1.docx", "sp-f", docx_of(SOW))
    st.file("d-sp", "s2", "Quill NDA.md", "sp-f", NDA)
    return st


def test_onedrive_client_credentials_paging_redirect_and_sync(tmp_inbox, cleanup):
    st = graph_state()
    with mc.serve(lambda base: mc.graph_app(st, base)) as base:
        cfg = {"tenant_id": "tenant-1", "user": "jordan@arcadia.test", "folder": "Contracts", "api_base": base + "/v1.0", "login_base": base}
        cid = make("onedrive", "pytest-od", cfg, {"client_id": "app-id", "client_secret": "app-secret"})
        t = service.instance(service.load(cid)).test()
        assert t["ok"] and "3 supported" in t["detail"]
        r = service.sync(cid)
        assert r["new"] == 3 and r["skipped"] == 1 and r["failed"] == 0 and st.calls.count("download") == 3        # paging (2 per page) + redirect download without the bearer token
        cons = contracts_of("pytest-od")
        assert len(cons) == 3 and all("sharepoint.com" in c["source_url"] for c in cons)
        assert {c["vendor"] for c in cons} >= {"Helix Digital Consulting Inc", "Quill Staffing Group Ltd"}
        wrong = make("onedrive", "pytest-od-bad", cfg, {"client_id": "app-id", "client_secret": "nope"})
        with pytest.raises(ConnectorError, match="Microsoft sign-in.*Invalid client secret"):
            service.instance(service.load(wrong)).test()
        missing = make("onedrive", "pytest-od-nofolder", {**cfg, "folder": "Nope"}, {"client_id": "app-id", "client_secret": "app-secret"})
        assert service.sync(missing)["status"] == "error"


def test_sharepoint_site_library_drafts_target_and_api(tmp_inbox, client, cleanup):
    st = graph_state()
    with mc.serve(lambda base: mc.graph_app(st, base)) as base:
        body = {"name": "pytest-sp", "type": "sharepoint", "target": "drafts", "trigger_mode": "manual", "interval_minutes": 30,
                "config": {"tenant_id": "tenant-1", "site_url": "https://contoso.sharepoint.com/sites/Legal", "library": "Documents", "folder": "Vendor Agreements", "api_base": base + "/v1.0", "login_base": base, "evil": "x"},
                "secrets": {"client_id": "app-id", "client_secret": "app-secret"}}
        made = client.post("/api/connectors", json=body).json()
        assert made["type_label"] == "SharePoint" and "secrets_enc" not in made and made["secrets_set"]["client_secret"] and "evil" not in made["config"]
        cid = made["id"]
        listed = client.get("/api/connectors").json()["connectors"]
        assert any(c["id"] == cid for c in listed) and "app-secret" not in json.dumps(listed)
        # blank secret on update keeps the stored one
        up = client.put(f"/api/connectors/{cid}", json={**body, "secrets": {"client_secret": ""}, "interval_minutes": 15}).json()
        assert up["interval_minutes"] == 15 and up["secrets_set"]["client_secret"]
        assert client.post(f"/api/connectors/{cid}/test").json()["ok"] is True
        lib = client.put(f"/api/connectors/{cid}", json={**body, "config": {**body["config"], "library": "Nope"}}).json()
        t = client.post(f"/api/connectors/{cid}/test").json()
        assert t["ok"] is False and "Nope" in t["detail"] and "Documents" in t["detail"]
        client.put(f"/api/connectors/{cid}", json=body)
        r = client.post(f"/api/connectors/{cid}/sync?wait=true").json()
        assert r["status"] == "ok" and r["new"] == 2, r
        cons = contracts_of("pytest-sp")
        assert len(cons) == 2 and all(c["status"] == "draft" and c["source_path"].startswith("drafts/") for c in cons)   # drafts target -> draft status
        files = client.get(f"/api/connectors/{cid}/files").json()
        assert len(files) == 2 and files[0]["web_url"]
        runs = client.get("/api/admin/pipeline/runs").json()
        assert any(x["pipeline"] == "connector:pytest-sp" for x in runs)
        assert client.post("/api/connectors", json={**body, "type": "dropbox"}).status_code == 422
        assert client.post("/api/connectors", json=body).status_code == 409                                      # duplicate name
        assert client.delete(f"/api/connectors/{cid}").json()["deleted"] == cid
        _ = lib


def test_scheduler_picks_due_periodic_connectors_only(seeded, cleanup):
    a = make("gdrive", "pytest-due-a", {"folder": "x"}, {})
    from app.routes_connectors import ConnectorIn, create

    b = create(ConnectorIn(name="pytest-due-b", type="gdrive", config={"folder": "x"}, trigger_mode="manual"))["id"]
    c = make("gdrive", "pytest-due-c", {"folder": "x"}, {})
    with SessionLocal() as s:
        s.execute(text("UPDATE connectors SET next_sync_at = now() + interval '1 hour' WHERE id=:i"), {"i": c})
        s.commit()
    due = service.due()
    assert a in due and b not in due and c not in due


_ = pipeline
