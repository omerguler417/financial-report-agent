# Step 5a: the finished report as display blocks, shared by the website (now) and the PDF and Word files (step 5b): the demo label
# comes first, sections come in a fixed order, every statement shows its sources, unverified statements are marked, and figures are
# formatted for display without any new calculation.
import copy

import pytest
from fastapi.testclient import TestClient

from backend import main, report_blocks
from backend.demo import demo_data as D
from tests.helpers import make_settings

SECTIONS = ["Overview", "Where the sources disagree", "Key figures", "Key figures by fiscal year", "What the reports say",
            "Earnings call", "News", "Risks", "Not verified", "Missing information", "Limitations"]


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    client = TestClient(main.create_app(make_settings(tmp_path_factory.mktemp("blocks")), background_jobs=False))
    state = client.post("/api/analyses", json={"company": "Northgate", "demo": True, "as_of": "2026-11-20"}).json()
    return client, state["id"], client.get(f"/api/analyses/{state['id']}/report").json()


def statements(view):
    return [item for b in view["blocks"] if b["type"] == "statements" for item in b["items"]]


def test_the_demo_label_comes_first_and_sections_keep_their_order(demo):
    _, _, report = demo
    view = report_blocks.build(report)
    assert view["blocks"][0] == {"type": "banner", "text": D.DEMO_LABEL} and view["demo_label"] == D.DEMO_LABEL
    headings = [b["text"] for b in view["blocks"] if b["type"] == "heading" and b["level"] == 2]
    positions = [next(i for i, h in enumerate(headings) if h.endswith(name)) for name in SECTIONS]
    assert positions == sorted(positions)
    assert "Northgate Energy Corp (demo)" in view["title"]


def test_every_statement_shows_its_sources_and_unverified_ones_are_marked(demo):
    _, _, report = demo
    items = statements(report_blocks.build(report))
    assert len(items) >= 30
    assert all(item["sources"] and all(s["text"] for s in item["sources"]) for item in items)
    unverified = [i for i in items if i["label"] == "unverified"]
    assert len(unverified) == 3 and all(i["issues"] for i in unverified)
    texts = " | ".join(s["text"] for i in items for s in i["sources"])
    assert "Annual report FY2025 (demo), p. 6" in texts and "Demo Wire (fictional), 2026-10-30" in texts
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
    sources = next(b for b in view["blocks"] if b["type"] == "list" and b.get("title") == "Sources of the key figures")
    pe_sources = next(item for item in sources["items"] if item.startswith("P/E:"))
    assert "Quarterly report Q3 2026 (demo), pp. 2, 3" in pe_sources and "close 2026-11-20" in pe_sources


def test_a_live_report_has_no_demo_banner():
    report = {"mode": "live", "demo_label": None, "company": {"ticker": "X", "name": "X Corp"}, "analysis_date": "2026-11-20",
              "peers": {"peers": [], "excluded": []}, "notes": [],
              "agent1": {"indicators": {"current_period": "FY2025", "definition_version": "v1.0", "current": [], "history": {}},
                         "summary": [], "peer_comparison": []},
              "agent2": {"call": {"statements": []}, "news": {"since": None, "included": [], "excluded": []}},
              "agent3": {"overview": [], "disagreements": [], "risks": [], "unverified_statements": [], "missing_information": [],
                         "limitations": []}}
    view = report_blocks.build(copy.deepcopy(report))
    assert view["demo_label"] is None and all(b["type"] != "banner" for b in view["blocks"])


def test_the_view_endpoint_returns_the_blocks(demo):
    client, job_id, _ = demo
    view = client.get(f"/api/analyses/{job_id}/view").json()
    assert view["blocks"][0]["type"] == "banner"
    assert client.get("/api/analyses/0123456789ab/view").status_code == 404


def test_the_page_and_its_script_are_always_rechecked_by_the_browser(demo):
    client, _, _ = demo  # browsers must not keep showing an old copy of the page after an update
    for path in ("/", "/static/app.js", "/static/styles.css"):
        assert client.get(path).headers.get("cache-control") == "no-cache", path
