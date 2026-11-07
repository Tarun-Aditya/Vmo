"""Access control: local accounts (scrypt), signed session tokens, API tokens, optional OpenID Connect (RS256 id/access tokens checked against the issuer's JWKS),
three roles (viewer < reviewer < admin) enforced in one middleware, and an audit log of every change.

AUTH_MODE=off (default, for the demo) leaves everything open as an implicit admin. AUTH_MODE=on requires a login or token on every /api call."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time

import httpx
import jwt
from sqlalchemy import text

from app.connectors import crypto
from app.db import SessionLocal

RANK = {"viewer": 0, "reviewer": 1, "admin": 2}
SESSION_HOURS = 12
PUBLIC = ("/health", "/api/auth/login", "/api/auth/config", "/api/auth/bootstrap", "/api/meta")
READ_LIKE_POSTS = ("/api/ask", "/api/chat")         # POSTs that only read (questions): viewers may ask


def mode() -> str:
    return os.environ.get("AUTH_MODE", "off").lower()


def required(method: str, path: str) -> str | None:
    """The minimum role for a request, or None if it is public."""
    if method == "OPTIONS" or any(path == p or path.startswith(p + "/") for p in PUBLIC):
        return None
    if path.startswith(("/api/admin", "/api/connectors", "/api/users", "/api/audit")):
        return "admin"
    if method in ("GET", "HEAD") or path.startswith(READ_LIKE_POSTS):
        return "viewer"
    return "reviewer"


# ------------------------------------------------------------------ passwords and tokens
def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${base64.b64encode(salt).decode()}${base64.b64encode(h).decode()}"


def check_password(pw: str, stored: str | None) -> bool:
    try:
        _, s, h = (stored or "").split("$")
        calc = hashlib.scrypt(pw.encode(), salt=base64.b64decode(s), n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(calc, base64.b64decode(h))
    except Exception:
        return False


def _sign_key() -> bytes:
    return hashlib.sha256(b"contractiq-session|" + crypto._key()).digest()


def make_session(email: str, role: str) -> str:
    body = base64.urlsafe_b64encode(json.dumps({"e": email, "r": role, "x": int(time.time()) + SESSION_HOURS * 3600}).encode()).decode().rstrip("=")
    sig = base64.urlsafe_b64encode(hmac.new(_sign_key(), body.encode(), hashlib.sha256).digest()).decode().rstrip("=")
    return f"{body}.{sig}"


def read_session(tok: str) -> dict | None:
    try:
        body, sig = tok.split(".")
        want = base64.urlsafe_b64encode(hmac.new(_sign_key(), body.encode(), hashlib.sha256).digest()).decode().rstrip("=")
        if not hmac.compare_digest(sig, want):
            return None
        d = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        return d if d["x"] > time.time() else None
    except Exception:
        return None


def new_api_token() -> tuple[str, str, str]:
    raw = "ciq_" + secrets.token_urlsafe(32)
    return raw, hashlib.sha256(raw.encode()).hexdigest(), raw[:10]


# ------------------------------------------------------------------ OpenID Connect
_jwks: dict = {"at": 0.0, "keys": None, "url": None}


def oidc_config() -> dict | None:
    iss = os.environ.get("OIDC_ISSUER")
    if not iss:
        return None
    return {"issuer": iss.rstrip("/"), "audience": os.environ.get("OIDC_AUDIENCE"), "roles_claim": os.environ.get("OIDC_ROLES_CLAIM", "roles"),
            "default_role": os.environ.get("OIDC_DEFAULT_ROLE", "viewer"), "jwks_url": os.environ.get("OIDC_JWKS_URL")}


def _jwks_keys(cfg: dict, force: bool = False) -> list[dict]:
    if force or not _jwks["keys"] or time.time() - _jwks["at"] > 600:
        url = cfg["jwks_url"] or httpx.get(cfg["issuer"] + "/.well-known/openid-configuration", timeout=10).json()["jwks_uri"]
        _jwks.update(keys=httpx.get(url, timeout=10).json()["keys"], at=time.time(), url=url)
    return _jwks["keys"]


def verify_oidc(tok: str) -> dict | None:
    cfg = oidc_config()
    if not cfg:
        return None
    try:
        kid = jwt.get_unverified_header(tok).get("kid")
        keys = _jwks_keys(cfg)
        k = next((x for x in keys if x.get("kid") == kid), None) or next((x for x in _jwks_keys(cfg, True) if x.get("kid") == kid), None)
        if not k:
            return None
        claims = jwt.decode(tok, jwt.PyJWK(k).key, algorithms=["RS256", "ES256"], issuer=cfg["issuer"], audience=cfg["audience"] or None,
                            options={"verify_aud": bool(cfg["audience"])})
    except Exception:
        return None
    email = (claims.get("email") or claims.get("preferred_username") or claims.get("sub") or "").lower()
    if not email:
        return None
    raw = claims.get(cfg["roles_claim"]) or []
    roles = [raw] if isinstance(raw, str) else list(raw)
    role = max([r for r in roles if r in RANK] or [cfg["default_role"]], key=lambda r: RANK[r])
    return {"email": email, "name": claims.get("name"), "role": role, "source": "oidc"}


# ------------------------------------------------------------------ identity
def identify(token: str | None) -> dict | None:
    """The caller behind a bearer token: {email, name, role, source} or None."""
    if not token:
        return None
    if token.startswith("ciq_"):
        h = hashlib.sha256(token.encode()).hexdigest()
        with SessionLocal() as s:
            r = s.execute(text("""SELECT t.id, t.role AS trole, u.email, u.name, u.role, u.active FROM api_tokens t JOIN users u ON u.id = t.user_id
                                  WHERE t.token_hash = :h AND NOT t.revoked"""), {"h": h}).mappings().first()
            if not r or not r["active"]:
                return None
            s.execute(text("UPDATE api_tokens SET last_used_at = now() WHERE id = :i"), {"i": r["id"]})
            s.commit()
        role = r["trole"] if RANK[r["trole"]] <= RANK[r["role"]] else r["role"]      # a token never outranks its owner
        return {"email": r["email"], "name": r["name"], "role": role, "source": "token"}
    if token.count(".") == 1:
        d = read_session(token)
        if not d:
            return None
        with SessionLocal() as s:
            u = s.execute(text("SELECT email, name, role, active FROM users WHERE email = :e"), {"e": d["e"]}).mappings().first()
        return {"email": u["email"], "name": u["name"], "role": u["role"], "source": "session"} if u and u["active"] else None
    if token.count(".") == 2:
        u = verify_oidc(token)
        if not u:
            return None
        with SessionLocal() as s:        # provision on first sight; the identity provider owns the role
            s.execute(text("""INSERT INTO users (email, name, role, source, last_login_at) VALUES (:e,:n,:r,'oidc',now())
                              ON CONFLICT (email) DO UPDATE SET role = EXCLUDED.role, name = COALESCE(EXCLUDED.name, users.name), last_login_at = now()
                              WHERE users.source = 'oidc'"""), {"e": u["email"], "n": u["name"], "r": u["role"]})
            row = s.execute(text("SELECT active, role FROM users WHERE email = :e"), {"e": u["email"]}).mappings().first()
            s.commit()
        return {**u, "role": row["role"]} if row and row["active"] else None
    return None


def audit(user: dict | None, method: str, path: str, status: int | None, ip: str | None = None, event: str = "request", detail: dict | None = None) -> None:
    try:
        with SessionLocal() as s:
            s.execute(text("INSERT INTO audit_log (user_email, role, method, path, status, ip, event, detail) VALUES (:u,:r,:m,:p,:s,:i,:e,CAST(:d AS jsonb))"),
                      {"u": (user or {}).get("email"), "r": (user or {}).get("role"), "m": method, "p": path[:300], "s": status, "i": ip, "e": event, "d": json.dumps(detail or {})})
            s.commit()
    except Exception:       # an audit failure must never break the request it describes
        pass
