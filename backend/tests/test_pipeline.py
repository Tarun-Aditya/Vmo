"""The folder pipeline: pick up new or changed documents, link parents, stay idempotent, isolate failures,
and the scheduler's due-logic."""
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app import pipeline, scheduler
from app.db import SessionLocal

MSA = """<!-- page: 1 -->
# Master Services Agreement – Testco

**Parties:** Arcadia Retail Inc. (the "Customer") and Testco Inc (the "Supplier")
**Effective Date:** 1 October 2026
**Document Type:** MSA

## 1. Term
This Agreement commences on 1 October 2026 and, unless terminated earlier in accordance with its terms, expires on 1 October 2028.

## 2. Payment
The Customer shall pay undisputed invoices within {days} days of receipt of a valid invoice. Late payment interest shall not exceed 1% per month.

## 3. Limitation of Liability
Each party's liability under this Agreement is unlimited, including liability for indirect and consequential losses.
"""
SOW = """# SOW 1 – Testco Platform

**Parties:** Arcadia Retail Inc. (the "Customer") and Testco Inc (the "Supplier")
**Effective Date:** 1 November 2026
**Document Type:** SOW

## 1. Master Agreement Reference
This SOW is issued under the Master Services Agreement dated 1 October 2026 between the parties (Master Services Agreement – Testco). Capitalised terms have the meaning given in that agreement.

## 2. Term
This SOW commences on 1 November 2026 and, unless terminated earlier in accordance with its terms, expires on 1 November 2027.

## 3. Fees
The annual fees under this SOW are USD 1,200,000 and the total contract value is USD 1,200,000, exclusive of applicable taxes.
"""


def rows(sql, **p):
    with SessionLocal() as s:
        return [dict(r) for r in s.execute(text(sql), p).mappings().all()]


def test_new_documents_are_ingested_and_parents_linked_in_any_order(tmp_inbox):
    (tmp_inbox / "a_sow.md").write_text(SOW)                      # child arrives before its parent
    (tmp_inbox / "b_msa.md").write_text(MSA.format(days=20))
    res = pipeline.run_pipeline("manual")
    assert res["status"] == "completed" and res["new_docs"] == 2 and res["failed"] == 0
    c = {r["type"]: r for r in rows("SELECT * FROM contracts WHERE source_path LIKE 'pytest/%'")}
    assert c["MSA"]["vendor"] == "Testco Inc" and c["MSA"]["payment_terms_days"] == 20 and c["MSA"]["liability_cap_text"] == "Unlimited"
    assert c["SOW"]["parent_id"] == c["MSA"]["id"] and float(c["SOW"]["annual_value"]) == 1_200_000 and c["SOW"]["currency"] == "USD"
    # everything derived lands in the shared tables: clauses, fields, values, checklist, redline
    cid = c["MSA"]["id"]
    assert rows("SELECT count(*) AS n FROM clauses WHERE contract_id=:c", c=cid)[0]["n"] == 3
    assert rows("SELECT value_num FROM extracted_values WHERE contract_id=:c AND metric_key='payment_terms_days'", c=cid)[0]["value_num"] == 20
    fails = {r["rule_key"] for r in rows("SELECT rule_key FROM check_results WHERE contract_id=:c AND status='fail'", c=cid)}
    assert {"payment_terms_min", "no_unlimited_liability", "executed"} <= fails
    assert rows("SELECT 1 FROM redlines WHERE contract_id=:c", c=cid)


def test_rerun_is_idempotent_and_a_changed_file_is_updated(tmp_inbox):
    f = tmp_inbox / "msa.md"
    f.write_text(MSA.format(days=20))
    assert pipeline.run_pipeline("manual")["new_docs"] == 1
    again = pipeline.run_pipeline("manual")
    assert (again["new_docs"], again["updated"], again["unchanged"]) == (0, 0, 1)
    cid = rows("SELECT id FROM contracts WHERE source_path='pytest/msa.md'")[0]["id"]
    f.write_text(MSA.format(days=60))                              # the vendor sent a revised version
    upd = pipeline.run_pipeline("manual")
    assert (upd["new_docs"], upd["updated"]) == (0, 1)
    row = rows("SELECT id, payment_terms_days FROM contracts WHERE source_path='pytest/msa.md'")[0]
    assert row["id"] == cid and row["payment_terms_days"] == 60    # same record, new content
    st = {r["rule_key"]: r["status"] for r in rows("SELECT rule_key, status FROM check_results WHERE contract_id=:c", c=cid)}
    assert st["payment_terms_min"] == "pass" and st["payment_terms_target"] == "pass"
    assert rows("SELECT count(*) AS n FROM clauses WHERE contract_id=:c", c=cid)[0]["n"] == 3   # no duplicate clauses


def test_sidecar_sets_category_owner_and_draft_status(tmp_inbox):
    (tmp_inbox / "d.md").write_text(MSA.format(days=45))
    (tmp_inbox / "d.meta.json").write_text(json.dumps({"category": "Cloud", "owner": "Sam Ortiz", "status": "draft"}))
    pipeline.run_pipeline("upload")
    r = rows("SELECT category, owner, status FROM contracts WHERE source_path='pytest/d.md'")[0]
    assert (r["category"], r["owner"], r["status"]) == ("Cloud", "Sam Ortiz", "draft")
    assert not rows("SELECT 1 FROM check_results WHERE contract_id=(SELECT id FROM contracts WHERE source_path='pytest/d.md') AND rule_key='executed'")  # post-sign rule skipped for drafts


def test_one_bad_document_does_not_stop_the_run(tmp_inbox, monkeypatch):
    (tmp_inbox / "good.md").write_text(MSA.format(days=45))
    (tmp_inbox / "bad.md").write_text(MSA.format(days=45))
    real = pipeline.ingest_file

    def flaky(s, path, root, cfg, *a, **k):
        if path.name == "bad.md":
            raise ValueError("boom")
        return real(s, path, root, cfg, *a, **k)

    monkeypatch.setattr(pipeline, "ingest_file", flaky)
    res = pipeline.run_pipeline("manual")
    assert (res["new_docs"], res["failed"]) == (1, 1)
    ev = rows("SELECT action, detail FROM pipeline_events WHERE run_id=:r AND action='failed'", r=res["run_id"])
    assert ev and "boom" in ev[0]["detail"]


def test_only_one_run_at_a_time(seeded):
    assert pipeline._lock.acquire(blocking=False)
    try:
        assert pipeline.run_pipeline("manual")["status"] == "busy"
    finally:
        pipeline._lock.release()


def test_scheduler_due_logic_follows_frequency_and_pause(seeded):
    with SessionLocal() as s:
        saved = s.execute(text("SELECT enabled, interval_minutes, last_run_at, next_run_at FROM pipeline_config WHERE key='contracts'")).first()
    try:
        def put(**kw):
            with SessionLocal() as s:
                s.execute(text("UPDATE pipeline_config SET enabled=:e, next_run_at=:n WHERE key='contracts'"), kw)
                s.commit()

        now = datetime.now(timezone.utc)
        put(e=True, n=now - timedelta(minutes=1))
        assert scheduler.due() is True                              # next run has passed
        put(e=True, n=now + timedelta(hours=2))
        assert scheduler.due() is False                             # not yet
        put(e=False, n=now - timedelta(minutes=1))
        assert scheduler.due() is False                             # paused
        with SessionLocal() as s:                                   # changing the frequency recomputes the next run
            scheduler.set_interval(s, 15, True)
            s.commit()
            row = s.execute(text("SELECT interval_minutes, next_run_at, last_run_at FROM pipeline_config WHERE key='contracts'")).first()
        assert row[0] == 15 and abs((row[1] - row[2]) - timedelta(minutes=15)) < timedelta(seconds=2)
    finally:
        with SessionLocal() as s:
            s.execute(text("UPDATE pipeline_config SET enabled=:a, interval_minutes=:b, last_run_at=:c, next_run_at=:d WHERE key='contracts'"),
                      dict(a=saved[0], b=saved[1], c=saved[2], d=saved[3]))
            s.commit()


def test_files_are_identified_by_content_hash_not_by_name_and_every_run_is_audited(tmp_inbox):
    f = tmp_inbox / "msa.md"
    f.write_text(MSA.format(days=20))
    first = pipeline.run_pipeline("manual")
    cid = rows("SELECT id FROM contracts WHERE source_path='pytest/msa.md'")[0]["id"]
    ev = rows("SELECT action, content_hash, size_bytes, reason FROM pipeline_events WHERE run_id=:r", r=first["run_id"])[0]
    assert ev["action"] == "new" and len(ev["content_hash"]) == 64 and ev["size_bytes"] > 0
    f.rename(tmp_inbox / "renamed_msa.md")                                       # same bytes, new name: nothing is re-extracted
    moved = pipeline.run_pipeline("manual")
    assert (moved["new_docs"], moved["updated"]) == (0, 0)
    e = rows("SELECT action, content_hash, reason FROM pipeline_events WHERE run_id=:r", r=moved["run_id"])[0]
    assert e["action"] == "moved" and e["content_hash"] == ev["content_hash"] and "renamed from pytest/msa.md" in e["reason"]
    assert rows("SELECT source_path FROM contracts WHERE id=:c", c=cid)[0]["source_path"] == "pytest/renamed_msa.md"
    (tmp_inbox / "copy_of_msa.md").write_text(MSA.format(days=20))               # an identical copy is skipped, not ingested twice
    dup = pipeline.run_pipeline("manual")
    assert dup["new_docs"] == 0 and rows("SELECT count(*) AS n FROM contracts WHERE content_hash=:h", h=ev["content_hash"])[0]["n"] == 1
    skipped = {r["path"]: r for r in rows("SELECT path, action, reason FROM pipeline_events WHERE run_id=:r", r=dup["run_id"])}
    assert all(v["action"] == "unchanged" for v in skipped.values()) and any("duplicate of" in (v["reason"] or "") for v in skipped.values())
