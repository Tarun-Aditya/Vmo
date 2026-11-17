"""The Claude tool-use loop, driven by a fake client: SQL error -> feedback -> corrected retry."""

from types import SimpleNamespace as NS

import pytest
from sqlalchemy import text

from app import ask


def tool_use(i, name, **inp):
    return NS(type="tool_use", id=i, name=name, input=inp)


@pytest.fixture
def seeded(db):
    with db.connect() as c:
        if c.execute(text("select count(*) from contracts")).scalar() < 18:
            pytest.skip("database not seeded")


def test_loop_feeds_sql_error_back_and_retries(monkeypatch, seeded):
    script = [
        NS(
            stop_reason="tool_use",
            content=[tool_use("1", "run_sql", query="SELECT nope FROM v_renewals")],
        ),
        NS(
            stop_reason="tool_use",
            content=[tool_use("2", "run_sql", query="SELECT count(*) AS n FROM v_renewals")],
        ),
        NS(
            stop_reason="end_turn",
            content=[NS(type="text", text="There are 25 renewable contracts.")],
        ),
    ]
    seen = []

    def fake_create(purpose, **kw):
        seen.append([m for m in kw["messages"]])
        return script[len(seen) - 1]

    monkeypatch.setattr("app.llm.create", fake_create)
    res = ask.ask_llm("How many?")
    assert res["answer"].startswith("There are 25")
    assert [("error" in c["output"]) for c in res["tool_calls"]] == [True, False]
    # the error text was fed back to the model as an is_error tool_result
    fed_back = seen[1][-1]["content"][0]
    assert fed_back["is_error"] and "nope" in fed_back["content"]
    assert res["tool_calls"][1]["output"]["rows"] == [[25]]


def _forget_document_changes(db):
    with db.begin() as c:
        c.execute(text("DELETE FROM app_settings WHERE key = 'documents_changed_at'"))


def test_cached_answers_are_not_used_after_the_documents_change(monkeypatch, seeded, db):
    """A cached answer saved before documents were added would leave them out: once they change, the answer is computed again."""
    monkeypatch.setattr("app.llm.available", lambda: False)
    q = "Which vendors have uncapped liability?"
    _forget_document_changes(db)
    try:
        assert ask.answer(q, demo_mode=True)["source"] == "cache"
        from app.db import SessionLocal

        with SessionLocal() as s:
            ask.mark_documents_changed(s, "test")
            s.commit()
        r = ask.answer(q, demo_mode=True)
        assert r["source"] != "cache" and r["tool_calls"]
    finally:
        _forget_document_changes(db)


def test_demo_mode_uses_cache_and_offline_answers_are_cited(monkeypatch, seeded, db):
    monkeypatch.setattr("app.llm.available", lambda: False)
    _forget_document_changes(db)      # as if the cache was saved after the last change to the documents
    r = ask.answer("Which vendors have uncapped liability?", demo_mode=True)
    assert r["source"] == "cache" and r["tool_calls"][0]["name"] == "run_sql"
    r = ask.answer(
        "which contracts give the vendor ownership of the deliverables we pay for", demo_mode=False
    )
    assert r["citations"] and r["citations"][0]["title"].endswith("AdSpark Analytics")
    assert "ANTHROPIC_API_KEY" in ask.answer("Tell me a joke", False)["answer"]
