import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_engine import dispatch as dispatcher
from app.ai_engine import engine
from app.assistant import service
from app.assistant.models import Conversation, Message
from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.rate_limit import rate_limit
from app.users.models import User

router = APIRouter(prefix="/assistant", tags=["assistant"])


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class RenameIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)


def _own(db: Session, user: User, cid: uuid.UUID) -> Conversation:
    c = db.get(Conversation, cid)
    if not c or c.user_id != user.id:
        raise HTTPException(404, "not_found")
    return c


def _conv(c: Conversation) -> dict:
    return {"id": str(c.id), "title": c.title, "updated_at": c.updated_at}


@router.get("/conversations")
def list_conversations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [_conv(c) for c in db.scalars(select(Conversation).where(Conversation.user_id == user.id).order_by(Conversation.updated_at.desc()).limit(100))]


@router.post("/conversations", status_code=201)
def new_conversation(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = Conversation(user_id=user.id)
    db.add(c)
    db.commit()
    return _conv(c)


@router.get("/conversations/{cid}")
def get_conversation(cid: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = _own(db, user, cid)
    msgs = db.scalars(select(Message).where(Message.conversation_id == c.id).order_by(Message.created_at))
    return {**_conv(c), "messages": [{"id": str(m.id), "role": m.role, "content": m.content, "request_id": str(m.request_id) if m.request_id else None,
                                      "created_at": m.created_at} for m in msgs]}


@router.patch("/conversations/{cid}")
def rename(cid: uuid.UUID, body: RenameIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = _own(db, user, cid)
    c.title = body.title
    db.commit()
    return _conv(c)


@router.delete("/conversations/{cid}", status_code=204)
def delete_conversation(cid: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = _own(db, user, cid)
    db.query(Message).filter(Message.conversation_id == c.id).delete()  # hard delete: the content is gone, not hidden
    db.delete(c)
    db.commit()


@router.post("/conversations/{cid}/messages", status_code=202, dependencies=[Depends(rate_limit("assistant", 40))])
def send_message(cid: uuid.UUID, body: MessageIn, background: BackgroundTasks, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not idempotency_key or not (8 <= len(idempotency_key) <= 100):
        raise HTTPException(400, "idempotency_key_required")
    c = _own(db, user, cid)
    try:
        req = service.send(db, user, c, body.content, idempotency_key)
    except engine.EngineError as e:
        raise HTTPException(e.status, e.code) from None
    if req.status == "queued":
        dispatcher.dispatch(req.id, background)
    return {"request_id": str(req.id), "status": req.status}
