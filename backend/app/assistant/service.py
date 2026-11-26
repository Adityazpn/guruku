import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_engine import engine
from app.assistant.models import Conversation, Message

HISTORY_LIMIT = 10  # most recent messages sent as context (bounded cost + bounded data exposure)
DEFAULT_TITLE = "Percakapan baru"


def history(db: Session, conv_id) -> list[dict]:
    rows = list(db.scalars(select(Message).where(Message.conversation_id == conv_id).order_by(Message.created_at.desc()).limit(HISTORY_LIMIT)))
    return [{"role": m.role, "content": m.content[:2000]} for m in reversed(rows)]


def send(db: Session, user, conv: Conversation, content: str, idempotency_key: str):
    ctx = history(db, conv.id)
    req = engine.submit(db, user.id, "asisten-guru", {"message": content, "history": ctx, "conversation_id": str(conv.id)}, idempotency_key)
    if not db.scalar(select(Message.id).where(Message.request_id == req.id, Message.role == "user")):
        db.add(Message(conversation_id=conv.id, role="user", content=content, request_id=req.id))
        if conv.title == DEFAULT_TITLE:
            conv.title = " ".join(content.split())[:60] or DEFAULT_TITLE
        db.commit()
    return req


def on_success(db: Session, req, result: dict) -> None:
    """Called inside the engine's success transaction: stores the answer (once per request)."""
    conv_id = uuid.UUID(req.input["conversation_id"])
    if db.get(Conversation, conv_id) is None:  # conversation deleted while the request was running
        return
    if db.scalar(select(Message.id).where(Message.request_id == req.id, Message.role == "assistant")):
        return
    text = result["jawaban"]
    tips = result.get("saran_tindak_lanjut") or []
    if tips:
        text += "\n\nSaran tindak lanjut:\n" + "\n".join(f"- {t}" for t in tips)
    db.add(Message(conversation_id=conv_id, role="assistant", content=text, request_id=req.id))
