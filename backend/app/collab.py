"""Live collaboration channel: one WebSocket room per document. Who is here (presence), and pushes when something changes (a new version was saved, comments or suggestions changed), so
everyone sees it at once without polling. Simultaneous typing in the same text is NOT merged (that needs a CRDT editor): instead a save made from an out-of-date version is refused
with a conflict (see routes_docs.save), so nobody silently overwrites a colleague."""
from __future__ import annotations

import asyncio
import json
from collections import defaultdict

from fastapi import WebSocket

ROOMS: dict[int, dict[WebSocket, dict]] = defaultdict(dict)       # document id -> websocket -> {name, since}
_LOOP: asyncio.AbstractEventLoop | None = None


async def _send_all(cid: int, msg: dict, skip: WebSocket | None = None) -> None:
    for ws in list(ROOMS.get(cid, {})):
        if ws is skip:
            continue
        try:
            await ws.send_text(json.dumps(msg))
        except Exception:
            ROOMS[cid].pop(ws, None)


def presence(cid: int) -> list[dict]:
    seen, out = set(), []
    for info in ROOMS.get(cid, {}).values():
        if info["name"] not in seen:
            seen.add(info["name"])
            out.append({"name": info["name"], "editing": info.get("editing", False)})
    return out


def notify(cid: int, msg: dict) -> None:
    """Callable from ordinary (threaded) request handlers: schedules the push on the server's event loop."""
    if _LOOP and ROOMS.get(cid):
        asyncio.run_coroutine_threadsafe(_send_all(cid, msg), _LOOP)


async def room(ws: WebSocket, cid: int, name: str) -> None:
    global _LOOP
    _LOOP = asyncio.get_running_loop()
    await ws.accept()
    ROOMS[cid][ws] = {"name": name}
    await _send_all(cid, {"type": "presence", "users": presence(cid)})
    try:
        while True:
            m = json.loads(await ws.receive_text())
            if m.get("type") == "editing":
                ROOMS[cid][ws]["editing"] = bool(m.get("on"))
                await _send_all(cid, {"type": "presence", "users": presence(cid)})
    except Exception:
        pass
    finally:
        ROOMS[cid].pop(ws, None)
        await _send_all(cid, {"type": "presence", "users": presence(cid)})
