"""Word / Google-Docs style review: comment threads anchored to text (add, reply, assign, resolve, reopen), AI playbook findings opened as threads, and share links
(view / comment / edit, optionally expiring) so a colleague or a vendor can open one draft without an account. Notifications go through the alerts engine."""
from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text

from app.db import SessionLocal
from app.routes_auth import me

router = APIRouter(prefix="/api")
LEVEL = {"view": 0, "comment": 1, "edit": 2}


def rows(sql: str, **p) -> list[dict]:
    with SessionLocal() as s:
        return [dict(r) for r in s.execute(text(sql), p).mappings().all()]


def _doc(cid: int) -> dict:
    d = rows("SELECT id, title, vendor, type, status, body_md FROM contracts WHERE id=:i", i=cid)
    if not d:
        raise HTTPException(404, "document not found")
    return d[0]


def _version(cid: int) -> int:
    return rows("SELECT COALESCE(max(version), 1) AS v FROM document_versions WHERE contract_id=:i", i=cid)[0]["v"]


def _notify(cid: int, thread_id: int, who: list[str], title: str, body: str, key: str) -> None:
    """One in-app alert per (thread, person, kind) through the alerts table; the alerts engine delivers it to the configured channels."""
    with SessionLocal() as s:
        for w in who:
            s.execute(text("""INSERT INTO alerts (rule_key, dedupe_key, title, body, severity, link, contract_id, vendor) VALUES ('comment', :d, :t, :b, 'medium', :l, :c, NULL)
                              ON CONFLICT (dedupe_key) DO NOTHING"""), {"d": f"comment:{thread_id}:{w}:{key}", "t": title, "b": f"For {w}: {body[:200]}", "l": f"/documents/{cid}/edit?thread={thread_id}", "c": cid})
        s.commit()


def _mentions(body: str) -> list[str]:
    return sorted(set(re.findall(r"@([\w.\-]+(?:@[\w.\-]+)?)", body)))


def thread_view(tid: int) -> dict:
    t = rows("SELECT * FROM comment_threads WHERE id=:i", i=tid)
    if not t:
        raise HTTPException(404, "thread not found")
    return {**t[0], "comments": rows("SELECT id, author, body, created_at, edited_at FROM comments WHERE thread_id=:i ORDER BY id", i=tid)}


def threads_of(cid: int, status: str | None = None) -> list[dict]:
    ts = rows("SELECT * FROM comment_threads WHERE contract_id=:c AND (CAST(:s AS text) IS NULL OR status=:s) ORDER BY COALESCE(anchor_start, 0), id", c=cid, s=status)
    cm = rows("SELECT id, thread_id, author, body, created_at, edited_at FROM comments WHERE thread_id IN (SELECT id FROM comment_threads WHERE contract_id=:c) ORDER BY id", c=cid)
    by: dict[int, list] = {}
    for c in cm:
        by.setdefault(c["thread_id"], []).append(c)
    return [{**t, "comments": by.get(t["id"], [])} for t in ts]


def _locate(md: str, quote: str, start: int | None) -> tuple[int | None, int | None]:
    """Keep the stored range if it still holds the quote, else find the quote again (the text may have been edited since)."""
    if quote and start is not None and md[start:start + len(quote)] == quote:
        return start, start + len(quote)
    i = md.find(quote) if quote else -1
    return (i, i + len(quote)) if i >= 0 else (None, None)


class ThreadIn(BaseModel):
    body: str
    anchor_text: str | None = None
    anchor_start: int | None = None
    assignee: str | None = None
    due_date: str | None = None
    clause_type: str | None = None


def create_thread(cid: int, b: ThreadIn, author: str, source: str = "user", ai_key: str | None = None, severity: str | None = None) -> dict:
    d = _doc(cid)
    if not b.body.strip():
        raise HTTPException(422, "a comment needs text")
    s0, e0 = _locate(d["body_md"] or "", b.anchor_text or "", b.anchor_start)
    with SessionLocal() as s:
        tid = s.execute(text("""INSERT INTO comment_threads (contract_id, version, anchor_text, anchor_start, anchor_end, clause_type, source, severity, created_by, assignee, due_date, ai_key)
                                VALUES (:c,:v,:q,:s,:e,:ct,:src,:sev,:by,:a,CAST(:d AS date),:k) ON CONFLICT (contract_id, ai_key) DO NOTHING RETURNING id"""),
                        {"c": cid, "v": _version(cid), "q": b.anchor_text, "s": s0, "e": e0, "ct": b.clause_type, "src": source, "sev": severity, "by": author, "a": b.assignee or None,
                         "d": b.due_date or None, "k": ai_key}).scalar()
        if tid:
            s.execute(text("INSERT INTO comments (thread_id, author, body) VALUES (:t,:a,:b)"), {"t": tid, "a": author, "b": b.body.strip()})
        s.commit()
    if not tid:
        return {}
    who = [w for w in {*_mentions(b.body), *([b.assignee] if b.assignee else [])} if w != author]
    if who:
        _notify(cid, tid, who, f"{author} commented on {d['title']}", b.body, "new")
    return thread_view(tid)


# ------------------------------------------------------------------ threads (signed-in users)
@router.get("/documents/{cid}/threads")
def list_threads(cid: int, status: str | None = None):
    _doc(cid)
    ts = threads_of(cid, status)
    return {"threads": ts, "open": sum(t["status"] == "open" for t in threads_of(cid)), "version": _version(cid)}


@router.post("/documents/{cid}/threads")
def add_thread(cid: int, b: ThreadIn, request: Request):
    return create_thread(cid, b, me(request)["email"])


class ReplyIn(BaseModel):
    body: str


@router.post("/threads/{tid}/comments")
def reply(tid: int, b: ReplyIn, request: Request):
    t = thread_view(tid)
    author = me(request)["email"]
    if not b.body.strip():
        raise HTTPException(422, "a reply needs text")
    with SessionLocal() as s:
        s.execute(text("INSERT INTO comments (thread_id, author, body) VALUES (:t,:a,:b)"), {"t": tid, "a": author, "b": b.body.strip()})
        s.commit()
    who = [w for w in {*_mentions(b.body), t["created_by"], t.get("assignee") or ""} if w and w != author and "@" in w or w in _mentions(b.body)]
    if who:
        _notify(t["contract_id"], tid, who, f"{author} replied on {_doc(t['contract_id'])['title']}", b.body, f"reply{len(t['comments'])}")
    return thread_view(tid)


class ThreadPatch(BaseModel):
    status: str | None = None
    assignee: str | None = None
    due_date: str | None = None


@router.put("/threads/{tid}")
def update_thread(tid: int, b: ThreadPatch, request: Request):
    t = thread_view(tid)
    who = me(request)["email"]
    if b.status not in (None, "open", "resolved"):
        raise HTTPException(422, "status must be open or resolved")
    with SessionLocal() as s:
        if b.status:
            s.execute(text("UPDATE comment_threads SET status=:st, resolved_by=CASE WHEN :st='resolved' THEN :w END, resolved_at=CASE WHEN :st='resolved' THEN now() END WHERE id=:i"), {"st": b.status, "w": who, "i": tid})
        if b.assignee is not None or b.due_date is not None:
            s.execute(text("UPDATE comment_threads SET assignee=COALESCE(NULLIF(:a,''), assignee), due_date=COALESCE(CAST(NULLIF(:d,'') AS date), due_date) WHERE id=:i"), {"a": b.assignee, "d": b.due_date, "i": tid})
        s.commit()
    if b.status == "resolved" and t["created_by"] != who and "@" in t["created_by"]:
        _notify(t["contract_id"], tid, [t["created_by"]], f"{who} resolved a thread on {_doc(t['contract_id'])['title']}", t["comments"][0]["body"] if t["comments"] else "", "resolved")
    if b.assignee and b.assignee != who:
        _notify(t["contract_id"], tid, [b.assignee], f"{who} assigned you a thread on {_doc(t['contract_id'])['title']}", t["comments"][0]["body"] if t["comments"] else "", "assigned")
    return thread_view(tid)


@router.delete("/threads/{tid}")
def delete_thread(tid: int, request: Request):
    t = thread_view(tid)
    u = me(request)
    if u["role"] != "admin" and u["email"] != t["created_by"]:
        raise HTTPException(403, "only the author or an administrator can delete a thread")
    with SessionLocal() as s:
        s.execute(text("DELETE FROM comment_threads WHERE id=:i"), {"i": tid})
        s.commit()
    return {"ok": True}


@router.post("/documents/{cid}/threads/from-redline")
def threads_from_redline(cid: int):
    """Open one thread per playbook deviation (idempotent), authored by ContractIQ, so reviewers work through them like comments and resolve them."""
    _doc(cid)
    red = rows("SELECT items FROM redlines WHERE contract_id=:c", c=cid)
    made = 0
    for it in (red[0]["items"] if red else []) or []:
        body = f"{it.get('deviation') or 'Differs from the standard.'}" + (f"\n\nStandard position: {it['standard_position']}" if it.get("standard_position") else "") + (f"\n\nSuggested wording: {it['suggested_text']}" if it.get("suggested_text") else "")
        t = create_thread(cid, ThreadIn(body=body, anchor_text=(it.get("draft_text") or "")[:160] or None, clause_type=it.get("clause_type")), "ContractIQ", "ai", f"redline:{it.get('clause_type')}", it.get("severity"))
        made += bool(t)
    return {"created": made, "open": sum(t["status"] == "open" for t in threads_of(cid))}


# ------------------------------------------------------------------ share links
class ShareIn(BaseModel):
    level: str = "comment"
    expires_days: int | None = 14
    label: str | None = None


@router.post("/documents/{cid}/share")
def create_share(cid: int, b: ShareIn, request: Request):
    _doc(cid)
    if b.level not in LEVEL:
        raise HTTPException(422, "level must be view, comment or edit")
    raw = "shr_" + secrets.token_urlsafe(24)
    exp = datetime.now(timezone.utc) + timedelta(days=b.expires_days) if b.expires_days else None
    with SessionLocal() as s:
        lid = s.execute(text("INSERT INTO share_links (contract_id, token_hash, prefix, level, label, expires_at, created_by) VALUES (:c,:h,:p,:l,:lb,:e,:u) RETURNING id"),
                        {"c": cid, "h": hashlib.sha256(raw.encode()).hexdigest(), "p": raw[:10], "l": b.level, "lb": b.label, "e": exp, "u": me(request)["email"]}).scalar()
        s.commit()
    return {"id": lid, "token": raw, "path": f"/shared/{raw}", "level": b.level, "expires_at": exp, "note": "Copy the link now: it is not shown again."}


@router.get("/documents/{cid}/share")
def list_shares(cid: int):
    return rows("SELECT id, prefix, level, label, expires_at, created_by, created_at, revoked, last_used_at, uses FROM share_links WHERE contract_id=:c ORDER BY id DESC", c=cid)


@router.delete("/documents/{cid}/share/{sid}")
def revoke_share(cid: int, sid: int):
    with SessionLocal() as s:
        s.execute(text("UPDATE share_links SET revoked=true WHERE id=:i AND contract_id=:c"), {"i": sid, "c": cid})
        s.commit()
    return {"ok": True}


def _link(token: str, need: str) -> dict:
    r = rows("SELECT * FROM share_links WHERE token_hash=:h", h=hashlib.sha256(token.encode()).hexdigest())
    if not r or r[0]["revoked"] or (r[0]["expires_at"] and r[0]["expires_at"] < datetime.now(timezone.utc)):
        raise HTTPException(404, "This link is not valid any more")
    if LEVEL[r[0]["level"]] < LEVEL[need]:
        raise HTTPException(403, f"This link only allows {r[0]['level']}")
    with SessionLocal() as s:
        s.execute(text("UPDATE share_links SET last_used_at=now(), uses=uses+1 WHERE id=:i"), {"i": r[0]["id"]})
        s.commit()
    return r[0]


@router.get("/shared/{token}")
def shared_open(token: str):
    ln = _link(token, "view")
    d = _doc(ln["contract_id"])
    return {"title": d["title"], "vendor": d["vendor"], "type": d["type"], "md": d["body_md"], "level": ln["level"], "threads": threads_of(ln["contract_id"]), "version": _version(ln["contract_id"])}


class GuestThread(ThreadIn):
    name: str


@router.post("/shared/{token}/threads")
def shared_thread(token: str, b: GuestThread):
    ln = _link(token, "comment")
    return create_thread(ln["contract_id"], b, f"{b.name.strip()[:60]} (guest)", "guest")


class GuestReply(ReplyIn):
    name: str


@router.post("/shared/{token}/threads/{tid}/comments")
def shared_reply(token: str, tid: int, b: GuestReply):
    ln = _link(token, "comment")
    t = thread_view(tid)
    if t["contract_id"] != ln["contract_id"]:
        raise HTTPException(404, "thread not found")
    with SessionLocal() as s:
        s.execute(text("INSERT INTO comments (thread_id, author, body) VALUES (:t,:a,:b)"), {"t": tid, "a": f"{b.name.strip()[:60]} (guest)", "b": b.body.strip()})
        s.commit()
    return thread_view(tid)


class GuestSave(BaseModel):
    md: str
    name: str


@router.put("/shared/{token}/content")
def shared_save(token: str, b: GuestSave):
    ln = _link(token, "edit")
    from app.routes_docs import save_document

    return save_document(ln["contract_id"], b.md, f"Edited by {b.name.strip()[:60]} (shared link)", "share")


class ImportIn(BaseModel):
    filename: str
    content_b64: str


@router.post("/documents/{cid}/comments/import")
def import_comments(cid: int, b: ImportIn, request: Request):
    """Bring in the comments of a .docx that came back from a colleague or the vendor (Word / Google Docs) as threads; the same comment is never imported twice."""
    import base64

    from app import docx_comments

    _doc(cid)
    try:
        found = docx_comments.read_comments(base64.b64decode(b.content_b64))
    except Exception:
        raise HTTPException(422, "that file is not a readable .docx")
    made = 0
    for c in found:
        key = "docx:" + hashlib.sha1(f"{c['author']}|{c['anchor_text']}|{c['body']}".encode()).hexdigest()[:20]
        made += bool(create_thread(cid, ThreadIn(body=c["body"] or "(empty comment)", anchor_text=c["anchor_text"] or None), f"{c['author']} (Word)", "user", key))
    return {"found": len(found), "imported": made}
