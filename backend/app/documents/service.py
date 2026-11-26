import uuid

import jsonschema
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai_engine.models import AiTool
from app.documents.models import Document, DocumentVersion


class DocError(Exception):
    def __init__(self, code: str, status: int = 400):
        super().__init__(code)
        self.code, self.status = code, status


def latest(db: Session, doc_id) -> DocumentVersion:
    return db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == doc_id).order_by(DocumentVersion.version_no.desc()))


def add_version(db: Session, doc: Document, content: dict, *, source: str, note: str = "", expect_current: int | None = None) -> DocumentVersion:
    """Appends a version. `expect_current` gives optimistic concurrency: a stale editor gets 409 instead of overwriting."""
    db.execute(select(Document.id).where(Document.id == doc.id).with_for_update())  # serialize writers per document
    cur = db.scalar(select(func.max(DocumentVersion.version_no)).where(DocumentVersion.document_id == doc.id)) or 0
    if expect_current is not None and expect_current != cur:
        raise DocError("version_conflict", 409)
    v = DocumentVersion(document_id=doc.id, version_no=cur + 1, content=content, source=source, note=note[:300])
    db.add(v)
    db.flush()
    return v


def create_from_request(db: Session, req, tool: AiTool) -> Document:
    """Called when an AI request succeeds. One document per request; a regeneration adds a version to its target."""
    existing = db.scalar(select(Document).where(Document.request_id == req.id))
    if existing:
        return existing
    if req.target_document_id:
        doc = db.get(Document, req.target_document_id)
        if doc and not doc.is_deleted and doc.user_id == req.user_id:
            add_version(db, doc, req.output, source="regenerate", note="Dibuat ulang oleh AI")
            doc.request_id = req.id
            return doc
    topic = (req.input or {}).get("topic") or (req.input or {}).get("subject") or ""
    doc = Document(user_id=req.user_id, tool_slug=tool.slug, title=f"{tool.name}: {topic}"[:200] if topic else tool.name, input=req.input, request_id=req.id)
    db.add(doc)
    db.flush()
    add_version(db, doc, req.output, source="ai")
    return doc


def validate_content(tool: AiTool, content: dict) -> None:
    try:
        jsonschema.validate(content, tool.output_schema)
    except jsonschema.ValidationError as e:
        raise DocError(f"invalid_content: {e.message[:150]}", 422) from None


def duplicate(db: Session, doc: Document) -> Document:
    new = Document(user_id=doc.user_id, tool_slug=doc.tool_slug, title=(doc.title + " (salinan)")[:200], input=doc.input, source_document_id=doc.id)
    db.add(new)
    db.flush()
    add_version(db, new, latest(db, doc.id).content, source="duplicate", note=f"Salinan dari {doc.title}")
    return new


__all__ = ["create_from_request", "add_version", "latest", "validate_content", "duplicate", "DocError", "uuid", "IntegrityError"]
