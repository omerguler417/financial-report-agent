# Step 2: reading documents into numbered pages (PDF, Word, Excel, HTML, text) and finding the pages relevant to a question.
from backend import report_reader as rr
from backend import retrieval
from backend.demo import demo_data as D
from backend.demo.demo_providers import demo_services


def make_pdf(path, pages: list[str]):
    """Write a minimal text PDF (one Helvetica text block per page) without any PDF-writing library."""
    def esc(s):
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    n = len(pages)
    page_ids, content_ids = [4 + 2 * i for i in range(n)], [5 + 2 * i for i in range(n)]
    objs = {1: "<< /Type /Catalog /Pages 2 0 R >>",
            2: f"<< /Type /Pages /Kids [{' '.join(f'{p} 0 R' for p in page_ids)}] /Count {n} >>",
            3: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"}
    for i, text in enumerate(pages):
        stream = "BT /F1 12 Tf 50 750 Td 14 TL " + " ".join(f"({esc(line)}) Tj T*" for line in text.split("\n") if line) + " ET"
        objs[page_ids[i]] = (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> "
                             f"/Contents {content_ids[i]} 0 R >>")
        objs[content_ids[i]] = f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream"
    out, offsets = b"%PDF-1.4\n", {}
    for k in sorted(objs):
        offsets[k] = len(out)
        out += f"{k} 0 obj\n{objs[k]}\nendobj\n".encode("latin-1")
    xref, size = len(out), max(objs) + 1
    out += f"xref\n0 {size}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{offsets[k]:010d} 00000 n \n".encode() for k in range(1, size))
    out += f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(out)


# ---------- reading ----------

def test_pdf_pages_keep_their_numbers(tmp_path):
    make_pdf(tmp_path / "r.pdf", ["Cover page", "Income statement\nTotal revenues 1,234.5", "Balance sheet\nTotal assets 9,876.0"])
    result = rr.read_document(tmp_path / "r.pdf")
    assert [p.number for p in result.pages] == [1, 2, 3] and [p.label for p in result.pages] == ["p. 1", "p. 2", "p. 3"]
    assert "Total revenues 1,234.5" in result.pages[1].text and "Total assets 9,876.0" in result.pages[2].text
    assert result.notes == []


def test_pdf_without_text_is_reported_not_guessed(tmp_path):
    make_pdf(tmp_path / "scan.pdf", [""])
    result = rr.read_document(tmp_path / "scan.pdf")
    assert result.pages[0].text == "" and any("No text could be extracted" in n for n in result.notes)


def test_word_documents_become_sections_with_tables_as_rows(tmp_path):
    import docx
    d = docx.Document()
    d.add_paragraph("Revenue discussion")
    table = d.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text, table.rows[0].cells[1].text = "Total revenues", "1,234.5"
    d.save(tmp_path / "a.docx")
    result = rr.read_document(tmp_path / "a.docx")
    assert result.pages[0].label == "section 1" and "Total revenues | 1,234.5" in result.pages[0].text
    assert any("sections" in n for n in result.notes)


def test_excel_sheets_become_pages(tmp_path):
    import openpyxl
    wb = openpyxl.Workbook()
    wb.active.title = "Income"
    wb.active.append(["Total revenues", 1234.5])
    wb.create_sheet("Balance").append(["Total assets", 9876])
    wb.save(tmp_path / "a.xlsx")
    pages = rr.read_document(tmp_path / "a.xlsx").pages
    assert [p.label for p in pages] == ["sheet Income", "sheet Balance"]
    assert "Total revenues | 1234.5" in pages[0].text and "Total assets | 9876" in pages[1].text


def test_html_and_text_pages(tmp_path):
    (tmp_path / "a.html").write_text("<html><script>x()</script><p>One &amp; two</p>"
                                     "<div style='page-break-after: always'></div><p>Three</p></html>")
    pages = rr.read_document(tmp_path / "a.html").pages
    assert [p.text for p in pages] == ["One & two", "Three"] and pages[1].label == "p. 2"
    (tmp_path / "b.html").write_text("<p>No page breaks here</p>")
    result = rr.read_document(tmp_path / "b.html")
    assert result.pages[0].label == "section 1" and any("No page breaks" in n for n in result.notes)
    (tmp_path / "a.txt").write_text("page one\fpage two")
    assert [p.label for p in rr.read_document(tmp_path / "a.txt").pages] == ["p. 1", "p. 2"]


def test_unsupported_and_corrupt_files_give_notes_not_crashes(tmp_path):
    (tmp_path / "a.xyz").write_text("x")
    assert rr.read_document(tmp_path / "a.xyz") is None
    unsupported = rr.try_read_document(tmp_path / "a.xyz")
    assert unsupported.pages == [] and "cannot be read" in unsupported.notes[0]
    (tmp_path / "bad.pdf").write_bytes(b"not a pdf")
    broken = rr.try_read_document(tmp_path / "bad.pdf")
    assert broken.pages == [] and "could not be read" in broken.notes[0]


def test_plain_text_still_works_for_existing_callers(tmp_path):
    (tmp_path / "a.txt").write_text("Revenue rose 12%.")
    assert rr.plain_text(tmp_path / "a.txt") == "Revenue rose 12%."
    make_pdf(tmp_path / "r.pdf", ["Total revenues 1,234.5"])
    assert "1,234.5" in rr.plain_text(tmp_path / "r.pdf")
    assert rr.plain_text(tmp_path / "a.xyz") is None
    (tmp_path / "bad.pdf").write_bytes(b"not a pdf")
    assert rr.plain_text(tmp_path / "bad.pdf") is None  # a damaged file is skipped and flagged by the caller, not a crash


# ---------- retrieval ----------

PAGES = {"d1": [rr.Page(1, "Corporate governance and board members", "p. 1"),
                rr.Page(2, "Consolidated balance sheet: total assets, total equity and borrowings", "p. 2"),
                rr.Page(3, "Risk factors and legal proceedings", "p. 3")]}


def test_retrieval_ranks_the_relevant_page_first_and_keeps_its_location():
    top = retrieval.retrieve(PAGES, "balance sheet total assets equity", k=2)
    assert top[0].doc_id == "d1" and top[0].page == 2 and top[0].label == "p. 2" and top[0].score > 0
    assert len(top) <= 2 and all(p.score > 0 for p in top)


def test_retrieval_returns_nothing_when_nothing_matches():
    assert retrieval.retrieve(PAGES, "zzzz qqqq") == []
    assert retrieval.retrieve({}, "revenue") == []


def test_retrieval_finds_statement_pages_in_the_demo_reports():
    report = next(d for d in demo_services().documents.find(D.TARGET) if d["period"] == "FY2025")
    docs = {report["doc_id"]: rr.pages_from_texts(report["pages"])}
    income = retrieval.retrieve(docs, "net income attributable to common shareholders income before taxes", k=1)[0]
    balance = retrieval.retrieve(docs, "total assets borrowings lease liabilities total equity", k=1)[0]
    assert (income.page, income.label) == (3, "p. 3") and (balance.page, balance.label) == (4, "p. 4")
