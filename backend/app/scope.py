"""Property scope: which contracts, vendors and alerts concern one property, and which property a request is limited to.

A contract applies at a property when v_property_contracts says so (it names the property, or it is a group agreement covering it), and so do the documents
that hang off such an agreement: its schedules, amendments, and the vendor's NDA and DPA. A user whose account carries a property sees that property only:
every endpoint that can be narrowed takes `property`, and for such a user the account's property replaces whatever was asked."""
from __future__ import annotations

from fastapi import HTTPException, Request
from sqlalchemy import text

# API paths a property-limited user may call (everything else is refused in the access middleware: deny by default, so a screen added later
# cannot show other properties' data by accident). GET unless listed in WRITE_OK.
READ_OK = ("/api/auth", "/api/meta", "/api/status", "/api/my-property", "/api/properties", "/api/contracts", "/api/renewals", "/api/portfolio-map",
           "/api/obligations", "/api/sla", "/api/certificates", "/api/alerts", "/api/spend", "/api/invoices", "/api/service-events", "/api/vendor-contacts",
           "/api/conversations")
WRITE_OK = ("/api/auth/logout", "/api/auth/mfa", "/api/ask", "/api/chat", "/api/obligations/", "/api/certificates/", "/api/alerts/", "/api/service-events",
            "/api/vendor-contacts", "/api/renewals/decisions", "/api/conversations")


READ_EXACT = ("/api/documents", "/api/ask/suggestions")      # these two lists are narrowed to the property; the paths under /api/documents/ are not allowed


def allowed_for_property_user(method: str, path: str) -> bool:
    if path.startswith("/api/properties/compare"):
        return False                                   # comparing hotels is a group-level view
    if method in ("GET", "HEAD", "OPTIONS"):
        return path.startswith(READ_OK) or path.rstrip("/") in READ_EXACT
    return path.startswith(WRITE_OK)


def user_property(request: Request | None) -> str | None:
    u = getattr(getattr(request, "state", None), "user", None) if request is not None else None
    return (u or {}).get("property") or None


def effective(request: Request | None, asked: str | None) -> str | None:
    """The property this request is about: the account's own property for a property-limited user (asking for another one is refused), else what was asked."""
    mine = user_property(request)
    if mine:
        if asked and asked != mine:
            raise HTTPException(403, f"Your account is limited to {mine}")
        return mine
    return asked or None


def contract_ids(s, prop: str) -> list[int]:
    return [r[0] for r in s.execute(text("""
        WITH here AS (SELECT DISTINCT contract_id AS id FROM v_property_contracts WHERE property = :p)
        SELECT id FROM here
        UNION SELECT c.id FROM contracts c WHERE c.parent_id IN (SELECT id FROM here)              -- amendments and DPAs of an agreement that applies here,
                                           AND (c.property IS NULL OR c.property = :p)          -- and its schedules for this property, never another property's
        UNION SELECT c.id FROM contracts c WHERE c.type IN ('NDA', 'DPA') AND c.status <> 'draft'
                                           AND c.vendor IN (SELECT vendor FROM contracts WHERE id IN (SELECT id FROM here))
        UNION SELECT c.id FROM contracts c WHERE c.property = :p"""), {"p": prop})]


def vendors(s, prop: str) -> list[str]:
    return [r[0] for r in s.execute(text("SELECT DISTINCT vendor FROM contracts WHERE id = ANY(:ids) ORDER BY 1"), {"ids": contract_ids(s, prop)})]


def check_contract(request: Request, cid: int) -> None:
    """Refuse a contract outside a property-limited user's property."""
    mine = user_property(request)
    if not mine:
        return
    from app.db import SessionLocal

    with SessionLocal() as s:
        if cid not in contract_ids(s, mine):
            raise HTTPException(403, f"Your account is limited to {mine}")


def alert_properties(s, contract_id: int | None, vendor: str | None) -> list[str]:
    """The properties an alert concerns: those its contract applies at, else those its vendor serves. Empty = group-wide."""
    if contract_id:
        for sql in ("SELECT property FROM contracts WHERE id = :c AND property IS NOT NULL",                     # a contract naming its property concerns that property only
                    "SELECT DISTINCT property FROM v_property_contracts WHERE contract_id = :c ORDER BY 1",
                    "SELECT DISTINCT property FROM v_property_contracts WHERE contract_id = (SELECT parent_id FROM contracts WHERE id = :c) ORDER BY 1"):     # an amendment / DPA: its agreement's
            r = [x[0] for x in s.execute(text(sql), {"c": contract_id})]
            if r:
                return r
    if vendor:
        return [x[0] for x in s.execute(text("SELECT DISTINCT property FROM v_property_contracts WHERE vendor = :v ORDER BY 1"), {"v": vendor})]
    return []


# ------------------------------------------------------------------ Ask for a property-limited account: the database itself only shows that property
from contextvars import ContextVar  # noqa: E402

SQL_LIMIT: ContextVar[dict | None] = ContextVar("sql_limit", default=None)       # {"prop", "ids", "vendors"} while answering for a property-limited account
QUALIFIED = __import__("re").compile(r"\b(?:public|pg_catalog|pg_temp\w*|information_schema)\s*\.", __import__("re").I)


def limit_for(prop: str) -> dict:
    from app.db import SessionLocal

    with SessionLocal() as s:
        return {"prop": prop, "ids": contract_ids(s, prop), "vendors": vendors(s, prop)}


def shadow_views(conn, lim: dict) -> None:
    """On `conn` (a dedicated connection that is closed afterwards), create a temporary view for every relation the read-only role can read, with the same
    name and only the rows of one property. PostgreSQL resolves unqualified names in the session's temporary schema first, so any query on this connection
    sees the property's rows only; schema-qualified names are refused before the query runs (QUALIFIED)."""
    ids = "ARRAY[" + ",".join(str(int(i)) for i in lim["ids"]) + "]::int[]" if lim["ids"] else "ARRAY[]::int[]"
    vs = "ARRAY[" + ",".join("'" + v.replace("'", "''") + "'" for v in lim["vendors"]) + "]::text[]" if lim["vendors"] else "ARRAY[]::text[]"
    prop = "'" + lim["prop"].replace("'", "''") + "'"
    rels = conn.exec_driver_sql("""SELECT DISTINCT table_name FROM information_schema.role_table_grants
                                   WHERE grantee = current_user AND privilege_type = 'SELECT' AND table_schema = 'public'""").fetchall()
    for (rel,) in rels:
        cols = {r[0] for r in conn.exec_driver_sql("SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = %(t)s", {"t": rel})}
        if rel == "contracts":
            cond = f"id = ANY({ids})"
        elif rel == "properties":
            cond = f"name = {prop}"
        elif "contract_id" in cols and "vendor" in cols:
            cond = f"contract_id = ANY({ids}) OR (contract_id IS NULL AND vendor = ANY({vs}))"
        elif "contract_id" in cols:
            cond = f"contract_id = ANY({ids})"
        elif "property" in cols and "vendor" in cols:
            cond = f"(property = {prop} OR property IS NULL) AND vendor = ANY({vs})"
        elif "property" in cols:
            cond = f"property = {prop}"
        elif "vendor" in cols:
            cond = f"vendor = ANY({vs})"
        else:
            continue                                   # configuration (metrics, clause library, templates, rules): the same for every property
        conn.exec_driver_sql(f'CREATE TEMP VIEW "{rel}" AS SELECT * FROM public."{rel}" WHERE {cond}'.replace("%", "%%"))
