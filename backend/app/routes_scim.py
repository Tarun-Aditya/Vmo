"""SCIM 2.0 (Users) so an identity provider (Okta, Entra ID, ...) can create, update and deactivate accounts. Authenticate with an administrator API token as the SCIM bearer token.
SCIM-created users have no local password: they sign in through OpenID Connect; their role comes from the `roles` value (viewer | reviewer | admin), default viewer."""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text

from app.db import SessionLocal

router = APIRouter(prefix="/api/scim/v2")
SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
LIST = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
ROLES = ("viewer", "reviewer", "admin")


def rows(sql: str, **p) -> list[dict]:
    with SessionLocal() as s:
        return [dict(r) for r in s.execute(text(sql), p).mappings().all()]


def out(u: dict) -> dict:
    return {"schemas": [SCHEMA], "id": str(u["id"]), "externalId": u.get("external_id"), "userName": u["email"], "displayName": u.get("name"), "active": u["active"],
            "emails": [{"value": u["email"], "primary": True}], "roles": [{"value": u["role"]}], "meta": {"resourceType": "User", "created": u["created_at"].isoformat() if u.get("created_at") else None}}


def _role(body: dict, default: str = "viewer") -> str:
    vals = [r.get("value") if isinstance(r, dict) else r for r in body.get("roles") or []]
    ok = [v for v in vals if v in ROLES]
    return max(ok, key=ROLES.index) if ok else default


def _err(code: int, detail: str):
    raise HTTPException(code, detail)


@router.get("/ServiceProviderConfig")
def config():
    return {"schemas": ["urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"], "patch": {"supported": True}, "bulk": {"supported": False}, "filter": {"supported": True, "maxResults": 200},
            "changePassword": {"supported": False}, "sort": {"supported": False}, "etag": {"supported": False}, "authenticationSchemes": [{"type": "oauthbearertoken", "name": "Bearer token", "description": "An administrator API token"}]}


@router.get("/Users")
def list_users(filter: str | None = None, startIndex: int = 1, count: int = 100):
    where, p = "", {}
    if filter:
        m = re.fullmatch(r'\s*userName\s+eq\s+"([^"]+)"\s*', filter, re.I)
        if not m:
            _err(400, "only the filter: userName eq \"...\" is supported")
        where, p = "WHERE lower(email) = lower(:e)", {"e": m.group(1)}
    us = rows(f"SELECT * FROM users {where} ORDER BY id", **p)
    page = us[max(startIndex - 1, 0): max(startIndex - 1, 0) + min(count, 200)]
    return {"schemas": [LIST], "totalResults": len(us), "startIndex": startIndex, "itemsPerPage": len(page), "Resources": [out(u) for u in page]}


@router.post("/Users", status_code=201)
async def create(request: Request):
    b = await request.json()
    email = (b.get("userName") or "").strip().lower()
    if "@" not in email:
        _err(400, "userName must be an e-mail address")
    if rows("SELECT 1 FROM users WHERE lower(email)=:e", e=email):
        _err(409, "a user with that userName exists")
    name = b.get("displayName") or " ".join(x for x in [(b.get("name") or {}).get("givenName"), (b.get("name") or {}).get("familyName")] if x) or None
    with SessionLocal() as s:
        i = s.execute(text("INSERT INTO users (email, name, role, source, active, external_id) VALUES (:e,:n,:r,'scim',:a,:x) RETURNING id"),
                      {"e": email, "n": name, "r": _role(b), "a": b.get("active", True), "x": b.get("externalId")}).scalar()
        s.commit()
    return out(rows("SELECT * FROM users WHERE id=:i", i=i)[0])


def _get(uid: str) -> dict:
    u = rows("SELECT * FROM users WHERE id=:i", i=int(uid) if uid.isdigit() else -1)
    if not u:
        _err(404, "user not found")
    return u[0]


@router.get("/Users/{uid}")
def get_user(uid: str):
    return out(_get(uid))


def _guard_last_admin(u: dict, new_role: str, active: bool) -> None:
    if u["role"] == "admin" and (new_role != "admin" or not active) and rows("SELECT count(*) AS n FROM users WHERE role='admin' AND active AND id <> :i", i=u["id"])[0]["n"] == 0:
        _err(409, "the last active administrator cannot be demoted or deactivated")


@router.put("/Users/{uid}")
async def replace(uid: str, request: Request):
    b, u = await request.json(), _get(uid)
    role, active = _role(b, u["role"]), b.get("active", True)
    _guard_last_admin(u, role, active)
    with SessionLocal() as s:
        s.execute(text("UPDATE users SET name=COALESCE(:n,name), role=:r, active=:a, external_id=COALESCE(:x,external_id) WHERE id=:i"), {"n": b.get("displayName"), "r": role, "a": active, "x": b.get("externalId"), "i": u["id"]})
        s.commit()
    return out(_get(uid))


@router.patch("/Users/{uid}")
async def patch(uid: str, request: Request):
    b, u = await request.json(), _get(uid)
    role, active, name = u["role"], u["active"], u["name"]
    for op in b.get("Operations", []):
        path, val = (op.get("path") or "").lower(), op.get("value")
        if isinstance(val, dict) and not path:
            active = val.get("active", active)
            name = val.get("displayName", name)
            if "roles" in val:
                role = _role(val, role)
        elif path == "active":
            active = val if isinstance(val, bool) else str(val).lower() == "true"
        elif path == "displayname":
            name = val
        elif path == "roles":
            role = _role({"roles": val if isinstance(val, list) else [val]}, role)
    _guard_last_admin(u, role, active)
    with SessionLocal() as s:
        s.execute(text("UPDATE users SET name=:n, role=:r, active=:a WHERE id=:i"), {"n": name, "r": role, "a": active, "i": u["id"]})
        s.commit()
    return out(_get(uid))


@router.delete("/Users/{uid}", status_code=204)
def deactivate(uid: str):
    u = _get(uid)
    _guard_last_admin(u, u["role"], False)
    with SessionLocal() as s:
        s.execute(text("UPDATE users SET active=false WHERE id=:i"), {"i": u["id"]})
        s.commit()
