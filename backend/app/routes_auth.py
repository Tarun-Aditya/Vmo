"""Auth API: login / bootstrap / me, user management, API tokens, audit log. Enforcement lives in the middleware (app.main)."""
from __future__ import annotations

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
    return {"auth_required": auth.mode() == "on", "needs_bootstrap": auth.mode() == "on" and n == 0, "oidc": bool(auth.oidc_config()), "roles": ROLES}


@router.get("/auth/me")
def whoami(request: Request):
    return {**me(request), "auth_required": auth.mode() == "on"}


class LoginIn(BaseModel):
    email: str
    password: str


def _login(email: str, pw: str, ip: str | None) -> dict:
    u = rows("SELECT * FROM users WHERE email = :e AND source = 'local'", e=email.strip().lower())
    if not u or not u[0]["active"] or not auth.check_password(pw, u[0]["password_hash"]):
        auth.audit({"email": email}, "POST", "/api/auth/login", 401, ip, "login_failed")
        raise HTTPException(401, "Wrong e-mail or password")
    with SessionLocal() as s:
        s.execute(text("UPDATE users SET last_login_at = now() WHERE id = :i"), {"i": u[0]["id"]})
        s.commit()
    auth.audit(u[0], "POST", "/api/auth/login", 200, ip, "login")
    return {"token": auth.make_session(u[0]["email"], u[0]["role"]), "user": {"email": u[0]["email"], "name": u[0]["name"], "role": u[0]["role"]}}


@router.post("/auth/login")
def login(b: LoginIn, request: Request):
    return _login(b.email, b.password, request.client.host if request.client else None)


class UserIn(BaseModel):
    email: str
    name: str | None = None
    password: str | None = None
    role: str = "viewer"
    active: bool = True


def _check(u: UserIn, creating: bool) -> None:
    if u.role not in ROLES or "@" not in u.email:
        raise HTTPException(422, "a valid e-mail and a role of viewer, reviewer or admin are required")
    if (creating and not u.password) or (u.password and len(u.password) < 8):
        raise HTTPException(422, "password of at least 8 characters required")


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
