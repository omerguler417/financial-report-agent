# The horizon chosen in the New analysis form (3, 5 or 10 fiscal years; 5 by default): it sets how many years of history are read,
# how many year-end prices are looked up, and the window of the multi-year indicators (revenue CAGR, multi-year FCF conversion and
# the historical multiple medians). With fewer years than chosen, the actual coverage is labelled; nothing is filled in.
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from backend import financials
from backend import indicators as ind
from backend import main
from backend.demo import demo_data as D
from backend.demo.demo_providers import demo_services
from backend.agents.financial_analyst import company_inputs
from backend.fetchers import market_data
from backend.indicators import CompanyInputs
from tests.helpers import make_settings
from tests.test_edgar import edgar_for
from tests.test_indicators import period

ON = date(2026, 11, 20)


def long_history(**changes) -> CompanyInputs:
    """Eleven fiscal years, FY2015 to FY2025: revenue 100, 110, ... 200; FCF 10 and group net income 20 every year."""
    periods = {f"FY{y}": period(f"FY{y}", revenue=100 + 10 * (y - 2015), cfo_reported=30, capex=20, net_income_group=20)
               for y in range(2015, 2026)}
    return CompanyInputs(**{"name": "Long Co", "periods": periods, "latest_fy": "FY2025", **changes})


def current(c):
    return {r.indicator: r for r in ind.analyse(c)["current"]}


def test_five_years_is_the_default_and_only_3_5_or_10_are_offered():
    assert CompanyInputs("X", {}, "FY2025").horizon_years == 5
    assert ind.HORIZONS == (3, 5, 10)


@pytest.mark.parametrize("years, first, name", [(3, "FY2022", "Three-year"), (5, "FY2020", "Five-year"), (10, "FY2015", "Ten-year")])
def test_revenue_cagr_and_fcf_conversion_follow_the_horizon(years, first, name):
    r = current(long_history(horizon_years=years))
    cagr = r["revenue_cagr"]
    assert cagr.period == f"{first}–FY2025" and f"{years}-year CAGR" in cagr.note
    begin = 100 + 10 * (int(first[2:]) - 2015)
    assert cagr.value == pytest.approx((200 / begin) ** (1 / years) - 1)
    conversion = r["fcf_conversion_5y"]  # the id stays the same; the name and window follow the horizon
    assert conversion.name == f"{name} FCF earnings conversion" and conversion.period == f"FY{2026 - years}–FY2025"
    assert conversion.value == pytest.approx(0.5) and f"over {years} years" in conversion.note


def test_fewer_years_than_the_horizon_are_labelled_with_the_actual_coverage():
    c = long_history(horizon_years=10)
    for y in range(2015, 2019):  # only FY2019 to FY2025 remain: seven years
        del c.periods[f"FY{y}"]
    r = current(c)
    assert r["revenue_cagr"].period == "FY2019–FY2025" and "A 10-year CAGR needs 11 annual observations." in r["revenue_cagr"].note
    assert "7-year measure, not 10" in r["fcf_conversion_5y"].note
    assert r["fcf_conversion_5y"].name == "7-year FCF earnings conversion"  # named for the years actually used, not the horizon


def test_the_historical_median_uses_the_year_ends_in_the_horizon():
    def median(years):
        return current(company_inputs({"ticker": D.TARGET, "name": D.COMPANIES[D.TARGET]["name"]}, demo_services(), ON, D.DEMO_LABEL,
                                      horizon=years)[0])["pe_hist_median"]
    three, ten = median(3), median(10)
    assert "3 of 3" in three.note and three.period == "year ends 2023–2025"
    assert "of 10" in ten.note and "not 10" in ten.note  # the demo has five years of data: the coverage is labelled


class Market:
    def __init__(self):
        self.asked = []

    def daily_series(self, ticker, start, end):
        self.asked.append(end)
        days = [start + timedelta(days=i) for i in range((end - start).days + 1)]  # a close every day, weekends included
        bars = [market_data.DailyBar(day=d, close=10.0, adjusted_close=10.0, volume=1.0,
                                     timestamp=datetime(d.year, d.month, d.day, 16, 0, tzinfo=ZoneInfo("America/New_York"))) for d in days]
        return market_data.PriceSeries(ticker=ticker, exchange="NYSE", currency="USD", timezone="America/New_York", source="Test",
                                       bars=bars)


def test_year_end_prices_are_looked_up_for_each_year_in_the_horizon():
    points = financials.price_points(Market(), "X", date(2026, 6, 1), years=10)
    assert sorted(k for k in points if k.startswith("year end")) == [f"year end {y}-12-31" for y in range(2016, 2026)]
    assert len([k for k in financials.price_points(Market(), "X", date(2026, 6, 1)) if k.startswith("year end")]) == 5


def test_edgar_keeps_one_more_fiscal_year_than_the_horizon(tmp_path):
    e, _ = edgar_for(tmp_path)
    figures = [{"period": f"FY{y}"} for y in range(2010, 2026)] + [{"period": "YTD Q3 2014"}, {"period": "YTD Q3 2015"}]
    kept = {f["period"] for f in e._recent(figures, years=4)}
    assert kept == {"FY2022", "FY2023", "FY2024", "FY2025"}
    assert len([f for f in e._recent(figures, years=11) if f["period"].startswith("FY")]) == 11


def test_the_horizon_is_chosen_per_analysis_and_shown_in_the_report(tmp_path):
    c = TestClient(main.create_app(make_settings(tmp_path), background_jobs=False))
    state = c.post("/api/analyses", json={"company": "Northgate", "demo": True, "as_of": "2026-11-20", "horizon_years": 3}).json()
    assert state["status"] == "completed", state.get("error")
    report = c.get(f"/api/analyses/{state['id']}/report").json()
    assert report["agent1"]["indicators"]["horizon_years"] == 3
    rows = {r["indicator"]: r for r in report["agent1"]["indicators"]["current"]}
    assert rows["fcf_conversion_5y"]["name"].startswith("Three-year")
    view = c.get(f"/api/analyses/{state['id']}/view").json()
    assert any("horizon 3 fiscal years" in b.get("text", "") for b in view["blocks"])
    default = c.post("/api/analyses", json={"company": "Northgate", "demo": True, "as_of": "2026-11-20"}).json()
    assert c.get(f"/api/analyses/{default['id']}/report").json()["agent1"]["indicators"]["horizon_years"] == 5
    assert c.post("/api/analyses", json={"company": "Northgate", "demo": True, "horizon_years": 7}).status_code == 422
