# Step 5a: the finished report as display blocks, shared by the website (now) and the PDF and Word files (step 5b): the demo label
# comes first, sections come in a fixed order, every statement shows its sources, unverified statements are marked, and figures are
# formatted for display without any new calculation.
import copy

import pytest
from fastapi.testclient import TestClient

from backend import main, report_blocks
from tests.sample import data as D
from tests.helpers import make_settings, sample_app

SECTIONS = ["Executive summary", "Financial summary", "Trading comparables", "Historical valuation", "Financial analysis",
            "Business overview and outlook", "Earnings call highlights", "Where the sources disagree", "Key risks", "Valuation summary",
            "Appendix A. All indicators", "Appendix B. Indicators by fiscal year", "Appendix C. Sources of the indicators",
            "Appendix D. Not verified", "Appendix E. Missing information", "Appendix F. Methodology and limitations"]


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    client = sample_app(tmp_path_factory.mktemp("blocks"))
    state = client.post("/api/analyses", json={"company": "Northgate", "as_of": "2026-11-20"}).json()
    return client, state["id"], client.get(f"/api/analyses/{state['id']}/report").json()


def statements(view):
    return [item for b in view["blocks"] if b["type"] == "statements" for item in b["items"]]


def test_the_title_comes_first_and_sections_keep_their_order(demo):
    _, _, report = demo
    view = report_blocks.build(report)
    assert view["blocks"][0]["type"] == "heading" and view["blocks"][0]["level"] == 1 and "demo_label" not in view
    headings = [b["text"] for b in view["blocks"] if b["type"] == "heading" and b["level"] == 2]
    positions = [next(i for i, h in enumerate(headings) if h.endswith(name)) for name in SECTIONS]
    assert positions == sorted(positions)
    assert "Northgate Energy Corp (demo)" in view["title"]


def test_every_statement_shows_its_sources_and_unverified_ones_are_marked(demo):
    _, _, report = demo
    items = statements(report_blocks.build(report))
    assert len(items) >= 20
    assert all(item["sources"] and all(s["text"] for s in item["sources"]) for item in items)
    unverified = [i for i in items if i["label"] == "unverified"]
    assert len(unverified) == 2 and all(i["issues"] for i in unverified)
    texts = " | ".join(s["text"] for i in items for s in i["sources"])
    assert "Annual report FY2025 (demo), p. 6" in texts and "Q3 2026 earnings call transcript (demo), p. 2" in texts
    assert "Calculated: Common ROE (TTM to Q3 2026)" in texts


def test_key_figures_are_formatted_from_python_results_with_their_sources(demo):
    _, _, report = demo
    view = report_blocks.build(report)
    table = next(b for b in view["blocks"] if b["type"] == "table" and b["columns"][0] == "Indicator" and "Peer median" in b["columns"])
    rows = {row[0]: row for row in table["rows"]}
    pe = next(r for r in report["agent1"]["indicators"]["current"] if r["indicator"] == "pe")
    roe = next(r for r in report["agent1"]["indicators"]["current"] if r["indicator"] == "roe_common")
    assert rows["P/E"][1] == f"{pe['value']:.2f}x" and rows["Common ROE"][1] == f"{roe['value'] * 100:.2f}%"
    assert all(isinstance(cell, str) for row in table["rows"] for cell in row)
    sources = next(b for b in view["blocks"] if b["type"] == "list" and b.get("title") == "Sources of each indicator")
    quarterly = next(item for item in sources["items"] if item.startswith("Quarterly report Q3 2026 (demo)"))
    assert "pp." in quarterly and len(sources["items"]) < 20  # grouped by document, not one long line per indicator
    assert any("close" in item and "2026-11-20" in item for item in sources["items"])


def test_a_report_with_no_results_still_has_its_sections():
    report = {"company": {"ticker": "X", "name": "X Corp"}, "analysis_date": "2026-11-20", "peers": {"peers": [], "excluded": []},
              "agent1": {"indicators": {"current_period": "FY2025", "definition_version": "v1.0", "current": [], "history": {}},
                         "summary": [], "peer_comparison": []},
              "agent2": {"call": {"statements": []}},
              "agent3": {"overview": [], "disagreements": [], "risks": [], "unverified_statements": [], "missing_information": [],
                         "limitations": []}}
    view = report_blocks.build(copy.deepcopy(report))
    headings = [b["text"] for b in view["blocks"] if b["type"] == "heading" and b["level"] == 2]
    assert headings and "No disagreements were identified." in [b.get("text") for b in view["blocks"]]


def test_the_view_endpoint_returns_the_blocks(demo):
    client, job_id, _ = demo
    view = client.get(f"/api/analyses/{job_id}/view").json()
    assert view["blocks"][0]["type"] == "heading" and view["comparisons"]["groups"]
    assert client.get("/api/analyses/0123456789ab/view").status_code == 404


def test_the_page_and_its_script_are_always_rechecked_by_the_browser(demo):
    client, _, _ = demo  # browsers must not keep showing an old copy of the page after an update
    for path in ("/", "/static/app.js", "/static/styles.css"):
        assert client.get(path).headers.get("cache-control") == "no-cache", path


def test_edgar_figures_are_cited_by_filing_statement_and_tag_not_by_page():
    result = {"inputs": [{"sources": [{"doc_id": "0000789019-25-000010", "title": "10-K for the period ended 2025-06-30 (filed 2025-07-30)",
                                        "section": "income statement", "tag": "us-gaap:Revenues", "published": "2025-07-30"},
                                       {"doc_id": "0000789019-25-000010", "title": "10-K for the period ended 2025-06-30 (filed 2025-07-30)",
                                        "section": "balance sheet", "tag": "us-gaap:Assets", "published": "2025-07-30"}]}]}
    [line] = report_blocks._sources_by_document([result])
    assert "p. None" not in line
    assert line == "10-K for the period ended 2025-06-30 (filed 2025-07-30): balance sheet, income statement"


def test_the_report_has_numbered_exhibits_with_sources_and_a_key_data_box(demo):
    _, _, report = demo
    blocks = report_blocks.build(report)["blocks"]
    exhibits = [b for b in blocks if b["type"] == "table" and b.get("title", "").startswith("Exhibit")]
    assert [b["title"].split(":")[0] for b in exhibits] == ["Exhibit 1", "Exhibit 2", "Exhibit 3"]
    assert all(b["source"].startswith("Source:") for b in exhibits)
    assert "Trading comparables" in exhibits[1]["title"] and exhibits[1]["rows"][-1][0] == "Peer median"
    box = next(b for b in blocks if b["type"] == "summarybox")
    assert any(label.startswith("Share price") for label, _ in box["key_data"])
    assert box["comparisons"] and all(isinstance(line, str) for line in box["comparisons"]) and box["peers"]
    assert blocks.index(box) < next(i for i, b in enumerate(blocks) if b["type"] == "heading" and b["level"] == 2)  # on the first page
    import re
    text = " ".join(str(b) for b in blocks).lower()
    for word in ("price target", "rating", "buy", "sell", "overweight", "underweight"):  # no recommendation of any kind
        assert not re.search(rf"\b{word}\b", text), word


def test_verified_statements_come_before_unverified_ones(demo):
    _, _, report = demo
    blocks = report_blocks.build(report)["blocks"]
    summary = next(b for b in blocks if b["type"] == "statements")  # the executive summary
    labels = [item["label"] for item in summary["items"]]
    assert "unverified" in labels and labels == sorted(labels, key=lambda l: l == "unverified")


def test_the_report_gives_the_calls_key_points_and_questions_not_the_whole_transcript(demo):
    _, _, report = demo
    blocks = report_blocks.build(report)["blocks"]
    headings = [b["text"] for b in blocks if b["type"] == "heading" and b["level"] == 3]
    assert {"Key points", "Guidance", "Questions and answers"} <= set(headings)
    qa = blocks[next(i for i, b in enumerate(blocks) if b.get("text") == "Questions and answers") + 1]
    tags = [item["tag"] for item in qa["items"]]
    assert tags[0].startswith("Question · Priya Nair") and tags[1].startswith("Answer · Daniel Okafor")


def test_the_all_indicators_appendix_has_a_short_status_column(demo):
    _, _, report = demo
    table = next(b for b in report_blocks.build(report)["blocks"] if b["type"] == "table" and b["columns"][0] == "Indicator" and "Peer median" in b["columns"])
    assert table["columns"][-1] == "Status" and all(len(row[-1]) < 30 for row in table["rows"])


def test_the_fiscal_year_appendix_shows_values_or_a_dash_never_status_words(demo):
    _, _, report = demo
    blocks = report_blocks.build(report)["blocks"]
    table = next(b for b in blocks if b["type"] == "table" and b["columns"][0] == "Indicator" and b["columns"][1].startswith("FY"))
    cells = [cell for row in table["rows"] for cell in row[1:]]
    assert not any(word in cell for cell in cells for word in ("missing", "reported only", "per share"))
    rows = {row[0]: row for row in table["rows"]}
    assert "Diluted EPS (USD)" in rows and rows["Diluted EPS (USD)"][-1] != "—"  # the reported value, not "reported only"
    assert all(any(cell != "—" for cell in row[1:]) for row in table["rows"])  # a row with no value in any year is left out


def test_the_report_does_not_label_statements_with_agent_names(demo):
    _, _, report = demo
    blocks = report_blocks.build(report)["blocks"]
    tags = [item.get("tag") or "" for b in blocks if b["type"] == "statements" for item in b["items"]]
    assert not any("Based on" in t or "Agent" in t for t in tags)
    not_verified = blocks[next(i for i, b in enumerate(blocks) if b.get("text", "").endswith("Not verified")) + 1]
    assert not any(item.startswith("Agent") for item in not_verified["items"])


def test_sections_get_agent3s_commentary_and_the_report_ends_with_a_valuation_summary(demo):
    # approved 28 November 2026: a headline and paragraph per section (Python lines when there is none), and a Python-decided summary
    _, _, report = demo
    blocks = report_blocks.build(report)["blocks"]
    commentary = [b for b in blocks if b["type"] == "commentary"]
    assert commentary and all(b["text"] and b["sources"] for b in commentary)
    assert any(b["headline"] for b in commentary)
    start = next(i for i, b in enumerate(blocks) if b.get("text", "").endswith("Valuation summary"))
    end = next(i for i, b in enumerate(blocks) if b.get("text", "").startswith("Appendix A"))
    summary = [b for b in blocks[start + 1:end] if b["type"] != "footnotes"]  # the section's source list comes last
    assert summary[0]["style"] == "lead" and summary[0]["text"].startswith("Taken together")
    table = next(b for b in summary if b["type"] == "table")
    assert table["columns"][:4] == ["Multiple", "Current", "Peer median", "Against peers"] and "±15%" in table["notes"][0]
    assert summary[-1]["text"] == "This sums up the comparisons in this report. It is not investment advice."
    old = copy.deepcopy(report)
    del old["agent3"]["commentary"]  # a report saved before commentary existed shows the Python lines instead
    assert not [b for b in report_blocks.build(old)["blocks"] if b["type"] == "commentary"]


def test_points_carry_footnote_numbers_and_each_section_ends_with_its_sources(demo):
    # decided 28 November 2026: no source line under every point; superscript numbers and one short source list per section
    _, _, report = demo
    blocks = report_blocks.build(report)["blocks"]
    start = next(i for i, b in enumerate(blocks) if b.get("text", "").endswith("Executive summary"))
    end = next(i for i, b in enumerate(blocks) if i > start and b["type"] == "heading" and b["level"] == 2)
    section = blocks[start:end]
    items = [item for b in section if b["type"] == "statements" for item in b["items"]]
    notes = next(b for b in section if b["type"] == "footnotes")
    assert section[-1] is notes and [n["number"] for n in notes["items"]] == list(range(1, len(notes["items"]) + 1))
    assert all(item["notes"] for item in items) and {n for item in items for n in item["notes"]} == {n["number"] for n in notes["items"]}
    texts = [n["text"] for n in notes["items"]]
    assert len(texts) == len(set(texts))  # a source cited by several points gets one number
    calculated = [t for t in texts if t.startswith("Company filings and market prices")]
    assert len(calculated) <= 1 and (not calculated or "calculations in Appendix A, sources in Appendix C" in calculated[0])
    assert not any(t.startswith("Calculated:") for t in texts)
    for b in blocks:  # every section with sourced points has its own list, numbered from 1
        if b["type"] == "footnotes":
            assert b["items"][0]["number"] == 1


def test_notes_use_short_document_names_and_report_wording():
    # decided 28 November 2026: short names in the notes (the full titles stay in Appendix C), and no "our calculations"
    short = report_blocks._short_title
    assert short("10-Q for the period ended 2026-09-30 (filed 2026-10-28)") == "10-Q, quarter ended Sep 2026"
    assert short("10-K for the period ended 2026-06-30 (filed 2026-07-29)") == "10-K, fiscal year ended Jun 2026"
    assert short("20-F for the period ended 2025-12-31 (filed 2026-04-02)") == "20-F, fiscal year ended Dec 2025"
    assert short("Earnings call transcript, MSFT fiscal 2027 Q1 (Alpha Vantage)") == "Q1 FY2027 earnings call"
    assert short("Annual report FY2025 (demo)") == "Annual report FY2025 (demo)"
    assert report_blocks._cite({"doc_id": "x", "title": "10-Q for the period ended 2026-09-30 (filed 2026-10-28)", "page": 28})["note"] == (
        "10-Q, quarter ended Sep 2026, p. 28")


def test_the_report_never_says_our_calculations(demo):
    _, _, report = demo
    import json
    text = json.dumps(report_blocks.build(report)).lower()
    assert "our calculations" not in text and "our work" not in text
    exhibits = [b for b in report_blocks.build(report)["blocks"] if b["type"] == "table" and b.get("source")]
    assert all(b["source"].startswith("Source: Company filings") and "Verity" in b["source"] for b in exhibits)
