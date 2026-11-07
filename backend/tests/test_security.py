"""Security controls: password policy, lockout, MFA with recovery codes, SCIM provisioning, headers, retention."""
import base64

import pytest
from sqlalchemy import text

from app import mfa, retention
from app.db import SessionLocal


@pytest.fixture()
def secured(client, seeded, monkeypatch):
    def wipe():
        with SessionLocal() as s:
            for q in ("DELETE FROM api_tokens", "DELETE FROM users", "DELETE FROM audit_log"):
                s.execute(text(q))
            s.commit()
    wipe()
    monkeypatch.setenv("AUTH_MODE", "on")
    yield client
    monkeypatch.delenv("AUTH_MODE")
    wipe()


def H(t):
    return {"Authorization": f"Bearer {t}"}


def boot(c, pw="correct-horse-1"):
    return c.post("/api/auth/bootstrap", json={"email": "root@arcadia.test", "password": pw, "name": "Root"}).json()


def test_totp_matches_the_rfc_vectors():
    secret = base64.b32encode(b"12345678901234567890").decode()           # RFC 6238 appendix B, SHA-1
    assert mfa.code(secret, 59, digits=8) == "94287082" and mfa.code(secret, 1111111109, digits=8) == "07081804" and mfa.code(secret, 20000000000, digits=8) == "65353130"
    assert mfa.verify(secret, mfa.code(secret)) and not mfa.verify(secret, "000000" if mfa.code(secret) != "000000" else "111111")


def test_password_policy_and_lockout(secured):
    c = secured
    assert c.post("/api/auth/bootstrap", json={"email": "root@arcadia.test", "password": "short"}).status_code == 422
    assert c.post("/api/auth/bootstrap", json={"email": "root@arcadia.test", "password": "aaaaaaaaaaaa"}).status_code == 422                 # too simple
    assert c.post("/api/auth/bootstrap", json={"email": "robert@arcadia.test", "password": "robert-password"}).status_code == 422           # contains the e-mail name
    b = boot(c)
    assert b["token"]
    for _ in range(5):
        assert c.post("/api/auth/login", json={"email": "root@arcadia.test", "password": "wrong-password-1"}).status_code == 401
    assert c.post("/api/auth/login", json={"email": "root@arcadia.test", "password": "correct-horse-1"}).status_code == 423              # locked, even with the right password
    uid = c.get("/api/users", headers=H(b["token"])).json()[0]["id"]
    assert c.post(f"/api/users/{uid}/unlock", headers=H(b["token"])).status_code == 200
    assert c.post("/api/auth/login", json={"email": "root@arcadia.test", "password": "correct-horse-1"}).status_code == 200
    ev = {x["event"] for x in c.get("/api/audit", headers=H(b["token"])).json()}
    assert {"login_failed", "login_locked", "login"} <= ev


def test_mfa_enrol_login_recovery_and_disable(secured):
    c = secured
    tok = H(boot(c)["token"])
    s = c.post("/api/auth/mfa/setup", headers=tok).json()
    assert s["otpauth_uri"].startswith("otpauth://totp/") and s["secret"] in s["otpauth_uri"]
    assert c.post("/api/auth/mfa/enable", headers=tok, json={"code": "123456"}).status_code == 422
    en = c.post("/api/auth/mfa/enable", headers=tok, json={"code": mfa.code(s["secret"])}).json()
    assert en["enabled"] and len(en["recovery_codes"]) == 8
    login = lambda **kw: c.post("/api/auth/login", json={"email": "root@arcadia.test", "password": "correct-horse-1", **kw})  # noqa: E731
    assert login().status_code == 401 and "6-digit" in login().json()["detail"]                                         # password alone is not enough
    assert login(code="000000").status_code == 401
    ok = login(code=mfa.code(s["secret"]))
    assert ok.status_code == 200
    assert login(code=en["recovery_codes"][0]).status_code == 200 and login(code=en["recovery_codes"][0]).status_code == 401     # a recovery code works once
    t2 = H(ok.json()["token"])
    assert c.post("/api/auth/mfa/disable", headers=t2, json={"code": "000000"}).status_code == 422
    assert c.post("/api/auth/mfa/disable", headers=t2, json={"code": mfa.code(s["secret"])}).json()["enabled"] is False
    assert login().status_code == 200


def test_scim_provisioning_and_last_admin_guard(secured):
    c = secured
    b = boot(c)
    uid = c.get("/api/users", headers=H(b["token"])).json()[0]["id"]
    scim = H(c.post(f"/api/users/{uid}/tokens", headers=H(b["token"]), json={"name": "okta", "role": "admin"}).json()["token"])
    assert c.get("/api/scim/v2/Users").status_code == 401 and c.get("/api/scim/v2/ServiceProviderConfig", headers=scim).json()["patch"]["supported"]
    n = c.post("/api/scim/v2/Users", headers=scim, json={"userName": "dana@arcadia.test", "displayName": "Dana", "externalId": "okta-1", "roles": [{"value": "reviewer"}], "active": True})
    assert n.status_code == 201 and n.json()["roles"] == [{"value": "reviewer"}]
    assert c.post("/api/scim/v2/Users", headers=scim, json={"userName": "dana@arcadia.test"}).status_code == 409
    f = c.get('/api/scim/v2/Users?filter=userName eq "dana@arcadia.test"', headers=scim).json()
    assert f["totalResults"] == 1 and f["Resources"][0]["externalId"] == "okta-1"
    did = n.json()["id"]
    p = c.patch(f"/api/scim/v2/Users/{did}", headers=scim, json={"Operations": [{"op": "replace", "value": {"active": False}}]}).json()
    assert p["active"] is False
    assert c.patch(f"/api/scim/v2/Users/{did}", headers=scim, json={"Operations": [{"op": "replace", "path": "roles", "value": [{"value": "admin"}]}]}).json()["roles"] == [{"value": "admin"}]
    assert c.delete(f"/api/scim/v2/Users/{did}", headers=scim).status_code == 204
    assert c.delete(f"/api/scim/v2/Users/{uid}", headers=scim).status_code == 409                                       # the only remaining active admin
    viewer = H(c.post("/api/auth/login", json={"email": "root@arcadia.test", "password": "correct-horse-1"}).json()["token"])
    assert c.post("/api/users", headers=viewer, json={"email": "v@arcadia.test", "password": "viewer-pass-1", "role": "viewer"}).status_code == 200
    vt = H(c.post("/api/auth/login", json={"email": "v@arcadia.test", "password": "viewer-pass-1"}).json()["token"])
    assert c.get("/api/scim/v2/Users", headers=vt).status_code == 403


def test_security_headers_and_retention(client, seeded, monkeypatch):
    h = client.get("/api/meta").headers
    assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "SAMEORIGIN" and h["cache-control"] == "no-store"
    with SessionLocal() as s:
        s.execute(text("DELETE FROM audit_log"))
        s.execute(text("INSERT INTO audit_log (ts, user_email, event) VALUES (now() - interval '400 days', 'old@x', 'request'), (now(), 'new@x', 'request')"))
        s.commit()
    assert retention.purge() == {"audit": 0, "alerts": 0}                              # off by default: nothing is deleted
    monkeypatch.setenv("AUDIT_RETENTION_DAYS", "365")
    assert retention.purge()["audit"] == 1
    with SessionLocal() as s:
        assert [r[0] for r in s.execute(text("SELECT user_email FROM audit_log"))] == ["new@x"]
        s.execute(text("DELETE FROM audit_log"))
        s.commit()


def test_metrics_request_id_and_addin_files(client, seeded):
    m = client.get("/api/ops/metrics").text
    assert "contractiq_contracts " in m and "contractiq_alerts_open " in m and "# TYPE contractiq_pipeline_last_run_age_seconds gauge" in m
    assert len(client.get("/health").headers["x-request-id"]) >= 8 and client.get("/health", headers={"x-request-id": "abc123"}).headers["x-request-id"] == "abc123"
    assert client.get("/addin/manifest.xml").status_code == 200 and "TaskPaneApp" in client.get("/addin/manifest.xml").text
    assert client.get("/addin/taskpane.js").status_code == 200
