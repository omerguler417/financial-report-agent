# Share prices from one consistent provider, with ticker, exchange, currency, source and timestamp recorded and stale prices flagged.
# Working: provider-independent freshness rules and the provider interface. The Yahoo connector obeys Yahoo's robots.txt, which currently refuses automated access.
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from backend.config import Settings
from backend.fetchers.http_client import PoliteClient
from backend.market_calendar import calendar_for


@dataclass
class DailyBar:
    day: date
    close: float
    adjusted_close: float | None
    timestamp: datetime


@dataclass
class PriceSeries:
    ticker: str
    exchange: str
    currency: str
    timezone: str
    source: str
    bars: list[DailyBar]


@dataclass
class PriceQuote:
    ticker: str
    exchange: str
    currency: str
    source: str
    price_date: str
    close: float
    adjusted_close: float | None
    price_timestamp: str
    retrieved_at: str
    reference_session: str
    stale: bool
    note: str

    def to_dict(self) -> dict:
        return asdict(self)


class PriceUnavailable(Exception):
    pass


def select_quote(series: PriceSeries, now: datetime, on_date: date | None = None, extra_closures=()) -> PriceQuote:
    """Current valuation: the latest completed session's close; stale if older.
    Historical valuation: the close on the requested date, or the last session before it."""
    calendar = calendar_for(series.exchange, series.timezone, extra_closures)
    if on_date is None:
        reference = calendar.latest_completed_session(now)
    else:
        reference = calendar.session_on_or_before(on_date)
    usable = [b for b in series.bars if b.day <= reference and b.close is not None]
    if not usable:
        raise PriceUnavailable(f"No closing price for {series.ticker} on or before {reference.isoformat()}.")
    bar = max(usable, key=lambda b: b.day)
    stale = bar.day < reference
    note = calendar.note
    if stale:
        note = f"Stale: latest available close is {bar.day.isoformat()}, but the reference session is {reference.isoformat()}. " + note
    return PriceQuote(
        ticker=series.ticker, exchange=series.exchange, currency=series.currency, source=series.source,
        price_date=bar.day.isoformat(), close=bar.close, adjusted_close=bar.adjusted_close,
        price_timestamp=bar.timestamp.isoformat(), retrieved_at=now.astimezone(timezone.utc).isoformat(),
        reference_session=reference.isoformat(), stale=stale, note=note,
    )


class YahooChartProvider:
    """Yahoo Finance chart endpoint. Every request goes through PoliteClient, so robots.txt is obeyed."""

    name = "Yahoo Finance (chart endpoint)"
    base_url = "https://query1.finance.yahoo.com/v8/finance/chart/"

    def __init__(self, client: PoliteClient):
        self.client = client

    def daily_series(self, ticker: str, start: date, end: date) -> PriceSeries:
        start_ts = int(datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp())
        end_ts = int(datetime(end.year, end.month, end.day, tzinfo=timezone.utc).timestamp()) + 86400
        response = self.client.get(self.base_url + ticker, params={
            "period1": start_ts, "period2": end_ts, "interval": "1d", "events": "div,splits",
        })
        return self.parse(ticker, response.json())

    def parse(self, ticker: str, payload: dict) -> PriceSeries:
        chart = payload.get("chart") or {}
        if chart.get("error") or not chart.get("result"):
            raise PriceUnavailable(f"{self.name} returned no data for {ticker}: {chart.get('error')}")
        result = chart["result"][0]
        meta = result["meta"]
        tz = ZoneInfo(meta.get("exchangeTimezoneName", "UTC"))
        closes = result["indicators"]["quote"][0].get("close", [])
        adjusted = (result["indicators"].get("adjclose") or [{}])[0].get("adjclose") or [None] * len(closes)
        bars = []
        for ts, close, adj in zip(result.get("timestamp", []), closes, adjusted):
            if close is None:
                continue
            moment = datetime.fromtimestamp(ts, tz)
            bars.append(DailyBar(moment.date(), float(close), None if adj is None else float(adj), moment))
        return PriceSeries(ticker=meta.get("symbol", ticker), exchange=meta.get("exchangeName", ""),
                           currency=meta.get("currency", ""), timezone=str(tz), source=self.name, bars=bars)


def get_provider(settings: Settings, client: PoliteClient):
    if settings.price_provider == "yahoo":
        return YahooChartProvider(client)
    raise PriceUnavailable(f"Unknown price provider '{settings.price_provider}'.")


def get_closing_price(ticker: str, settings: Settings, client: PoliteClient, on_date: date | None = None,
                      now: datetime | None = None) -> PriceQuote:
    now = now or datetime.now(timezone.utc)
    target = on_date or now.date()
    series = get_provider(settings, client).daily_series(ticker, target - timedelta(days=14), target)
    return select_quote(series, now, on_date, settings.extra_market_closures)
