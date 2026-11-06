"""Offline aggregate-question planner: parsing and window maths need no DB; answers need the seed."""

import datetime as dt

import pytest
from sqlalchemy import text

from app import ask, ask_nl

CATS = [
    "IT Services",
    "SaaS",
    "Logistics",
    "Facilities",
    "Marketing",
    "Security",
    "Staffing",
    "Telecom",
]
VENDORS = [
    "Bluepeak Technologies Pvt Ltd",
    "Meridian Logistics Services Ltd",
    "PulseHR Technologies Pvt Ltd",
]
OWNERS = ["Priya Nair (IT Procurement)", "Anil Kapoor (Supply Chain)"]
TODAY = dt.date(2026, 11, 6)


def P(q):
    return ask_nl.parse(q, TODAY, CATS, VENDORS, OWNERS)


def test_quarter_and_month_bounds():
    assert ask_nl._quarter_bounds(TODAY, 1) == (dt.date(2027, 1, 1), dt.date(2027, 3, 31))
    assert ask_nl._quarter_bounds(TODAY, 0) == (dt.date(2026, 10, 1), dt.date(2026, 12, 31))
    assert ask_nl._quarter_bounds(dt.date(2026, 11, 6), 2) == (
        dt.date(2027, 4, 1),
        dt.date(2027, 6, 30),
    )
    assert ask_nl._month_bounds(dt.date(2026, 12, 15), 1) == (
        dt.date(2027, 1, 1),
        dt.date(2027, 1, 31),
    )


def test_parse_metric_window_group():
    p = P("How many contracts are expiring in the next quarter?")
    assert p["metric"] == "count" and p["win"]["start"] == dt.date(2027, 1, 1)
    assert P("total annual value of contracts by vendor")["group"] == "vendor"
    assert P("How many contracts expire in the next 90 days?")["win"][
        "end"
    ] == TODAY + dt.timedelta(days=90)
    assert (
        "notice"
        in ask_nl.build_sql(P("how many contracts have a notice deadline next month"))[
            "aggregate"
        ].lower()
    )


def test_filters_do_not_get_dropped_or_confused():
    # regression: "without a DPA" must not also select the DPA *contract type*
    p = P("How many contracts process personal data without a DPA?")
    assert "processes_personal_data AND NOT has_dpa" in p["where"] and not any(
        w.startswith("type IN") for w in p["where"]
    )
    assert "has_dpa" in P("How many contracts have a DPA?")["where"]  # regression: was ignored
    assert "type IN ('DPA')" in P("How many DPAs do we have?")["where"]
    assert (
        ask_nl.subject_of(P("How many contracts are owned by Priya?"), 4)
        == "contracts owned by Priya"
    )
    assert (
        "vendor = 'Bluepeak Technologies Pvt Ltd'"
        in P("total annual value of Bluepeak contracts")["where"]
    )


def test_unrecognised_questions_return_none():
    assert P("Tell me a joke") is None and P("what is the weather") is None


@pytest.fixture
def seeded(db):
    with db.connect() as c:
        if c.execute(text("select count(*) from contracts")).scalar() < 18:
            pytest.skip("database not seeded")


def test_scripted_matching_is_not_greedy(monkeypatch, seeded):
    # regression: "...of SaaS contracts" used to be answered with the "...of all active contracts" script
    monkeypatch.setattr("app.llm.available", lambda: False)
    r = ask.answer("What is the total annual value of SaaS contracts?", False)
    assert r["source"] == "offline-planner" and "₹1.36 crore" in r["answer"]


def test_aggregate_answer_has_headline_breakdown_and_list(monkeypatch, seeded):
    monkeypatch.setattr("app.llm.available", lambda: False)
    r = ask.answer(
        "How many auto-renewing contracts do we have and what is their total annual value?", False
    )
    assert r["answer"].startswith("5 auto-renewing contracts")
    assert [c["name"] for c in r["tool_calls"]] == ["run_sql"] * 3  # aggregate, breakdown, list
    assert r["tool_calls"][0]["output"]["rows"][0][0] == 5
    # presented as headline tiles + a breakdown table + the contract table, SQL hidden in thinking
    assert [t["label"] for t in r["tiles"]] == ["Contracts", "Annual value"]
    assert [t["title"] for t in r["tables"]] == ["Breakdown by category", "Contracts"]
    assert len(r["tables"][1]["rows"]) == 5 and "sql" in r["thinking"][1]
    assert r["thinking"][0]["title"] == "Understood the question"


def test_table_questions_pick_the_requested_columns(monkeypatch, seeded):
    monkeypatch.setattr("app.llm.available", lambda: False)
    r = ask.answer("Show start date, end date and signatures for all contracts", False)
    t = r["tables"][0]
    labels = [c["label"] for c in t["columns"]]
    assert labels == ["Contract", "Type", "Start date", "End date", "Signed by (Arcadia)", "Arcadia signed on",
                      "Signed by (Supplier)", "Supplier signed on", "Fully signed"]
    assert len(t["rows"]) == 19 and t["columns"][-1]["kind"] == "bool" and t["columns"][2]["kind"] == "date"
    assert not r["tiles"]                                  # plain list: no headline tiles


def test_signature_and_clause_presence_filters(monkeypatch, seeded):
    monkeypatch.setattr("app.llm.available", lambda: False)
    r = ask.answer("Which contracts are not fully signed?", False)
    assert [x["title"] for x in r["tables"][0]["rows"]] == ["Work Order 2 – Store Wi-Fi Refresh – Bluepeak Technologies"]
    r = ask.answer("Which contracts do not have an audit rights clause?", False)
    rows = r["tables"][0]["rows"]
    assert 0 < len(rows) < 19 and all(x["has_audit_rights"] is False for x in rows)
    assert "without an audit rights clause" in r["answer"]


def test_single_document_question_returns_its_clauses(monkeypatch, seeded):
    monkeypatch.setattr("app.llm.available", lambda: False)
    r = ask.answer("Show the key clauses in the Bluepeak MSA", False)
    t = r["tables"][0]
    assert [c["label"] for c in t["columns"]] == ["Contract", "Clause", "Page", "Clause text"]
    assert len(t["rows"]) == 21 and {x["title"] for x in t["rows"]} == {"Master Services Agreement – Bluepeak Technologies"}
    assert t["rows"][-1]["clause"] == "Execution"


def test_thinking_hides_sql_from_the_answer_but_keeps_it_inspectable(monkeypatch, seeded):
    monkeypatch.setattr("app.llm.available", lambda: False)
    r = ask.answer("Which vendors have uncapped liability?", False)
    assert "SELECT" not in r["answer"] and r["tables"][0]["columns"][0]["label"] == "Vendor"
    assert any(s.get("sql", "").startswith("SELECT") for s in r["thinking"])
    assert r["thinking"][-1]["title"] == "Composed the answer"


def test_vendor_level_questions(monkeypatch, seeded):
    monkeypatch.setattr("app.llm.available", lambda: False)
    r = ask.answer("How many vendors have contracts expiring in the next 90 days?", False)
    assert r["answer"].startswith("6 vendors with contracts expiring")
    assert [t["label"] for t in r["tiles"]] == ["Contracts", "Vendors", "Annual value"]
    assert r["tables"][0]["title"] == "Vendors" and len(r["tables"][0]["rows"]) == 6
    r = ask.answer("Which vendors have auto-renewing contracts?", False)
    assert r["answer"].startswith("5 vendors with auto-renewing contracts")


def test_new_clause_words_and_work_orders(monkeypatch, seeded):
    monkeypatch.setattr("app.llm.available", lambda: False)
    p = P("Which contracts do not have an insurance clause?")
    assert "NOT has_insurance" in p["where"]
    assert "NOT has_force_majeure" in P("contracts without a force majeure clause")["where"]
    r = ask.answer("Show all Bluepeak contracts with start date, end date and annual value", False)
    assert len(r["tables"][0]["rows"]) == 7
