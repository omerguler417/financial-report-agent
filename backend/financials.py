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
}

YTD = re.compile(r"YTD (Q[1-4]|H[12]) (\d{4})")


def build_inputs(name: str, figures: list[dict], price: Figure | None, business_model: str = "operating",
                 demo_label: str | None = None) -> CompanyInputs:
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
    return CompanyInputs(name, periods, latest, current, prior, price, business_model, demo_label)


def price_figure(quote, demo: bool = False) -> Figure:
    """The closing price from a market-data quote, with its source."""
    source = {"publisher": quote.source, "date": quote.price_date, "exchange": quote.exchange}
    return Figure("price", quote.close, f"{quote.currency} per share", f"close {quote.price_date}", [{**source, "demo": True} if demo else source],
                  "Stale price: the latest expected session is missing." if quote.stale else "")


def closing_price(market, ticker: str, on, demo: bool = False) -> Figure:
    """Closing price of the latest completed session on or before `on`."""
    from datetime import timedelta
    from backend.fetchers.market_data import select_quote
    series = market.daily_series(ticker, on - timedelta(days=14), on)
    now = datetime(on.year, on.month, on.day, 23, 59, tzinfo=ZoneInfo(series.timezone))
    return price_figure(select_quote(series, now, on_date=on), demo)


def business_model(profile: dict) -> str:
    """Banks and insurers get the v1.0 section 8 treatment; taken from the industry classification, never from the company's name."""
    industry = (profile.get("industry") or "").lower()
    if "bank" in industry:
        return "bank"
    if "insur" in industry:
        return "insurer"
    return "operating"
