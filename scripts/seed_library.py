"""Creates the library categories from the spec and a few SAMPLE items (clearly labelled "[CONTOH]", flagged is_sample) so the library is not empty
before real, reviewed resources are supplied. Replace/archive them in Admin > Pustaka. Usage (from backend/): python ../scripts/seed_library.py"""
import hashlib
import io
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from docx import Document  # noqa: E402

import app.models  # noqa: E402,F401
from app.core import db as dbmod  # noqa: E402
from app.core.storage import get_storage  # noqa: E402
from app.library.models import LibraryCategory, LibraryFile, LibraryItem  # noqa: E402

CATS = [("template-slide", "Template Slide Mengajar"), ("template-administrasi", "Template Administrasi Kelas"), ("template-portofolio", "Template Portofolio Guru"),
        ("template-lkpd", "Template LKPD"), ("template-modul-ajar", "Template Modul Ajar"), ("template-rpp", "Template RPP"), ("template-ujian", "Template Ujian"),
        ("ebook", "E-book Pendidikan"), ("panduan-administrasi", "Panduan Administrasi Guru"), ("panduan-ai", "Panduan AI untuk Guru"), ("kumpulan-prompt", "Kumpulan Prompt Pendidikan")]
SAMPLES = [("template-rpp", "[CONTOH] Kerangka RPP", "SD/MI", "free"), ("template-lkpd", "[CONTOH] Kerangka LKPD", "SMP/MTs", "free"),
           ("kumpulan-prompt", "[CONTOH] Contoh Prompt untuk Guru", "", "premium")]

dbmod.get_engine()
store = get_storage()
with dbmod._SessionLocal() as db:
    for i, (slug, name) in enumerate(CATS):
        if not db.query(LibraryCategory).filter_by(slug=slug).first():
            db.add(LibraryCategory(slug=slug, name=name, sort=i))
    db.flush()
    for slug, title, level, access in SAMPLES:
        if db.query(LibraryItem).filter_by(title=title).first():
            continue
        cat = db.query(LibraryCategory).filter_by(slug=slug).one()
        item = LibraryItem(category_id=cat.id, title=title, description="Konten contoh untuk menguji pustaka. BUKAN sumber resmi; akan diganti dengan materi yang sudah ditinjau.",
                           level=level, tags=["contoh"], access=access, is_sample=True, status="published")
        db.add(item)
        db.flush()
        d = Document()
        d.add_heading(title, 1)
        d.add_paragraph("Ini adalah dokumen contoh. Ganti dengan materi asli yang telah dibuat dan ditinjau.")
        buf = io.BytesIO()
        d.save(buf)
        data = buf.getvalue()
        key = f"library/{item.id}/{uuid.uuid4().hex}.docx"
        store.put(key, data, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        db.add(LibraryFile(item_id=item.id, version_no=1, storage_key=key, filename="contoh.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                           size=len(data), checksum=hashlib.sha256(data).hexdigest()))
    db.commit()
print("library seeded (categories + labelled sample items)")
