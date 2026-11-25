# Exports the report as a PDF (the default download) and as an editable Word file. Both draw the same display blocks as the website
# (backend/report_blocks.py), so all three show the same content. A demo report carries the DEMO label in the header of every page.
import html
import io

import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

RED, GREY, AMBER = colors.HexColor("#9b1c1c"), colors.HexColor("#52606d"), colors.HexColor("#8a5a00")
# The PDF's built-in fonts cover Western European text; these few signs are swapped for close equivalents.
SWAPS = {"−": "-", "→": "->", "≤": "<=", "≥": ">="}


def _clean(text) -> str:
    text = str(text if text is not None else "")
    for sign, plain in SWAPS.items():
        text = text.replace(sign, plain)
    return text


def _esc(text) -> str:
    return html.escape(_clean(text), quote=False)


def _sources(item: dict) -> str:
    parts = []
    for s in item["sources"]:
        label = _esc(s["text"])
        parts.append(f'<a href="{html.escape(s["url"])}" color="#2f5d8a">{label}</a>' if s.get("url") else label)
    return "Source: " + "; ".join(parts)


# ---------- PDF ----------

def _styles() -> dict:
    base = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=base["BodyText"], fontName="Helvetica", fontSize=9.5, leading=12.5, spaceAfter=4)
    return {
        "title": ParagraphStyle("title", parent=base["Title"], fontName="Helvetica-Bold", fontSize=16, leading=20, alignment=0, spaceAfter=4),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=13, leading=16, spaceBefore=12, spaceAfter=4),
        "h3": ParagraphStyle("h3", parent=base["Heading3"], fontName="Helvetica-Bold", fontSize=11, leading=14, spaceBefore=8, spaceAfter=2),
        "h4": ParagraphStyle("h4", parent=body, fontName="Helvetica-Bold", spaceBefore=6),
        "body": body,
        "tag": ParagraphStyle("tag", parent=body, fontName="Helvetica-Bold", fontSize=8, textColor=GREY, spaceAfter=0),
        "small": ParagraphStyle("small", parent=body, fontSize=8, leading=10, textColor=GREY),
        "issue": ParagraphStyle("issue", parent=body, fontSize=8.5, leading=11, textColor=AMBER),
        "cell": ParagraphStyle("cell", parent=body, fontSize=7.5, leading=9.5, spaceAfter=0),
        "banner": ParagraphStyle("banner", parent=body, fontName="Helvetica-Bold", textColor=RED, alignment=TA_CENTER, borderColor=RED,
                                 borderWidth=0.8, borderPadding=5, backColor=colors.HexColor("#fde8e8"), spaceBefore=4, spaceAfter=10),
    }


def _pdf_table(block: dict, st: dict, width: float) -> list:
    columns = block["columns"]
    if len(columns) == 5:  # key figures: give the status and notes column the most room
        widths = [w * width for w in (0.16, 0.11, 0.11, 0.15, 0.47)]
    else:
        widths = [0.28 * width] + [0.72 * width / (len(columns) - 1)] * (len(columns) - 1)
    rows = [[Paragraph(f"<b>{_esc(c)}</b>", st["cell"]) for c in columns]]
    rows += [[Paragraph(_esc(cell), st["cell"]) for cell in row] for row in block["rows"]]
    table = Table(rows, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c5ccd3")),
                               ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef1f4")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return [table] + [Paragraph(_esc(note), st["small"]) for note in block.get("notes", [])]


def _pdf_flowables(view: dict, st: dict, width: float) -> list:
    out = []
    for block in view["blocks"]:
        kind = block["type"]
        if kind == "banner":
            out.append(Paragraph(_esc(block["text"]), st["banner"]))
        elif kind == "heading":
            out.append(Paragraph(_esc(block["text"]), st["title" if block["level"] == 1 else "h2" if block["level"] == 2 else "h3"]))
        elif kind == "paragraph":
            out.append(Paragraph(_esc(block["text"]), st["body"]))
        elif kind == "statements":
            if not block["items"]:
                out.append(Paragraph("Nothing to show.", st["small"]))
            for item in block["items"]:
                if item.get("tag"):
                    out.append(Paragraph(_esc(item["tag"]), st["tag"]))
                badge = '<font color="#8a5a00"><b>[Unverified]</b></font> ' if item["label"] == "unverified" else ""
                out.append(Paragraph(badge + _esc(item["text"]), st["body"]))
                if item["sources"]:
                    out.append(Paragraph(_sources(item), st["small"]))
                for issue in item["issues"]:
                    out.append(Paragraph(_esc(issue), st["issue"]))
                out.append(Spacer(1, 3))
        elif kind == "table":
            out += _pdf_table(block, st, width)
        elif kind == "list":
            if block.get("title"):
                out.append(Paragraph(_esc(block["title"]), st["h4"]))
            style = st["issue"] if block.get("style") == "warn" else st["body"]
            out += [Paragraph("• " + _esc(item), style) for item in block["items"]]
    return out


def to_pdf(view: dict) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=1.8 * cm, rightMargin=1.8 * cm, topMargin=2.2 * cm, bottomMargin=1.8 * cm,
                            title=_clean(view["title"]), author="Financial Report Analysis Agent")
    label = view.get("demo_label")

    def decorate(canvas, document):
        canvas.saveState()
        if label:  # the DEMO label on every page
            canvas.setFont("Helvetica-Bold", 9)
            canvas.setFillColor(RED)
            canvas.drawCentredString(A4[0] / 2, A4[1] - 1.2 * cm, _clean(label))
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(GREY)
        canvas.drawRightString(A4[0] - 1.8 * cm, 1.0 * cm, f"Page {document.page}")
        canvas.drawString(1.8 * cm, 1.0 * cm, _clean(view["title"]))
        canvas.restoreState()

    doc.build(_pdf_flowables(view, _styles(), doc.width), onFirstPage=decorate, onLaterPages=decorate)
    return buffer.getvalue()


# ---------- Word ----------

def _run(paragraph, text, bold=False, size=None, color=None):
    run = paragraph.add_run(text)
    run.bold = bold
    if size:
        run.font.size = Pt(size)
    if color:
        run.font.color.rgb = RGBColor.from_string(color)
    return run


def to_docx(view: dict) -> bytes:
    document = docx.Document()
    document.core_properties.title = view["title"]
    document.styles["Normal"].font.size = Pt(10)
    label = view.get("demo_label")
    if label:  # a header repeats on every page
        header = document.sections[0].header.paragraphs[0]
        header.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _run(header, label, bold=True, size=9, color="9B1C1C")
    for block in view["blocks"]:
        kind = block["type"]
        if kind == "banner":
            p = document.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _run(p, block["text"], bold=True, color="9B1C1C")
        elif kind == "heading":
            document.add_heading(block["text"], level=min(block["level"] - 1, 3) if block["level"] > 1 else 0)
        elif kind == "paragraph":
            document.add_paragraph(block["text"])
        elif kind == "statements":
            if not block["items"]:
                _run(document.add_paragraph(), "Nothing to show.", size=9, color="52606D")
            for item in block["items"]:
                if item.get("tag"):
                    _run(document.add_paragraph(), item["tag"], bold=True, size=8, color="52606D")
                p = document.add_paragraph()
                if item["label"] == "unverified":
                    _run(p, "[Unverified] ", bold=True, color="8A5A00")
                _run(p, item["text"])
                if item["sources"]:
                    sources = "; ".join(s["text"] + (f" ({s['url']})" if s.get("url") else "") for s in item["sources"])
                    _run(document.add_paragraph(), "Source: " + sources, size=8, color="52606D")
                for issue in item["issues"]:
                    _run(document.add_paragraph(), issue, size=8.5, color="8A5A00")
        elif kind == "table":
            table = document.add_table(rows=1, cols=len(block["columns"]))
            table.style = "Table Grid"
            for cell, name in zip(table.rows[0].cells, block["columns"]):
                cell.text = ""
                _run(cell.paragraphs[0], name, bold=True, size=8)
            for row in block["rows"]:
                cells = table.add_row().cells
                for cell, value in zip(cells, row):
                    cell.text = ""
                    _run(cell.paragraphs[0], value, size=8)
            for note in block.get("notes", []):
                _run(document.add_paragraph(), note, size=8, color="52606D")
        elif kind == "list":
            if block.get("title"):
                _run(document.add_paragraph(), block["title"], bold=True)
            for item in block["items"]:
                p = document.add_paragraph(style="List Bullet")
                _run(p, item, color="8A5A00" if block.get("style") == "warn" else None)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()
