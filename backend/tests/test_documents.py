import io

import pytest
from docx import Document
from pypdf import PdfReader

from app.documents.builders import build
from app.documents.model import Block, Doc
from app.documents.render_docx import render_docx
from app.documents.render_pdf import render_pdf

OUT = {"tujuan_pembelajaran": [
    {"tujuan": "Peserta didik mampu menjelaskan pecahan senilai — “dengan benar”.",
     "indikator": ["Menyebutkan pengertian pecahan", "Membandingkan ½ dan ¼"], "level_kognitif": "C2"}],
    "catatan": "Asumsi: siswa sudah mengenal bilangan cacah."}
INP = {"education_level": "SD/MI", "curriculum": "Kurikulum Merdeka", "subject": "Matematika", "grade": "4", "topic": "Pecahan"}


def docx_text(data: bytes) -> str:
    d = Document(io.BytesIO(data))
    parts = [p.text for p in d.paragraphs] + [c.text for t in d.tables for r in t.rows for c in r.cells]
    parts += [p.text for p in d.sections[0].footer.paragraphs]
    return "\n".join(parts)


def pdf_text(data: bytes) -> str:
    return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(data)).pages)


def test_docx_has_all_content_footer_pagenumber_fields_and_a4_margins():
    data = render_docx(build("tp-generator", "Generator TP", INP, OUT))
    t = docx_text(data)
    for needle in ("Tujuan Pembelajaran", "Matematika", "TP 1 (C2)", "pecahan senilai", "“dengan benar”", "Membandingkan ½ dan ¼",
                   "Asumsi: siswa", "draf yang dihasilkan AI", "Halaman"):
        assert needle in t, needle
    sec = Document(io.BytesIO(data)).sections[0]
    assert round(sec.page_width.cm, 1) == 21.0 and round(sec.left_margin.cm, 2) == 2.54
    assert b"NUMPAGES" in data or b"NUMPAGES" in _raw(data)


def _raw(data: bytes) -> bytes:
    import zipfile
    z = zipfile.ZipFile(io.BytesIO(data))
    return b"".join(z.read(n) for n in z.namelist() if n.startswith("word/footer"))


def test_pdf_contains_content_and_disclaimer_and_page_number():
    data = render_pdf(build("tp-generator", "Generator TP", INP, OUT))
    assert data[:4] == b"%PDF"
    t = pdf_text(data)
    for needle in ("Tujuan Pembelajaran", "Kurikulum Merdeka", "TP 1 (C2)", "Membandingkan", "Catatan untuk guru",
                   "draf yang dihasilkan AI", "Halaman 1"):
        assert needle in t, needle


def test_long_document_is_not_truncated_and_paginates():
    items = [f"Butir nomor {i} untuk memastikan tidak ada konten yang terpotong." for i in range(400)]
    doc = Doc("Dokumen Panjang", blocks=[Block("heading", "Daftar"), Block("bullets", items=items)])
    t = pdf_text(render_pdf(doc))
    assert "Butir nomor 0 " in t and "Butir nomor 399 " in t
    assert len(PdfReader(io.BytesIO(render_pdf(doc))).pages) > 3
    assert "Butir nomor 399" in docx_text(render_docx(doc))


def test_table_header_repeats_across_pages():
    rows = [["No", "Uraian"]] + [[str(i), f"Baris {i}"] for i in range(150)]
    data = render_pdf(Doc("Tabel", blocks=[Block("table", rows=rows)]))
    pages = PdfReader(io.BytesIO(data)).pages
    assert len(pages) > 1 and all("Uraian" in p.extract_text() for p in pages)


def test_unknown_tool_falls_back_without_dropping_content():
    d = build("some-new-tool", "Alat Baru", INP, {"bagian": {"isi": ["a", "b"], "ringkas": "teks"}, "x": [{"k": "v"}]})
    t = docx_text(render_docx(d))
    for needle in ("a", "b", "teks", "v", "Alat Baru"):
        assert needle in t


def test_special_characters_in_user_text_do_not_break_pdf():
    doc = Doc("Uji <b>&", blocks=[Block("paragraph", "5 < 6 & 7 > 3 <script>x</script>")])
    assert "<script>" in pdf_text(render_pdf(doc))  # shown literally, not interpreted


@pytest.mark.parametrize("fmt", ["docx", "pdf"])
def test_export_endpoint(pg_client, pg, fmt):
    from app.ai_providers.adapters.fake import FakeProvider
    from tests.aihelpers import TP_INPUT, VALID, reset_fake, setup_ai
    reset_fake()
    with pg() as db:
        setup_ai(db)
        db.commit()
    c = pg_client
    pw = "correct-horse-battery"
    for e in ("a@example.com", "b@example.com"):
        c.post("/api/v1/auth/register", json={"email": e, "password": pw})
    h = lambda e: {"Authorization": "Bearer " + c.post("/api/v1/auth/login", json={"email": e, "password": pw}).json()["access_token"]}  # noqa: E731
    FakeProvider.script = [VALID]
    rid = c.post("/api/v1/tools/tp-generator/generate", json={"input": TP_INPUT},
                 headers={**h("a@example.com"), "Idempotency-Key": "export-key-1"}).json()["id"]
    r = c.get(f"/api/v1/ai/requests/{rid}/export?format={fmt}", headers=h("a@example.com"))
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    assert ("Peserta didik mampu" in (docx_text(r.content) if fmt == "docx" else pdf_text(r.content)))
    assert c.get(f"/api/v1/ai/requests/{rid}/export?format={fmt}", headers=h("b@example.com")).status_code == 404
    assert c.get(f"/api/v1/ai/requests/{rid}/export?format=exe", headers=h("a@example.com")).status_code == 422
    assert c.get(f"/api/v1/ai/requests/{rid}/export").status_code == 401
