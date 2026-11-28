# Exports the report as a PDF (the default download) and as an editable Word file. Both draw the same display blocks as the website
# (backend/report_blocks.py), so all three show the same content.
import html
import io

import docx
from docx.shared import Pt, RGBColor
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

GREY, AMBER = colors.HexColor("#52606d"), colors.HexColor("#8a5a00")
NAVY, RULE, SHADE = colors.HexColor("#0b2545"), colors.HexColor("#c9d1db"), colors.HexColor("#f2f4f7")
FOOTER = "For educational purposes only. Not investment advice."
# The PDF's built-in fonts cover Western European text; these few signs are swapped for close equivalents.
SWAPS = {"−": "-", "→": "->", "≤": "<=", "≥": ">="}


def _clean(text) -> str:
    text = str(text if text is not None else "")
    for sign, plain in SWAPS.items():
        text = text.replace(sign, plain)
    return text


def _esc(text) -> str:
    return html.escape(_clean(text), quote=False)


def _marks(item: dict) -> str:
    """Footnote numbers after a point, as superscript."""
    return f' <super><font size="6.5" color="#2f5d8a">{",".join(str(n) for n in item.get("notes", []))}</font></super>' if item.get("notes") else ""


# ---------- PDF ----------

def _styles() -> dict:
    base = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=base["BodyText"], fontName="Helvetica", fontSize=9.5, leading=12.5, spaceAfter=4)
    return {
        "kicker": ParagraphStyle("kicker", parent=body, fontName="Helvetica-Bold", fontSize=8, textColor=GREY, spaceAfter=2),
        "title": ParagraphStyle("title", parent=base["Title"], fontName="Times-Bold", fontSize=21, leading=25, alignment=0, spaceAfter=4,
                                textColor=NAVY),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName="Times-Bold", fontSize=14, leading=17, spaceBefore=14, spaceAfter=2,
                             textColor=NAVY, keepWithNext=1),
        "h3": ParagraphStyle("h3", parent=base["Heading3"], fontName="Helvetica-Bold", fontSize=9.5, leading=12, spaceBefore=8, spaceAfter=2,
                             textColor=NAVY, keepWithNext=1),
        "exhibit": ParagraphStyle("exhibit", parent=body, fontName="Helvetica-Bold", fontSize=8.5, textColor=NAVY, spaceBefore=6, spaceAfter=3),
        "source": ParagraphStyle("source", parent=body, fontName="Helvetica-Oblique", fontSize=7, leading=9, textColor=GREY, spaceBefore=2),
        "head": ParagraphStyle("head", parent=body, fontName="Helvetica-Bold", fontSize=6.6, leading=8.5, spaceAfter=0, textColor=colors.white),
        "lead": ParagraphStyle("lead", parent=body, fontName="Helvetica-Bold"),
        "point": ParagraphStyle("point", parent=body, leftIndent=11, bulletIndent=0, spaceAfter=5),
        "note": ParagraphStyle("note", parent=body, fontSize=6.8, leading=9, textColor=GREY, spaceAfter=6),
        "headline": ParagraphStyle("headline", parent=body, fontName="Times-Bold", fontSize=11, leading=14, textColor=NAVY, spaceBefore=2,
                                   spaceAfter=3),
        "box": ParagraphStyle("box", parent=body, fontSize=8.5, leading=11, spaceAfter=3),
        "subtitle": ParagraphStyle("subtitle", parent=body, fontSize=9, textColor=GREY, spaceAfter=2),
        "num": ParagraphStyle("num", parent=body, fontSize=7.5, leading=9.5, spaceAfter=0, alignment=2),
        "h4": ParagraphStyle("h4", parent=body, fontName="Helvetica-Bold", spaceBefore=6),
        "body": body,
        "tag": ParagraphStyle("tag", parent=body, fontName="Helvetica-Bold", fontSize=8, textColor=GREY, spaceAfter=0),
        "small": ParagraphStyle("small", parent=body, fontSize=8, leading=10, textColor=GREY),
        "issue": ParagraphStyle("issue", parent=body, fontSize=8.5, leading=11, textColor=AMBER),
        "cell": ParagraphStyle("cell", parent=body, fontSize=7.5, leading=9.5, spaceAfter=0),
    }


def _pdf_table(block: dict, st: dict, width: float) -> list:
    """A bank-style exhibit: navy header row, thin rules between rows, figures right-aligned, the source underneath."""
    columns = block["columns"]
    if len(columns) == 5 and columns[-1] == "Status and notes":  # all indicators: give the notes column the most room
        widths = [w * width for w in (0.16, 0.11, 0.11, 0.15, 0.47)]
    else:
        first = 0.5 if len(columns) <= 2 else 0.22 if len(columns) > 7 else 0.30  # wide comparables tables give the figures more room
        widths = [first * width] + [(1 - first) * width / (len(columns) - 1)] * (len(columns) - 1)
    numeric = block.get("title", "").startswith("Exhibit")
    rows = [[Paragraph(_esc(c), st["head"]) for c in columns]]
    rows += [[Paragraph(_esc(cell), st["num"] if numeric and i else st["cell"]) for i, cell in enumerate(row)] for row in block["rows"]]
    table = Table(rows, colWidths=widths, repeatRows=1)
    style = [("BACKGROUND", (0, 0), (-1, 0), NAVY), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("LINEBELOW", (0, 1), (-1, -1), 0.3, RULE), ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
             ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]
    if block["rows"] and block["rows"][-1][0] == "Peer median":
        style += [("BACKGROUND", (0, -1), (-1, -1), SHADE), ("LINEABOVE", (0, -1), (-1, -1), 0.8, NAVY)]
    table.setStyle(TableStyle(style))
    out = [Paragraph(_esc(block["title"]), st["exhibit"])] if block.get("title") else []
    out.append(table)
    if block.get("source"):
        out.append(Paragraph(_esc(block["source"]), st["source"]))
    out += [Paragraph(_esc(note), st["small"]) for note in block.get("notes", [])]
    return [KeepTogether(out)] if numeric and len(block["rows"]) < 25 else out


def _pdf_summarybox(block: dict, st: dict, width: float) -> list:
    """The first-page box of a research note: key comparisons on the left, key data and peers on the right."""
    left_w, right_w = 0.6 * width, 0.4 * width
    left = [Paragraph("KEY COMPARISONS", st["kicker"])]
    left += [Paragraph("• " + _esc(line), st["box"]) for line in block["comparisons"]] or [Paragraph("No peer comparison available.", st["box"])]
    data = Table([[Paragraph(_esc(label), st["small"]), Paragraph(f"<b>{_esc(value)}</b>", st["num"])] for label, value in block["key_data"]],
                 colWidths=[0.55 * (right_w - 12), 0.45 * (right_w - 12)])
    data.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -2), 0.3, RULE), ("TOPPADDING", (0, 0), (-1, -1), 2),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 2), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    right = [Paragraph("KEY DATA", st["kicker"]), data, Spacer(1, 6), Paragraph(f"<b>Peers:</b> {_esc(block['peers'])}", st["small"])]
    box = Table([[left, right]], colWidths=[left_w, right_w])
    box.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEABOVE", (0, 0), (-1, 0), 1.4, NAVY),
                             ("BACKGROUND", (1, 0), (1, 0), SHADE), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                             ("LEFTPADDING", (0, 0), (0, 0), 0), ("RIGHTPADDING", (0, 0), (0, 0), 10), ("LEFTPADDING", (1, 0), (1, 0), 6),
                             ("RIGHTPADDING", (1, 0), (1, 0), 6), ("LINEBELOW", (0, 0), (-1, 0), 0.4, RULE)]))
    return [Spacer(1, 6), box, Spacer(1, 4)]


def _pdf_flowables(view: dict, st: dict, width: float) -> list:
    out = []
    for block in view["blocks"]:
        kind = block["type"]
        if kind == "heading" and block["level"] == 1:
            out += [Paragraph("COMPANY ANALYSIS", st["kicker"]), Paragraph(_esc(block["text"]), st["title"])]
        elif kind == "heading" and block["level"] == 2:
            out += [Paragraph(_esc(block["text"]), st["h2"]), HRFlowable(width="100%", thickness=0.8, color=NAVY, spaceAfter=4)]
        elif kind == "heading":
            out.append(Paragraph(_esc(block["text"]), st["h3"]))
        elif kind == "summarybox":
            out += _pdf_summarybox(block, st, width)
        elif kind == "paragraph" and out and getattr(out[-1], "style", None) is st["title"]:  # the line under the title
            out.append(Paragraph(_esc(block["text"]), st["subtitle"]))
        elif kind == "paragraph":
            out.append(Paragraph(_esc(block["text"]), st[{"lead": "lead", "note": "small"}.get(block.get("style"), "body")]))
        elif kind == "commentary":  # a section's headline and paragraph, with its footnote numbers
            if block.get("headline"):
                out.append(Paragraph(_esc(block["headline"]), st["headline"]))
            out.append(Paragraph(_esc(block["text"]) + _marks(block), st["body"]))
        elif kind == "statements":
            if not block["items"]:
                out.append(Paragraph("Nothing to show.", st["small"]))
            for item in block["items"]:
                if item.get("tag"):
                    out.append(Paragraph(_esc(item["tag"]), st["tag"]))
                badge = '<font color="#8a5a00"><b>[Unverified]</b></font> ' if item["label"] == "unverified" else ""
                out.append(Paragraph(badge + _esc(item["text"]) + _marks(item), st["point"], bulletText="•"))
                for issue in item["issues"]:
                    out.append(Paragraph(_esc(issue), st["issue"]))
        elif kind == "footnotes":  # the section's sources in one line of small print
            parts = []
            for note in block["items"]:
                text = _esc(note["text"])
                if note.get("url"):
                    text = f'<a href="{html.escape(note["url"])}" color="#52606d">{text}</a>'
                parts.append(f'<super><font color="#2f5d8a"><b>{note["number"]}</b></font></super>&nbsp;{text}')
            out += [Spacer(1, 2), HRFlowable(width="100%", thickness=0.4, color=RULE, spaceAfter=2),
                    Paragraph(' <font color="#b6c0cc">·</font> '.join(parts), st["note"])]
        elif kind == "table":
            out += _pdf_table(block, st, width)
        elif kind == "list":
            if block.get("title"):
                out.append(Paragraph(_esc(block["title"]), st["h4"]))
            style = {"warn": st["issue"], "small": st["small"], "warn-small": st["issue"]}.get(block.get("style"), st["body"])
            out += [Paragraph("• " + _esc(item), style) for item in block["items"]]
    return out


def _keep_headings_with_text(flowables: list) -> list:
    """A section heading, its rule and the first thing under it go on the same page."""
    out, i = [], 0
    while i < len(flowables):
        f = flowables[i]
        if isinstance(f, Paragraph) and f.style.name == "h2" and i + 2 < len(flowables) and isinstance(flowables[i + 1], HRFlowable):
            out.append(KeepTogether(flowables[i:i + 3]))
            i += 3
        else:
            out.append(f)
            i += 1
    return out


def to_pdf(view: dict) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=1.8 * cm, rightMargin=1.8 * cm, topMargin=2.2 * cm, bottomMargin=1.8 * cm,
                            title=_clean(view["title"]), author="Financial Report Analysis Agent")

    def decorate(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(NAVY)
        canvas.setLineWidth(0.6)
        canvas.line(1.8 * cm, A4[1] - 1.5 * cm, A4[0] - 1.8 * cm, A4[1] - 1.5 * cm)
        canvas.setFont("Times-Bold", 10)
        canvas.setFillColor(NAVY)
        canvas.drawString(1.8 * cm, A4[1] - 1.3 * cm, "Verity")
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(GREY)
        canvas.drawString(1.8 * cm + canvas.stringWidth("Verity", "Times-Bold", 10) + 6, A4[1] - 1.3 * cm, "Financial Report Analysis Agent")
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(GREY)
        canvas.drawRightString(A4[0] - 1.8 * cm, A4[1] - 1.3 * cm, "Company analysis")
        canvas.drawCentredString(A4[0] / 2, 0.65 * cm, FOOTER)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(GREY)
        canvas.drawRightString(A4[0] - 1.8 * cm, 1.0 * cm, f"Page {document.page}")
        canvas.drawString(1.8 * cm, 1.0 * cm, _clean(view["title"]))
        canvas.restoreState()

    doc.build(_keep_headings_with_text(_pdf_flowables(view, _styles(), doc.width)), onFirstPage=decorate, onLaterPages=decorate)
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


def _word_marks(paragraph, item: dict):
    if item.get("notes"):
        run = _run(paragraph, " " + ",".join(str(n) for n in item["notes"]), size=7, color="2F5D8A")
        run.font.superscript = True


def to_docx(view: dict) -> bytes:
    document = docx.Document()
    document.core_properties.title = view["title"]
    document.styles["Normal"].font.size = Pt(10)
    for name in ("Title", "Heading 1", "Heading 2"):  # serif headings in navy, as in a bank's report
        document.styles[name].font.name = "Times New Roman"
        document.styles[name].font.color.rgb = RGBColor.from_string("0B2545")
    footer = document.sections[0].footer.paragraphs[0]
    _run(footer, FOOTER, size=7, color="52606D")
    header = document.sections[0].header.paragraphs[0]
    _run(header, "Verity", bold=True, size=10, color="0B2545")
    _run(header, "  Financial Report Analysis Agent", size=7.5, color="52606D")
    for block in view["blocks"]:
        kind = block["type"]
        if kind == "heading":
            if block["level"] == 1:
                _run(document.add_paragraph(), "COMPANY ANALYSIS", bold=True, size=8, color="52606D")
            document.add_heading(block["text"], level=min(block["level"] - 1, 3) if block["level"] > 1 else 0)
        elif kind == "summarybox":
            table = document.add_table(rows=1, cols=2)
            left, right = table.rows[0].cells
            _run(left.paragraphs[0], "KEY COMPARISONS", bold=True, size=8, color="52606D")
            for line in block["comparisons"]:
                _run(left.add_paragraph(), "• " + line, size=8.5)
            _run(right.paragraphs[0], "KEY DATA", bold=True, size=8, color="52606D")
            for label, value in block["key_data"]:
                p = right.add_paragraph()
                _run(p, f"{label}: ", size=8.5, color="52606D")
                _run(p, value, bold=True, size=8.5)
            _run(right.add_paragraph(), f"Peers: {block['peers']}", size=8.5)
        elif kind == "paragraph" and block.get("style") == "note":
            _run(document.add_paragraph(), block["text"], size=8.5, color="52606D")
        elif kind == "paragraph":
            _run(document.add_paragraph(), block["text"], bold=block.get("style") == "lead")
        elif kind == "commentary":
            if block.get("headline"):
                _run(document.add_paragraph(), block["headline"], bold=True, size=11, color="0B2545")
            p = document.add_paragraph()
            _run(p, block["text"])
            _word_marks(p, block)
        elif kind == "statements":
            if not block["items"]:
                _run(document.add_paragraph(), "Nothing to show.", size=9, color="52606D")
            for item in block["items"]:
                if item.get("tag"):
                    _run(document.add_paragraph(), item["tag"], bold=True, size=8, color="52606D")
                p = document.add_paragraph(style="List Bullet")
                if item["label"] == "unverified":
                    _run(p, "[Unverified] ", bold=True, color="8A5A00")
                _run(p, item["text"])
                _word_marks(p, item)
                for issue in item["issues"]:
                    _run(document.add_paragraph(), issue, size=8.5, color="8A5A00")
        elif kind == "footnotes":  # one line of small print
            p = document.add_paragraph()
            for i, note in enumerate(block["items"]):
                if i:
                    _run(p, "  ·  ", size=7.5, color="B6C0CC")
                _run(p, str(note["number"]), bold=True, size=7, color="2F5D8A").font.superscript = True
                _run(p, " " + note["text"] + (f" ({note['url']})" if note.get("url") else ""), size=7.5, color="52606D")
        elif kind == "table":
            if block.get("title"):
                _run(document.add_paragraph(), block["title"], bold=True, size=9, color="0B2545")
            table = document.add_table(rows=1, cols=len(block["columns"]))
            table.style = "Light List Accent 1"
            for cell, name in zip(table.rows[0].cells, block["columns"]):
                cell.text = ""
                _run(cell.paragraphs[0], name, bold=True, size=8)
            for row in block["rows"]:
                cells = table.add_row().cells
                for cell, value in zip(cells, row):
                    cell.text = ""
                    _run(cell.paragraphs[0], value, size=8)
            if block.get("source"):
                p = document.add_paragraph()
                _run(p, block["source"], size=7.5, color="52606D").italic = True
            for note in block.get("notes", []):
                _run(document.add_paragraph(), note, size=8, color="52606D")
        elif kind == "list":
            if block.get("title"):
                _run(document.add_paragraph(), block["title"], bold=True)
            for item in block["items"]:
                p = document.add_paragraph(style="List Bullet")
                _run(p, item, color="8A5A00" if "warn" in str(block.get("style")) else None,
                     size=8.5 if block.get("style") in ("small", "warn-small") else None)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()
