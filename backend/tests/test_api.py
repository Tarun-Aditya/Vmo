"""API tests against the seeded database (skipped when no DB / not seeded)."""
from sqlalchemy import text

from app.db import SessionLocal

ACC = "Accentia Technology Services Inc"


def _long(client, cid):
    import datetime as dt

    d = dt.date.fromisoformat(client.get(f"/api/contracts/{cid}").json()["contract"]["effective_date"])
    return f"{d.day} {d:%B %Y}"


def by_title(client):
    return {r["title"]: r for r in client.get("/api/contracts").json()}


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "db": "ok", "pgvector": "ok"}


def test_documents_include_drafts_and_filters_work(client):
    rows = client.get("/api/contracts").json()
    assert len(rows) == 32 and sum(r["status"] == "draft" for r in rows) == 5
    assert {c["type"] for c in client.get("/api/contracts?category=SaaS").json()} == {"SaaS", "DPA"}
    assert len(client.get("/api/contracts?status=draft").json()) == 5
    docs = client.get("/api/documents").json()
    assert len(docs) == 32 and docs[-1]["status"] == "draft"                     # drafts listed last
    assert [d["vendor"] for d in client.get("/api/documents?search=nginova").json()] == ["Nginova Systems Inc"]


def test_detail_shows_amendment_provenance_values_and_checks(client):
    msa = client.get("/api/contracts?type=MSA&search=Accentia").json()[0]
    d = client.get(f"/api/contracts/{msa['id']}").json()
    pay = next(e for e in d["effective_terms"] if e["field"] == "payment_terms_days")
    assert pay["value"] == 30 and pay["overridden"] and "Amendment" in pay["source_title"]
    assert {c["type"] for c in d["hierarchy"]["children"]} == {"SOW", "Amendment", "NDA"}
    assert any(v["metric_key"] == "insurance_cover_usd" and float(v["value_num"]) == 5_000_000 for v in d["values"])
    assert any(c["rule_key"] == "governing_law_ny" and c["status"] == "pass" for c in d["checks"])
    assert all(f["confidence"] is not None for f in d["fields"])


def test_dashboard_matches_planted_facts(client):
    d = client.get("/api/dashboard").json()
    k = d["kpis"]
    assert k["contracts"] == 27 and k["uncapped"] == 3 and k["autorenew_notice_soon"] == 2 and k["expiring_90"] == 8
    assert float(k["annual_value"]) == 38_070_000                                    # drafts are not counted
    counts = {n: v["count"] for n, v in d["lanes"].items()}
    assert counts["30"] == 4 and sum(counts.values()) == k["expiring_90"] == 8               # how the later ones split between 60 and 90 days moves as the seed date ages
    adspark = next(i for i in d["lanes"]["30"]["items"] if "AdSpark" in i["title"])
    assert adspark["notice_passed"] and adspark["auto_renew"] and len(d["monthly"]) == 12


def test_sql_guard(client):
    from app.ask import run_sql

    assert "error" in run_sql("DELETE FROM contracts") and "error" in run_sql("SELECT 1; SELECT 2")
    assert "error" in run_sql("SELECT embedding FROM clauses")              # column revoked from the read-only role
    assert "error" in run_sql("SELECT * FROM pipeline_runs")                # admin tables are not readable either
    assert run_sql("SELECT count(*) AS n FROM v_checks WHERE result = 'fail'")["rows"][0][0] > 0


def test_redline_unifies_drafts_checklist_and_template_changes(client):
    docs = client.get("/api/redline/documents").json()
    drafts = {d["title"][:18]: d for d in docs if d["status"] == "draft"}
    assert [d["status"] for d in docs[:5]] == ["draft"] * 5                          # drafts first
    assert sorted(d["deviations"] for d in drafts.values()) == [0, 3, 4, 5, 6]
    clean = next(d for d in docs if "clean control" in d["title"])
    assert clean["deviations"] == 0 and clean["checks_failed"] == 0
    quanta = next(d for d in docs if "Quanta" in d["title"])
    r = client.get(f"/api/redline/{quanta['id']}").json()
    failing = {c["rule_key"]: c for c in r["checklist"] if c["status"] == "fail"}
    assert {"sla_min", "incident_notice_max", "no_discretionary_processing"} <= set(failing)
    assert failing["incident_notice_max"]["actual"] == "168 hours" and failing["incident_notice_max"]["expected"] == "≤ 72 hours"
    assert failing["sla_min"]["suggested_text"] and r["checklist_summary"]["fail"] == len(failing)
    assert any(i["status"] == "missing" and i["clause_type"] == "data_return" for i in r["items"])
    again = client.post(f"/api/redline/{quanta['id']}/rerun").json()                 # recompute on demand
    assert again["source"] in ("heuristic", "llm") and len(again["items"]) == len(r["items"])


def test_templates_heatmap_ignores_drafts(client):
    saas = next(t for t in client.get("/api/templates").json() if t["type"] == "SaaS")
    assert saas["contracts"] == 5 and saas["deviating_contracts"] == 5
    m = client.get(f"/api/templates/{saas['id']}").json()
    assert len(m["matrix"]) == 5 and any(c for r in m["matrix"] for c in r["cells"].values())


def test_hierarchy_msa_sow_work_order_and_signatures(client):
    rows = client.get("/api/contracts").json()
    by_id = {r["id"]: r for r in rows}
    wos = [r for r in rows if r["type"] == "Work Order"]
    assert len(wos) == 4
    for wo in wos:
        sow = by_id[wo["parent_id"]]
        assert sow["type"] == "SOW" and by_id[sow["parent_id"]]["type"] == "MSA"
    wo2 = by_title(client)["Work Order 2 – Endpoint Security Hardening – Accentia Technology Services"]
    assert not wo2["fully_executed"] and wo2["supplier_signatory"] is None
    sig = client.get(f"/api/contracts/{wo2['id']}").json()["signatures"]
    assert sig["customer_signatory"] == "Michael Brennan" and sig["supplier_signed_date"] is None
    assert sum(1 for r in rows if not r["fully_executed"] and r["status"] != "draft") == 1


def test_clause_matrix_ticks_crosses_citations_and_drafts(client):
    m = client.get("/api/clause-matrix").json()
    assert len(m["columns"]) == 23 and [len(g["rows"]) for g in m["groups"]] == [25, 5]
    exe = {r["title"]: r for r in m["groups"][0]["rows"]}
    msa = exe["Master Services Agreement – Accentia Technology Services"]["cells"]
    assert msa["liability_cap"]["present"] and msa["liability_cap"]["page"] == 4 and "liability" in msa["liability_cap"]["text"].lower()
    nda = exe["NDA – Delmont Consulting"]["cells"]["payment"]
    assert not nda["present"] and not nda["expected"] and "not part of the standard" in nda["note"]
    wo2 = exe["Work Order 2 – Endpoint Security Hardening – Accentia Technology Services"]["cells"]["execution"]
    assert not wo2["present"] and "Not fully signed" in wo2["note"]
    quanta = next(r for r in m["groups"][1]["rows"] if "Quanta" in r["title"])["cells"]["data_return"]
    assert not quanta["present"] and quanta["expected"] and "gap" in quanta["note"]
    only = client.get("/api/clause-matrix", params={"vendor": ACC}).json()
    assert [len(g["rows"]) for g in only["groups"]] == [7, 0]


def test_vendors_list_profile_and_risk(client):
    v = {x["vendor"]: x for x in client.get("/api/vendors").json()}
    assert len(v) == 9
    acc, dl = v[ACC], v["Delmont Consulting LLP"]
    assert (acc["documents"], acc["contracts"]) == (8, 7) and acc["annual_value"] == 18_700_000 and acc["work_order_value"] == 1_950_000
    assert dl["risk"] in ("high", "critical") and dl["risk_score"] > 30 and any(f["key"] == "uncapped" for f in dl["flags"])
    assert any(f["key"] == "pd_no_dpa" for f in v["PulseHR Inc"]["flags"])
    assert any(f["key"] == "notice_passed" for f in v["AdSpark Analytics LLP"]["flags"])
    p = client.get(f"/api/vendors/{ACC}").json()
    assert len(p["documents"]) == 8 and p["summary"]["unsigned"] == 1 and len(p["upcoming"]) == 7
    assert any(d["heading"] == "Key Personnel" for d in p["deviations"])
    assert client.get("/api/vendors/No Such Vendor").status_code == 404


def test_sow_and_work_order_inherit_from_msa(client):
    rows = by_title(client)
    wo = client.get(f"/api/contracts/{rows['Work Order 1 – Data Center Exit Wave 2 – Accentia Technology Services']['id']}").json()
    assert [x["type"] for x in wo["lineage"]] == ["MSA", "SOW"]
    cap = next(t for t in wo["inherited_terms"] if t["label"] == "Liability cap")
    assert cap["value"] == 2.0 and "Amendment" in cap["source_title"]               # inherits the AMENDED value
    sow = client.get(f"/api/contracts/{rows['SOW 1 – SAP S/4HANA Transformation, Phase 1 – Delmont Consulting']['id']}").json()
    assert sow["inherited_terms"][0]["value"] == "Unlimited"
    assert any(d["clause_type"] == "order_of_precedence" and d["severity"] == "high" for d in sow["deviations"])


# ----------------------------------------------------------------------------- admin
def test_pipeline_status_and_frequency_config(client):
    st = client.get("/api/status").json()
    assert st["documents"] == {"active": 27, "draft": 5} and st["running"] is False
    saved = client.get("/api/admin/pipeline").json()["config"]
    try:
        r = client.put("/api/admin/pipeline", json={"enabled": True, "interval_minutes": 30}).json()
        assert r["config"]["interval_minutes"] == 30 and r["inbox_files"] >= 32
        assert client.put("/api/admin/pipeline", json={"enabled": True, "interval_minutes": 0}).status_code == 422
    finally:
        client.put("/api/admin/pipeline", json={"enabled": saved["enabled"], "interval_minutes": saved["interval_minutes"]})
    runs = client.get("/api/admin/pipeline/runs").json()
    assert runs and any(client.get(f"/api/admin/pipeline/runs/{r['id']}/events").json() for r in runs)   # at least one recent run lists its files


def test_upload_document_is_picked_up_everywhere(client, clean_docs):
    doc = """# NDA – Upload Test Co

**Parties:** Arcadia Retail Inc. (the "Customer") and Upload Test Co Inc (the "Supplier")
**Effective Date:** 1 December 2026
**Document Type:** NDA

## 1. Confidentiality
Each party shall keep the other party's Confidential Information confidential, use it only for the purposes of this NDA, and continue to do so for 1 year after the NDA ends.
"""
    r = client.post("/api/admin/pipeline/upload", json={"filename": "upload-test.md", "content": doc, "category": "Legal"}).json()
    assert r["run"]["new_docs"] == 1
    row = next(c for c in client.get("/api/contracts").json() if c["vendor"] == "Upload Test Co Inc")
    d = client.get(f"/api/contracts/{row['id']}").json()
    assert any(c["rule_key"] == "confidentiality_min_years" and c["status"] == "fail" for c in d["checks"])
    assert any(v["metric_key"] == "confidentiality_years" and float(v["value_num"]) == 1 for v in d["values"])
    assert any(x["vendor"] == "Upload Test Co Inc" for x in client.get("/api/vendors").json())
    assert client.post("/api/admin/pipeline/upload", json={"filename": "x.md", "content": "  "}).status_code == 422


def test_kcc_library_add_edit_delete_changes_the_matrix_everywhere(client, seeded):
    body = {"name": "Price Parity", "keywords": ["price parity", "most favou?red"], "heading_aliases": ["Price Parity"], "severity_if_missing": "low", "applies_to": ["MSA"]}
    try:
        r = client.post("/api/admin/kcc", json=body)
        assert r.status_code == 200 and r.json()["key"] == "price_parity" and r.json()["reprocessed"] == 32
        assert client.post("/api/admin/kcc", json=body).status_code == 409
        assert len(client.get("/api/clause-matrix").json()["columns"]) == 24      # new column on the Key clauses page
        with __import__("app.db", fromlist=["engine"]).engine.connect() as c:    # ...and in the SQL the Ask assistant uses
            assert c.execute(text("SELECT count(*) FROM information_schema.columns WHERE table_name='v_key_clauses' AND column_name='has_price_parity'")).scalar() == 1
        client.put("/api/admin/kcc/price_parity", json={**body, "in_matrix": False})
        assert len(client.get("/api/clause-matrix").json()["columns"]) == 23
    finally:
        assert client.delete("/api/admin/kcc/price_parity").status_code in (200, 404)
    assert len(client.get("/api/clause-matrix").json()["columns"]) == 23
    assert client.delete("/api/admin/kcc/payment").status_code == 409                 # built-ins can only be disabled


def test_kcc_test_preview_finds_matching_clauses(client):
    r = client.post("/api/admin/kcc/test", json={"keywords": ["force majeure|beyond its reasonable control"], "heading_aliases": []}).json()
    assert r["clauses"] >= 3 and r["documents"] >= 3 and r["examples"][0]["matched_by"].startswith("keyword")
    assert client.post("/api/admin/kcc/test", json={"keywords": ["(unclosed"], "heading_aliases": []}).json()["clauses"] == 0   # bad regex ignored


def test_values_and_limits_custom_metric_and_rule_flow(client, seeded):
    m = {"name": "Late fee percent", "kcc_key": "payment", "pattern": r"not exceed (\d+)% per month", "kind": "number", "unit": "%"}
    try:
        assert client.post("/api/admin/metrics", json={**m, "pattern": "(bad"}).status_code == 422
        pre = client.post("/api/admin/metrics/test", json=m).json()
        assert pre["matches"] >= 20                                                  # preview before saving
        assert client.post("/api/admin/metrics", json=m).status_code == 200
        rule = {"name": "Late fee at most 1%", "rule_type": "metric_threshold", "metric_key": "late_fee_percent", "operator": "<=", "threshold": 1, "severity": "low", "applies_to": ["MSA", "SOW"]}
        assert client.post("/api/admin/rules", json=rule).status_code == 200
        res = {r["key"]: r for r in client.get("/api/admin/rules").json()}["late_fee_at_most_1"]["results"]
        assert res.get("pass", 0) > 0 and res.get("fail", 0) == 0
        msa = next(c for c in client.get("/api/contracts?type=MSA").json())
        d = client.get(f"/api/contracts/{msa['id']}").json()
        assert any(v["metric_key"] == "late_fee_percent" for v in d["values"])       # shown on the contract
        assert client.post("/api/admin/rules", json={**rule, "name": "x", "operator": "!="}).status_code == 422
        assert client.post("/api/admin/rules", json={"name": "y", "rule_type": "text_forbidden", "phrase": "(bad"}).status_code == 422
    finally:
        client.delete("/api/admin/rules/late_fee_at_most_1")
        client.delete("/api/admin/metrics/late_fee_percent")
    assert "late_fee_percent" not in {m["key"] for m in client.get("/api/admin/metrics").json()}


def test_editing_a_threshold_rechecks_every_document(client, seeded):
    rules = {r["key"]: r for r in client.get("/api/admin/rules").json()}
    r = rules["payment_terms_target"]
    fails_before = r["results"].get("fail", 0)
    try:
        client.put("/api/admin/rules/payment_terms_target", json={**r, "threshold": 60})
        after = {x["key"]: x for x in client.get("/api/admin/rules").json()}["payment_terms_target"]["results"]
        assert after["fail"] > fails_before                                          # stricter limit, more failures
    finally:
        client.put("/api/admin/rules/payment_terms_target", json=r)
    back = {x["key"]: x for x in client.get("/api/admin/rules").json()}["payment_terms_target"]["results"]
    assert back.get("fail", 0) == fails_before


# ----------------------------------------------------------------------------- generator
def test_new_contract_from_template_preview_edit_create(client, clean_docs):
    forms = client.get("/api/generator/forms").json()
    assert [f["template"] for f in forms["forms"]] == ["MSA", "SOW", "WO", "NDA", "SaaS", "DPA"] and ACC in forms["vendors"]
    msa = next(p for p in forms["parents"] if p["type"] == "MSA" and p["vendor"] == ACC)
    params = {"vendor": ACC, "parent_id": msa["id"], "scope": "Retail analytics platform build", "annual_fees": 1_800_000, "term_months": 12,
              "payment_terms_days": 20, "effective_date": "2026-12-01"}
    pre = client.post("/api/generator/preview", json={"template": "SOW", "params": params}).json()
    assert f"issued under the Master Services Agreement dated {_long(client, msa['id'])}" in pre["md"] and "USD 1,800,000" in pre["md"]
    fails = {c["rule_key"] for c in pre["analysis"]["checks"] if c["status"] == "fail"}
    assert fails == {"payment_terms_min", "payment_terms_target"}                    # 20 days breaks the payment policy
    fixed = pre["md"].replace("within 20 days", "within 45 days")                    # the user edits the text, re-checks
    ok = client.post("/api/generator/analyze", json={"template": "SOW", "md": fixed}).json()
    assert ok["summary"]["fail"] == 0 and ok["summary"]["pass"] >= 10
    made = client.post("/api/generator/create", json={"template": "SOW", "params": params, "md": fixed}).json()
    assert made["status"] == "created" and made["failed_checks"] == []
    d = client.get(f"/api/contracts/{made['contract_id']}").json()
    assert d["contract"]["status"] == "draft" and d["contract"]["origin"] == "generated" and d["parent"]["id"] == msa["id"]
    assert float(d["contract"]["annual_value"]) == 1_800_000
    assert any(x["id"] == made["contract_id"] for x in client.get("/api/redline/documents").json())     # appears in Redline
    assert client.post("/api/generator/preview", json={"template": "SOW", "params": {}}).status_code == 422   # vendor required


def test_a_clause_added_in_admin_is_found_on_the_next_run_even_without_its_own_heading(client, seeded):
    """Add a key clause with keywords, the pipeline re-runs over every document, and a sentence buried under an unrelated heading is identified."""
    from app import pipeline

    cid = client.post("/api/redline/upload", json={"filename": "residency_demo.md", "owner": "Legal", "category": "Legal", "content":
                      "# Services Agreement – Residency Demo\n\n**Parties:** Arcadia Retail Inc. (the \"Customer\") and Residency Demo Inc (the \"Supplier\")\n\n## Payment\nThe Customer shall pay undisputed invoices within 30 days of receipt of a valid invoice. The Supplier shall keep all Customer Data stored in the European Union.\n"}).json()["contract_id"]
    body = {"name": "Data Residency", "keywords": ["stored in the european union", "data residency"], "heading_aliases": ["Data Residency"], "severity_if_missing": "medium", "applies_to": ["MSA", "SOW", "SaaS", "NDA"]}
    try:
        before = [c for c in client.get(f"/api/contracts/{cid}").json()["clauses"] if c["clause_type"] == "data_residency"]
        assert before == []
        assert client.post("/api/admin/kcc", json=body).status_code == 200                       # saving re-runs the pipeline over all documents
        found = [c for c in client.get(f"/api/contracts/{cid}").json()["clauses"] if c["clause_type"] == "data_residency"]
        assert found and "European Union" in found[0]["text"] and "found in text" in found[0]["heading"]
        with SessionLocal() as s:
            assert s.execute(text("SELECT has_data_residency FROM v_key_clauses WHERE contract_id=:c"), {"c": cid}).scalar() is True
    finally:
        client.delete("/api/admin/kcc/data_residency")
        with SessionLocal() as s:
            root = pipeline.inbox_path(s)
            s.execute(text("DELETE FROM contracts WHERE vendor ILIKE '%Residency Demo%'"))
            s.commit()
        for f in list(root.rglob("residency_demo*")):
            f.unlink()


def test_a_clause_added_in_admin_is_checked_in_redlines_with_suggested_wording(client, seeded):
    """A draft that lacks the new clause gets a redline item with the admin's standard wording, and the checklist rule fails; a draft that has it does not."""

    std = "All Customer Data shall be stored and processed only within the European Union."
    mk = lambda name, extra: client.post("/api/redline/upload", json={"filename": name, "owner": "Legal", "category": "Legal", "content":
        f"# Services Agreement – {name}\n\n**Parties:** Arcadia Retail Inc. (the \"Customer\") and {name} Inc (the \"Supplier\")\n\n## Payment\nThe Customer shall pay undisputed invoices within 30 days of receipt of a valid invoice.\n{extra}"}).json()["contract_id"]
    body = {"name": "Data Residency", "keywords": ["stored in the european union", "data residency"], "heading_aliases": ["Data Residency"], "standard_text": std,
            "playbook_position": "Customer Data stays in the EU.", "severity_if_missing": "high", "applies_to": ["MSA", "SOW", "SaaS", "NDA", "Services"]}
    try:
        without, has = mk("ResidencyNone", ""), mk("ResidencyHas", f"\n## Data Residency\n{std}\n")
        assert client.post("/api/admin/kcc", json=body).status_code == 200
        items = lambda cid: {i["clause_type"]: i for i in client.get(f"/api/redline/{cid}").json()["items"]}
        miss = items(without)["data_residency"]
        assert miss["status"] == "missing" and miss["severity"] == "high" and miss["suggested_text"] == std
        assert "data_residency" not in items(has)
    finally:
        client.delete("/api/admin/kcc/data_residency")
        with SessionLocal() as s:
            s.execute(text("DELETE FROM contracts WHERE vendor ILIKE 'Residency%'"))
            s.commit()


def test_claude_tags_a_custom_clause_in_any_wording_and_the_matrix_cites_it(client, seeded, monkeypatch):
    """With Claude available, a passage that no keyword matches is tagged (quote verified against the text, cached by hash); the Key clauses matrix shows it with a citation."""
    from app import llm

    calls = []

    def fake(purpose, model, system, user, tool, **kw):
        calls.append(purpose)
        i = next(int(x.split("]")[0]) for x in user.split("[")[1:] if "Hosting" in x)
        return {"matches": [{"key": "data_residency", "clause_index": i, "quote": "Our servers never leave the Union."},      # hallucinated: not in the clause
                            ]} if len(calls) == 1 else {"matches": []}

    cid = client.post("/api/redline/upload", json={"filename": "ai_tag.md", "owner": "Legal", "category": "Legal", "content":
        "# Services Agreement – Aitag\n\n**Parties:** Arcadia Retail Inc. (the \"Customer\") and Aitag Inc (the \"Supplier\")\n\n## Hosting\nCustomer records remain on infrastructure located inside the member states of the EU at all times.\n"}).json()["contract_id"]
    body = {"name": "Data Residency", "description": "Where customer data must be stored", "keywords": ["no-such-keyword"], "heading_aliases": ["Data Residency"], "severity_if_missing": "medium", "applies_to": ["Services", "MSA", "SOW", "SaaS", "NDA"]}
    with SessionLocal() as s:
        s.execute(text("DELETE FROM kcc_ai_cache"))
        s.commit()
    try:
        import types

        from app import kcc_ai
        shim = types.SimpleNamespace(available=lambda: True, call_tool=fake, prompt=llm.prompt, note_failure=llm.note_failure)    # Claude stands in for kcc tagging only
        monkeypatch.setattr(kcc_ai, "llm", shim)
        client.post("/api/admin/kcc", json=body)
        assert not [c for c in client.get(f"/api/contracts/{cid}").json()["clauses"] if c["clause_type"] == "data_residency"]      # the invented quote was rejected
        def good(purpose, model, system, user, tool, **kw):
            calls.append(purpose)
            i = next((int(x.split("]")[0]) for x in user.split("[")[1:] if "Hosting" in x), None)
            return {"matches": [] if i is None else [{"key": "data_residency", "clause_index": i, "quote": "Customer records remain on infrastructure located inside the member states of the EU at all times."}]}
        shim.call_tool = good
        with SessionLocal() as s:
            s.execute(text("DELETE FROM kcc_ai_cache"))
            s.commit()
        assert client.put("/api/admin/kcc/data_residency", json=body).status_code == 200
        tagged = [c for c in client.get(f"/api/contracts/{cid}").json()["clauses"] if c["clause_type"] == "data_residency"]
        assert tagged and "AI-tagged" in tagged[0]["heading"] and "member states" in tagged[0]["text"]
        n = calls.count("kcc_tag")
        client.put("/api/admin/kcc/data_residency", json=body)                       # same document + same definition: answered from the cache
        assert calls.count("kcc_tag") == n
        m = client.get("/api/clause-matrix").json()
        row = next(r for g in m["groups"] for r in g["rows"] if r["id"] == cid)
        cell = row["cells"]["data_residency"]
        assert cell["present"] and cell["page"] and "member states" in cell["text"] and "data_residency" in [c["key"] for c in m["columns"]]
    finally:
        client.delete("/api/admin/kcc/data_residency")
        with SessionLocal() as s:
            s.execute(text("DELETE FROM kcc_ai_cache"))
            s.execute(text("DELETE FROM contracts WHERE vendor ILIKE 'Aitag%'"))
            s.commit()


def test_demo_mode_switch_turns_claude_off_everywhere_and_back(client, seeded, monkeypatch):
    """Demo ON: provider offline whatever is configured. Demo OFF: the configured backend (Claude) is used by every module."""
    from app import llm, mode
    from app.config import settings

    monkeypatch.setattr(settings, "llm_provider", "api")
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-test")
    try:
        assert client.put("/api/admin/mode", json={"demo": False}).json()["engine"] == "api"
        m = client.get("/api/meta").json()
        assert m["demo_mode"] is False and m["llm_provider"] == "api" and llm.available()
        r = client.put("/api/admin/mode", json={"demo": True}).json()
        assert r["demo_mode"] is True and r["engine"] == "offline"
        m = client.get("/api/meta").json()
        assert m["demo_mode"] is True and m["llm_provider"] == "offline" and not llm.available()
    finally:
        mode.set_demo(False)
