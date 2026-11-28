# Twelve Data price adapter: actual and split-adjusted daily closes with their source, one fetch per company per analysis, the key
# sent in a header (never in the address or a message), the robots.txt exception for api.twelvedata.com only, and the rule that an
# analysis dated today uses the latest completed session, never today's unfinished trading.
from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx2
import pytest

from backend import financials
from backend.fetchers import market_data
from backend.fetchers.http_client import AccessDenied, PoliteClient
from tests.helpers import make_settings

KEY = "td-test-key-0000"
NY = ZoneInfo("America/New_York")
META = {"symbol": "MSFT", "interval": "1day", "currency": "USD", "exchange_timezone": "America/New_York", "exchange": "NASDAQ",
        "type": "Common Stock"}
ACTUAL = [{"datetime": "2026-11-25", "close": "479.915", "volume": "271414"},  # today, still trading
          {"datetime": "2026-11-24", "close": "496.13", "volume": "23086900"},
          {"datetime": "2026-11-23", "close": "492.50", "volume": "30404400"},
          {"datetime": "2021-12-31", "close": "336.32", "volume": "18000000"}]
SPLIT_ADJUSTED = [{**row, "close": "168.16"} if row["datetime"] == "2021-12-31" else row for row in ACTUAL]  # as if a 2-for-1 split


class FakeTwelveData:
    def __init__(self, error=None):
        self.requests, self.error = [], error

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if request.url.path == "/robots.txt":
            return httpx2.Response(200, text="User-agent: *\nDisallow: /\n")
        if request.url.host == "api.twelvedata.com" and request.url.path == "/time_series":
            if self.error:
                return httpx2.Response(200, json={"code": 401, "message": self.error, "status": "error"})
            values = SPLIT_ADJUSTED if request.url.params.get("adjust") == "splits" else ACTUAL
            return httpx2.Response(200, json={"meta": META, "values": values, "status": "ok"})
        return httpx2.Response(200, text="ok")


def provider(tmp_path, fake):
    settings = make_settings(tmp_path, market_data_provider="twelve_data", market_data_api_key=KEY,
                             market_data_base_url="https://api.twelvedata.com", min_seconds_between_requests_per_host=0.0,
                             market_data_min_interval_seconds=0.0)
    return market_data.get_provider(settings, PoliteClient(settings, transport=httpx2.MockTransport(fake)))


def test_daily_closes_come_with_split_adjusted_history_and_their_source(tmp_path):
    fake = FakeTwelveData()
    series = provider(tmp_path, fake).daily_series("MSFT", date(2021, 12, 1), date(2026, 11, 25))
    assert (series.exchange, series.currency, series.timezone, series.source) == ("NASDAQ", "USD", "America/New_York", "Twelve Data")
    days = [b.day for b in series.bars]
    assert days == sorted(days)
    old = next(b for b in series.bars if b.day == date(2021, 12, 31))
    assert old.close == 336.32 and old.adjusted_close == 168.16 and old.volume == 18000000.0
    calls = [r for r in fake.requests if r.url.path == "/time_series"]
    assert {r.url.params["adjust"] for r in calls} == {"none", "splits"}
    assert all(r.headers["authorization"] == f"apikey {KEY}" and KEY not in str(r.url) for r in calls)


def test_one_fetch_per_company_serves_every_later_price_in_the_analysis(tmp_path):
    fake = FakeTwelveData()
    p = provider(tmp_path, fake)
    p.daily_series("MSFT", date(2026, 11, 11), date(2026, 11, 25))
    p.daily_series("MSFT", date(2025, 11, 10), date(2025, 11, 24))
    p.daily_series("MSFT", date(2021, 12, 17), date(2021, 12, 31))
    assert len([r for r in fake.requests if r.url.path == "/time_series"]) == 2  # one actual, one split-adjusted


def test_api_errors_are_reported_without_the_key(tmp_path):
    p = provider(tmp_path, FakeTwelveData(error=f"apikey {KEY} is incorrect or not specified"))
    with pytest.raises(market_data.PriceUnavailable) as raised:
        p.daily_series("MSFT", date(2026, 11, 1), date(2026, 11, 25))
    assert "401" in str(raised.value) and KEY not in str(raised.value)


def test_the_robots_exception_covers_twelve_data_only(tmp_path):
    settings = make_settings(tmp_path, min_seconds_between_requests_per_host=0.0)
    client = PoliteClient(settings, transport=httpx2.MockTransport(FakeTwelveData()))
    assert client.allowed("https://api.twelvedata.com/time_series")  # recorded exception (CLAUDE.md)
    assert not client.allowed("https://example.org/data")  # every other site's robots.txt still applies
    with pytest.raises(AccessDenied):
        client.get("https://example.org/data")


class Market:
    def __init__(self, series):
        self.series = series

    def daily_series(self, ticker, start, end):
        return self.series


def test_an_analysis_dated_today_uses_the_latest_completed_session(tmp_path, monkeypatch):
    series = provider(tmp_path, FakeTwelveData()).daily_series("MSFT", date(2021, 12, 1), date(2026, 11, 25))
    monkeypatch.setattr(financials, "_now", lambda tz: datetime(2026, 11, 25, 14, 0, tzinfo=NY))  # trading is still open
    price = financials.closing_price(Market(series), "MSFT", date(2026, 11, 25))
    assert price.value == 496.13 and price.period == "close 2026-11-24"
    assert price.sources[0]["publisher"] == "Twelve Data"
    past = financials.closing_price(Market(series), "MSFT", date(2026, 11, 23))  # a past analysis date: that day's close
    assert past.value == 492.50


def test_a_share_class_ticker_is_sent_the_way_twelve_data_writes_it(tmp_path):
    # a live Coca-Cola run (28 November 2026): peer BF-B (SEC style) got no price; Twelve Data writes the class as BF.B
    fake = FakeTwelveData()
    series = provider(tmp_path, fake).daily_series("BF-B", date(2026, 11, 11), date(2026, 11, 25))
    assert {r.url.params["symbol"] for r in fake.requests if r.url.path == "/time_series"} == {"BF.B"}
    assert series.ticker == "BF-B"  # the analysis keeps the SEC ticker
