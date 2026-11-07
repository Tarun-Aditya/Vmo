"""Access control: open by default; with AUTH_MODE=on logins, roles, API tokens, OpenID Connect, last-admin protection and the audit log."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import text

from app.db import SessionLocal


@pytest.fixture()
def secured(client, seeded, monkeypatch):
    def wipe():
        with SessionLocal() as s:
            s.execute(text("DELETE FROM api_tokens"))
            s.execute(text("DELETE FROM users"))
            s.execute(text("DELETE FROM audit_log"))
            s.commit()
    wipe()
    monkeypatch.setenv("AUTH_MODE", "on")
    yield client
    monkeypatch.delenv("AUTH_MODE")
    wipe()


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


def setup_users(c):
    boot = c.post("/api/auth/bootstrap", json={"email": "root@arcadia.test", "password": "correct-horse", "name": "Root"}).json()
    adm = H(boot["token"])
    for email, role in (("rev@arcadia.test", "reviewer"), ("view@arcadia.test", "viewer")):
        assert c.post("/api/users", headers=adm, json={"email": email, "password": "password-1", "role": role}).status_code == 200
    login = lambda e: H(c.post("/api/auth/login", json={"email": e, "password": "password-1"}).json()["token"])  # noqa: E731
    return adm, login("rev@arcadia.test"), login("view@arcadia.test")


def test_open_by_default(client, seeded):
    assert client.get("/api/auth/me").json()["role"] == "admin" and client.get("/api/auth/config").json()["auth_required"] is False
    assert client.get("/api/contracts").status_code == 200


def test_everything_needs_a_login_and_first_admin_bootstrap(secured, monkeypatch):
    monkeypatch.setenv("SIMULATORS", "0")                  # in demo mode the built-in identity provider is advertised as SSO
    c = secured
    assert c.get("/health").status_code == 200 and c.get("/api/auth/config").json() == {"auth_required": True, "min_password": 10, "needs_bootstrap": True, "oidc": False, "roles": ["viewer", "reviewer", "admin"]}
    assert c.get("/api/contracts").status_code == 401
    assert c.post("/api/auth/bootstrap", json={"email": "root@arcadia.test", "password": "short"}).status_code == 422
    r = c.post("/api/auth/bootstrap", json={"email": "root@arcadia.test", "password": "correct-horse"})
    assert r.status_code == 200 and r.json()["user"]["role"] == "admin"
    assert c.post("/api/auth/bootstrap", json={"email": "x@y.test", "password": "correct-horse"}).status_code == 403      # only once
    assert c.get("/api/contracts", headers=H(r.json()["token"])).status_code == 200
    assert c.get("/api/contracts", headers=H("garbage.token")).status_code == 401
    assert c.post("/api/auth/login", json={"email": "root@arcadia.test", "password": "wrong"}).status_code == 401


def test_roles(secured):
    c = secured
    adm, rev, view = setup_users(c)
    cid = c.get("/api/contracts?status=draft", headers=adm).json()[0]["id"]
    assert c.get("/api/contracts", headers=view).status_code == 200
    assert c.post("/api/ask", headers=view, json={"question": "How many contracts do we have?"}).status_code != 403          # asking is reading
    assert c.put(f"/api/redline/{cid}/review", headers=view, json={"status": "approved"}).status_code == 403
    assert c.put(f"/api/redline/{cid}/review", headers=rev, json={"status": "in_review", "assignee": "meera"}).status_code == 200
    assert c.get("/api/admin/pipeline", headers=rev).status_code == 403 and c.get("/api/connectors", headers=rev).status_code == 403
    assert c.get("/api/users", headers=rev).status_code == 403 and c.get("/api/audit", headers=view).status_code == 403
    assert c.get("/api/connectors", headers=adm).status_code == 200
    assert c.get("/api/auth/me", headers=rev).json()["role"] == "reviewer"


def test_api_tokens_never_outrank_the_owner_and_can_be_revoked(secured):
    c = secured
    adm, rev, view = setup_users(c)
    uid = next(u["id"] for u in c.get("/api/users", headers=adm).json() if u["email"] == "view@arcadia.test")
    t = c.post(f"/api/users/{uid}/tokens", headers=adm, json={"name": "bi-tool", "role": "admin"}).json()
    assert t["token"].startswith("ciq_")
    assert c.get("/api/contracts", headers=H(t["token"])).status_code == 200
    assert c.get("/api/users", headers=H(t["token"])).status_code == 403                  # the owner is a viewer: the token is capped
    listed = c.get(f"/api/users/{uid}/tokens", headers=adm).json()
    assert listed[0]["prefix"] == t["token"][:10] and listed[0]["last_used_at"] and "token" not in listed[0]
    c.delete(f"/api/users/{uid}/tokens/{t['id']}", headers=adm)
    assert c.get("/api/contracts", headers=H(t["token"])).status_code == 401


def test_last_admin_is_protected_and_disabled_users_are_locked_out(secured):
    c = secured
    adm, rev, view = setup_users(c)
    users = {u["email"]: u for u in c.get("/api/users", headers=adm).json()}
    root = users["root@arcadia.test"]
    assert c.put(f"/api/users/{root['id']}", headers=adm, json={"email": root["email"], "role": "viewer"}).status_code == 409
    assert c.delete(f"/api/users/{root['id']}", headers=adm).status_code == 409
    v = users["view@arcadia.test"]
    assert c.put(f"/api/users/{v['id']}", headers=adm, json={"email": v["email"], "role": "viewer", "active": False}).status_code == 200
    assert c.get("/api/contracts", headers=view).status_code == 401
    assert c.post("/api/auth/login", json={"email": v["email"], "password": "password-1"}).status_code == 401


def test_audit_log_records_changes_denials_and_logins_but_not_reads(secured):
    c = secured
    adm, rev, view = setup_users(c)
    cid = c.get("/api/contracts?status=draft", headers=adm).json()[0]["id"]
    c.put(f"/api/redline/{cid}/review", headers=view, json={"status": "approved"})
    c.put(f"/api/redline/{cid}/review", headers=rev, json={"status": "in_review"})
    c.get("/api/contracts", headers=adm)
    log = c.get("/api/audit?limit=100", headers=adm).json()
    kinds = {(x["event"], x["user_email"], x["status"]) for x in log}
    assert ("denied", "view@arcadia.test", 403) in kinds and ("request", "rev@arcadia.test", 200) in kinds and ("login", "rev@arcadia.test", 200) in kinds
    assert not any(x["method"] == "GET" and x["path"] == "/api/contracts" for x in log)
    assert [x["event"] for x in c.get("/api/audit?event=denied", headers=adm).json()] == ["denied"]


def test_openid_connect_tokens_are_verified_against_the_issuer_keys(secured, monkeypatch):
    from app import auth

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid="k1", alg="RS256", use="sig")

    class H_(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"keys": [jwk]}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H_)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    iss = "https://idp.arcadia.test"
    monkeypatch.setenv("OIDC_ISSUER", iss)
    monkeypatch.setenv("OIDC_AUDIENCE", "contractiq")
    monkeypatch.setenv("OIDC_JWKS_URL", f"http://127.0.0.1:{srv.server_port}/jwks")
    auth._jwks.update(keys=None)
    try:
        c = secured
        c.post("/api/auth/bootstrap", json={"email": "root@arcadia.test", "password": "correct-horse"})
        mk = lambda **kw: jwt.encode({"iss": iss, "aud": "contractiq", "exp": int(time.time()) + 600, "email": "sam@arcadia.test", "name": "Sam", "roles": ["reviewer"], **kw}, key, algorithm="RS256", headers={"kid": "k1"})  # noqa: E731
        ok = c.get("/api/auth/me", headers=H(mk()))
        assert ok.status_code == 200 and ok.json()["email"] == "sam@arcadia.test" and ok.json()["role"] == "reviewer" and ok.json()["source"] == "oidc"
        assert c.get("/api/users", headers=H(mk())).status_code == 403
        assert c.get("/api/auth/me", headers=H(mk(aud="someone-else"))).status_code == 401
        assert c.get("/api/auth/me", headers=H(mk(exp=int(time.time()) - 10))).status_code == 401
        assert c.get("/api/auth/me", headers=H(mk(iss="https://evil.test"))).status_code == 401
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        forged = jwt.encode({"iss": iss, "aud": "contractiq", "exp": int(time.time()) + 600, "email": "sam@arcadia.test", "roles": ["admin"]}, other, algorithm="RS256", headers={"kid": "k1"})
        assert c.get("/api/auth/me", headers=H(forged)).status_code == 401
        assert c.get("/api/auth/config").json()["oidc"] is True
    finally:
        srv.shutdown()
