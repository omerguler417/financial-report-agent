# Share prices from one consistent provider, with ticker, exchange, currency, source and timestamp recorded and stale prices flagged.
# Working: provider-independent freshness rules and the provider interface. No provider is chosen; until one is configured, price requests return a setup message.
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone

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


# Adapters available in the code, by provider name. Empty until a provider is chosen.
ADAPTERS: dict[str, type[PriceProvider]] = {}


def get_provider(settings: Settings, client: PoliteClient) -> PriceProvider:
    services.require(settings, "market_data")  # clear setup message when unconfigured or no adapter exists
    return ADAPTERS[settings.market_data_provider](settings, client)


def get_closing_price(ticker: str, settings: Settings, client: PoliteClient, on_date: date | None = None,
                      now: datetime | None = None) -> PriceQuote:
    now = now or datetime.now(timezone.utc)
    target = on_date or now.date()
    series = get_provider(settings, client).daily_series(ticker, target - timedelta(days=14), target)
    return select_quote(series, now, on_date, settings.extra_market_closures)
