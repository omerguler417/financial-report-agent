# Reads reports into numbered pages (or sections, or sheets) so every claim can cite a precise location: PDF, Word, Excel, HTML, text, CSV, JSON, XML.
# Tables come out as text rows ("cell | cell"); there is no separate table structure. Scanned PDFs (no text layer) are reported, not read: OCR is not implemented.
import html
import re
from dataclasses import dataclass
from pathlib import Path

TEXT_EXTENSIONS = {".txt", ".csv", ".json", ".xml"}
HTML_EXTENSIONS = {".htm", ".html"}
SECTION_CHARS = 3500
HTML_PAGE_BREAK = re.compile(r"(?i)<[^>]*page-break-(?:before|after)\s*:\s*always[^>]*>")


@dataclass
class Page:
    number: int
    text: str
    label: str  # how the location is cited: "p. 3", "section 2", "sheet Income"


@dataclass
class ReadResult:
    pages: list[Page]
    notes: list[str]


def pages_from_texts(texts: list[str]) -> list[Page]:
    """Pages from a document already split into pages (for example a call transcript split by speaker turn)."""
    return [Page(i + 1, t, f"p. {i + 1}") for i, t in enumerate(texts)]


def _sections(text: str) -> list[Page]:
    """Text without page markers, split into ~3500-character sections at paragraph boundaries."""
    chunks, current = [], ""
    for paragraph in re.split(r"\n\s*\n", text):
        if current and len(current) + len(paragraph) > SECTION_CHARS:
            chunks.append(current)
            current = ""
        current += paragraph + "\n\n"
    if current.strip():
        chunks.append(current)
    return [Page(i + 1, c.strip(), f"section {i + 1}") for i, c in enumerate(chunks)] or [Page(1, "", "section 1")]


def _clean_html(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", raw)
    raw = re.sub(r"(?i)</(p|div|tr|li|table|h[1-6])>|<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?i)</t[dh]>", " | ", raw)
    text = html.unescape(re.sub(r"(?s)<[^>]+>", " ", raw))
    return re.sub(r"[ \t\xa0]+", " ", re.sub(r"\n\s*\n+", "\n\n", text)).strip()


def _read_pdf(path: Path) -> ReadResult:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    pages = [Page(i + 1, (page.extract_text() or "").strip(), f"p. {i + 1}") for i, page in enumerate(reader.pages)]
    notes = []
    if pages and not any(p.text for p in pages):
        notes.append("No text could be extracted from this PDF (it may be a scan). OCR is not implemented; upload a text, Word or HTML version.")
    return ReadResult(pages, notes)


def _read_docx(path: Path) -> ReadResult:
    import docx
    document = docx.Document(str(path))
    parts = [p.text for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        parts.append("\n".join(" | ".join(cell.text.strip() for cell in row.cells) for row in table.rows))
    return ReadResult(_sections("\n\n".join(parts)), ["Word documents have no fixed pages; locations are cited as sections."])


def _read_xlsx(path: Path) -> ReadResult:
    import openpyxl
    workbook = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    pages = []
    for sheet in workbook.worksheets:
        rows = [" | ".join("" if c is None else str(c) for c in row) for row in sheet.iter_rows(values_only=True)]
        pages.append(Page(len(pages) + 1, "\n".join(r for r in rows if r.strip(" |")), f"sheet {sheet.title}"))
    workbook.close()
    return ReadResult(pages, ["Cell values are read as last saved; formulas are not recalculated."])


def read_document(path: Path) -> ReadResult | None:
    """Numbered pages for a supported file, or None for an unsupported type. A corrupt file raises an error."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".pdf":
        return _read_pdf(path)
    if ext == ".docx":
        return _read_docx(path)
    if ext == ".xlsx":
        return _read_xlsx(path)
    if ext in HTML_EXTENSIONS:
        raw = path.read_text(encoding="utf-8", errors="replace")
        chunks = HTML_PAGE_BREAK.split(raw)
        if len(chunks) > 1:
            return ReadResult([Page(i + 1, _clean_html(c), f"p. {i + 1}") for i, c in enumerate(chunks)], [])
        return ReadResult(_sections(_clean_html(raw)), ["No page breaks found; locations are cited as sections."])
    if ext in TEXT_EXTENSIONS:
        raw = path.read_text(encoding="utf-8", errors="replace")
        if "\f" in raw:
            return ReadResult(pages_from_texts([p.strip() for p in raw.split("\f")]), [])
        return ReadResult(_sections(raw), [])
    return None


def try_read_document(path: Path) -> ReadResult:
    """Like read_document, but never raises: unsupported or unreadable files give no pages and a note saying why."""
    name = Path(path).name
    try:
        result = read_document(path)
    except Exception as exc:  # corrupt, encrypted or truncated files are reported, not fatal
        return ReadResult([], [f"{name}: the file could not be read ({type(exc).__name__})."])
    if result is None:
        return ReadResult([], [f"{name}: this file type cannot be read."])
    return result


def plain_text(path: Path) -> str | None:
    """All text of a document, or None when the type is unsupported or the file cannot be read (used where page numbers are not needed)."""
    result = try_read_document(path)
    return "\n\n".join(p.text for p in result.pages) if result.pages else None
