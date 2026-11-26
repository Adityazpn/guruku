from datetime import timedelta

from sqlalchemy import Text, cast, select, update
from sqlalchemy.orm import Session

from app.ai_engine.models import AiRequest, AiTool
from app.core.db import utcnow
from app.credits.models import CreditSetting
from app.documents.models import Document
from app.privacy.models import Consent

CONSENT_VERSION = "1"
CONSENT_TEXT = ("Saya memahami bahwa data siswa yang saya masukkan akan diproses oleh penyedia AI setelah nama dan pengenal pribadi disamarkan. "
                "Saya berwenang memakai data ini untuk keperluan pembelajaran, akan memakai alias/nama depan seperlunya, dan memahami bahwa keluaran bersifat saran, bukan diagnosis.")


def has_consent(db: Session, user_id, type_: str = "student_data") -> bool:
    return db.scalar(select(Consent.id).where(Consent.user_id == user_id, Consent.type == type_, Consent.revoked_at.is_(None))) is not None


def grant(db: Session, user_id, type_: str = "student_data") -> None:
    if not has_consent(db, user_id, type_):
        db.add(Consent(user_id=user_id, type=type_, version=CONSENT_VERSION, granted_at=utcnow()))


def revoke(db: Session, user_id, type_: str = "student_data") -> None:
    now = utcnow()
    for c in db.scalars(select(Consent).where(Consent.user_id == user_id, Consent.type == type_, Consent.revoked_at.is_(None))):
        c.revoked_at = now


def retention_days(db: Session) -> int:
    row = db.scalar(select(CreditSetting).where(CreditSetting.key == "student_data_retention_days"))
    return int(row.value) if row and row.value else 30


def purge_request_data(db: Session, user_id=None, older_than_days: int | None = None) -> int:
    """Blanks the stored input/output and the name map of sensitive-tool requests. The user's own documents are separate
    (they delete those themselves, or via delete_student_data). Returns the number of requests purged."""
    q = select(AiRequest).join(AiTool, AiTool.id == AiRequest.tool_id).where(AiTool.sensitive.is_(True), AiRequest.anon_map_enc.is_not(None) | (cast(AiRequest.input, Text) != "{}"))
    if user_id:
        q = q.where(AiRequest.user_id == user_id)
    if older_than_days is not None:
        q = q.where(AiRequest.created_at <= utcnow() - timedelta(days=older_than_days))
    n = 0
    for r in db.scalars(q):
        r.input, r.output, r.anon_map_enc = {}, None, None
        n += 1
    return n


def delete_student_data(db: Session, user_id) -> dict:
    """User-initiated erasure of everything created by student-data tools: request payloads and documents."""
    slugs = [t.slug for t in db.scalars(select(AiTool).where(AiTool.sensitive.is_(True)))]
    docs = db.execute(update(Document).where(Document.user_id == user_id, Document.tool_slug.in_(slugs), Document.is_deleted.is_(False)).values(is_deleted=True)).rowcount
    from app.documents.models import DocumentVersion

    for d in db.scalars(select(Document).where(Document.user_id == user_id, Document.tool_slug.in_(slugs))):
        for v in db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == d.id)):
            v.content = {}  # soft-deleted is not erased: blank the content itself
        d.input = {}
    return {"documents": docs, "requests": purge_request_data(db, user_id)}
