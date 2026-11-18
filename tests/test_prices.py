# Price freshness (US holiday rules, latest completed session, stale flags, historical dates) and the provider-neutral price interface.
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from backend.errors import ProviderNotConfigured
from backend.fetchers import market_data
from backend.fetchers.http_client import PoliteClient
from backend.fetchers.market_data import DailyBar, PriceSeries, get_closing_price, select_quote
from backend.market_calendar import calendar_for, us_holidays
from tests.helpers import make_settings

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




def test_unconfigured_market_data_gives_a_setup_message(tmp_path):
    settings = make_settings(tmp_path)
    with pytest.raises(ProviderNotConfigured) as exc:
        get_closing_price("AAPL", settings, PoliteClient(settings), now=ny(2026, 11, 12, 17))
    assert exc.value.missing == ["MARKET_DATA_PROVIDER", "MARKET_DATA_API_KEY"]


def test_named_provider_without_an_adapter_says_so(tmp_path):
    settings = make_settings(tmp_path, market_data_provider="someprovider", market_data_api_key="k")
    with pytest.raises(ProviderNotConfigured, match="No adapter exists yet for provider 'someprovider'"):
        get_closing_price("AAPL", settings, PoliteClient(settings))


def test_a_registered_adapter_is_used_through_the_interface(tmp_path, monkeypatch):
    class FakeAdapter(market_data.PriceProvider):
        name = "fake prices"

        def daily_series(self, ticker, start, end):
            return series([date(2026, 11, 10), date(2026, 11, 11), date(2026, 11, 12)])
    monkeypatch.setitem(market_data.ADAPTERS, "fake", FakeAdapter)
    settings = make_settings(tmp_path, market_data_provider="fake", market_data_api_key="k")
    q = get_closing_price("AAPL", settings, PoliteClient(settings), now=ny(2026, 11, 12, 17))
    assert q.price_date == "2026-11-12" and not q.stale
