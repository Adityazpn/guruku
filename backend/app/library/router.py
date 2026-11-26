import hashlib
import mimetypes
import re
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.admin.audit import audit
from app.core.db import get_db
from app.core.deps import get_current_user, require_roles
from app.core.rate_limit import rate_limit
from app.core.storage import get_storage, verify_local_token
from app.library.models import LibraryAccessLog, LibraryCategory, LibraryFile, LibraryItem
from app.subscriptions import service as subs
from app.users.models import User

router = APIRouter(tags=["library"])
admin = APIRouter(prefix="/admin/library", tags=["admin-library"], dependencies=[Depends(require_roles("super_admin", "content_admin"))])
editor = Depends(require_roles("super_admin", "content_admin"))

MAX_BYTES = 25 * 1024 * 1024
ALLOWED = {"pdf": b"%PDF", "docx": b"PK", "pptx": b"PK", "xlsx": b"PK", "txt": None}


class ItemIn(BaseModel):
    category_slug: str = Field(max_length=60)
    title: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=4000)
    level: str = Field(default="", max_length=20)
    subject: str = Field(default="", max_length=100)
    tags: list[str] = Field(default_factory=list, max_length=15)
    access: str = Field(default="free", pattern="^(free|premium)$")
    is_sample: bool = False


class ItemPatch(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    tags: list[str] | None = Field(default=None, max_length=15)
    access: str | None = Field(default=None, pattern="^(free|premium)$")
    status: str | None = Field(default=None, pattern="^(draft|published|archived)$")
    level: str | None = Field(default=None, max_length=20)
    subject: str | None = Field(default=None, max_length=100)


def _current_file(db: Session, item_id) -> LibraryFile | None:
    return db.scalar(select(LibraryFile).where(LibraryFile.item_id == item_id).order_by(LibraryFile.version_no.desc()))


def _out(db: Session, i: LibraryItem, has_premium: bool | None = None, admin_view: bool = False) -> dict:
    f = _current_file(db, i.id)
    cat = db.get(LibraryCategory, i.category_id)
    out = {"id": str(i.id), "title": i.title, "description": i.description, "category": cat.slug if cat else "", "category_name": cat.name if cat else "",
           "level": i.level, "subject": i.subject, "tags": i.tags, "access": i.access, "is_sample": i.is_sample,
           "has_file": f is not None, "file_type": f.filename.rsplit(".", 1)[-1] if f else None, "size": f.size if f else None,
           "locked": i.access == "premium" and not has_premium}
    if admin_view:
        out |= {"status": i.status, "version": f.version_no if f else 0}
    return out


@router.get("/library/categories")
def categories(db: Session = Depends(get_db)):
    return [{"slug": c.slug, "name": c.name} for c in db.scalars(select(LibraryCategory).order_by(LibraryCategory.sort))]


@router.get("/library/items")
def items(q: str = Query("", max_length=100), category: str | None = None, level: str | None = None, subject: str | None = None, tag: str | None = None,
          access: str | None = Query(None, pattern="^(free|premium)$"), page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=50),
          user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    base = select(LibraryItem).where(LibraryItem.status == "published")
    if q:
        like = f"%{q}%"
        base = base.where(or_(LibraryItem.title.ilike(like), LibraryItem.description.ilike(like), LibraryItem.subject.ilike(like)))
    if category:
        base = base.join(LibraryCategory, LibraryCategory.id == LibraryItem.category_id).where(LibraryCategory.slug == category)
    if level:
        base = base.where(LibraryItem.level == level)
    if subject:
        base = base.where(LibraryItem.subject.ilike(subject))
    if access:
        base = base.where(LibraryItem.access == access)
    rows = list(db.scalars(base.order_by(LibraryItem.created_at.desc())))
    if tag:  # tags are a JSON list; filter in Python to stay database-agnostic
        rows = [r for r in rows if tag.lower() in [t.lower() for t in r.tags]]
    prem = subs.live(db, user.id) is not None
    return {"total": len(rows), "page": page, "items": [_out(db, r, prem) for r in rows[(page - 1) * page_size: page * page_size]]}


@router.get("/library/items/{item_id}")
def item(item_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    i = db.get(LibraryItem, item_id)
    if not i or i.status != "published":
        raise HTTPException(404, "not_found")
    return _out(db, i, subs.live(db, user.id) is not None)


@router.post("/library/items/{item_id}/download", dependencies=[Depends(rate_limit("lib_download", 60))])
def download(item_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    i = db.get(LibraryItem, item_id)
    if not i or i.status != "published":
        raise HTTPException(404, "not_found")
    if i.access == "premium" and subs.live(db, user.id) is None:
        raise HTTPException(403, "premium_required")  # enforced here on the server, not just by hiding the button
    f = _current_file(db, i.id)
    if not f:
        raise HTTPException(404, "no_file")
    db.add(LibraryAccessLog(item_id=i.id, file_id=f.id, user_id=user.id))
    db.commit()
    return {"url": get_storage().signed_url(f.storage_key, f.filename, f.mime, 300), "expires_in": 300, "filename": f.filename}


@router.get("/library/files/{token:path}")
def local_file(token: str):
    """Serves a locally stored file for a valid, unexpired signed token (the S3 backend uses presigned S3 URLs instead)."""
    d = verify_local_token(token)
    if not d:
        raise HTTPException(403, "invalid_or_expired_link")
    try:
        data = get_storage().get(d["k"])
    except (FileNotFoundError, ValueError):
        raise HTTPException(404, "not_found") from None
    return Response(data, media_type=d["t"], headers={"Content-Disposition": f'attachment; filename="{d["f"].replace(chr(34), "")}"', "Cache-Control": "private, no-store"})


@router.get("/library/downloads")
def history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(LibraryAccessLog, LibraryItem).join(LibraryItem, LibraryItem.id == LibraryAccessLog.item_id)
                      .where(LibraryAccessLog.user_id == user.id).order_by(LibraryAccessLog.created_at.desc()).limit(100)).all()
    return [{"item_id": str(i.id), "title": i.title, "downloaded_at": a.created_at} for a, i in rows]


# ------------------------------------------------------------------ admin
def _cat(db: Session, slug: str) -> LibraryCategory:
    c = db.scalar(select(LibraryCategory).where(LibraryCategory.slug == slug))
    if not c:
        raise HTTPException(422, "unknown_category")
    return c


@admin.post("/categories", status_code=201)
def create_category(slug: str = Query(pattern="^[a-z0-9-]{2,60}$"), name: str = Query(min_length=2, max_length=120), request: Request = None,
                    user: User = editor, db: Session = Depends(get_db)):
    if db.scalar(select(LibraryCategory).where(LibraryCategory.slug == slug)):
        raise HTTPException(409, "category_exists")
    c = LibraryCategory(slug=slug, name=name, sort=(db.scalar(select(func.max(LibraryCategory.sort))) or 0) + 1)
    db.add(c)
    audit(db, user, "library.category.create", "category", slug, after={"name": name}, request=request)
    db.commit()
    return {"slug": c.slug, "name": c.name}


@admin.get("/items")
def admin_items(db: Session = Depends(get_db)):
    return [_out(db, i, True, admin_view=True) for i in db.scalars(select(LibraryItem).order_by(LibraryItem.created_at.desc()).limit(300))]


@admin.post("/items", status_code=201)
def create_item(body: ItemIn, request: Request, user: User = editor, db: Session = Depends(get_db)):
    c = _cat(db, body.category_slug)
    i = LibraryItem(category_id=c.id, title=body.title, description=body.description, level=body.level, subject=body.subject, tags=body.tags,
                    access=body.access, is_sample=body.is_sample, status="draft")
    db.add(i)
    db.flush()
    audit(db, user, "library.item.create", "library_item", i.id, after=body.model_dump(), request=request)
    db.commit()
    return _out(db, i, True, admin_view=True)


@admin.patch("/items/{item_id}")
def patch_item(item_id: uuid.UUID, body: ItemPatch, request: Request, user: User = editor, db: Session = Depends(get_db)):
    i = db.get(LibraryItem, item_id)
    if not i:
        raise HTTPException(404, "not_found")
    ch = body.model_dump(exclude_none=True)
    if ch.get("status") == "published" and _current_file(db, i.id) is None:
        raise HTTPException(409, "upload_a_file_before_publishing")
    before = {k: getattr(i, k) for k in ch}
    for k, v in ch.items():
        setattr(i, k, v)
    audit(db, user, "library.item.update", "library_item", i.id, before=before, after=ch, request=request)
    db.commit()
    return _out(db, i, True, admin_view=True)


def _validate_upload(filename: str, data: bytes) -> tuple[str, str]:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED:
        raise HTTPException(422, "file_type_not_allowed")
    if len(data) == 0 or len(data) > MAX_BYTES:
        raise HTTPException(422, "file_size_invalid")
    magic = ALLOWED[ext]
    if magic is not None and not data.startswith(magic):  # content must match the claimed type
        raise HTTPException(422, "file_content_mismatch")
    if ext == "txt":
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(422, "file_content_mismatch") from None
    safe = re.sub(r"[^A-Za-z0-9._ -]", "_", filename.rsplit("/", 1)[-1])[:150]
    return ext, safe or f"file.{ext}"


@admin.post("/items/{item_id}/files", status_code=201)
async def upload(item_id: uuid.UUID, request: Request, file: UploadFile = File(...), user: User = editor, db: Session = Depends(get_db)):
    i = db.get(LibraryItem, item_id)
    if not i:
        raise HTTPException(404, "not_found")
    data = await file.read(MAX_BYTES + 1)
    ext, safe = _validate_upload(file.filename or "", data)
    mime = mimetypes.guess_type(f"x.{ext}")[0] or "application/octet-stream"
    cur = _current_file(db, i.id)
    key = f"library/{i.id}/{uuid.uuid4().hex}.{ext}"  # random key: user-supplied names never reach the file system
    get_storage().put(key, data, mime)
    v = LibraryFile(item_id=i.id, version_no=(cur.version_no + 1) if cur else 1, storage_key=key, filename=safe, mime=mime, size=len(data),
                    checksum=hashlib.sha256(data).hexdigest())
    db.add(v)
    audit(db, user, "library.file.upload", "library_item", i.id, after={"version": v.version_no, "filename": safe, "size": v.size}, request=request)
    db.commit()
    return _out(db, i, True, admin_view=True)


@admin.get("/downloads")
def admin_downloads(db: Session = Depends(get_db)):
    rows = db.execute(select(LibraryItem.title, func.count(LibraryAccessLog.id)).join(LibraryAccessLog, LibraryAccessLog.item_id == LibraryItem.id)
                      .group_by(LibraryItem.title).order_by(func.count(LibraryAccessLog.id).desc()).limit(50)).all()
    return [{"title": t, "downloads": n} for t, n in rows]


