# Step 5b: the report as a PDF (default) and an editable Word file, both drawn from the same display blocks as the website, with the
# same content.
import io

import docx
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from backend import main, report_blocks, report_export
from tests.sample import data as D
from tests.helpers import make_settings, sample_app


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    client = sample_app(tmp_path_factory.mktemp("export"))
    state = client.post("/api/analyses", json={"company": "Northgate", "as_of": "2026-11-20"}).json()
    report = client.get(f"/api/analyses/{state['id']}/report").json()
    return client, state["id"], report_blocks.build(report)


def pdf_pages(data: bytes) -> list[str]:
    return [" ".join((page.extract_text() or "").split()) for page in PdfReader(io.BytesIO(data)).pages]


def docx_text(data: bytes) -> tuple[list[str], str]:
    document = docx.Document(io.BytesIO(data))
    headers = [" ".join(p.text for p in s.header.paragraphs) for s in document.sections]
    body = [p.text for p in document.paragraphs] + [c.text for t in document.tables for row in t.rows for c in row.cells]
    return headers, "\n".join(body)


def test_the_pdf_has_the_same_content_and_numbered_pages(demo):
    _, _, view = demo
    pages = pdf_pages(report_export.to_pdf(view))
    assert len(pages) >= 3
    assert all(f"Page {i}" in page for i, page in enumerate(pages, 1))
    text = " ".join(pages)
    for heading in [b["text"] for b in view["blocks"] if b["type"] == "heading" and b["level"] == 2]:
        assert heading in text, heading
    assert "Unverified" in text and "Annual report FY2025 (demo), p. 6" in text
    pe = next(row for b in view["blocks"] if b["type"] == "table" for row in b["rows"] if row[0] == "P/E")
    assert pe[1] in text  # the P/E value exactly as the website shows it


def test_the_word_file_has_the_same_content(demo):
    _, _, view = demo
    headers, body = docx_text(report_export.to_docx(view))
    for heading in [b["text"] for b in view["blocks"] if b["type"] == "heading" and b["level"] == 2]:
        assert heading in body, heading
    assert "Unverified" in body and "Annual report FY2025 (demo), p. 6" in body and "P/E" in body


def test_a_short_report_has_no_label_in_either_file():
    view = {"title": "Financial analysis: X Corp (X)",
            "blocks": [{"type": "heading", "level": 1, "text": "Financial analysis: X Corp (X)"},
                       {"type": "paragraph", "text": "Analysis date 2026-11-20"}]}
    assert not any("DEMO" in page for page in pdf_pages(report_export.to_pdf(view)))
    headers, body = docx_text(report_export.to_docx(view))
    assert all("Verity" in h and "DEMO" not in h for h in headers) and "X Corp" in body


def test_the_download_endpoints_return_files_with_a_clear_name(demo):
    client, job_id, _ = demo
    pdf = client.get(f"/api/analyses/{job_id}/download/pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf" and pdf.content.startswith(b"%PDF")
    assert 'filename="NRTH.DEMO_analysis_2026-11-20.pdf"' in pdf.headers["content-disposition"]
    word = client.get(f"/api/analyses/{job_id}/download/docx")
    assert word.status_code == 200 and word.content.startswith(b"PK")
    assert word.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert client.get(f"/api/analyses/{job_id}/download/txt").status_code == 404
    assert client.get("/api/analyses/0123456789ab/download/pdf").status_code == 404


def test_both_files_show_the_exhibits_with_sources_the_key_data_and_the_footer(demo):
    _, _, view = demo
    pdf = " ".join(pdf_pages(report_export.to_pdf(view)))
    headers, body = docx_text(report_export.to_docx(view))
    footers = " ".join(p.text for s in docx.Document(io.BytesIO(report_export.to_docx(view))).sections for p in s.footer.paragraphs)
    for text in (pdf, body):
        for title in ("Exhibit 1: Financial summary", "Exhibit 2: Trading comparables", "Exhibit 3: Valuation against own history"):
            assert title in text, title
        assert "Source: Company filings" in text and "Market capitalisation" in text and "Peer median" in text
    assert "Not investment advice" in pdf and "Not investment advice" in footers


def test_the_files_carry_the_project_name_and_no_placeholder_brand(demo):
    _, _, view = demo
    pdf = " ".join(pdf_pages(report_export.to_pdf(view)))
    _, body = docx_text(report_export.to_docx(view))
    assert "Verity" in pdf and "Financial Report Analysis Agent" in pdf and "folio" not in pdf.lower() and "folio" not in body.lower()
    assert "our calculations" not in pdf.lower() and "Source: Company filings" in pdf  # report-style source lines (28 November 2026)


def test_both_files_show_the_commentary_and_the_valuation_summary(demo):
    _, _, view = demo
    pdf = " ".join(pdf_pages(report_export.to_pdf(view)))
    _, body = docx_text(report_export.to_docx(view))
    body = " ".join(body.split())
    first = next(b for b in view["blocks"] if b["type"] == "commentary" and b["headline"])
    for text in (pdf, body):
        assert first["headline"] in text and first["text"][:60] in text and "calculations in Appendix A" in text  # its footnote
        assert "Taken together, the company looks" in text and "It is not investment advice." in text and "Against own history" in text


def test_both_files_give_footnote_numbers_and_each_sections_sources_not_a_source_line_per_point(demo):
    _, _, view = demo
    pdf = " ".join(pdf_pages(report_export.to_pdf(view)))
    _, body = docx_text(report_export.to_docx(view))
    for text in (pdf, body):
        assert "Source: Annual report" not in text and "Calculated: P/E" not in text  # no source line under each point
        assert "Annual report FY2025 (demo), p. 6" in text and "sources in Appendix C" in text  # the sections' source lists


def test_short_sections_share_a_page_and_no_heading_is_left_at_the_bottom(demo):
    # 28 November 2026: each section started a new page (Financial summary and Trading comparables each alone on half-empty pages)
    _, _, view = demo
    pages = [(page.extract_text() or "").splitlines() for page in PdfReader(io.BytesIO(report_export.to_pdf(view))).pages]
    heads = [b["text"] for b in view["blocks"] if b["type"] == "heading" and b["level"] == 2]
    on = {h: next(i for i, lines in enumerate(pages) if any(h in line for line in lines)) for h in heads}
    assert on["3. Trading comparables"] == on["4. Historical valuation"]  # both fit on one page; before, each started its own
    for lines in pages:
        body = [line for line in lines if line.strip() and not line.startswith(("Financial analysis:", "For educational", "Page "))]
        assert body and not any(body[-1].strip() == h for h in heads), body[-1:]  # a section heading never ends a page
