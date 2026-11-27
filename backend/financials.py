# Report figures that passed the checks in backend/validation.py, turned into the inputs for the indicator calculations.
# Each figure keeps its value, unit, period and sources. TTM figures are built later, in backend/indicators.py.
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from backend.indicators import CompanyInputs, Figure, fiscal_year

# The figures Agent 1 asks for, with the v1.0 section 4 meaning the model must follow.
FIELDS = {
    "revenue": "Consolidated revenue or sales (for banks, not deposits or loan balances)",
    "ebit": "Operating earnings before interest and tax",
    "depreciation_amortisation": "Depreciation and amortisation charged in arriving at EBIT (not impairments)",
    "interest_expense": "Gross interest expense (not total finance costs or FX losses)",
    "pretax_income": "Income before income taxes",
    "income_tax": "Income tax expense",
    "net_income_group": "Total consolidated net income, including non-controlling interests",
    "nci_share_of_income": "Net income attributable to non-controlling interests",
    "net_income_common": "Net income attributable to the parent's common shareholders",
    "cfo_reported": "Net cash from operating activities, as reported",
    "capex": "Cash spent on long-term tangible and intangible operating assets, as a positive amount",
    "dividends_paid_common": "Cash dividends paid to common shareholders",
    "assets_total": "Total assets",
    "current_assets": "Total current assets",
    "current_liabilities": "Total current liabilities",
    "cash_eligible": "Unrestricted cash and cash equivalents",
    "debt_ex_leases": "Interest-bearing borrowings, short- and long-term, including current maturities",
    "lease_liabilities": "Recognised lease liabilities, current and non-current",
    "equity_common": "Equity attributable to the parent's common shareholders",
    "nci": "Non-controlling interests in equity",
    "equity_total": "Total equity",
    "preferred_equity": "Preferred equity, if shown",
    "non_operating_investments": "Non-operating financial investments, if shown separately",
    "shares_outstanding": "Common shares outstanding at the balance-sheet date",
    "statutory_tax_rate": "Home-country statutory income tax rate stated in the tax note (for US companies the federal rate), in percent",
    "cost_of_sales": "Cost of sales (not for banks)",
    "eps_basic": "Basic earnings per share as reported", "eps_diluted": "Diluted earnings per share as reported",
    "weighted_shares_basic": "Weighted-average basic shares", "weighted_shares_diluted": "Weighted-average diluted shares",
    "dividends_per_share": "Dividends paid per common share in the period",
    "short_term_investments": "Liquid short-term investments", "trade_receivables": "Net trade receivables", "inventories": "Inventories",
    "trade_payables": "Trade payables", "goodwill": "Goodwill", "intangible_assets": "Other intangible assets",
    "free_float_shares": "Shares in free float, as defined by the source",
    "interest_paid_in_cfo": "Cash interest paid, when it is classified within operating activities",
    "interest_paid_outside_cfo": "Cash interest paid, when it is classified outside operating activities",
    "lease_principal_outside_cfo": "Principal payments on lease liabilities classified outside operating activities",
    "dividends_paid_in_cfo": "Shareholder dividends paid that are classified within operating activities",
}

YTD = re.compile(r"YTD (Q[1-4]|H[12]) (\d{4})")


def build_inputs(name: str, figures: list[dict], price: Figure | None, business_model: str = "operating",
                 demo_label: str | None = None, points: dict | None = None) -> CompanyInputs:
    """figures: checked figures ({field, period, value, unit, sources}). Picks the latest fiscal year and, when one exists after it,
    the latest year-to-date period with the same period a year earlier, so TTM can be built."""
    periods: dict = {}
    for f in figures:
        periods.setdefault(f["period"], {})[f["field"]] = Figure(f["field"], f["value"], f["unit"], f["period"], list(f["sources"]))
    years = sorted((p for p in periods if fiscal_year(p)), key=fiscal_year)
    if not years:
        raise ValueError("No full fiscal-year figures were found in the reports, so the indicators cannot be calculated.")
    latest = years[-1]
    interim = sorted(((int(m.group(2)), m.group(1), p) for p in periods if (m := YTD.fullmatch(p)) and int(m.group(2)) > fiscal_year(latest)),
                     reverse=True)
    current = prior = None
    if interim:
        year, part, label = interim[0]
        prior_label = f"YTD {part} {year - 1}"
        if prior_label in periods:
            current, prior = label, prior_label
    return CompanyInputs(name, periods, latest, current, prior, price, business_model, demo_label, points or {})


def price_figure(quote, demo: bool = False) -> Figure:
    """The closing price from a market-data quote, with its source."""
    source = {"publisher": quote.source, "date": quote.price_date, "exchange": quote.exchange}
    return Figure("price", quote.close, f"{quote.currency} per share", f"close {quote.price_date}", [{**source, "demo": True} if demo else source],
                  "Stale price: the latest expected session is missing." if quote.stale else "")


def _now(tz):
    return datetime.now(tz)


def _quote(market, ticker: str, on):
    """The close for `on`. For today (or later), only a completed session counts, never today's unfinished trading (v1.0)."""
    from datetime import timedelta
    from backend.fetchers.market_data import select_quote
    series = market.daily_series(ticker, on - timedelta(days=14), on)
    tz = ZoneInfo(series.timezone)
    now = _now(tz)
    if on >= now.date():
        return select_quote(series, now)
    return select_quote(series, datetime(on.year, on.month, on.day, 23, 59, tzinfo=tz), on_date=on)


def closing_price(market, ticker: str, on, demo: bool = False) -> Figure:
    """Closing price of the latest completed session on or before `on`."""
    return price_figure(_quote(market, ticker, on), demo)


def months_before(day, months: int):
    year, month = divmod(day.year * 12 + day.month - 1 - months, 12)
    month += 1
    for d in (day.day, 30, 29, 28):  # the same day of the month, or the month's last day
        try:
            return day.replace(year=year, month=month, day=d)
        except ValueError:
            continue


def price_points(market, ticker: str, on, demo: bool = False, years: int = 5) -> dict:
    """Split-adjusted closes for price returns (now, 1, 3 and 12 months earlier) and closes at the preceding `years` calendar year
    ends (the analysis horizon), for historical multiple medians. A price that cannot be found is left out, never invented."""
    from datetime import date
    points = {}
    wanted = {"end": on, "1m": months_before(on, 1), "3m": months_before(on, 3), "12m": months_before(on, 12)}
    for key, day in wanted.items():
        try:
            q = _quote(market, ticker, day)
        except Exception:
            continue
        adjusted = q.adjusted_close if q.adjusted_close is not None else q.close
        source = {"publisher": q.source, "date": q.price_date, "exchange": q.exchange, **({"demo": True} if demo else {})}
        points[key] = Figure("adjusted_close", adjusted, f"{q.currency} per share", f"close {q.price_date}", [source],
                             "" if q.adjusted_close is not None else "No split-adjusted series; the plain close is used.")
    for year in range(on.year - 1, on.year - 1 - years, -1):
        day = date(year, 12, 31)
        try:
            points[f"year end {day.isoformat()}"] = closing_price(market, ticker, day, demo)
        except Exception:
            continue
    return points


def business_model(profile: dict) -> str:
    """Banks and insurers get the v1.0 section 8 treatment; taken from the industry classification, never from the company's name."""
    industry = (profile.get("industry") or "").lower()
    if "bank" in industry:
        return "bank"
    if "insur" in industry:
        return "insurer"
    return "operating"
