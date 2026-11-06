"""Chat: conversations (history) and the streaming answer. Events are emitted as the work happens:
  step      one entry of the thinking trail (understood the question, ran SQL, searched clauses...)
  reasoning model reasoning text (Claude with extended thinking)
  token     a piece of the written answer
  result    the complete structured answer (tiles, tables, thinking, citations)
With the offline engine the answer is computed in milliseconds and then revealed progressively; with Claude the
tool-use loop streams for real."""
from __future__ import annotations

import json
import time
from typing import Iterator

from sqlalchemy import text

from app import ask, ask_present, llm
from app.config import settings
from app.db import SessionLocal

STEP_PAUSE = 0.12      # offline engine only: pacing so the trail can be followed
TOKEN_PAUSE = 0.012


def _rows(sql: str, **p) -> list[dict]:
    with SessionLocal() as s:
        return [dict(r) for r in s.execute(text(sql), p).mappings().all()]


# ------------------------------------------------------------------ history
def list_conversations(q: str | None = None) -> list[dict]:
    return _rows("""SELECT c.id, c.title, c.updated_at, c.created_at, c.scope,
                           (SELECT count(*) FROM chat_messages m WHERE m.conversation_id = c.id AND m.role = 'user') AS questions,
                           (SELECT content FROM chat_messages m WHERE m.conversation_id = c.id AND m.role = 'assistant' ORDER BY id DESC LIMIT 1) AS last_answer
                    FROM conversations c
                    WHERE CAST(:q AS text) IS NULL OR c.title ILIKE :p
                       OR EXISTS (SELECT 1 FROM chat_messages m WHERE m.conversation_id = c.id AND m.content ILIKE :p)
                    ORDER BY c.updated_at DESC LIMIT 100""", q=q, p=f"%{q}%" if q else None)


def get_conversation(cid: int) -> dict | None:
    c = _rows("SELECT id, title, scope, created_at, updated_at FROM conversations WHERE id=:i", i=cid)
    if not c:
        return None
    msgs = _rows("SELECT id, role, content, payload, created_at FROM chat_messages WHERE conversation_id=:i ORDER BY id", i=cid)
    return {**c[0], "messages": msgs}


def rename(cid: int, title: str) -> None:
    with SessionLocal() as s:
        s.execute(text("UPDATE conversations SET title=:t WHERE id=:i"), {"t": title.strip()[:120] or "Untitled", "i": cid})
        s.commit()


def delete(cid: int) -> None:
    with SessionLocal() as s:
        s.execute(text("DELETE FROM conversations WHERE id=:i"), {"i": cid})
        s.commit()


def _save_user(cid: int | None, question: str, scope: list[int] | None) -> int:
    with SessionLocal() as s:
        if cid is None or not s.execute(text("SELECT 1 FROM conversations WHERE id=:i"), {"i": cid}).first():
            title = " ".join(question.split())[:70]
            cid = s.execute(text("INSERT INTO conversations (title, scope) VALUES (:t, CAST(:s AS jsonb)) RETURNING id"),
                            {"t": title, "s": json.dumps(scope or [])}).scalar()
        s.execute(text("INSERT INTO chat_messages (conversation_id, role, content, payload) VALUES (:c,'user',:q,CAST(:p AS jsonb))"),
                  {"c": cid, "q": question, "p": json.dumps({"scope": scope or []})})
        s.commit()
    return cid


def _save_answer(cid: int, res: dict) -> int:
    with SessionLocal() as s:
        mid = s.execute(text("INSERT INTO chat_messages (conversation_id, role, content, payload) VALUES (:c,'assistant',:a,CAST(:p AS jsonb)) RETURNING id"),
                        {"c": cid, "a": res.get("answer", ""), "p": json.dumps(res, default=str)}).scalar()
        s.execute(text("UPDATE conversations SET updated_at=now() WHERE id=:i"), {"i": cid})
        s.commit()
    return mid


def _history(cid: int, limit: int = 6) -> list[dict]:
    """Previous turns as plain messages, so follow-up questions have context (used by the Claude path)."""
    rows = _rows("SELECT role, content FROM chat_messages WHERE conversation_id=:i ORDER BY id DESC LIMIT :n", i=cid, n=limit * 2)
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)][:-1] if rows else []


# ------------------------------------------------------------------ streaming
def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, default=str)}\n\n"


def _reveal(res: dict) -> Iterator[dict]:
    for st in res.get("thinking", []):
        yield {"type": "step", "step": st}
        time.sleep(STEP_PAUSE)
    words = res.get("answer", "").split(" ")
    for i in range(0, len(words), 3):
        yield {"type": "token", "text": " ".join(words[i:i + 3]) + (" " if i + 3 < len(words) else "")}
        time.sleep(TOKEN_PAUSE)


def _llm_stream(question: str, scope: list[int] | None, history: list[dict]) -> Iterator[dict]:
    """Real streaming tool-use loop: reasoning and answer tokens as they arrive, a step per tool call."""
    if llm.provider() == "claude_code":                      # Claude subscription via the Agent SDK
        from app import agent

        for ev in agent.events(question, scope, history):
            if ev["type"] == "final":
                res = ev["res"]
                res["citations"] = ask.citations(res["tool_calls"])
                ask_present.finalize(res)
                yield {"type": "final", "res": res, "source": "claude-subscription"}
            else:
                yield ev
        return
    system = ask.build_system(scope)
    messages = history + [{"role": "user", "content": question}]
    calls, notes, sql_errors, answer = [], [], 0, ""
    yield {"type": "step", "step": {"title": "Understood the question", "detail": "Choosing between SQL over the extracted data and clause search."}}
    for _ in range(8):
        kwargs = dict(model=settings.model_ask, max_tokens=4000, system=system, tools=ask.TOOLS, messages=messages)
        if getattr(settings, "ask_thinking", True):
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": 1500}
        t0 = time.time()
        with llm._client().messages.stream(**kwargs) as stream:
            for ev in stream:
                if ev.type == "content_block_delta":
                    d = ev.delta
                    if d.type == "thinking_delta":
                        yield {"type": "reasoning", "text": d.thinking}
                    elif d.type == "text_delta":
                        yield {"type": "token", "text": d.text}
            final = stream.get_final_message()
        llm._log("ask-stream", "stream", settings.model_ask, final.usage.input_tokens, final.usage.output_tokens, int((time.time() - t0) * 1000))
        if final.stop_reason != "tool_use":
            answer = "".join(b.text for b in final.content if b.type == "text")
            break
        messages.append({"role": "assistant", "content": final.content})
        notes += [b.text for b in final.content if b.type == "text" and b.text.strip()]
        results = []
        for b in (b for b in final.content if b.type == "tool_use"):
            yield {"type": "step", "step": {"title": {"run_sql": "Running SQL", "search_clauses": "Searching clauses", "get_contract": "Reading a contract"}.get(b.name, b.name),
                                            "detail": (b.input.get("query") or b.input.get("id") or "") if isinstance(b.input, dict) else ""}}
            out = ask.execute_tool(b.name, b.input, scope)
            calls.append({"name": b.name, "input": b.input, "output": out})
            is_err = "error" in out
            sql_errors += is_err and b.name == "run_sql"
            content = json.dumps(out) + (" (This is the second SQL error: do not retry; explain what went wrong.)" if is_err and b.name == "run_sql" and sql_errors > 1 else "")
            results.append({"type": "tool_result", "tool_use_id": b.id, "content": content, "is_error": is_err})
        messages.append({"role": "user", "content": results})
    res = {"answer": answer or "I could not complete that question.", "tool_calls": calls, "notes": notes}
    res["citations"] = ask.citations(calls)
    ask_present.finalize(res)
    yield {"type": "final", "res": res, "source": "llm"}


def stream_answer(question: str, conversation_id: int | None, demo_mode: bool, scope: list[int] | None) -> Iterator[str]:
    t0 = time.time()
    scope = scope or None
    try:
        history = _history(conversation_id) if conversation_id else []
        cid = _save_user(conversation_id, question, scope)
        yield _sse({"type": "meta", "conversation_id": cid})
        res, source = None, "offline-planner"
        use_llm = llm.available() and not (demo_mode and not scope and _cached(question))
        if use_llm:
            try:
                for ev in _llm_stream(question, scope, history):
                    if ev["type"] == "final":
                        res, source = ev["res"], ev["source"]
                    else:
                        yield _sse(ev)
            except Exception as e:      # limit reached / network: answer with the offline engine instead
                llm.note_failure(e)
                yield _sse({"type": "step", "step": {"title": "Claude is unavailable right now, using the offline engine", "detail": str(e)[:200]}})
                res = None
        if res is None:
            res = ask.answer(question, demo_mode, scope, force_offline=True)
            source = res.get("source", "offline-planner")
            for ev in _reveal(res):
                yield _sse(ev)
        res.update(question=question, source=source, elapsed_ms=int((time.time() - t0) * 1000), scoped=len(scope) if scope else 0)
        mid = _save_answer(cid, res)
        yield _sse({"type": "result", "result": res, "message_id": mid})
    except Exception as e:
        yield _sse({"type": "error", "message": f"{type(e).__name__}: {e}"})
    yield _sse({"type": "done"})


def _cached(question: str) -> bool:
    with SessionLocal() as s:
        return s.execute(text("SELECT 1 FROM ask_cache WHERE question_key=:k"), {"k": ask.norm_key(question)}).first() is not None
