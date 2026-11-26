import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai_engine import dispatch as dispatcher
from app.ai_engine import engine
from app.ai_engine.models import AiTool
from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.rate_limit import rate_limit
from app.documents import service
from app.documents.builders import build
from app.documents.models import Document, DocumentDownload, DocumentVersion
from app.documents.render_docx import render_docx
from app.documents.render_pdf import render_pdf
from app.documents.render_pptx import render_pptx
from app.users.models import User

router = APIRouter(prefix="/documents", tags=["documents"])


class SaveIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: dict | None = None
    note: str = Field(default="", max_length=300)
    base_version: int = Field(ge=1)  # the version the editor started from


class RestoreIn(BaseModel):
    version: int = Field(ge=1)


def _own(db: Session, user: User, doc_id: uuid.UUID) -> Document:
    d = db.get(Document, doc_id)
    if not d or d.user_id != user.id or d.is_deleted:
        raise HTTPException(404, "not_found")  # identical answer for missing and not-yours
    return d


def _guard(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except service.DocError as e:
        raise HTTPException(e.status, e.code) from None
    except engine.EngineError as e:
        raise HTTPException(e.status, e.code) from None


def _tool(db: Session, slug: str) -> AiTool:
    return db.scalar(select(AiTool).where(AiTool.slug == slug))


def _out(db: Session, d: Document, full: bool = True) -> dict:
    v = service.latest(db, d.id)
    out = {"id": str(d.id), "title": d.title, "tool_slug": d.tool_slug, "version": v.version_no, "updated_at": d.updated_at, "created_at": d.created_at}
    if full:
        t = _tool(db, d.tool_slug)
        out |= {"content": v.content, "input": d.input, "output_schema": t.output_schema if t else {}, "tool_name": t.name if t else d.tool_slug}
    return out


@router.get("")
def list_documents(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), q: str = Query("", max_length=100),
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    base = select(Document).where(Document.user_id == user.id, Document.is_deleted.is_(False))
    if q:
        base = base.where(Document.title.ilike(f"%{q}%"))
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    rows = db.scalars(base.order_by(Document.updated_at.desc()).offset((page - 1) * page_size).limit(page_size))
    return {"total": total, "page": page, "items": [_out(db, d, full=False) for d in rows]}


@router.get("/{doc_id}")
def get_document(doc_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _out(db, _own(db, user, doc_id))


@router.patch("/{doc_id}")
def save_document(doc_id: uuid.UUID, body: SaveIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    d = _own(db, user, doc_id)
    if body.content is None and body.title is None:
        raise HTTPException(422, "nothing_to_save")
    if body.title:
        d.title = body.title
    if body.content is not None:
        _guard(service.validate_content, _tool(db, d.tool_slug), body.content)  # an edit can never break export
        _guard(service.add_version, db, d, body.content, source="edit", note=body.note, expect_current=body.base_version)
    elif body.base_version != service.latest(db, d.id).version_no:
        raise HTTPException(409, "version_conflict")
    d.updated_at = datetime.now(d.updated_at.tzinfo)
    db.commit()
    return _out(db, d)


@router.delete("/{doc_id}", status_code=204)
def delete_document(doc_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _own(db, user, doc_id).is_deleted = True
    db.commit()


@router.post("/{doc_id}/duplicate", status_code=201)
def duplicate_document(doc_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    new = service.duplicate(db, _own(db, user, doc_id))
    db.commit()
    return _out(db, new)


@router.get("/{doc_id}/versions")
def versions(doc_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    d = _own(db, user, doc_id)
    return [{"version": v.version_no, "source": v.source, "note": v.note, "created_at": v.created_at}
            for v in db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == d.id).order_by(DocumentVersion.version_no.desc()))]


def _version(db: Session, d: Document, n: int) -> DocumentVersion:
    v = db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == d.id, DocumentVersion.version_no == n))
    if not v:
        raise HTTPException(404, "version_not_found")
    return v


@router.post("/{doc_id}/restore")
def restore(doc_id: uuid.UUID, body: RestoreIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Restoring never deletes anything: the old content becomes a NEW latest version."""
    d = _own(db, user, doc_id)
    src = _version(db, d, body.version)
    service.add_version(db, d, src.content, source="restore", note=f"Dipulihkan dari versi {src.version_no}")
    db.commit()
    return _out(db, d)


@router.get("/{doc_id}/export")
def export(doc_id: uuid.UUID, format: str = Query("docx", pattern="^(docx|pdf|pptx)$"), version: int | None = Query(None, ge=1),
           user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    d = _own(db, user, doc_id)
    v = _version(db, d, version) if version else service.latest(db, d.id)
    t = _tool(db, d.tool_slug)
    doc = build(d.tool_slug, t.name if t else d.tool_slug, d.input, v.content)
    data = {"docx": render_docx, "pdf": render_pdf, "pptx": render_pptx}[format](doc)
    db.add(DocumentDownload(document_id=d.id, version_no=v.version_no, user_id=user.id, format=format))
    db.commit()
    mime = {"pdf": "application/pdf", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation"}[format]
    return Response(data, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{d.tool_slug}-{str(d.id)[:8]}-v{v.version_no}.{format}"'})


@router.post("/{doc_id}/regenerate", status_code=202, dependencies=[Depends(rate_limit("regenerate", 20))])
def regenerate(doc_id: uuid.UUID, background: BackgroundTasks, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Runs the tool again with the same inputs (charged like any generation). The result is added as a NEW version."""
    if not idempotency_key or not (8 <= len(idempotency_key) <= 100):
        raise HTTPException(400, "idempotency_key_required")
    d = _own(db, user, doc_id)
    req = _guard(engine.submit, db, user.id, d.tool_slug, d.input, idempotency_key, d.id)
    if req.status == "queued":
        dispatcher.dispatch(req.id, background)
    return {"id": str(req.id), "status": req.status}
