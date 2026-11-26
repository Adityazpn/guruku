import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, utcnow


class Document(Base, TimestampMixin):
    __tablename__ = "documents"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    tool_slug: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(200))
    input: Mapped[dict] = mapped_column(JSON)  # the form values it was generated from (used by export + regenerate)
    request_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ai_requests.id"), index=True)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id"))
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class DocumentVersion(Base):
    """Append-only history; every save, restore and regeneration adds a row."""

    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("document_id", "version_no"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    version_no: Mapped[int] = mapped_column()
    content: Mapped[dict] = mapped_column(JSON)
    note: Mapped[str] = mapped_column(String(300), default="")
    source: Mapped[str] = mapped_column(String(20), default="ai")  # ai | edit | restore | regenerate | duplicate
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DocumentDownload(Base):
    __tablename__ = "document_download_logs"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    version_no: Mapped[int] = mapped_column()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    format: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
