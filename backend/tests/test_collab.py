"""Suggesting mode (propose / accept / reject), conflict protection on save, and the live channel (presence and pushes)."""
import re

import pytest
from sqlalchemy import text

from app.db import SessionLocal


@pytest.fixture()
def draft(client, seeded):
    c = client.post("/api/redline/upload", json={"filename": "collab_nda.md", "content": "# Mutual NDA – Collab Labs\n\n**Parties:** Arcadia Retail Inc. (the \"Customer\") and Collab Labs Inc (the \"Supplier\")\n\n## Term\nThis Agreement commences on 1 December 2026 and continues for three (3) years.\n\n## Governing Law\nThis Agreement is governed by the laws of New York.\n\n## Payment\nThe Customer shall pay invoices within 20 days.\n", "owner": "Legal", "category": "Legal"}).json()["contract_id"]
    yield c
    from app import pipeline

    with SessionLocal() as s:
        root = pipeline.inbox_path(s)
        s.execute(text("DELETE FROM contracts WHERE vendor ILIKE '%Collab Labs%'"))
        s.commit()
    for f in list(root.rglob("collab_nda*")):
        f.unlink()


def test_suggestion_accept_reject_and_stale_text(client, draft):
    cid = draft
    md0 = client.get(f"/api/documents/{cid}/content").json()
    s = client.post(f"/api/documents/{cid}/suggestions", json={"original": "within 20 days", "proposed": "within 45 days", "note": "Policy is 45."}).json()
    assert s["suggestion"] == {"original": "within 20 days", "proposed": "within 45 days", "state": "open"} and "Suggested change" in s["comments"][0]["body"]
    assert client.post(f"/api/documents/{cid}/suggestions", json={"original": "This Agreement", "proposed": "That Agreement"}).status_code == 422          # appears twice: ambiguous
    assert client.post(f"/api/documents/{cid}/suggestions", json={"original": "nowhere in the text", "proposed": "x"}).status_code == 422
    assert "within 20 days" in client.get(f"/api/documents/{cid}/content").json()["md"]                                                           # nothing changes until accepted
    done = client.post(f"/api/threads/{s['id']}/accept").json()
    assert done["status"] == "resolved" and done["suggestion"]["state"] == "accepted"
    after = client.get(f"/api/documents/{cid}/content").json()
    assert "within 45 days" in after["md"] and "within 20 days" not in after["md"] and after["version"] == md0["version"] + 1
    assert client.post(f"/api/threads/{s['id']}/accept").status_code == 409                                                                       # only once
    r = client.post(f"/api/documents/{cid}/suggestions", json={"original": "laws of New York", "proposed": "laws of England"}).json()
    assert client.post(f"/api/threads/{r['id']}/reject").json()["suggestion"]["state"] == "rejected" and "laws of New York" in client.get(f"/api/documents/{cid}/content").json()["md"]
    stale = client.post(f"/api/documents/{cid}/suggestions", json={"original": "three (3) years", "proposed": "five (5) years"}).json()
    md = client.get(f"/api/documents/{cid}/content").json()["md"]
    client.put(f"/api/documents/{cid}/content", json={"md": md.replace("three (3) years", "four (4) years"), "note": "colleague edit"})                # the text moves on
    assert client.post(f"/api/threads/{stale['id']}/accept").status_code == 409


def test_a_save_from_an_out_of_date_version_is_refused(client, draft):
    cid = draft
    c = client.get(f"/api/documents/{cid}/content").json()
    ok = client.put(f"/api/documents/{cid}/content", json={"md": c["md"] + "\nExtra one.\n", "note": "A", "base_version": c["version"]})
    assert ok.status_code == 200 and ok.json()["version"] == c["version"] + 1
    late = client.put(f"/api/documents/{cid}/content", json={"md": c["md"] + "\nExtra two.\n", "note": "B", "base_version": c["version"]})       # B still started from the old version
    assert late.status_code == 409 and "conflict" in late.json()["detail"] and "Extra one" in client.get(f"/api/documents/{cid}/content").json()["md"]
    assert client.put(f"/api/documents/{cid}/content", json={"md": c["md"] + "\nExtra two.\n", "note": "B"}).status_code == 200                       # no base version: last write wins, as before


def test_live_channel_presence_and_pushes(client, draft):
    cid = draft
    with client.websocket_connect(f"/ws/documents/{cid}?name=Priya") as a:
        assert a.receive_json() == {"type": "presence", "users": [{"name": "Priya", "editing": False}]}
        with client.websocket_connect(f"/ws/documents/{cid}?name=Meera") as b:
            assert {u["name"] for u in a.receive_json()["users"]} == {"Priya", "Meera"}
            assert {u["name"] for u in b.receive_json()["users"]} == {"Priya", "Meera"}
            a.send_json({"type": "editing", "on": True})
            ev = b.receive_json()
            assert ev["type"] == "presence" and {u["name"]: u["editing"] for u in ev["users"]}["Priya"] is True
            assert a.receive_json()["type"] == "presence"                                                  # Priya's own screen is told too
            client.post(f"/api/documents/{cid}/threads", json={"body": "A comment"})                       # a comment: both screens hear about it
            assert a.receive_json()["type"] == "threads" and b.receive_json()["type"] == "threads"
            c = client.get(f"/api/documents/{cid}/content").json()
            client.put(f"/api/documents/{cid}/content", json={"md": c["md"] + "\nMore.\n", "note": "x"})
            ev = b.receive_json()
            assert ev["type"] == "version" and ev["version"] == c["version"] + 1 and a.receive_json()["type"] == "version"
        assert [u["name"] for u in a.receive_json()["users"]] == ["Priya"]                                   # Meera left


def test_live_channel_needs_a_sign_in_when_auth_is_on(client, draft, monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "on")
    with pytest.raises(Exception):
        with client.websocket_connect(f"/ws/documents/{draft}?name=x") as ws:
            ws.receive_json()
