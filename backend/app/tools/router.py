import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_engine import dispatch as dispatcher
from app.ai_engine import engine
from app.ai_engine.models import AiRequest, AiTool
from app.ai_engine.schemas import EstimateOut, RequestOut, ToolDetail, ToolOut
from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.rate_limit import rate_limit
from app.credits import service as credits
from app.users.models import User

router = APIRouter(tags=["tools"])


class GenerateIn(BaseModel):
    input: dict = Field(default_factory=dict)


def _tool(db: Session, slug: str) -> AiTool:
    t = db.scalar(select(AiTool).where(AiTool.slug == slug, AiTool.is_active.is_(True)))
    if not t:
        raise HTTPException(404, "tool_not_found")
    return t


def _guard(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except engine.EngineError as e:
        raise HTTPException(e.status, e.code) from None


@router.get("/tools", response_model=list[ToolOut])
def list_tools(category: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = select(AiTool).where(AiTool.is_active.is_(True)).order_by(AiTool.sort, AiTool.name)
    if category:
        q = q.where(AiTool.category == category)
    return [ToolOut(slug=t.slug, name=t.name, category=t.category, description=t.description) for t in db.scalars(q)]


@router.get("/tools/{slug}", response_model=ToolDetail)
def get_tool(slug: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    t = _tool(db, slug)
    return ToolDetail(slug=t.slug, name=t.name, category=t.category, description=t.description,
                      input_schema=t.input_schema)


@router.post("/tools/{slug}/estimate", response_model=EstimateOut)
def estimate(slug: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    t = _tool(db, slug)
    est = _guard(engine.estimate, db, t)
    wallet = credits.get_or_create_wallet(db, user.id)
    db.commit()
    total = credits.summary(db, wallet.id)["total"]
    return EstimateOut(mode=est["mode"], expected=est["expected"], min=est["min"], max=est["max"], balance=total,
                       sufficient=total >= est["reserve"])


@router.post("/tools/{slug}/generate", response_model=RequestOut, status_code=202,
             dependencies=[Depends(rate_limit("generate", 30))])
def generate(slug: str, body: GenerateIn, background: BackgroundTasks,
             idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
             user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not idempotency_key or not (8 <= len(idempotency_key) <= 100):
        raise HTTPException(400, "idempotency_key_required")
    req = _guard(engine.submit, db, user.id, slug, body.input, idempotency_key)
    if req.status == "queued":
        dispatcher.dispatch(req.id, background)
    return _out(db, req, slug)


def _out(db: Session, r: AiRequest, slug: str) -> RequestOut:
    return RequestOut(id=str(r.id), tool_slug=slug, status=r.status, output=r.output, error_code=r.error_code,
                      credits_reserved=r.credits_reserved, credits_charged=r.credits_charged,
                      created_at=r.created_at, finished_at=r.finished_at)


@router.get("/ai/requests/{request_id}", response_model=RequestOut)
def get_request(request_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = db.get(AiRequest, request_id)
    if not r or r.user_id != user.id:  # same answer for "missing" and "someone else's"
        raise HTTPException(404, "not_found")
    return _out(db, r, db.get(AiTool, r.tool_id).slug)
