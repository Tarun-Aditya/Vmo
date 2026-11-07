"""Ask through the Claude Code Agent SDK: the same tools (run_sql, search_clauses, get_contract) as the API loop, but billed to
the logged-in Claude subscription instead of an API key. Yields streaming events:
  reasoning  thinking text         step    one entry per tool call        token    the answer as it is written
  demote     text that turned out to be narration before a tool call (moves it from the answer to the reasoning)
  final      {answer, tool_calls, notes}"""
from __future__ import annotations

import asyncio
import json
import queue
import tempfile
import threading
import time
from typing import Iterator

from app import ask, llm
from app.config import settings

SERVER = "arcadia"
STEP_TITLE = {"run_sql": "Running SQL over the extracted data", "search_clauses": "Searching clauses", "get_contract": "Reading a contract"}


def _history_prompt(question: str, history: list[dict]) -> str:
    if not history:
        return question
    turns = "\n".join(f"{'User' if h['role'] == 'user' else 'Assistant'}: {h['content'][:1500]}" for h in history)
    return f"Conversation so far:\n{turns}\n\nNew question (it may refer to the conversation above): {question}"


async def _main(q: "queue.Queue", question: str, scope: list[int] | None, history: list[dict]) -> None:
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        ClaudeSDKClient,
        ResultMessage,
        StreamEvent,
        TextBlock,
        ToolUseBlock,
        create_sdk_mcp_server,
        tool,
    )

    calls: list[dict] = []
    notes: list[str] = []

    def make(spec: dict):
        name = spec["name"]

        @tool(name, spec["description"], spec["input_schema"])
        async def fn(args):
            out = await asyncio.to_thread(ask.execute_tool, name, dict(args), scope)
            calls.append({"name": name, "input": dict(args), "output": out})
            return {"content": [{"type": "text", "text": json.dumps(out, default=str)}], "is_error": "error" in out}

        return fn

    server = create_sdk_mcp_server(SERVER, tools=[make(t) for t in ask.TOOLS])
    opts = ClaudeAgentOptions(
        system_prompt=ask.build_system(scope), mcp_servers={SERVER: server}, tools=[], allowed_tools=[f"mcp__{SERVER}__{t['name']}" for t in ask.TOOLS],
        model=settings.model_ask, max_turns=10, include_partial_messages=True, setting_sources=[], cwd=tempfile.gettempdir(),
        thinking={"type": "enabled", "budget_tokens": 2000}, env={"ANTHROPIC_API_KEY": ""})
    t0 = time.time()
    turn_text, answer = "", ""
    q.put({"type": "step", "step": {"title": "Understood the question", "detail": "Choosing between SQL over the extracted data and clause search."}})
    async with ClaudeSDKClient(options=opts) as c:
        await c.query(_history_prompt(question, history))
        async for msg in c.receive_response():
            if isinstance(msg, StreamEvent):
                ev = msg.event
                if ev.get("type") == "content_block_delta":
                    d = ev.get("delta", {})
                    if d.get("type") == "thinking_delta":
                        q.put({"type": "reasoning", "text": d.get("thinking", "")})
                    elif d.get("type") == "text_delta":
                        turn_text += d.get("text", "")
                        q.put({"type": "token", "text": d.get("text", "")})
            elif isinstance(msg, AssistantMessage):
                uses = [b for b in msg.content if isinstance(b, ToolUseBlock)]
                text = "".join(b.text for b in msg.content if isinstance(b, TextBlock))
                if uses:
                    if text.strip():
                        notes.append(text)
                        q.put({"type": "demote", "text": text})
                    for b in uses:
                        name = b.name.split("__")[-1]
                        q.put({"type": "step", "step": {"title": STEP_TITLE.get(name, name), "detail": str(b.input.get("query") or b.input.get("id") or "")[:200]}})
                else:
                    answer = text
                turn_text = ""
            elif isinstance(msg, ResultMessage):
                u = msg.usage or {}
                llm._log("ask-agent", "agent", settings.model_ask, int(u.get("input_tokens", 0)) + int(u.get("cache_creation_input_tokens", 0)) + int(u.get("cache_read_input_tokens", 0)),
                         int(u.get("output_tokens", 0)), int((time.time() - t0) * 1000))
                if msg.is_error and not answer:
                    raise RuntimeError("; ".join(msg.errors or []) or msg.result or "the Claude call failed")
    q.put({"type": "final", "res": {"answer": answer or "I could not complete that question.", "tool_calls": calls, "notes": notes}})


def events(question: str, scope: list[int] | None = None, history: list[dict] | None = None) -> Iterator[dict]:
    """Sync bridge: runs the async SDK loop in a thread and yields its events as they happen."""
    q: queue.Queue = queue.Queue()

    def runner():
        try:
            asyncio.run(_main(q, question, scope, history or []))
        except Exception as e:  # surfaced to the caller below
            q.put({"type": "exception", "error": f"{type(e).__name__}: {e}"})
        q.put(None)

    threading.Thread(target=runner, daemon=True).start()
    while (ev := q.get()) is not None:
        if ev["type"] == "exception":
            raise RuntimeError(ev["error"])
        yield ev


def ask_agent(question: str, scope: list[int] | None = None, history: list[dict] | None = None) -> dict:
    res = None
    for ev in events(question, scope, history):
        if ev["type"] == "final":
            res = ev["res"]
    if res is None:
        raise RuntimeError("no answer produced")
    return res
