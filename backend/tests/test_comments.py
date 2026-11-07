"""Word / Google-Docs style review: anchored comment threads, replies, assign, resolve, AI findings as threads, approval gate, share links (view / comment / edit)."""
import pytest
from sqlalchemy import text

from app.db import SessionLocal


@pytest.fixture()
def draft(client, seeded):
    cid = next(d["id"] for d in client.get("/api/contracts?status=draft").json() if client.get(f"/api/redline/{d['id']}").json().get("items"))
    with SessionLocal() as s:
        s.execute(text("DELETE FROM comment_threads WHERE contract_id=:c"), {"c": cid})
        s.execute(text("DELETE FROM share_links WHERE contract_id=:c"), {"c": cid})
        s.execute(text("DELETE FROM contract_reviews WHERE contract_id=:c"), {"c": cid})
        s.commit()
    yield cid
    with SessionLocal() as s:
        s.execute(text("DELETE FROM comment_threads WHERE contract_id=:c"), {"c": cid})
        s.execute(text("DELETE FROM share_links WHERE contract_id=:c"), {"c": cid})
        s.execute(text("DELETE FROM contract_reviews WHERE contract_id=:c"), {"c": cid})
        s.execute(text("DELETE FROM alerts WHERE rule_key='comment'"))
        s.commit()


def test_thread_lifecycle_add_reply_assign_resolve_reopen(client, draft):
    md = client.get(f"/api/documents/{draft}/content").json()["md"]
    quote = md.split("\n")[2][:40] or md[:40]
    t = client.post(f"/api/documents/{draft}/threads", json={"body": "Can we shorten this? @meera.rao@arcadia.test", "anchor_text": quote, "assignee": "meera.rao@arcadia.test", "due_date": "2026-12-01"}).json()
    assert t["status"] == "open" and t["anchor_start"] is not None and md[t["anchor_start"]:t["anchor_end"]] == quote and len(t["comments"]) == 1
    r = client.post(f"/api/threads/{t['id']}/comments", json={"body": "Agreed, changed to 30 days."}).json()
    assert [c["body"] for c in r["comments"]][-1].startswith("Agreed")
    res = client.put(f"/api/threads/{t['id']}", json={"status": "resolved"}).json()
    assert res["status"] == "resolved" and res["resolved_by"] and res["resolved_at"]
    assert client.get(f"/api/documents/{draft}/threads?status=open").json()["threads"] == []
    assert client.put(f"/api/threads/{t['id']}", json={"status": "open"}).json()["status"] == "open"
    assert client.put(f"/api/threads/{t['id']}", json={"status": "nope"}).status_code == 422
    assert client.post(f"/api/documents/{draft}/threads", json={"body": "  "}).status_code == 422
    with SessionLocal() as s:       # the mention / assignment reached the notification centre, once
        n = s.execute(text("SELECT count(*) FROM alerts WHERE rule_key='comment' AND body LIKE 'For meera.rao@arcadia.test%'")).scalar()
    assert n >= 1
    assert client.delete(f"/api/threads/{t['id']}").json()["ok"]


def test_redline_findings_become_threads_once_and_gate_approval(client, draft):
    items = client.get(f"/api/redline/{draft}").json()["items"]
    r = client.post(f"/api/documents/{draft}/threads/from-redline").json()
    assert r["created"] == len(items) and r["open"] == len(items)
    assert client.post(f"/api/documents/{draft}/threads/from-redline").json()["created"] == 0           # idempotent
    t = client.get(f"/api/documents/{draft}/threads").json()["threads"][0]
    assert t["source"] == "ai" and t["created_by"] == "ContractIQ" and t["clause_type"]
    g = client.put(f"/api/redline/{draft}/review", json={"status": "approved"})
    assert g.status_code == 409 and "still open" in g.json()["detail"]
    for t in client.get(f"/api/documents/{draft}/threads").json()["threads"]:
        client.put(f"/api/threads/{t['id']}", json={"status": "resolved"})
    assert client.put(f"/api/redline/{draft}/review", json={"status": "approved"}).status_code == 200


def test_share_links_levels_expiry_and_revocation(client, draft):
    md = client.get(f"/api/documents/{draft}/content").json()["md"]
    view = client.post(f"/api/documents/{draft}/share", json={"level": "view", "label": "for legal"}).json()
    com = client.post(f"/api/documents/{draft}/share", json={"level": "comment"}).json()
    edit = client.post(f"/api/documents/{draft}/share", json={"level": "edit"}).json()
    assert view["token"].startswith("shr_") and view["path"] == f"/shared/{view['token']}"
    assert client.get(f"/api/shared/{view['token']}").json()["md"] == md
    assert client.post(f"/api/shared/{view['token']}/threads", json={"body": "hi", "name": "Vera"}).status_code == 403          # view only
    t = client.post(f"/api/shared/{com['token']}/threads", json={"body": "Please review clause 4", "name": "Vera (Vendor)", "anchor_text": md[:30]}).json()
    assert t["created_by"] == "Vera (Vendor) (guest)" and t["source"] == "guest"
    assert client.post(f"/api/shared/{com['token']}/threads/{t['id']}/comments", json={"body": "Updated", "name": "Vera"}).status_code == 200
    assert client.put(f"/api/shared/{com['token']}/content", json={"md": md + "\nX", "name": "Vera"}).status_code == 403      # comment only
    assert client.get("/api/shared/shr_nonsense").status_code == 404
    listed = client.get(f"/api/documents/{draft}/share").json()
    assert {x["level"] for x in listed} == {"view", "comment", "edit"} and "token" not in listed[0] and listed[0]["prefix"].startswith("shr_")
    client.delete(f"/api/documents/{draft}/share/{com['id']}")
    assert client.get(f"/api/shared/{com['token']}").status_code == 404
    with SessionLocal() as s:
        s.execute(text("UPDATE share_links SET expires_at = now() - interval '1 day' WHERE id=:i"), {"i": view["id"]})
        s.commit()
    assert client.get(f"/api/shared/{view['token']}").status_code == 404                                                           # expired


def test_guest_links_work_with_sign_in_required(client, draft, monkeypatch):
    link = client.post(f"/api/documents/{draft}/share", json={"level": "comment"}).json()
    monkeypatch.setenv("AUTH_MODE", "on")
    assert client.get("/api/contracts").status_code == 401                                              # the app is closed...
    assert client.get(f"/api/shared/{link['token']}").status_code == 200                               # ...the link is its own credential
    assert client.post(f"/api/documents/{draft}/share", json={"level": "view"}).status_code == 401


def test_comments_travel_in_the_word_file_and_come_back(client, draft):
    import base64
    import io
    import zipfile

    md = client.get(f"/api/documents/{draft}/content").json()["md"]
    para = next(x for x in md.split("\n") if len(x) > 60 and not x.startswith("#"))
    t = client.post(f"/api/documents/{draft}/threads", json={"body": "Reword this please.", "anchor_text": para[:50]}).json()
    client.post(f"/api/threads/{t['id']}/comments", json={"body": "Done, see v2."})
    r = client.get(f"/api/documents/{draft}/export.docx")
    assert r.status_code == 200 and r.headers["x-comments"] == "2"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    cx = z.read("word/comments.xml").decode()
    assert "Reword this please." in cx and "Done, see v2." in cx and "commentRangeStart" in z.read("word/document.xml").decode() and "comments+xml" in z.read("[Content_Types].xml").decode()
    # a colleague returns the file: its comments arrive as threads, once
    with SessionLocal() as s:
        s.execute(text("DELETE FROM comment_threads WHERE contract_id=:c"), {"c": draft})
        s.commit()
    b64 = base64.b64encode(r.content).decode()
    out = client.post(f"/api/documents/{draft}/comments/import", json={"filename": "back.docx", "content_b64": b64}).json()
    assert out["found"] == 2 and out["imported"] == 2
    assert client.post(f"/api/documents/{draft}/comments/import", json={"filename": "back.docx", "content_b64": b64}).json()["imported"] == 0
    ts = client.get(f"/api/documents/{draft}/threads").json()["threads"]
    assert {c["body"] for t_ in ts for c in t_["comments"]} == {"Reword this please.", "Done, see v2."} and all(t_["created_by"].endswith("(Word)") for t_ in ts)
    assert client.post(f"/api/documents/{draft}/comments/import", json={"filename": "x.docx", "content_b64": base64.b64encode(b"nope").decode()}).status_code == 422
