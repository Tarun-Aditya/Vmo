"""A simulated identity provider (OpenID Connect authorization-code flow with RS256 id tokens and a JWKS) plus the app's side of the flow (/api/auth/oidc/login and /callback), so
single sign-on can be shown without an Entra ID / Okta tenant. The same app code verifies real providers: set OIDC_ISSUER / OIDC_CLIENT_ID / OIDC_CLIENT_SECRET. Demo only."""
from __future__ import annotations

import os
import secrets
import time
from html import escape
from urllib.parse import urlencode

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

router = APIRouter()
_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_CODES: dict[str, dict] = {}
USERS = {"priya@arcadia.demo": ("Priya Rao", ["admin"]), "meera@arcadia.demo": ("Meera Shah", ["reviewer"]), "vik@arcadia.demo": ("Vik Anand", ["viewer"])}
CLIENT_ID, CLIENT_SECRET = "contractiq-demo", "demo-sso-secret"


def issuer(request: Request | None = None) -> str:
    return os.environ.get("OIDC_ISSUER") or ((os.environ.get("PUBLIC_API_URL") or str(request.base_url).rstrip("/")) + "/sim/idp")


idp = APIRouter(prefix="/sim/idp")


@idp.get("/.well-known/openid-configuration")
def discovery(request: Request):
    i = issuer(request)
    return {"issuer": i, "authorization_endpoint": f"{i}/authorize", "token_endpoint": f"{i}/token", "jwks_uri": f"{i}/jwks", "response_types_supported": ["code"], "id_token_signing_alg_values_supported": ["RS256"]}


@idp.get("/jwks")
def jwks():
    import json

    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(_KEY.public_key()))
    jwk.update(kid="sim-1", alg="RS256", use="sig")
    return {"keys": [jwk]}


@idp.get("/authorize", response_class=HTMLResponse)
def authorize(request: Request, client_id: str, redirect_uri: str, state: str = "", nonce: str = ""):
    if client_id != CLIENT_ID:
        raise HTTPException(400, "unknown client")
    opts = "".join(f'<button name="user" value="{escape(e)}">{escape(n)} — {escape(r[0])} <small>({escape(e)})</small></button>' for e, (n, r) in USERS.items())
    return (f'<!doctype html><meta charset="utf-8"><title>Sign-in simulator</title><style>body{{font:15px system-ui;max-width:480px;margin:40px auto}}button{{display:block;width:100%;margin:8px 0;padding:12px;text-align:left;font-size:15px;cursor:pointer}}'
            f'.s{{background:#fef3c7;border:1px solid #f59e0b;padding:6px 10px;border-radius:6px;font-size:12px}}</style><p class="s">Simulated identity provider for demonstration. Pick who you are.</p>'
            f'<form method="post" action="{issuer(request)}/authorize"><input type="hidden" name="redirect_uri" value="{escape(redirect_uri)}"><input type="hidden" name="state" value="{escape(state)}"><input type="hidden" name="nonce" value="{escape(nonce)}">{opts}</form>')


@idp.post("/authorize")
def authorize_post(request: Request, redirect_uri: str = Form(...), state: str = Form(""), nonce: str = Form(""), user: str = Form(...)):
    if user not in USERS:
        raise HTTPException(400, "unknown user")
    code = secrets.token_urlsafe(16)
    _CODES[code] = {"user": user, "nonce": nonce, "exp": time.time() + 120}
    return RedirectResponse(f"{redirect_uri}{'&' if '?' in redirect_uri else '?'}{urlencode({'code': code, 'state': state})}", status_code=303)


@idp.post("/token")
def token(request: Request, grant_type: str = Form(...), code: str = Form(...), client_id: str = Form(""), client_secret: str = Form("")):
    c = _CODES.pop(code, None)
    if grant_type != "authorization_code" or client_secret != CLIENT_SECRET or not c or c["exp"] < time.time():
        return JSONResponse({"error": "invalid_grant"}, status_code=400)
    name, roles = USERS[c["user"]]
    now = int(time.time())
    idt = jwt.encode({"iss": issuer(request), "aud": CLIENT_ID, "sub": c["user"], "email": c["user"], "name": name, "roles": roles, "nonce": c["nonce"], "iat": now, "exp": now + 600}, _KEY, algorithm="RS256", headers={"kid": "sim-1"})
    return {"id_token": idt, "access_token": secrets.token_urlsafe(16), "token_type": "Bearer", "expires_in": 600}
