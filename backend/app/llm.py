"""Anthropic wrapper: disk cache (so re-seeding is free and deterministic) + llm_calls logging."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from app.config import data_path, settings


def available() -> bool:
    return bool(settings.anthropic_api_key)


def _client():
    import anthropic

    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _log(purpose: str, phash: str, model: str, tin: int, tout: int, ms: int) -> None:
    try:
        from app.db import SessionLocal
        from app.models import LlmCall

        with SessionLocal() as s:
            s.add(LlmCall(purpose=purpose, prompt_hash=phash, model=model, input_tokens=tin,
                          output_tokens=tout, latency_ms=ms))
            s.commit()
    except Exception:  # logging must never break a request
        pass


def create(purpose: str, **kwargs):
    """messages.create with logging. Used by the Ask tool-use loop."""
    phash = hashlib.sha256(json.dumps(kwargs, sort_keys=True, default=str).encode()).hexdigest()[:16]
    t0 = time.time()
    resp = _client().messages.create(**kwargs)
    _log(purpose, phash, kwargs["model"], resp.usage.input_tokens, resp.usage.output_tokens,
         int((time.time() - t0) * 1000))
    return resp


def call_tool(purpose: str, model: str, system: str, user: str, tool: dict,
              max_tokens: int = 3000, use_cache: bool = True) -> dict:
    """Force a single tool call and return its JSON input. Results are cached on disk."""
    key = hashlib.sha256(json.dumps([model, system, user, tool], sort_keys=True).encode()).hexdigest()
    cache: Path = data_path() / ".cache" / "llm" / f"{key}.json"
    if use_cache and cache.exists():
        return json.loads(cache.read_text())
    resp = create(purpose, model=model, max_tokens=max_tokens, system=system,
                  messages=[{"role": "user", "content": user}], tools=[tool],
                  tool_choice={"type": "tool", "name": tool["name"]})
    out = next(b.input for b in resp.content if b.type == "tool_use")
    if use_cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(out))
    return out


def prompt(name: str) -> str:
    return (Path(__file__).parent / "prompts" / f"{name}.md").read_text()
