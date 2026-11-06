"""Anthropic wrapper: disk cache (so re-seeding is free and deterministic) + llm_calls logging."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from app.config import data_path, settings


def provider() -> str:
    """Which Claude backend is in use:
      api          - the Anthropic API (ANTHROPIC_API_KEY)
      claude_code  - the Claude Code CLI / Agent SDK, billed to the logged-in Claude subscription (no key needed)
      offline      - no LLM: rule-based extractor, pattern redline, scripted Ask planner
    LLM_PROVIDER=auto picks api when a key is set, else claude_code when the `claude` CLI is installed, else offline."""
    want = (settings.llm_provider or "auto").lower()
    if want == "offline":
        return "offline"
    if want == "api":
        return "api" if settings.anthropic_api_key else "offline"
    if want == "claude_code":
        return "claude_code" if shutil.which("claude") else "offline"
    if settings.anthropic_api_key:
        return "api"
    return "claude_code" if shutil.which("claude") else "offline"


_down_until = 0.0
last_error: str | None = None


def note_failure(e: Exception) -> None:
    """Remember a failed call. A subscription/usage limit pauses the LLM for a while so everything falls back to the
    offline engine at once instead of failing slowly one call at a time."""
    global _down_until, last_error
    last_error = str(e)[:300]
    low = last_error.lower()
    if "limit" in low or "quota" in low or "credit" in low or "rate" in low:
        _down_until = time.time() + 15 * 60


def status() -> dict:
    return {"provider": provider(), "label": PROVIDER_LABEL[provider()], "paused": time.time() < _down_until, "last_error": last_error}


def available() -> bool:
    return provider() != "offline" and time.time() >= _down_until


PROVIDER_LABEL = {"api": "Claude API", "claude_code": "Claude (subscription)", "offline": "Offline engine"}
_cli_slots = threading.Semaphore(4)       # at most 4 concurrent `claude` processes


def cli_env() -> dict:
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    return env


def _cli_tool(system: str, user: str, tool: dict, model: str, timeout: int = 300) -> tuple[dict, dict]:
    """One forced-structured-output call through the Claude Code CLI (subscription). Returns (output, usage)."""
    cmd = ["claude", "-p", "--output-format", "json", "--model", model, "--tools", "", "--no-session-persistence", "--setting-sources", "",
           "--disable-slash-commands", "--system-prompt", system, "--json-schema", json.dumps(tool["input_schema"])]
    last = ""
    for attempt in range(2):
        with _cli_slots:
            r = subprocess.run(cmd, input=user, capture_output=True, text=True, timeout=timeout, cwd=tempfile.gettempdir(), env=cli_env())
        try:
            d = json.loads(r.stdout)
            if not d.get("is_error") and isinstance(d.get("structured_output"), dict):
                return d["structured_output"], d.get("usage", {})
            last = str(d.get("result") or d)[:300]
        except ValueError:
            last = (r.stderr or r.stdout)[:300]
    raise RuntimeError(f"claude CLI call failed: {last}")


def _client():
    import anthropic

    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _log(purpose: str, phash: str, model: str, tin: int, tout: int, ms: int) -> None:
    try:
        from app.db import SessionLocal
        from app.models import LlmCall

        with SessionLocal() as s:
            s.add(
                LlmCall(
                    purpose=purpose,
                    prompt_hash=phash,
                    model=model,
                    input_tokens=tin,
                    output_tokens=tout,
                    latency_ms=ms,
                )
            )
            s.commit()
    except Exception:  # logging must never break a request
        pass


def create(purpose: str, **kwargs):
    """messages.create with logging. Used by the Ask tool-use loop."""
    phash = hashlib.sha256(json.dumps(kwargs, sort_keys=True, default=str).encode()).hexdigest()[
        :16
    ]
    t0 = time.time()
    resp = _client().messages.create(**kwargs)
    _log(
        purpose,
        phash,
        kwargs["model"],
        resp.usage.input_tokens,
        resp.usage.output_tokens,
        int((time.time() - t0) * 1000),
    )
    return resp


def call_tool(
    purpose: str,
    model: str,
    system: str,
    user: str,
    tool: dict,
    max_tokens: int = 3000,
    use_cache: bool = True,
) -> dict:
    """Force a single tool call and return its JSON input. Results are cached on disk."""
    key = hashlib.sha256(
        json.dumps([model, system, user, tool], sort_keys=True).encode()
    ).hexdigest()
    cache: Path = data_path() / ".cache" / "llm" / f"{key}.json"
    if use_cache and cache.exists():
        return json.loads(cache.read_text())
    if provider() == "claude_code":
        t0 = time.time()
        out, u = _cli_tool(system, user, tool, model)
        _log(purpose, key[:16], model, int(u.get("input_tokens", 0)) + int(u.get("cache_creation_input_tokens", 0)) + int(u.get("cache_read_input_tokens", 0)),
             int(u.get("output_tokens", 0)), int((time.time() - t0) * 1000))
    else:
        resp = create(
            purpose,
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            tools=[tool],
            tool_choice={"type": "tool", "name": tool["name"]},
        )
        out = next(b.input for b in resp.content if b.type == "tool_use")
    if use_cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(out))
    return out


def prompt(name: str) -> str:
    return (Path(__file__).parent / "prompts" / f"{name}.md").read_text()
