# Trading calendars for price freshness: US exchange holidays (NYSE/Nasdaq rules), the latest completed session, and stale-price checks.
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

US_EXCHANGE_CODES = {"NYQ", "NYSE", "NMS", "NGM", "NCM", "NASDAQ", "ASE", "PCX", "BTS", "NYSEARCA", "AMEX"}
US_TZ = ZoneInfo("America/New_York")
US_CLOSE = time(16, 0)
GENERIC_CLOSE = time(18, 0)  # conservative "session complete" time for exchanges without a holiday calendar


def _nth_weekday(year, month, weekday, n):
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def _last_weekday(year, month, weekday):
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    last = nxt - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _easter(year):
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month = (h + l_ - 7 * m + 114) // 31
    day = (h + l_ - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def _observed(day: date) -> date:
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


def us_holidays(year: int) -> set[date]:
    """Full-day closures under standing NYSE rules. Early closes are treated as normal days."""
    holidays = set()
    new_year = date(year, 1, 1)
    if new_year.weekday() == 6:
        holidays.add(date(year, 1, 2))
    elif new_year.weekday() != 5:  # a Saturday New Year's Day is not observed on Friday
        holidays.add(new_year)
    holidays.add(_nth_weekday(year, 1, 0, 3))   # Martin Luther King Jr. Day
    holidays.add(_nth_weekday(year, 2, 0, 3))   # Washington's Birthday
    holidays.add(_easter(year) - timedelta(days=2))  # Good Friday
    holidays.add(_last_weekday(year, 5, 0))     # Memorial Day
    if year >= 2022:
        holidays.add(_observed(date(year, 6, 19)))  # Juneteenth
    holidays.add(_observed(date(year, 7, 4)))   # Independence Day
    holidays.add(_nth_weekday(year, 9, 0, 1))   # Labor Day
    holidays.add(_nth_weekday(year, 11, 3, 4))  # Thanksgiving
    holidays.add(_observed(date(year, 12, 25)))  # Christmas
    return holidays


class TradingCalendar:
    def __init__(self, tz: ZoneInfo, close: time, use_us_holidays: bool, extra_closures=()):
        self.tz = tz
        self.close = close
        self.use_us_holidays = use_us_holidays
        self.extra_closures = {date.fromisoformat(d) if isinstance(d, str) else d for d in extra_closures}

    @property
    def note(self) -> str:
        if self.use_us_holidays:
            return "US exchange calendar: weekends and standing NYSE holidays; early closes treated as 16:00."
        return "No holiday calendar for this exchange: only weekends are excluded, so freshness is approximate."

    def is_trading_day(self, day: date) -> bool:
        if day.weekday() >= 5 or day in self.extra_closures:
            return False
        return not (self.use_us_holidays and day in us_holidays(day.year))

    def previous_trading_day(self, day: date) -> date:
        day -= timedelta(days=1)
        while not self.is_trading_day(day):
            day -= timedelta(days=1)
        return day

    def latest_completed_session(self, now: datetime) -> date:
        local = now.astimezone(self.tz)
        today = local.date()
        if self.is_trading_day(today) and local.time() >= self.close:
            return today
        return self.previous_trading_day(today)

    def session_on_or_before(self, day: date) -> date:
        return day if self.is_trading_day(day) else self.previous_trading_day(day)


def calendar_for(exchange_code: str | None, tz_name: str | None = None, extra_closures=()) -> TradingCalendar:
    if (exchange_code or "").upper() in US_EXCHANGE_CODES or tz_name == "America/New_York":
        return TradingCalendar(US_TZ, US_CLOSE, True, extra_closures)
    return TradingCalendar(ZoneInfo(tz_name or "UTC"), GENERIC_CLOSE, False, extra_closures)
