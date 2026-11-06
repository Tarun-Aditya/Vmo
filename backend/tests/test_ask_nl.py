"""Offline planner: parsing and window maths need no DB; answers use the seeded database."""
import datetime as dt

import pytest
from sqlalchemy import text

from app import ask, ask_nl, kcc

CATS = ["IT Services", "SaaS", "Cloud", "Consulting", "ERP", "Security", "Software", "Staffing", "Marketing"]
VENDORS = ["Accentia Technology Services Inc", "Delmont Consulting LLP", "PulseHR Inc"]
OWNERS = ["Jordan Blake (IT Procurement)", "Sam Ortiz (Infrastructure)"]
TODAY = dt.date(2026, 11, 6)
CFG = (
    [{"key": k["key"], "name": k["name"], "keywords": k["keywords"], "heading_aliases": k["heading_aliases"]} for k in kcc.default_kcc() if k["in_matrix"]],
    [{"key": m["key"], "name": m["name"], "kind": m["kind"], "unit": m["unit"]} for m in kcc.default_metrics()],
    [{"key": r["key"], "name": r["name"]} for r in kcc.default_rules()],
)


def P(q, scope=None):
    return ask_nl.parse(q, TODAY, CATS, VENDORS, OWNERS, scope=scope, cfg=CFG)


def test_quarter_and_month_bounds():
    assert ask_nl._quarter_bounds(TODAY, 1) == (dt.date(2027, 1, 1), dt.date(2027, 3, 31))
    assert ask_nl._quarter_bounds(TODAY, 0) == (dt.date(2026, 10, 1), dt.date(2026, 12, 31))
    assert ask_nl._month_bounds(dt.date(2026, 12, 15), 1) == (dt.date(2027, 1, 1), dt.date(2027, 1, 31))


def test_parse_metric_window_group_and_vendor_level():
    p = P("How many contracts are expiring in the next quarter?")
    assert p["metric"] == "count" and p["win"]["start"] == dt.date(2027, 1, 1)
    assert P("total annual value of contracts by vendor")["group"] == "vendor"
    assert P("How many contracts expire in the next 90 days?")["win"]["end"] == TODAY + dt.timedelta(days=90)
    assert P("Which vendors have contracts expiring in the next 90 days?")["vendor_level"]


def test_filters_do_not_get_dropped_or_confused():
    p = P("How many contracts process personal data without a DPA?")
    assert "processes_personal_data AND NOT has_dpa" in p["where"] and not any(w.startswith("type IN") for w in p["where"])
    assert "has_dpa" in P("How many contracts have a DPA?")["where"]
    assert "type IN ('DPA')" in P("How many DPAs do we have?")["where"]
    assert ask_nl.subject_of(P("How many contracts are owned by Jordan?"), 4) == "contracts owned by Jordan"
    assert "vendor = 'Accentia Technology Services Inc'" in P("total annual value of Accentia contracts")["where"]
    assert "NOT has_insurance" in P("Which contracts do not have an insurance clause?")["where"]
    assert "NOT has_force_majeure" in P("contracts without a force majeure clause")["where"]
    assert "status = 'draft'" in P("Which drafts have unlimited liability?")["where"]


def test_threshold_and_checklist_parsing():
    w = " ".join(P("Which contracts have payment terms below 45 days?")["where"])
    assert "metric_key = 'payment_terms_days'" in w and "< 45" in w
    w = " ".join(P("Which MSAs have insurance cover per claim under $2 million?")["where"])
    assert "insurance_cover_usd" in w and "< 2e+06" in w
    p = P("Which contracts fail the checklist?")
    assert p["intent"] == "checks" and not p["only_pass"]
    assert P("Which critical checklist rules fail on drafts?")["severities"] == ["critical"]
    assert P("Which contracts fail the Payment terms ≥ 30 days rule?")["rule_hits"] == ["payment_terms_min"]


def test_unrecognised_questions_return_none_unless_scoped():
    assert P("Tell me a joke") is None and P("what is the weather") is None
    assert P("Can the supplier replace personnel freely?", scope=[4])["intent"] == "search"     # scoped: fall back to clause search


def test_scope_selects_the_answer_shape():
    assert P("Tell me about this contract", scope=[4])["intent"] == "card"
    assert P("What is the payment term?", scope=[4])["intent"] == "card"
    assert P("What does the indemnity clause say?", scope=[4])["intent"] == "doc_clauses"
    assert "contract_id IN (4, 9)" in P("Which clauses are missing?", scope=[4, 9])["where"]


# ----------------------------------------------------------------------------- answers (database)
@pytest.fixture
def offline(monkeypatch, seeded):
    monkeypatch.setattr("app.llm.available", lambda: False)


def ids():
    from app.db import SessionLocal

    with SessionLocal() as s:
        return {r[0]: r[1] for r in s.execute(text("select title, id from contracts"))}


def test_scripted_matching_is_not_greedy(offline):
    r = ask.answer("What is the total annual value of SaaS contracts?", False)
    assert r["source"] == "offline-planner" and "$2.17M" in r["answer"]


def test_aggregate_answer_has_headline_breakdown_and_list(offline):
    r = ask.answer("How many auto-renewing contracts do we have and what is their total annual value?", False)
    assert r["answer"].startswith("5 auto-renewing contracts") and "$" in r["answer"]
    assert [c["name"] for c in r["tool_calls"]] == ["run_sql"] * 3 and r["tool_calls"][0]["output"]["rows"][0][0] == 5
    assert [t["label"] for t in r["tiles"]] == ["Contracts", "Annual value"]
    assert [t["title"] for t in r["tables"]] == ["Breakdown by category", "Contracts"] and len(r["tables"][1]["rows"]) == 5
    assert r["thinking"][0]["title"] == "Understood the question" and "sql" in r["thinking"][1]


def test_table_questions_pick_the_requested_columns(offline):
    r = ask.answer("Show start date, end date and signatures for all contracts", False)
    t = r["tables"][0]
    assert [c["label"] for c in t["columns"]] == ["Contract", "Type", "Start date", "End date", "Signed by (Arcadia)", "Arcadia signed on",
                                                   "Signed by (Supplier)", "Supplier signed on", "Fully signed"]
    assert len(t["rows"]) == 25 and t["columns"][-1]["kind"] == "bool" and t["columns"][2]["kind"] == "date" and not r["tiles"]


def test_signature_clause_and_draft_filters(offline):
    r = ask.answer("Which contracts are not fully signed?", False)
    assert [x["title"] for x in r["tables"][0]["rows"]] == ["Work Order 2 – Endpoint Security Hardening – Accentia Technology Services"]
    r = ask.answer("Which contracts do not have an audit rights clause?", False)
    assert "without an audit rights clause" in r["answer"] and all(x["has_audit_rights"] is False for x in r["tables"][0]["rows"])
    r = ask.answer("Which draft contracts have unlimited liability?", False)
    assert [x["title"] for x in r["tables"][0]["rows"]] == []   or "Orbitline" in r["tables"][0]["rows"][0]["title"]


def test_values_and_thresholds_are_askable(offline):
    r = ask.answer("What is the insurance cover per claim for each MSA?", False)
    t = r["tables"][0]
    assert [c["label"] for c in t["columns"]] == ["Contract", "Type", "Insurance cover per claim"] and t["columns"][2]["kind"] == "money"
    assert sorted(float(x["insurance_cover_usd"]) for x in t["rows"]) == [500_000, 5_000_000, 5_000_000]
    r = ask.answer("Which contracts have payment terms below 45 days?", False)
    assert {x["title"][:20] for x in r["tables"][0]["rows"]} == {"SOW 1 – SAP S/4HANA ", "Master Services Agre"} and "payment terms" in r["answer"]


def test_checklist_questions(offline):
    r = ask.answer("Which contracts fail the checklist?", False)
    assert [t["title"] for t in r["tables"]] == ["By severity", "Checklist results"] and r["tables"][1]["columns"][4]["kind"] == "severity"
    assert r["tables"][1]["rows"][0]["severity"] == "critical"
    r = ask.answer("Which draft contracts fail the checklist with critical severity?", False)
    assert {x["severity"] for x in r["tables"][1]["rows"]} == {"critical"} and all("Draft" in x["title"] for x in r["tables"][1]["rows"])


def test_single_document_question_returns_its_clauses(offline):
    r = ask.answer("Show the key clauses in the Accentia MSA", False)
    t = r["tables"][0]
    assert [c["label"] for c in t["columns"]] == ["Contract", "Clause", "Page", "Clause text"] and len(t["rows"]) == 21
    assert {x["title"] for x in t["rows"]} == {"Master Services Agreement – Accentia Technology Services"} and t["rows"][-1]["clause"] == "Execution"


def test_thinking_hides_sql_from_the_answer_but_keeps_it_inspectable(offline):
    r = ask.answer("Which vendors have uncapped liability?", False)
    assert "SELECT" not in r["answer"] and r["tables"][0]["columns"][0]["label"] == "Vendor"
    assert any(s.get("sql", "").startswith("SELECT") for s in r["thinking"]) and r["thinking"][-1]["title"] == "Composed the answer"


def test_vendor_level_questions(offline):
    r = ask.answer("How many vendors have contracts expiring in the next 90 days?", False)
    assert r["answer"].startswith("6 vendors with contracts expiring") and [t["label"] for t in r["tiles"]] == ["Contracts", "Vendors", "Annual value"]
    assert r["tables"][0]["title"] == "Vendors" and len(r["tables"][0]["rows"]) == 6


# ----------------------------------------------------------------------------- scope: specific documents
def test_scoped_fact_sheet_for_one_document(offline):
    msa = ids()["Master Services Agreement – Delmont Consulting"]
    r = ask.answer("Tell me about this contract", False, [msa])
    t = r["tables"][0]
    assert t["kv"] and r["scoped"] == 1 and r["source"] == "offline-planner"
    facts = {x["field"]: x["value"] for x in t["rows"]}
    assert facts["Governing law"] == "England and Wales" and facts["Liability cap"] == "Unlimited" and facts["Vendor"] == "Delmont Consulting LLP"
    assert float(facts["Insurance cover per claim"]) == 500_000
    r = ask.answer("What is the liability cap and governing law?", False, [msa])
    assert [x["field"] for x in r["tables"][0]["rows"]] == ["Contract", "Liability cap", "Liability cap multiple", "Governing law"]


def test_scoped_clause_text_and_semantic_fallback(offline):
    i = ids()
    r = ask.answer("What does the indemnity clause say?", False, [i["Master Services Agreement – Delmont Consulting"]])
    assert "The Customer shall indemnify the Supplier" in r["tables"][0]["rows"][0]["text"]
    sow = i["SOW 1 – Application Managed Services – Accentia Technology Services"]
    r = ask.answer("Can the supplier replace personnel freely?", False, [sow])
    top = r["tables"][-1]["rows"][0]
    assert top["heading"] == "Key Personnel" and "replace any personnel at any time" in top["text"] and {x["title"] for x in r["tables"][-1]["rows"]} == {top["title"]}


def test_scope_includes_drafts_and_never_leaks_other_documents(offline):
    i = ids()
    draft = i["Draft SaaS Agreement – Quanta Billing Cloud"]
    r = ask.answer("Which checklist rules does it fail?", False, [draft])
    assert {x["title"] for x in r["tables"][-1]["rows"]} == {"Draft SaaS Agreement – Quanta Billing Cloud"}
    both = ask.answer("Show start date, end date and signatures", False, [draft, i["NDA – Skyguard Security"]])
    assert {x["title"] for x in both["tables"][0]["rows"]} == {"Draft SaaS Agreement – Quanta Billing Cloud", "NDA – Skyguard Security"}
    from app.ask import execute_tool

    assert "outside the selected scope" in execute_tool("get_contract", {"id": 1}, scope=[draft])["error"]
    hits = execute_tool("search_clauses", {"query": "liability", "top_k": 15}, scope=[draft])["hits"]
    assert {h["contract_id"] for h in hits} == {draft}
