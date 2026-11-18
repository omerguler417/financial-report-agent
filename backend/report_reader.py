# Extracts text and financial tables from reports, keeping the original text and labelling any translation.
# Working: plain text from text, HTML, CSV, JSON and XML files. Awaiting implementation: PDF, Word and Excel text and table extraction.
import html
import re
from pathlib import Path

TEXT_EXTENSIONS = {".txt", ".csv", ".json", ".xml"}
HTML_EXTENSIONS = {".htm", ".html"}


def plain_text(path: Path) -> str | None:
    """Return the document's text, or None when extraction for this file type is not implemented yet."""
    ext = Path(path).suffix.lower()
    if ext in TEXT_EXTENSIONS:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    if ext in HTML_EXTENSIONS:
        raw = Path(path).read_text(encoding="utf-8", errors="replace")
        raw = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", raw)
        return html.unescape(re.sub(r"(?s)<[^>]+>", " ", raw))
    return None
