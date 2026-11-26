import io

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from app.documents.model import Doc

NAVY = RGBColor(0x0B, 0x1F, 0x4B)


def _field(run, instr: str) -> None:
    for t, txt in (("begin", None), (None, instr), ("end", None)):
        if t:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), t)
        else:
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = txt
        run._r.append(el)


def render_docx(doc: Doc) -> bytes:
    d = Document()
    sec = d.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)  # A4
    sec.left_margin = sec.right_margin = sec.top_margin = sec.bottom_margin = Cm(2.54)
    normal = d.styles["Normal"]
    normal.font.name, normal.font.size = "Calibri", Pt(11)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")
    for name, size in (("Heading 1", 16), ("Heading 2", 13), ("Heading 3", 12)):
        st = d.styles[name]
        st.font.name, st.font.size, st.font.color.rgb = "Calibri", Pt(size), NAVY

    t = d.add_paragraph()
    r = t.add_run(doc.title)
    r.bold, r.font.size, r.font.color.rgb = True, Pt(20), NAVY
    t.alignment = WD_ALIGN_PARAGRAPH.LEFT
    if doc.meta:
        tbl = d.add_table(rows=0, cols=2)
        tbl.style = "Table Grid"
        for k, v in doc.meta:
            cells = tbl.add_row().cells
            cells[0].text, cells[1].text = k, v
            cells[0].paragraphs[0].runs[0].bold = True
            cells[0].width, cells[1].width = Cm(4.5), Cm(11.5)
        d.add_paragraph()
    for b in doc.blocks:
        if b.kind == "heading":
            d.add_heading(b.text, level=min(max(b.level, 1), 3))
        elif b.kind == "paragraph":
            d.add_paragraph(b.text)
        elif b.kind in ("bullets", "numbered"):
            for it in b.items:
                d.add_paragraph(it, style="List Bullet" if b.kind == "bullets" else "List Number")
        elif b.kind == "table" and b.rows:
            tbl = d.add_table(rows=len(b.rows), cols=len(b.rows[0]))
            tbl.style = "Table Grid"
            for i, row in enumerate(b.rows):
                for j, val in enumerate(row):
                    tbl.cell(i, j).text = val
                    if i == 0:
                        tbl.cell(i, j).paragraphs[0].runs[0].bold = True
            d.add_paragraph()

    fp = sec.footer.paragraphs[0]
    fr = fp.add_run(doc.footer + "\nHalaman ")
    fr.font.size = Pt(8)
    pr = fp.add_run()
    pr.font.size = Pt(8)
    _field(pr, "PAGE")
    fp.add_run(" dari ").font.size = Pt(8)
    nr = fp.add_run()
    nr.font.size = Pt(8)
    _field(nr, "NUMPAGES")
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER

    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()
