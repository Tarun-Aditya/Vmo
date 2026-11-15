"""Chat API: streaming answers (server-sent events) and conversation history."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app import chat, scope

router = APIRouter(prefix="/api")


class ChatIn(BaseModel):
    question: str
    conversation_id: int | None = None
    demo_mode: bool = False
    contract_ids: list[int] | None = None


def _owner(request: Request) -> str | None:
    u = getattr(request.state, "user", None)
    return u.get("email") if u else None


def _own(request: Request, cid: int) -> None:
    """A property-limited account may open only the conversations it started."""
    if scope.user_property(request):
        c = chat.get_conversation(cid)
        if not c or c.get("owner") != _owner(request):
            raise HTTPException(404, "conversation not found")


def limited(request: Request, ids: list[int] | None) -> tuple[list[int] | None, dict | None]:
    """For a property-limited account: the documents a question may cover (its property's, or the chosen ones among them) and the database limit."""
    mine = scope.user_property(request)
    if not mine:
        return ids, None
    lim = scope.limit_for(mine)
    allowed = set(lim["ids"])
    return ([i for i in ids if i in allowed] or sorted(allowed)) if ids else sorted(allowed), lim


@router.post("/chat/stream")
def chat_stream(b: ChatIn, request: Request):
    if not b.question.strip():
        raise HTTPException(422, "ask a question")
    if b.conversation_id:
        _own(request, b.conversation_id)
    ids, lim = limited(request, b.contract_ids)
    owner = _owner(request)

    def stream():
        # the response is produced after this function returns, one step at a time, each step in a worker thread with its own context:
        # the property limit is applied around every step, not once
        it = chat.stream_answer(b.question.strip(), b.conversation_id, b.demo_mode and not lim, ids, owner)      # no portfolio-wide cached answers for a limited account
        while True:
            tok = scope.SQL_LIMIT.set(lim)
            try:
                chunk = next(it)
            except StopIteration:
                return
            finally:
                scope.SQL_LIMIT.reset(tok)
            yield chunk

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/conversations")
def conversations(request: Request, q: str | None = None):
    return chat.list_conversations(q or None, _owner(request) if scope.user_property(request) else None)


@router.get("/conversations/{cid}")
def conversation(cid: int, request: Request):
    _own(request, cid)
    c = chat.get_conversation(cid)
    if not c:
        raise HTTPException(404, "conversation not found")
    return c


class RenameIn(BaseModel):
    title: str


@router.patch("/conversations/{cid}")
def conversation_rename(cid: int, b: RenameIn, request: Request):
    _own(request, cid)
    chat.rename(cid, b.title)
    return chat.get_conversation(cid)


@router.delete("/conversations/{cid}")
def conversation_delete(cid: int, request: Request):
    _own(request, cid)
    chat.delete(cid)
    return {"deleted": cid}
