# Price freshness: US holiday rules, latest completed session, stale flags, historical dates, and obeying robots.txt.
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx2
import pytest

from backend.fetchers.http_client import AccessDenied, PoliteClient
from backend.fetchers.market_data import (DailyBar, PriceSeries, YahooChartProvider, get_closing_price, select_quote)
from backend.market_calendar import calendar_for, us_holidays
from tests.helpers import FakeClock, make_settings

NY = ZoneInfo("America/New_York")


def ny(*args):
    return datetime(*args, tzinfo=NY)


def test_us_holidays_2026():
    h = us_holidays(2026)
    expected = [date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3), date(2026, 5, 25),
                date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7), date(2026, 11, 26), date(2026, 12, 25)]
    assert sorted(h) == expected


def test_saturday_new_year_is_not_observed_on_friday():
    assert date(2022, 1, 1) not in us_holidays(2022)
    assert calendar_for("NYQ").is_trading_day(date(2021, 12, 31))


@pytest.mark.parametrize("now, expected", [
    (ny(2026, 11, 12, 15, 0), date(2026, 11, 11)),   # before today's close -> yesterday
    (ny(2026, 11, 12, 16, 5), date(2026, 11, 12)),   # after close -> today
    (ny(2026, 11, 14, 12, 0), date(2026, 11, 13)),   # Saturday -> Friday
    (ny(2026, 11, 27, 10, 0), date(2026, 11, 25)),   # day after Thanksgiving, before close
    (ny(2026, 4, 6, 9, 0), date(2026, 4, 2)),        # Monday after Good Friday
])
def test_latest_completed_session(now, expected):
    assert calendar_for("NYQ").latest_completed_session(now) == expected


def test_extra_closures_from_settings():
    cal = calendar_for("NYQ", extra_closures=["2025-01-09"])
    assert not cal.is_trading_day(date(2025, 1, 9))


def series(days):
    bars = [DailyBar(d, 100.0 + i, 99.0 + i, datetime(d.year, d.month, d.day, 16, tzinfo=NY)) for i, d in enumerate(days)]
    return PriceSeries("AAPL", "NMS", "USD", "America/New_York", "test", bars)


def test_current_price_is_latest_session_and_not_stale():
    s = series([date(2026, 11, 10), date(2026, 11, 11), date(2026, 11, 12)])  # Nov 12 is a live intraday bar
    q = select_quote(s, ny(2026, 11, 12, 11, 0))
    assert q.price_date == "2026-11-11" and not q.stale
    assert q.currency == "USD" and q.exchange == "NMS" and q.source == "test"


def test_price_is_stale_when_older_than_latest_session():
    q = select_quote(series([date(2026, 11, 9), date(2026, 11, 10)]), ny(2026, 11, 12, 17, 0))
    assert q.stale and q.reference_session == "2026-11-12" and "Stale" in q.note


def test_historical_date_on_weekend_uses_previous_session():
    q = select_quote(series([date(2026, 11, 5), date(2026, 11, 6)]), ny(2026, 11, 12, 17), on_date=date(2026, 11, 8))
    assert q.price_date == "2026-11-06" and not q.stale


CHART = {"chart": {"error": None, "result": [{
    "meta": {"symbol": "AAPL", "currency": "USD", "exchangeName": "NMS", "exchangeTimezoneName": "America/New_York"},
    "timestamp": [int(ny(2026, 11, 10, 9, 30).timestamp()), int(ny(2026, 11, 11, 9, 30).timestamp())],
    "indicators": {"quote": [{"close": [350.5, None]}], "adjclose": [{"adjclose": [349.9, None]}]},
}]}}


def test_yahoo_payload_parsing_skips_missing_closes():
    s = YahooChartProvider(client=None).parse("AAPL", CHART)
    assert [(b.day, b.close, b.adjusted_close) for b in s.bars] == [(date(2026, 11, 10), 350.5, 349.9)]


def test_provider_refusal_by_robots_txt_is_respected(tmp_path):
    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx2.Response(200, text="User-agent: *\nDisallow: /\n")
        raise AssertionError("must not request a disallowed URL")
    fc = FakeClock()
    client = PoliteClient(make_settings(tmp_path), transport=httpx2.MockTransport(handler), sleep=fc.sleep, clock=fc.clock)
    with pytest.raises(AccessDenied):
        get_closing_price("AAPL", make_settings(tmp_path), client, now=ny(2026, 11, 12, 17))


def test_price_fetch_when_allowed(tmp_path):
    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx2.Response(404)
        return httpx2.Response(200, json=CHART)
    fc = FakeClock()
    settings = make_settings(tmp_path)
    client = PoliteClient(settings, transport=httpx2.MockTransport(handler), sleep=fc.sleep, clock=fc.clock)
    q = get_closing_price("AAPL", settings, client, now=ny(2026, 11, 11, 17))
    assert q.price_date == "2026-11-10" and q.stale  # the Nov 11 close is missing in the data
