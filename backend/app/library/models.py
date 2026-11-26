import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, utcnow


class LibraryCategory(Base, TimestampMixin):
    __tablename__ = "library_categories"
    slug: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    sort: Mapped[int] = mapped_column(default=0)


class LibraryItem(Base, TimestampMixin):
    __tablename__ = "library_items"
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("library_categories.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    level: Mapped[str] = mapped_column(String(20), default="")  # SD/MI | SMP/MTs | SMA/MA | SMK | ""
    subject: Mapped[str] = mapped_column(String(100), default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    access: Mapped[str] = mapped_column(String(10), default="free")  # free | premium
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)  # sample content is always labelled as such in the UI
    status: Mapped[str] = mapped_column(String(10), default="draft", index=True)  # draft | published | archived


class LibraryFile(Base):
    """Versioned: uploading a new file for an item adds a version; only the latest is served."""

    __tablename__ = "library_files"
    __table_args__ = (UniqueConstraint("item_id", "version_no"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("library_items.id", ondelete="CASCADE"), index=True)
    version_no: Mapped[int] = mapped_column()
    storage_key: Mapped[str] = mapped_column(String(200))
    filename: Mapped[str] = mapped_column(String(200))
    mime: Mapped[str] = mapped_column(String(120))
    size: Mapped[int] = mapped_column()
    checksum: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LibraryAccessLog(Base):
    __tablename__ = "library_access_logs"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("library_items.id"), index=True)
    file_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("library_files.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
