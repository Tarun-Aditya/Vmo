"""Approval routing: admin-defined rules pick an approval chain for a draft from its type, value and the worst deviation severity found; approvers decide step by step;
the last approval approves the draft (still blocked while comment threads are open). Approvers are notified, and stalled steps raise reminders, through the alerts engine."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text

from app.db import SessionLocal
from app.routes_auth import me

router = APIRouter(prefix="/api")
SEV = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def rows(sql: str, **p) -> list[dict]:
    with SessionLocal() as s:
        return [dict(r) for r in s.execute(text(sql), p).mappings().all()]


# ------------------------------------------------------------------ rules (admin)
class StepIn(BaseModel):
    label: str
    approvers: list[str]


class RuleIn(BaseModel):
    name: str
    doc_types: list[str] = []
    min_value: float | None = None
    min_severity: str | None = None
    steps: list[StepIn]
    enabled: bool = True
    sort_order: int = 100
    remind_after_days: int = 3


def _check(b: RuleIn) -> None:
    if not b.name.strip() or not b.steps or any(not s.label.strip() or not s.approvers for s in b.steps):
        raise HTTPException(422, "a rule needs a name and at least one step with an approver")
    if b.min_severity is not None and b.min_severity not in SEV:
        raise HTTPException(422, "min_severity must be low, medium, high or critical")


@router.get("/admin/approval-rules")
def list_rules():
    return rows("SELECT * FROM approval_rules ORDER BY sort_order, id")


@router.post("/admin/approval-rules")
def create_rule(b: RuleIn):
    _check(b)
    with SessionLocal() as s:
        i = s.execute(text("""INSERT INTO approval_rules (name, doc_types, min_value, min_severity, steps, enabled, sort_order, remind_after_days)
                              VALUES (:n,:t,:v,:s,CAST(:st AS jsonb),:e,:o,:r) RETURNING id"""),
                      {"n": b.name.strip(), "t": b.doc_types, "v": b.min_value, "s": b.min_severity, "st": json.dumps([x.model_dump() for x in b.steps]), "e": b.enabled, "o": b.sort_order, "r": b.remind_after_days}).scalar()
        s.commit()
    return rows("SELECT * FROM approval_rules WHERE id=:i", i=i)[0]


@router.put("/admin/approval-rules/{rid}")
def update_rule(rid: int, b: RuleIn):
    _check(b)
    with SessionLocal() as s:
        n = s.execute(text("""UPDATE approval_rules SET name=:n, doc_types=:t, min_value=:v, min_severity=:s, steps=CAST(:st AS jsonb), enabled=:e, sort_order=:o, remind_after_days=:r WHERE id=:i"""),
                      {"n": b.name.strip(), "t": b.doc_types, "v": b.min_value, "s": b.min_severity, "st": json.dumps([x.model_dump() for x in b.steps]), "e": b.enabled, "o": b.sort_order, "r": b.remind_after_days, "i": rid}).rowcount
        s.commit()
    if not n:
        raise HTTPException(404, "rule not found")
    return rows("SELECT * FROM approval_rules WHERE id=:i", i=rid)[0]


@router.delete("/admin/approval-rules/{rid}")
def delete_rule(rid: int):
    with SessionLocal() as s:
        s.execute(text("DELETE FROM approval_rules WHERE id=:i"), {"i": rid})
        s.commit()
    return {"ok": True}


# ------------------------------------------------------------------ approvals
def _notify(cid: int, aid: int, who: list[str], title: str, body: str, key: str) -> None:
    with SessionLocal() as s:
        for w in who:
            s.execute(text("""INSERT INTO alerts (rule_key, dedupe_key, title, body, severity, link, contract_id) VALUES ('approval', :d, :t, :b, 'medium', :l, :c)
                              ON CONFLICT (dedupe_key) DO NOTHING"""), {"d": f"approval:{aid}:{w}:{key}", "t": title, "b": f"For {w}: {body[:200]}", "l": f"/redline/{cid}", "c": cid})
        s.commit()


def view(aid: int) -> dict:
    a = rows("SELECT * FROM approvals WHERE id=:i", i=aid)
    if not a:
        raise HTTPException(404, "approval not found")
    return {**a[0], "steps": rows("SELECT * FROM approval_steps WHERE approval_id=:i ORDER BY seq", i=aid)}


def _match(cid: int) -> dict | None:
    c = rows("SELECT id, title, type, COALESCE(total_value, annual_value, 0) AS value FROM contracts WHERE id=:i", i=cid)
    if not c:
        raise HTTPException(404, "document not found")
    c = c[0]
    red = rows("SELECT items FROM redlines WHERE contract_id=:i", i=cid)
    worst = max([SEV.get(x.get("severity"), 0) for x in ((red[0]["items"] if red else []) or [])] or [-1])
    for r in rows("SELECT * FROM approval_rules WHERE enabled ORDER BY sort_order, id"):
        if r["doc_types"] and c["type"] not in r["doc_types"]:
            continue
        if r["min_value"] is not None and float(c["value"]) < float(r["min_value"]):
            continue
        if r["min_severity"] is not None and worst < SEV[r["min_severity"]]:
            continue
        return r
    return None


@router.get("/documents/{cid}/approval")
def current(cid: int):
    a = rows("SELECT id FROM approvals WHERE contract_id=:c AND status IN ('pending') ORDER BY id DESC LIMIT 1", c=cid) or rows("SELECT id FROM approvals WHERE contract_id=:c ORDER BY id DESC LIMIT 1", c=cid)
    return {"approval": view(a[0]["id"]) if a else None, "matching_rule": (lambda r: r and {"id": r["id"], "name": r["name"]})(_match(cid))}


@router.post("/documents/{cid}/approval/start")
def start(cid: int, request: Request):
    if rows("SELECT 1 FROM approvals WHERE contract_id=:c AND status='pending'", c=cid):
        raise HTTPException(409, "an approval is already in progress for this draft")
    r = _match(cid)
    if not r:
        raise HTTPException(404, "no approval rule applies to this document: add one in Admin → Approval rules")
    with SessionLocal() as s:
        aid = s.execute(text("INSERT INTO approvals (contract_id, rule_id, rule_name, created_by) VALUES (:c,:r,:n,:u) RETURNING id"), {"c": cid, "r": r["id"], "n": r["name"], "u": me(request)["email"]}).scalar()
        for i, st in enumerate(r["steps"]):
            s.execute(text("INSERT INTO approval_steps (approval_id, seq, label, approvers, status, activated_at) VALUES (:a,:q,:l,:p,:s,CASE WHEN :q=1 THEN now() END)"),
                      {"a": aid, "q": i + 1, "l": st["label"], "p": st["approvers"], "s": "pending" if i == 0 else "waiting"})
        s.execute(text("""INSERT INTO contract_reviews (contract_id, status) VALUES (:c,'in_review') ON CONFLICT (contract_id) DO UPDATE SET status='in_review', updated_at=now()"""), {"c": cid})
        s.commit()
    title = rows("SELECT title FROM contracts WHERE id=:c", c=cid)[0]["title"]
    _notify(cid, aid, r["steps"][0]["approvers"], f"Approval needed: {title}", f"Step 1 ({r['steps'][0]['label']}) of {len(r['steps'])}", "s1")
    return view(aid)


class DecideIn(BaseModel):
    decision: str
    comment: str | None = None


@router.post("/approvals/{aid}/steps/{sid}/decide")
def decide(aid: int, sid: int, b: DecideIn, request: Request):
    import os

    a = view(aid)
    st = next((x for x in a["steps"] if x["id"] == sid), None)
    if not st or a["status"] != "pending" or st["status"] != "pending":
        raise HTTPException(409, "this step is not waiting for a decision")
    if b.decision not in ("approve", "reject"):
        raise HTTPException(422, "decision must be approve or reject")
    u = me(request)
    if os.environ.get("AUTH_MODE", "off").lower() == "on" and u["email"] not in st["approvers"] and u["role"] != "admin":
        raise HTTPException(403, "you are not an approver for this step")
    cid = a["contract_id"]
    title = rows("SELECT title FROM contracts WHERE id=:c", c=cid)[0]["title"]
    if b.decision == "approve" and st["seq"] == len(a["steps"]):          # the final approval approves the draft: open threads still block it
        n = rows("SELECT count(*) AS n FROM comment_threads WHERE contract_id=:c AND status='open'", c=cid)[0]["n"]
        if n:
            raise HTTPException(409, f"{n} comment thread{'s are' if n != 1 else ' is'} still open: resolve {'them' if n != 1 else 'it'} before the final approval")
    with SessionLocal() as s:
        s.execute(text("UPDATE approval_steps SET status=:s, decided_by=:u, decided_at=now(), comment=:c WHERE id=:i"), {"s": "approved" if b.decision == "approve" else "rejected", "u": u["email"], "c": b.comment, "i": sid})
        if b.decision == "reject":
            s.execute(text("UPDATE approvals SET status='rejected', finished_at=now() WHERE id=:a"), {"a": aid})
            s.execute(text("UPDATE contract_reviews SET status='changes_requested', note=COALESCE(:n, note), updated_at=now() WHERE contract_id=:c"), {"n": b.comment, "c": cid})
        elif st["seq"] == len(a["steps"]):
            s.execute(text("UPDATE approvals SET status='approved', finished_at=now() WHERE id=:a"), {"a": aid})
            s.execute(text("UPDATE contract_reviews SET status='approved', updated_at=now() WHERE contract_id=:c"), {"c": cid})
        else:
            s.execute(text("UPDATE approval_steps SET status='pending', activated_at=now() WHERE approval_id=:a AND seq=:q"), {"a": aid, "q": st["seq"] + 1})
        s.commit()
    nxt = next((x for x in a["steps"] if x["seq"] == st["seq"] + 1), None)
    if b.decision == "approve" and nxt:
        _notify(cid, aid, nxt["approvers"], f"Approval needed: {title}", f"Step {nxt['seq']} ({nxt['label']}) after {u['email']} approved", f"s{nxt['seq']}")
    elif b.decision == "reject" and a["created_by"]:
        _notify(cid, aid, [a["created_by"]], f"Approval rejected: {title}", f"{u['email']}: {b.comment or 'no comment'}", "rej")
    elif b.decision == "approve":
        _notify(cid, aid, [a["created_by"] or "owner"], f"Approved: {title}", "All approval steps are complete.", "done")
    return view(aid)


@router.delete("/approvals/{aid}")
def cancel(aid: int):
    with SessionLocal() as s:
        s.execute(text("UPDATE approvals SET status='cancelled', finished_at=now() WHERE id=:a AND status='pending'"), {"a": aid})
        s.commit()
    return view(aid)


@router.get("/approvals/pending")
def pending(approver: str | None = None):
    """Steps waiting for a decision, optionally only those where `approver` is listed (the 'my approvals' inbox)."""
    return rows("""SELECT a.id AS approval_id, s.id AS step_id, s.seq, s.label, s.approvers, c.id AS contract_id, c.title, c.vendor, a.rule_name, s.activated_at,
                          (CURRENT_DATE - s.activated_at::date) AS days_waiting
                   FROM approval_steps s JOIN approvals a ON a.id = s.approval_id JOIN contracts c ON c.id = a.contract_id
                   WHERE a.status='pending' AND s.status='pending' AND (CAST(:u AS text) IS NULL OR :u = ANY(s.approvers)) ORDER BY s.activated_at""", u=approver)
