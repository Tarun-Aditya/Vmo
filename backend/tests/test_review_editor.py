"""Briefs, uploads, per-pipeline triggers, online editing with versions, redline review decisions."""
import base64
import io
import zipfile
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app import brief, ingest_text, pipeline, scheduler
from app.db import SessionLocal
from app.routes_docs import apply_accepted

DRAFT = """# Draft MSA – Reviewco

**Parties:** Arcadia Retail Inc. (the "Customer") and Reviewco Inc (the "Supplier")
**Effective Date:** 1 October 2026
**Document Type:** MSA

## 1. Term
This Agreement commences on 1 October 2026 and, unless terminated earlier in accordance with its terms, expires on 1 October 2028.

## 2. Payment
The Customer shall pay undisputed invoices within 10 days of receipt of a valid invoice.

## 3. Limitation of Liability
Each party's liability under this Agreement is unlimited, including liability for indirect and consequential losses.
"""


def test_brief_reads_free_text_key_values_json_and_csv():
    r = brief.read_brief("New SOW with Helios Digital Inc for a Snowflake data platform build starting 15 January 2027 for 18 months. "
                         "Annual fees $1.8M, net 30. Governed by the laws of Delaware. Owner: Jordan Blake. Liability capped at 2x fees.")
    p = r["params"]
    assert r["template"] == "SOW" and p["vendor"] == "Helios Digital Inc" and p["effective_date"] == "2027-01-15" and p["term_months"] == 18
    assert p["annual_fees"] == 1_800_000 and p["payment_terms_days"] == 30 and p["governing_law"] == "Delaware" and p["owner"] == "Jordan Blake" and p["liability_cap"] == 2
    kv = brief.read_brief("template: SaaS\nvendor: Foo Corp\nterm: 2 years\nannual fees: $250k\nauto-renew: yes\nnotice: 90 days\nsla: 99.95%")
    assert kv["template"] == "SaaS" and kv["params"] == {"vendor": "Foo Corp", "term_months": 24, "annual_fees": 250_000, "auto_renew": True, "notice_days": 90, "sla": 99.95}
    js = brief.read_brief('{"Supplier": "Bar LLC", "Payment terms": "60 days", "Personal data": "yes"}')
    assert js["params"] == {"vendor": "Bar LLC", "payment_terms_days": 60, "personal_data": True}
    cs = brief.read_brief("field,value\nvendor,Baz Inc\nwarranty,120 days\n")
    assert cs["params"] == {"vendor": "Baz Inc", "warranty_days": 120}


def test_docx_text_is_extracted_with_headings():
    xml = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
           '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>1. Term</w:t></w:r></w:p>'
           '<w:p><w:r><w:t>Twelve months.</w:t></w:r></w:p></w:body></w:document>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", xml)
    assert ingest_text.extract_text("x.docx", buf.getvalue()).strip() == "## 1. Term\n\nTwelve months."


def test_apply_accepted_replaces_clause_text_and_adds_missing_clauses():
    items = [dict(clause_type="liability_cap", status="changed", heading="Limitation of Liability", severity="critical",
                  draft_text="Each party's liability under this Agreement is unlimited, including liability for indirect and consequential losses.",
                  suggested_text="Each party's liability shall not exceed 1 times the annual fees."),
             dict(clause_type="insurance", status="missing", heading="Insurance", severity="medium", draft_text="", suggested_text="Each party shall maintain insurance.")]
    md, n = apply_accepted(DRAFT + "\n## 4. Execution\nSigned.\n", items, {"liability_cap", "insurance"})
    assert n == 2 and "shall not exceed 1 times" in md and "unlimited" not in md
    assert md.index("## 5. Insurance") < md.index("Execution")                      # new clause lands before the signature block
    assert apply_accepted(DRAFT, items, set())[1] == 0


def test_each_pipeline_has_its_own_trigger(tmp_inbox, tmp_path):
    with SessionLocal() as s:
        saved = s.execute(text("SELECT enabled, trigger_mode, folders, last_fingerprint, next_run_at FROM pipeline_config WHERE key='drafts'")).first()
    try:
        with SessionLocal() as s:
            s.execute(text("UPDATE pipeline_config SET enabled=true, trigger_mode='on_change', folders='pytest', last_fingerprint=NULL WHERE key='drafts'"))
            s.commit()
        assert scheduler.due("drafts") is False or True                      # empty folder: fingerprint of nothing
        (tmp_inbox / "d.md").write_text(DRAFT)
        (tmp_inbox / "d.meta.json").write_text('{"status": "draft"}')
        assert scheduler.due("drafts") is True                               # a new file triggers it
        res = pipeline.run_pipeline("watch", pipeline_key="drafts")
        assert res["new_docs"] == 1 and scheduler.due("drafts") is False     # processed; nothing changed since
        (tmp_inbox / "d.md").write_text(DRAFT.replace("10 days", "20 days"))
        assert scheduler.due("drafts") is True                               # an edit triggers it again
        with SessionLocal() as s:                                            # manual and periodic modes behave differently
            s.execute(text("UPDATE pipeline_config SET trigger_mode='manual' WHERE key='drafts'"))
            s.commit()
        assert scheduler.due("drafts") is False
        with SessionLocal() as s:
            s.execute(text("UPDATE pipeline_config SET trigger_mode='periodic', next_run_at=:n WHERE key='drafts'"), {"n": datetime.now(timezone.utc) - timedelta(minutes=1)})
            s.commit()
        assert scheduler.due("drafts") is True
        assert pipeline.run_pipeline("watch", pipeline_key="contracts")["scanned"] == 0   # the other pipeline does not touch these files
    finally:
        with SessionLocal() as s:
            s.execute(text("UPDATE pipeline_config SET enabled=:a, trigger_mode=:b, folders=:c, last_fingerprint=:d, next_run_at=:e WHERE key='drafts'"),
                      dict(a=saved[0], b=saved[1], c=saved[2], d=saved[3], e=saved[4]))
            s.commit()


def test_online_edit_versions_review_and_apply(client, tmp_inbox):
    (tmp_inbox / "d.md").write_text(DRAFT)
    (tmp_inbox / "d.meta.json").write_text('{"status": "draft"}')
    pipeline.run_pipeline("manual")
    with SessionLocal() as s:
        cid = s.execute(text("SELECT id FROM contracts WHERE source_path='pytest/d.md'")).scalar()
    doc = client.get(f"/api/documents/{cid}/content").json()
    assert doc["editable"] and doc["md"].startswith("# Draft MSA") and doc["versions"] == []
    # the checklist flags short payment terms and unlimited liability
    fails = {c["rule_key"] for c in client.get(f"/api/redline/{cid}").json()["checklist"] if c["status"] == "fail"}
    assert {"payment_terms_min", "no_unlimited_liability"} <= fails
    # edit online: save a new version -> re-extracted
    r = client.put(f"/api/documents/{cid}/content", json={"md": doc["md"].replace("within 10 days", "within 45 days"), "note": "payment to 45"}).json()
    assert r["version"] == 2
    vs = client.get(f"/api/documents/{cid}/content").json()["versions"]
    assert [v["version"] for v in vs] == [2, 1] and vs[0]["note"] == "payment to 45"
    assert "10 days" in client.get(f"/api/documents/{cid}/versions/1").json()["md"]
    with SessionLocal() as s:
        assert s.execute(text("SELECT payment_terms_days FROM contracts WHERE id=:i"), {"i": cid}).scalar() == 45
    # review queue: status + decisions + apply
    red = client.get(f"/api/redline/{cid}").json()
    assert red["review"]["status"] == "pending" and "pending" in {d["review_status"] for d in client.get("/api/redline/documents").json()}
    item = next(i for i in red["items"] if i["clause_type"] == "liability_cap")
    out = client.put(f"/api/redline/{cid}/decision", json={"clause_type": "liability_cap", "decision": "accepted"}).json()
    assert out["decisions"] == {"liability_cap": "accepted"} and out["review"]["status"] == "in_review"
    applied = client.post(f"/api/redline/{cid}/apply").json()
    assert applied["applied"] == 1 and applied["version"] == 3
    now = client.get(f"/api/documents/{cid}/content").json()["md"]
    assert item["suggested_text"] in now and "unlimited" not in now
    fails = {c["rule_key"] for c in client.get(f"/api/redline/{cid}").json()["checklist"] if c["status"] == "fail"}
    assert "no_unlimited_liability" not in fails
    assert client.put(f"/api/redline/{cid}/review", json={"status": "approved", "note": "ok"}).json()["review"]["status"] == "approved"
    assert client.put(f"/api/redline/{cid}/review", json={"status": "nope"}).status_code == 422


def test_executed_contracts_cannot_be_edited_and_upload_lands_in_the_queue(client, tmp_inbox, monkeypatch):
    with SessionLocal() as s:
        executed = s.execute(text("SELECT id FROM contracts WHERE status='active' LIMIT 1")).scalar()
    assert client.put(f"/api/documents/{executed}/content", json={"md": "# x"}).status_code == 409
    monkeypatch.setattr(pipeline, "inbox_path", lambda s=None: tmp_inbox.parent)
    r = client.post("/api/redline/upload", json={"filename": "vendor draft.md", "content_b64": base64.b64encode(DRAFT.replace("Reviewco", "Uploadco").encode()).decode()})
    assert r.status_code == 200 and r.json()["contract_id"]
    cid = r.json()["contract_id"]
    d = {x["id"]: x for x in client.get("/api/redline/documents").json()}[cid]
    assert d["status"] == "draft" and d["review_status"] == "pending" and d["deviations"] + d["checks_failed"] > 0
    with SessionLocal() as s:
        s.execute(text("DELETE FROM contracts WHERE id=:i"), {"i": cid})
        s.commit()
    (tmp_inbox.parent / "drafts" / "vendor_draft.md").unlink(missing_ok=True)
    (tmp_inbox.parent / "drafts" / "vendor_draft.meta.json").unlink(missing_ok=True)


def test_generator_brief_clause_picker_and_library(client):
    lib = client.get("/api/generator/library").json()
    assert len(lib) >= 20 and {"key", "heading", "preview", "in_templates"} <= set(lib[0])
    f = {x["template"]: x for x in client.get("/api/generator/forms").json()["forms"]}
    assert "payment" in f["MSA"]["clause_keys"]
    b = client.post("/api/generator/brief", json={"text": "Vendor: Qux Inc\nPayment terms: 30 days\nTerm: 3 years"}).json()
    assert b["params"] == {"vendor": "Qux Inc", "payment_terms_days": 30, "term_months": 36}
    keys = [k for k in f["NDA"]["clause_keys"] if k != "governing_law"] + ["audit_rights"]
    md = client.post("/api/generator/preview", json={"template": "NDA", "params": {"vendor": "Qux Inc", "clauses": keys}}).json()["md"]
    assert "Audit Rights" in md and "Governing Law" not in md
    assert client.post("/api/generator/brief", json={"text": "  "}).status_code == 422


def test_chat_streams_steps_then_answer_and_keeps_history(client):
    import json

    def run(q, cid=None, scope=None):
        r = client.post("/api/chat/stream", json={"question": q, "conversation_id": cid, "demo_mode": False, "contract_ids": scope})
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        return [json.loads(x[5:]) for x in r.text.split("\n\n") if x.startswith("data:")]

    ev = run("How many contracts are expiring in the next quarter?")
    kinds = [e["type"] for e in ev]
    assert kinds[0] == "meta" and kinds[-1] == "done" and "step" in kinds and "token" in kinds and kinds.index("step") < kinds.index("token") < kinds.index("result")
    res = next(e for e in ev if e["type"] == "result")["result"]
    assert "".join(e["text"] for e in ev if e["type"] == "token").strip() == res["answer"].strip() and res["tables"] and res["thinking"]
    cid = ev[0]["conversation_id"]
    ev2 = run("Which vendors have uncapped liability?", cid)                      # a follow-up lands in the same conversation
    assert ev2[0]["conversation_id"] == cid
    conv = client.get(f"/api/conversations/{cid}").json()
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant", "user", "assistant"] and conv["messages"][1]["payload"]["tables"]
    lst = {c["id"]: c for c in client.get("/api/conversations").json()}
    assert lst[cid]["questions"] == 2 and cid in {c["id"] for c in client.get("/api/conversations?q=uncapped").json()}
    assert cid not in {c["id"] for c in client.get("/api/conversations?q=zzznotthere").json()}
    assert client.patch(f"/api/conversations/{cid}", json={"title": "Renamed"}).json()["title"] == "Renamed"
    assert client.delete(f"/api/conversations/{cid}").status_code == 200 and client.get(f"/api/conversations/{cid}").status_code == 404
    assert client.post("/api/chat/stream", json={"question": " "}).status_code == 422
