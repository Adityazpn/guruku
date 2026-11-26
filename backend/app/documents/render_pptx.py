"""Doc -> PowerPoint. A heading (level 1-2) starts a slide; bullets/paragraphs become its body; tables become text rows."""
import io

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Inches, Pt

from app.documents.model import Doc

NAVY = RGBColor(0x0B, 0x1F, 0x4B)
MAX_LINES = 7  # per slide; longer content continues on a following slide so nothing is cut off


def _slides(doc: Doc) -> list[tuple[str, list[str]]]:
    out: list[tuple[str, list[str]]] = [(doc.title, [f"{k}: {v}" for k, v in doc.meta])]
    title, body = None, []
    for b in doc.blocks:
        if b.kind == "heading" and b.level <= 2:
            if title is not None:
                out.append((title, body))
            title, body = b.text, []
        elif title is None:
            title, body = doc.title, []
            body += _lines(b)
        else:
            body += _lines(b)
    if title is not None:
        out.append((title, body))
    final = []
    for t, lines in out:
        chunks = [lines[i:i + MAX_LINES] for i in range(0, max(len(lines), 1), MAX_LINES)] or [[]]
        final += [(t if n == 0 else f"{t} (lanjutan)", c) for n, c in enumerate(chunks)]
    return final


def _lines(b) -> list[str]:
    if b.kind in ("bullets", "numbered"):
        return list(b.items)
    if b.kind == "table":
        return [" | ".join(r) for r in b.rows]
    return [x for x in b.text.split("\n") if x.strip()] if b.kind == "paragraph" else []


def render_pptx(doc: Doc) -> bytes:
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)  # 16:9
    for i, (title, lines) in enumerate(_slides(doc)):
        slide = prs.slides.add_slide(prs.slide_layouts[5])  # title only
        t = slide.shapes.title
        t.text = title
        t.text_frame.paragraphs[0].font.size, t.text_frame.paragraphs[0].font.bold, t.text_frame.paragraphs[0].font.color.rgb = Pt(34 if i else 40), True, NAVY
        box = slide.shapes.add_textbox(Inches(0.8), Inches(1.8), Inches(11.7), Inches(4.8))
        tf = box.text_frame
        tf.word_wrap = True
        for n, line in enumerate(lines):
            p = tf.paragraphs[0] if n == 0 else tf.add_paragraph()
            p.text = ("• " if i else "") + line
            p.font.size = Pt(22 if len(line) < 110 else 18)
            p.space_after = Pt(8)
        foot = slide.shapes.add_textbox(Inches(0.8), Inches(6.9), Inches(11.7), Inches(0.4))
        foot.text_frame.text = doc.footer[:150]
        foot.text_frame.paragraphs[0].font.size = Pt(9)
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()
