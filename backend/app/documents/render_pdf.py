import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.documents.model import Doc

NAVY = colors.HexColor("#0B1F4B")


def render_pdf(doc: Doc) -> bytes:
    ss = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=ss["BodyText"], fontName="Helvetica", fontSize=10.5, leading=14.5, spaceAfter=6)
    title = ParagraphStyle("title", parent=ss["Title"], fontName="Helvetica-Bold", fontSize=20, textColor=NAVY, alignment=0)
    heads = {n: ParagraphStyle(f"h{n}", parent=body, fontName="Helvetica-Bold", fontSize=s, textColor=NAVY,
                               spaceBefore=10, spaceAfter=4, keepWithNext=1) for n, s in ((1, 15), (2, 12.5), (3, 11.5))}
    P = lambda t, st: Paragraph(escape(t).replace("\n", "<br/>"), st)  # noqa: E731

    story = [P(doc.title, title), Spacer(1, 6)]
    if doc.meta:
        t = Table([[P(k, body), P(v, body)] for k, v in doc.meta], colWidths=[4.5 * cm, 11.5 * cm])
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story += [t, Spacer(1, 10)]
    for b in doc.blocks:
        if b.kind == "heading":
            story.append(P(b.text, heads[min(max(b.level, 1), 3)]))
        elif b.kind == "paragraph":
            story.append(P(b.text, body))
        elif b.kind in ("bullets", "numbered"):
            story.append(ListFlowable([ListItem(P(i, body)) for i in b.items],
                                      bulletType="bullet" if b.kind == "bullets" else "1", leftIndent=14))
        elif b.kind == "table" and b.rows:
            t = Table([[P(c, body) for c in row] for row in b.rows], repeatRows=1)  # header repeats on each page
            t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E6F2FF")),
                                   ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            story += [t, Spacer(1, 8)]

    def footer(canvas, d):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.grey)
        for i, line in enumerate(_wrap(doc.footer, 120)):
            canvas.drawCentredString(A4[0] / 2, 1.5 * cm + 9 * (1 - i), line)
        canvas.drawCentredString(A4[0] / 2, 0.9 * cm, f"Halaman {d.page}")
        canvas.restoreState()

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=2.54 * cm, rightMargin=2.54 * cm, topMargin=2.54 * cm,
                      bottomMargin=2.54 * cm, title=doc.title, author="Guruku").build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


def _wrap(text: str, n: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > n:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    return lines + [cur]
