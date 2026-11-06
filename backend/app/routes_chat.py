"""Chat API: streaming answers (server-sent events) and conversation history."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app import chat

router = APIRouter(prefix="/api")


class ChatIn(BaseModel):
    question: str
    conversation_id: int | None = None
    demo_mode: bool = False
    contract_ids: list[int] | None = None


@router.post("/chat/stream")
def chat_stream(b: ChatIn):
    if not b.question.strip():
        raise HTTPException(422, "ask a question")
    return StreamingResponse(chat.stream_answer(b.question.strip(), b.conversation_id, b.demo_mode, b.contract_ids), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/conversations")
def conversations(q: str | None = None):
    return chat.list_conversations(q or None)


@router.get("/conversations/{cid}")
def conversation(cid: int):
    c = chat.get_conversation(cid)
    if not c:
        raise HTTPException(404, "conversation not found")
    return c


class RenameIn(BaseModel):
    title: str


@router.patch("/conversations/{cid}")
def conversation_rename(cid: int, b: RenameIn):
    chat.rename(cid, b.title)
    return chat.get_conversation(cid)


@router.delete("/conversations/{cid}")
def conversation_delete(cid: int):
    chat.delete(cid)
    return {"deleted": cid}
