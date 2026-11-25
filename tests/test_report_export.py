# Step 5b: the report as a PDF (default) and an editable Word file, both drawn from the same display blocks as the website. A demo
# report carries the DEMO label on every page of both files; the content matches the website's blocks.
import io

import docx
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from backend import main, report_blocks, report_export
from backend.demo import demo_data as D
from tests.helpers import make_settings


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    client = TestClient(main.create_app(make_settings(tmp_path_factory.mktemp("export")), background_jobs=False))
    state = client.post("/api/analyses", json={"company": "Northgate", "demo": True, "as_of": "2026-11-20"}).json()
    report = client.get(f"/api/analyses/{state['id']}/report").json()
    return client, state["id"], report_blocks.build(report)


def pdf_pages(data: bytes) -> list[str]:
    return [" ".join((page.extract_text() or "").split()) for page in PdfReader(io.BytesIO(data)).pages]


def docx_text(data: bytes) -> tuple[list[str], str]:
    document = docx.Document(io.BytesIO(data))
    headers = [" ".join(p.text for p in s.header.paragraphs) for s in document.sections]
    body = [p.text for p in document.paragraphs] + [c.text for t in document.tables for row in t.rows for c in row.cells]
    return headers, "\n".join(body)


def test_the_pdf_has_the_demo_label_on_every_page_and_the_same_content(demo):
    _, _, view = demo
    pages = pdf_pages(report_export.to_pdf(view))
    assert len(pages) >= 3
    assert all(D.DEMO_LABEL in page for page in pages)
    text = " ".join(pages)
    for heading in [b["text"] for b in view["blocks"] if b["type"] == "heading" and b["level"] == 2]:
        assert heading in text, heading
    assert "Unverified" in text and "Annual report FY2025 (demo), p. 6" in text
    pe = next(row for b in view["blocks"] if b["type"] == "table" for row in b["rows"] if row[0] == "P/E")
    assert pe[1] in text  # the P/E value exactly as the website shows it


def test_the_word_file_has_the_demo_label_on_every_page_and_the_same_content(demo):
    _, _, view = demo
    headers, body = docx_text(report_export.to_docx(view))
    assert headers and all(D.DEMO_LABEL in h for h in headers)  # a Word header repeats on every page
    for heading in [b["text"] for b in view["blocks"] if b["type"] == "heading" and b["level"] == 2]:
        assert heading in body, heading
    assert "Unverified" in body and "Annual report FY2025 (demo), p. 6" in body and "P/E" in body


def test_a_live_report_has_no_demo_label_in_either_file():
    view = {"title": "Financial analysis: X Corp (X)", "demo_label": None,
            "blocks": [{"type": "heading", "level": 1, "text": "Financial analysis: X Corp (X)"},
                       {"type": "paragraph", "text": "Analysis date 2026-11-20 · live mode"}]}
    assert not any("DEMO" in page for page in pdf_pages(report_export.to_pdf(view)))
    headers, body = docx_text(report_export.to_docx(view))
    assert not any("DEMO" in h for h in headers) and "X Corp" in body


def test_the_download_endpoints_return_files_with_a_clear_name(demo):
    client, job_id, _ = demo
    pdf = client.get(f"/api/analyses/{job_id}/download/pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf" and pdf.content.startswith(b"%PDF")
    assert 'filename="NRTH.DEMO_analysis_2026-11-20_DEMO.pdf"' in pdf.headers["content-disposition"]
    word = client.get(f"/api/analyses/{job_id}/download/docx")
    assert word.status_code == 200 and word.content.startswith(b"PK")
    assert word.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert client.get(f"/api/analyses/{job_id}/download/txt").status_code == 404
    assert client.get("/api/analyses/0123456789ab/download/pdf").status_code == 404
