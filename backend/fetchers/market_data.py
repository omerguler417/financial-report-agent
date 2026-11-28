# Share prices from one consistent provider, with ticker, exchange, currency, source and timestamp recorded and stale prices flagged.
# Working: provider-independent freshness rules and the provider interface. No provider is chosen; until one is configured, price requests return a setup message.
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from backend import services
from backend.config import Settings
from backend.fetchers.http_client import PoliteClient
from backend.market_calendar import calendar_for


@dataclass
class DailyBar:
    day: date
    close: float
    adjusted_close: float | None
    timestamp: datetime
    volume: float | None = None  # shares traded; used for the trading-liquidity indicators


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


class PriceProvider:
    """Interface every market-data adapter implements. No provider is chosen yet; an adapter is added to ADAPTERS
    (keyed by the MARKET_DATA_PROVIDER name) once one is selected. All its requests must go through PoliteClient."""

    name = "base"

    def __init__(self, settings: Settings, client: PoliteClient):
        self.settings, self.client = settings, client

    def daily_series(self, ticker: str, start: date, end: date) -> PriceSeries:
        raise NotImplementedError


class TwelveDataProvider(PriceProvider):
    """Twelve Data's official REST API with the group's own key (decided 25 November 2026). Its robots.txt disallows all crawlers; the
    group recorded a narrow exception for this API only (CLAUDE.md; docs/twelvedata_robots_exception.md). Per company, one request
    for actual closes and one for split-adjusted closes; later prices in the same analysis come from that answer. The key is sent in
    a header, never in the address."""

    name = "twelve_data"
    SOURCE = "Twelve Data"
    YEARS = 11  # one request covers 12-month returns and the year ends of the longest horizon (10 years)

    def __init__(self, settings: Settings, client: PoliteClient):
        super().__init__(settings, client)
        self.base = (settings.market_data_base_url or "https://api.twelvedata.com").rstrip("/")
        self._cache: dict = {}
        client.set_min_interval(self.base.split("://", 1)[-1].split("/", 1)[0], settings.market_data_min_interval_seconds)

    def _fetch(self, ticker: str, start: date, end: date, adjust: str) -> dict:
        response = self.client.get(f"{self.base}/time_series",
                                   params={"symbol": ticker, "interval": "1day", "start_date": start.isoformat(), "end_date": end.isoformat(),
                                           "adjust": adjust, "order": "ASC", "outputsize": 5000},
                                   headers={"Authorization": f"apikey {self.settings.market_data_api_key}"})
        body = response.json()
        if body.get("status") == "error":
            message = str(body.get("message", "")).replace(self.settings.market_data_api_key, "[key]")
            raise PriceUnavailable(f"Twelve Data could not provide prices for {ticker} (code {body.get('code')}): {message}")
        return body

    def daily_series(self, ticker: str, start: date, end: date) -> PriceSeries:
        key = ticker.upper()
        cached = self._cache.get(key)
        if cached is None or start < cached[0] or end > cached[1]:
            first = min(start, end - timedelta(days=366 * self.YEARS))
            self._cache[key] = (first, end, self._fetch(key, first, end, "none"), self._fetch(key, first, end, "splits"))
        _, _, actual, adjusted = self._cache[key]
        meta = actual.get("meta", {})
        tz_name = meta.get("exchange_timezone") or "America/New_York"
        tz = ZoneInfo(tz_name)
        split_adjusted = {v["datetime"][:10]: float(v["close"]) for v in adjusted.get("values", [])}
        bars = []
        for v in actual.get("values", []):
            day = date.fromisoformat(v["datetime"][:10])
            if start <= day <= end:
                bars.append(DailyBar(day, float(v["close"]), split_adjusted.get(v["datetime"][:10]),
                                     datetime(day.year, day.month, day.day, 16, 0, tzinfo=tz), float(v["volume"]) if v.get("volume") else None))
        bars.sort(key=lambda b: b.day)
        return PriceSeries(key, meta.get("exchange") or "", meta.get("currency") or "", tz_name, self.SOURCE, bars)


# Adapters available in the code, by the MARKET_DATA_PROVIDER name used in .env.
ADAPTERS: dict[str, type[PriceProvider]] = {"twelve_data": TwelveDataProvider}


def get_provider(settings: Settings, client: PoliteClient) -> PriceProvider:
    services.require(settings, "market_data")  # clear setup message when unconfigured or no adapter exists
    return ADAPTERS[settings.market_data_provider](settings, client)


def get_closing_price(ticker: str, settings: Settings, client: PoliteClient, now: datetime | None = None) -> PriceQuote:
    """The latest completed session's close: during trading hours, the previous session's close."""
    now = now or datetime.now(timezone.utc)
    series = get_provider(settings, client).daily_series(ticker, now.date() - timedelta(days=14), now.date())
    return select_quote(series, now, None, settings.extra_market_closures)
