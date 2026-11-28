# Investment-banking-style exhibits (approved 28 November 2026): the key market data, a financial summary by fiscal year plus the last
# twelve months, and a trading-comparables table with each peer and the median. Python builds and formats them from the calculated
# results; every figure keeps its sources; nothing is a rating, target or verdict.
import pytest

from backend import exhibits
from backend import indicators as ind
from tests.helpers import sample_app
from tests.sample import data as D
from tests.sample.providers import demo_company_inputs
from tests.test_indicators import sample
from datetime import date

ON = date(2026, 11, 20)


def test_the_financial_summary_has_each_fiscal_year_and_the_last_twelve_months_with_sources():
    analysis = ind.analyse(sample())
    summary = {row["period"]: row for row in analysis["financial_summary"]}
    assert list(summary) == ["FY2024", "FY2025", "TTM to Q3 2026"]
    ttm = summary["TTM to Q3 2026"]["items"]
    # TTM = FY2025 + YTD Q3 2026 − YTD Q3 2025: revenue 1000 + 800 − 700, EBIT 150 + 120 − 100, D&A 30 + 24 − 21, capex 50 + 45 − 35
    assert ttm["revenue"]["value"] == pytest.approx(1100) and ttm["ebit"]["value"] == pytest.approx(170)
    assert ttm["ebitda"]["value"] == pytest.approx(203) and ttm["capex"]["value"] == pytest.approx(60)
    assert all(item is None or item["sources"] for row in summary.values() for item in row["items"].values())
    market = analysis["market"]
    assert market["price"]["value"] == 20.0 and market["market_cap"]["value"] == pytest.approx(2000)
    assert market["enterprise_value"]["value"] == pytest.approx(2220)  # 2000 + debt 300 + NCI 20 − cash 100


def test_missing_figures_stay_missing_in_the_summary():
    c = sample()
    del c.periods["FY2024"]["capex"]
    summary = {row["period"]: row for row in ind.analyse(c)["financial_summary"]}
    assert summary["FY2024"]["items"]["capex"] is None and summary["FY2024"]["items"]["fcf"] is None


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    c = sample_app(tmp_path_factory.mktemp("exhibits"))
    state = c.post("/api/analyses", json={"company": "Northgate", "as_of": "2026-11-20"}).json()
    return c, c.get(f"/api/analyses/{state['id']}/report").json(), state["id"]


def test_the_exhibits_are_formatted_for_a_report(report):
    _, r, _ = report
    ex = exhibits.build(r)
    key = {row["label"]: row["value"] for row in ex["key_data"]}
    price = next(label for label in key if label.startswith("Share price (close "))
    assert key[price].startswith("USD ") and key["Market capitalisation"].startswith("USD ") and "Enterprise value" in key
    assert key["Market capitalisation"].endswith(("bn", "m"))  # banker style: USD 14.3bn, not 14,279 USD m
    summary = ex["financial_summary"]
    assert summary["columns"][0] == "USD millions" and summary["columns"][-1].startswith("LTM")
    revenue = next(row for row in summary["rows"] if row[0] == "Revenue")
    assert all(cell == "—" or cell.replace(",", "").replace(".", "").lstrip("-").isdigit() for cell in revenue[1:])


def test_the_comparables_table_lists_the_company_each_peer_and_the_median(report):
    _, r, _ = report
    comps = exhibits.build(r)["comparables"]
    names = [row[0] for row in comps["rows"]]
    assert names[0].startswith(D.COMPANIES[D.TARGET]["name"]) and names[-1] == "Peer median"
    assert {f"{p['name']} ({p['ticker']})" for p in r["peers"]["peers"]} <= set(names)
    assert "P/E" in comps["columns"] and "EV/EBITDA" in comps["columns"]
    pe = comps["columns"].index("P/E")
    company_pe = next(x for x in r["agent1"]["indicators"]["current"] if x["indicator"] == "pe")
    assert comps["rows"][0][pe] == f"{company_pe['value']:,.2f}x"


def test_the_view_carries_the_exhibits_for_the_dashboard(report):
    c, _, job = report
    view = c.get(f"/api/analyses/{job}/view").json()
    assert view["exhibits"]["comparables"]["rows"] and view["exhibits"]["financial_summary"]["rows"]


def test_rows_and_columns_without_any_data_are_left_out_of_the_exhibits(report):
    _, r, _ = report
    import copy
    r = copy.deepcopy(r)
    for row in r["agent1"]["indicators"]["financial_summary"]:
        row["items"]["capex"] = None  # no capital expenditure in any period
    current = {x["indicator"]: x for x in r["agent1"]["indicators"]["current"]}
    current["ev_sales"].update(status="missing", value=None)
    for row in r["agent1"]["peer_comparison"]:
        if row["indicator"] == "ev_sales":
            row["peer_median"] = None
            row["peer_values"] = {t: {"value": None, "status": "missing"} for t in row["peer_values"]}
    current["ps_hist_median"].update(status="missing", value=None)
    ex = exhibits.build(r)
    assert "Capital expenditure" not in [row[0] for row in ex["financial_summary"]["rows"]]
    assert "EV/sales" not in ex["comparables"]["columns"] and "P/E" in ex["comparables"]["columns"]
    assert "P/S" not in [row[0] for row in ex["historical"]["rows"]] and "P/E" in [row[0] for row in ex["historical"]["rows"]]
