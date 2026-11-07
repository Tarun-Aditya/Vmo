"""Auth API: login / bootstrap / me, user management, API tokens, audit log. Enforcement lives in the middleware (app.main)."""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text

from app import auth
from app.db import SessionLocal

router = APIRouter(prefix="/api")
ROLES = ("viewer", "reviewer", "admin")


def rows(sql: str, **p) -> list[dict]:
    with SessionLocal() as s:
        return [dict(r) for r in s.execute(text(sql), p).mappings().all()]


def me(request: Request) -> dict:
    return getattr(request.state, "user", None) or {"email": "demo@local", "name": "Demo (auth off)", "role": "admin", "source": "open"}


@router.get("/auth/config")
def config():
    n = rows("SELECT count(*) AS n FROM users")[0]["n"]
    return {"auth_required": auth.mode() == "on", "min_password": MIN_PASSWORD, "needs_bootstrap": auth.mode() == "on" and n == 0, "oidc": bool(auth.oidc_config()), "roles": ROLES}


@router.get("/auth/me")
def whoami(request: Request):
    return {**me(request), "auth_required": auth.mode() == "on"}


class LoginIn(BaseModel):
    email: str
    password: str
    code: str | None = None


MAX_FAILED, LOCK_MINUTES, MIN_PASSWORD = 5, 15, 10


def password_problem(pw: str, email: str = "") -> str | None:
    """The password policy: at least 10 characters, not the e-mail's name, not a single repeated character."""
    if len(pw or "") < MIN_PASSWORD:
        return f"password must be at least {MIN_PASSWORD} characters"
    if email and email.split("@")[0].lower() in pw.lower() and len(email.split("@")[0]) >= 4:
        return "password must not contain your e-mail name"
    if len(set(pw)) < 4:
        return "password is too simple"
    return None


def _login(email: str, pw: str, ip: str | None, code: str | None = None) -> dict:
    from datetime import datetime, timezone

    from app import mfa

    u = rows("SELECT * FROM users WHERE email = :e AND source = 'local'", e=email.strip().lower())
    if u and u[0]["locked_until"] and u[0]["locked_until"] > datetime.now(timezone.utc):
        auth.audit({"email": email}, "POST", "/api/auth/login", 423, ip, "login_locked")
        raise HTTPException(423, f"Too many failed attempts: try again in {LOCK_MINUTES} minutes")
    if not u or not u[0]["active"] or not auth.check_password(pw, u[0]["password_hash"]):
        if u:
            with SessionLocal() as s:
                s.execute(text("UPDATE users SET failed_logins = failed_logins + 1, locked_until = CASE WHEN failed_logins + 1 >= :m THEN now() + make_interval(mins => :l) ELSE locked_until END WHERE id = :i"),
                          {"m": MAX_FAILED, "l": LOCK_MINUTES, "i": u[0]["id"]})
                s.commit()
        auth.audit({"email": email}, "POST", "/api/auth/login", 401, ip, "login_failed")
        raise HTTPException(401, "Wrong e-mail or password")
    if u[0]["mfa_enabled"]:
        secret = auth.crypto.decrypt(u[0]["mfa_secret_enc"]).get("s", "")
        ok = bool(code) and mfa.verify(secret, code)
        if not ok and code:                                           # a recovery code works once
            h = mfa.hash_code(code)
            if h in (u[0]["recovery_hashes"] or []):
                with SessionLocal() as s:
                    s.execute(text("UPDATE users SET recovery_hashes = array_remove(recovery_hashes, :h) WHERE id = :i"), {"h": h, "i": u[0]["id"]})
                    s.commit()
                ok = True
        if not ok:
            auth.audit({"email": email}, "POST", "/api/auth/login", 401, ip, "mfa_failed" if code else "mfa_required")
            raise HTTPException(401, "Enter the 6-digit code from your authenticator app" if not code else "That code is not valid")
    with SessionLocal() as s:
        s.execute(text("UPDATE users SET last_login_at = now(), failed_logins = 0, locked_until = NULL WHERE id = :i"), {"i": u[0]["id"]})
        s.commit()
    auth.audit(u[0], "POST", "/api/auth/login", 200, ip, "login")
    return {"token": auth.make_session(u[0]["email"], u[0]["role"]), "user": {"email": u[0]["email"], "name": u[0]["name"], "role": u[0]["role"]}}


@router.post("/auth/login")
def login(b: LoginIn, request: Request):
    return _login(b.email, b.password, request.client.host if request.client else None, b.code)


class UserIn(BaseModel):
    email: str
    name: str | None = None
    password: str | None = None
    role: str = "viewer"
    active: bool = True


def _check(u: UserIn, creating: bool) -> None:
    if u.role not in ROLES or "@" not in u.email:
        raise HTTPException(422, "a valid e-mail and a role of viewer, reviewer or admin are required")
    if creating and not u.password:
        raise HTTPException(422, "a password is required")
    if u.password and (msg := password_problem(u.password, u.email)):
        raise HTTPException(422, msg)


@router.post("/auth/bootstrap")
def bootstrap(b: UserIn, request: Request):
    """Create the first administrator; only possible while there are no users."""
    if rows("SELECT 1 FROM users LIMIT 1"):
        raise HTTPException(403, "already set up")
    b.role = "admin"
    _check(b, True)
    with SessionLocal() as s:
        s.execute(text("INSERT INTO users (email, name, role, password_hash) VALUES (:e,:n,'admin',:p)"), {"e": b.email.strip().lower(), "n": b.name, "p": auth.hash_password(b.password or "")})
        s.commit()
    return _login(b.email, b.password or "", request.client.host if request.client else None)


@router.get("/users")
def users():
    return rows("""SELECT u.id, u.email, u.name, u.role, u.source, u.active, u.created_at, u.last_login_at,
                          (SELECT count(*) FROM api_tokens t WHERE t.user_id = u.id AND NOT t.revoked) AS tokens FROM users u ORDER BY u.id""")


@router.post("/users")
def create_user(b: UserIn):
    _check(b, True)
    try:
        with SessionLocal() as s:
            s.execute(text("INSERT INTO users (email, name, role, password_hash, active) VALUES (:e,:n,:r,:p,:a)"),
                      {"e": b.email.strip().lower(), "n": b.name, "r": b.role, "p": auth.hash_password(b.password or ""), "a": b.active})
            s.commit()
    except Exception:
        raise HTTPException(409, "a user with that e-mail exists")
    return next(x for x in users() if x["email"] == b.email.strip().lower())


def _admins_left(excluding: int) -> int:
    return rows("SELECT count(*) AS n FROM users WHERE role='admin' AND active AND id <> :i", i=excluding)[0]["n"]


@router.put("/users/{uid}")
def update_user(uid: int, b: UserIn, request: Request):
    _check(b, False)
    cur = rows("SELECT * FROM users WHERE id = :i", i=uid)
    if not cur:
        raise HTTPException(404, "user not found")
    if (b.role != "admin" or not b.active) and cur[0]["role"] == "admin" and _admins_left(uid) == 0:
        raise HTTPException(409, "the last active administrator cannot be demoted or disabled")
    with SessionLocal() as s:
        s.execute(text("UPDATE users SET name=:n, role=:r, active=:a, password_hash=COALESCE(:p, password_hash) WHERE id=:i"),
                  {"n": b.name, "r": b.role, "a": b.active, "p": auth.hash_password(b.password) if b.password else None, "i": uid})
        s.commit()
    return next(x for x in users() if x["id"] == uid)


@router.delete("/users/{uid}")
def delete_user(uid: int):
    cur = rows("SELECT role FROM users WHERE id = :i", i=uid)
    if cur and cur[0]["role"] == "admin" and _admins_left(uid) == 0:
        raise HTTPException(409, "the last administrator cannot be deleted")
    with SessionLocal() as s:
        s.execute(text("DELETE FROM users WHERE id = :i"), {"i": uid})
        s.commit()
    return {"ok": True}


class TokenIn(BaseModel):
    name: str
    role: str = "viewer"


@router.get("/users/{uid}/tokens")
def tokens(uid: int):
    return rows("SELECT id, name, prefix, role, created_at, last_used_at, revoked FROM api_tokens WHERE user_id = :i ORDER BY id DESC", i=uid)


@router.post("/users/{uid}/tokens")
def create_token(uid: int, b: TokenIn):
    if b.role not in ROLES or not b.name.strip() or not rows("SELECT 1 FROM users WHERE id = :i", i=uid):
        raise HTTPException(422, "name, role and an existing user are required")
    raw, h, prefix = auth.new_api_token()
    with SessionLocal() as s:
        tid = s.execute(text("INSERT INTO api_tokens (user_id, name, token_hash, prefix, role) VALUES (:u,:n,:h,:p,:r) RETURNING id"), {"u": uid, "n": b.name.strip(), "h": h, "p": prefix, "r": b.role}).scalar()
        s.commit()
    return {"id": tid, "token": raw, "note": "Shown once: copy it now."}


@router.delete("/users/{uid}/tokens/{tid}")
def revoke_token(uid: int, tid: int):
    with SessionLocal() as s:
        s.execute(text("UPDATE api_tokens SET revoked = true WHERE id = :t AND user_id = :u"), {"t": tid, "u": uid})
        s.commit()
    return {"ok": True}


@router.get("/audit")
def audit_log(limit: int = 200, user: str | None = None, event: str | None = None):
    w, p = [], {"l": min(limit, 1000)}
    if user:
        w.append("user_email ILIKE :u")
        p["u"] = f"%{user}%"
    if event:
        w.append("event = :e")
        p["e"] = event
    return rows(f"SELECT id, ts, user_email, role, method, path, status, ip, event, detail FROM audit_log {'WHERE ' + ' AND '.join(w) if w else ''} ORDER BY id DESC LIMIT :l", **p)


# ------------------------------------------------------------------ MFA (each person manages their own)
class CodeIn(BaseModel):
    code: str


@router.post("/auth/mfa/setup")
def mfa_setup(request: Request):
    from app import mfa

    u = me(request)
    if u.get("source") == "open":
        raise HTTPException(409, "sign-in is switched off")
    secret = mfa.new_secret()
    with SessionLocal() as s:
        s.execute(text("UPDATE users SET mfa_secret_enc = :s, mfa_enabled = false WHERE email = :e"), {"s": auth.crypto.encrypt({"s": secret}), "e": u["email"]})
        s.commit()
    return {"secret": secret, "otpauth_uri": mfa.uri(secret, u["email"]), "note": "Add it to an authenticator app, then confirm with a code to switch MFA on."}


@router.post("/auth/mfa/enable")
def mfa_enable(b: CodeIn, request: Request):
    from app import mfa

    u = me(request)
    r = rows("SELECT mfa_secret_enc FROM users WHERE email = :e", e=u["email"])
    if not r or not r[0]["mfa_secret_enc"] or not mfa.verify(auth.crypto.decrypt(r[0]["mfa_secret_enc"]).get("s", ""), b.code):
        raise HTTPException(422, "that code is not valid: check the app's clock and try the current code")
    codes = mfa.new_recovery_codes()
    with SessionLocal() as s:
        s.execute(text("UPDATE users SET mfa_enabled = true, recovery_hashes = :h WHERE email = :e"), {"h": [mfa.hash_code(c) for c in codes], "e": u["email"]})
        s.commit()
    auth.audit(u, "POST", "/api/auth/mfa/enable", 200, None, "mfa_enabled")
    return {"enabled": True, "recovery_codes": codes, "note": "Store these recovery codes now: each works once and they are not shown again."}


@router.post("/auth/mfa/disable")
def mfa_disable(b: CodeIn, request: Request):
    from app import mfa

    u = me(request)
    r = rows("SELECT mfa_secret_enc, mfa_enabled FROM users WHERE email = :e", e=u["email"])
    if not r or not r[0]["mfa_enabled"] or not mfa.verify(auth.crypto.decrypt(r[0]["mfa_secret_enc"]).get("s", ""), b.code):
        raise HTTPException(422, "a current code is needed to switch MFA off")
    with SessionLocal() as s:
        s.execute(text("UPDATE users SET mfa_enabled = false, mfa_secret_enc = NULL, recovery_hashes = '{}' WHERE email = :e"), {"e": u["email"]})
        s.commit()
    auth.audit(u, "POST", "/api/auth/mfa/disable", 200, None, "mfa_disabled")
    return {"enabled": False}


@router.post("/users/{uid}/unlock")
def unlock(uid: int):
    """Administrator: clear a lockout and, if a person lost their device, switch their MFA off so they can enrol again."""
    with SessionLocal() as s:
        s.execute(text("UPDATE users SET failed_logins = 0, locked_until = NULL, mfa_enabled = false, mfa_secret_enc = NULL, recovery_hashes = '{}' WHERE id = :i"), {"i": uid})
        s.commit()
    return {"ok": True}


# ------------------------------------------------------------------ single sign-on (OpenID Connect authorization-code flow)
def _sso_client() -> tuple[str, str]:
    cfg = auth.oidc_config() or {}
    return (os.environ.get("OIDC_CLIENT_ID") or ("contractiq-demo" if cfg.get("simulated") else ""), os.environ.get("OIDC_CLIENT_SECRET") or ("demo-sso-secret" if cfg.get("simulated") else ""))


def _public() -> str:
    return os.environ.get("PUBLIC_API_URL", "http://localhost:8000").rstrip("/")


@router.get("/auth/oidc/login")
def oidc_login():
    """Send the browser to the identity provider (discovered from the issuer)."""
    import secrets as _s
    from urllib.parse import urlencode

    import httpx
    from fastapi.responses import RedirectResponse

    cfg, (cid, _) = auth.oidc_config(), _sso_client()
    if not cfg or not cid:
        raise HTTPException(409, "single sign-on is not configured (OIDC_ISSUER, OIDC_CLIENT_ID, OIDC_CLIENT_SECRET)")
    meta = httpx.get(cfg["issuer"] + "/.well-known/openid-configuration", timeout=10).json()
    q = urlencode({"response_type": "code", "client_id": cid, "redirect_uri": f"{_public()}/api/auth/oidc/callback", "scope": "openid email profile", "state": _s.token_urlsafe(8), "nonce": _s.token_urlsafe(8)})
    return RedirectResponse(f"{meta['authorization_endpoint']}?{q}", status_code=302)


@router.get("/auth/oidc/callback")
def oidc_callback(code: str = "", state: str = ""):
    import httpx
    from fastapi.responses import RedirectResponse

    cfg, (cid, secret) = auth.oidc_config(), _sso_client()
    if not cfg or not code:
        raise HTTPException(400, "missing code")
    meta = httpx.get(cfg["issuer"] + "/.well-known/openid-configuration", timeout=10).json()
    r = httpx.post(meta["token_endpoint"], data={"grant_type": "authorization_code", "code": code, "client_id": cid, "client_secret": secret, "redirect_uri": f"{_public()}/api/auth/oidc/callback"}, timeout=15)
    if r.status_code != 200:
        raise HTTPException(401, "the identity provider refused the sign-in")
    user = auth.identify(r.json()["id_token"])             # verifies the signature, issuer, audience and expiry; creates / updates the account and its role
    if not user:
        raise HTTPException(401, "the identity token could not be verified, or the account is disabled")
    auth.audit(user, "GET", "/api/auth/oidc/callback", 200, None, "sso_login")
    web = os.environ.get("WEB_URL", "http://localhost:5173").rstrip("/")
    return RedirectResponse(f"{web}/?sso_token={auth.make_session(user['email'], user['role'])}", status_code=302)
