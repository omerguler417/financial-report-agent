# Test sample data: fictional companies, reports, prices, a call transcript and a recorded transcription. Nothing here is real or live.
# Reports are rendered as pages of text so later steps can practise extracting figures and citing document + page + section.
import random
from datetime import date, timedelta

from backend.market_calendar import calendar_for

DEMO_LABEL = "DEMO – fictional sample data, not real"
SOURCE_NAME = "DEMO sample documents (fictional)"
MARKET_NAME = "DEMO market data (fictional)"
LATEST_RESULTS_ANNOUNCEMENT = "2026-10-28"
YEARS = [2021, 2022, 2023, 2024, 2025]
STATUTORY_TAX_RATE = 21.0  # stated in each annual report's tax note; ROIC uses the home-country rate the report states

_OIL = dict(industry="Oil & Gas Integrated", sector="Energy", products=["crude oil", "natural gas"], customers=["refiners", "utilities"],
            segments=["upstream", "midstream", "downstream"], operating_model="integrated", regions={"North America": 0.7, "Europe": 0.3})
COMPANIES = {
    "NRTH.DEMO": dict(_OIL, name="Northgate Energy Corp (demo)", rev0=9200.0, growth=[0.22, -0.04, 0.05, 0.08, 0.06], margin=0.17,
                      assets_mult=1.5, equity_ratio=0.46, debt_ratio=0.20, nci_share=0.04, shares=812.0, payout=0.35, price0=11.0,
                      competitors=["Ridgeway Petroleum (demo)", "Saltlake Resources (demo)"]),
    "RDGE.DEMO": dict(_OIL, name="Ridgeway Petroleum (demo)", rev0=7400.0, growth=[0.18, -0.06, 0.04, 0.07, 0.05], margin=0.15,
                      assets_mult=1.6, equity_ratio=0.42, debt_ratio=0.24, nci_share=0.0, shares=640.0, payout=0.30, price0=14.0,
                      competitors=["Northgate Energy Corp (demo)"]),
    "SLTK.DEMO": dict(_OIL, name="Saltlake Resources (demo)", rev0=3900.0, growth=[0.25, -0.08, 0.03, 0.06, 0.04], margin=0.14,
                      assets_mult=1.7, equity_ratio=0.40, debt_ratio=0.27, nci_share=0.0, shares=310.0, payout=0.25, price0=9.0,
                      competitors=["Ridgeway Petroleum (demo)"]),
    "CRBN.DEMO": dict(_OIL, name="Carbonfield Oil & Gas (demo)", rev0=11800.0, growth=[0.20, -0.02, 0.06, 0.09, 0.07], margin=0.18,
                      assets_mult=1.4, equity_ratio=0.50, debt_ratio=0.18, nci_share=0.02, shares=1040.0, payout=0.40, price0=12.5,
                      competitors=["Northgate Energy Corp (demo)"]),
    "LKSB.DEMO": dict(industry="Banks - Regional", sector="Financial Services", products=["loans", "deposits"],
                      customers=["households", "small businesses"], segments=["retail banking", "commercial lending"],
                      operating_model="bank", regions={"North America": 1.0}, name="Lakeshore Bank (demo)", rev0=2100.0,
                      growth=[0.05, 0.04, 0.06, 0.05, 0.04], margin=0.33, assets_mult=12.0, equity_ratio=0.085, debt_ratio=0.06,
                      nci_share=0.0, shares=180.0, payout=0.35, price0=40.0, competitors=[]),
}
TARGET = "NRTH.DEMO"

LABELS = {
    "revenue": "Total revenues", "ebit": "Operating income (EBIT)", "depreciation_amortisation": "Depreciation and amortisation",
    "interest_expense": "Interest expense", "pretax_income": "Income before income taxes", "income_tax": "Income tax expense",
    "net_income_group": "Net income", "nci_share_of_income": "Net income attributable to noncontrolling interests",
    "net_income_common": "Net income attributable to common shareholders", "cfo_reported": "Net cash provided by operating activities",
    "capex": "Capital expenditures", "dividends_paid_common": "Dividends paid to common shareholders", "assets_total": "Total assets",
    "current_assets": "Total current assets", "current_liabilities": "Total current liabilities",
    "cash_eligible": "Cash and cash equivalents (unrestricted)", "debt_ex_leases": "Total borrowings", "lease_liabilities": "Lease liabilities",
    "equity_common": "Equity attributable to common shareholders", "nci": "Noncontrolling interests", "equity_total": "Total equity",
    "shares_outstanding": "Common shares outstanding (millions)",
    "statutory_tax_rate": "U.S. federal statutory income tax rate (%)",
    "cost_of_sales": "Cost of sales", "eps_basic": "Basic earnings per share (USD)", "eps_diluted": "Diluted earnings per share (USD)",
    "weighted_shares_basic": "Weighted-average basic shares (millions)", "weighted_shares_diluted": "Weighted-average diluted shares (millions)",
    "dividends_per_share": "Dividends paid per common share (USD)", "short_term_investments": "Short-term investments (liquid)",
    "trade_receivables": "Trade receivables, net", "inventories": "Inventories", "trade_payables": "Trade payables", "goodwill": "Goodwill",
    "intangible_assets": "Other intangible assets", "free_float_shares": "Free-float shares (millions)",
    "interest_paid_in_cfo": "Interest paid (within operating activities)",
    "lease_principal_outside_cfo": "Principal payments on lease liabilities (financing activities)",
}
INCOME = ["revenue", "cost_of_sales", "ebit", "depreciation_amortisation", "interest_expense", "pretax_income", "income_tax", "net_income_group",
          "nci_share_of_income", "net_income_common", "eps_basic", "eps_diluted", "weighted_shares_basic", "weighted_shares_diluted",
          "dividends_per_share"]
BALANCE = ["assets_total", "current_assets", "cash_eligible", "short_term_investments", "trade_receivables", "inventories", "goodwill",
           "intangible_assets", "current_liabilities", "trade_payables", "debt_ex_leases", "lease_liabilities", "equity_common", "nci",
           "equity_total", "shares_outstanding", "free_float_shares"]
CASHFLOW = ["cfo_reported", "interest_paid_in_cfo", "capex", "lease_principal_outside_cfo", "dividends_paid_common"]
PROVENANCE = {"currency": "USD", "units": "millions", "consolidation_scope": "consolidated", "accounting_framework": "US GAAP",
              "restatement_status": "as originally reported"}


def _r(x: float) -> float:
    return round(x, 1)


def _flows(c: dict, revenue: float, margin: float, debt: float) -> dict:
    """Income-statement and cash-flow figures, rounded so the rendered numbers add up exactly."""
    ebit = _r(revenue * margin)
    dna = _r(revenue * (0.03 if c["sector"] == "Financial Services" else 0.07))
    interest = _r(debt * 0.055)
    pretax = _r(ebit - interest)
    tax = _r(pretax * 0.22)
    net_group = _r(pretax - tax)
    nci_income = _r(net_group * c["nci_share"])
    net_common = _r(net_group - nci_income)
    bank = c["sector"] == "Financial Services"
    extra = {} if bank else {"cost_of_sales": _r(revenue * 0.6)}
    return {**extra, "interest_paid_in_cfo": _r(interest * 0.96), "revenue": _r(revenue), "ebit": ebit, "depreciation_amortisation": dna, "interest_expense": interest, "pretax_income": pretax,
            "income_tax": tax, "net_income_group": net_group, "nci_share_of_income": nci_income, "net_income_common": net_common,
            "cfo_reported": _r(net_group + dna * 0.95),
            "capex": _r(revenue * (0.03 if c["sector"] == "Financial Services" else 0.09)), "dividends_paid_common": _r(net_common * c["payout"])}


def _balance(c: dict, revenue: float, shares: float) -> dict:
    assets = _r(revenue * c["assets_mult"])
    equity_total = _r(assets * c["equity_ratio"])
    nci = _r(equity_total * c["nci_share"])
    operating = {} if c["sector"] == "Financial Services" else {
        "trade_receivables": _r(assets * 0.08), "inventories": _r(assets * 0.05), "trade_payables": _r(assets * 0.07)}
    return {**operating, "short_term_investments": _r(assets * 0.02), "goodwill": _r(assets * 0.05), "intangible_assets": _r(assets * 0.02),
            "free_float_shares": _r(shares * 0.93),
            "assets_total": assets, "current_assets": _r(assets * 0.25), "current_liabilities": _r(assets * 0.15),
            "cash_eligible": _r(assets * 0.06), "debt_ex_leases": _r(assets * c["debt_ratio"]), "lease_liabilities": _r(assets * c["debt_ratio"] * 0.1),
            "equity_common": _r(equity_total - nci), "nci": nci, "equity_total": _r(_r(equity_total - nci) + nci), "shares_outstanding": _r(shares)}


def _per_share_and_leases(v: dict) -> dict:
    """Per-share figures and lease repayments, which need the period's net income, dividends and balance sheet."""
    basic = _r(v["shares_outstanding"] * 1.004)
    diluted = _r(basic * 1.012)
    v.update(weighted_shares_basic=basic, weighted_shares_diluted=diluted, eps_basic=_r(v["net_income_common"] / basic),
             eps_diluted=_r(v["net_income_common"] / diluted), dividends_per_share=_r(v["dividends_paid_common"] / basic),
             lease_principal_outside_cfo=_r(v["lease_liabilities"] * 0.15))
    return v


def financials(ticker: str) -> dict:
    """Annual figures FY2021–FY2025 and year-to-date Q3 2026 / Q3 2025 (each with its period-end balance sheet), in USD millions (shares in millions)."""
    c = COMPANIES[ticker]
    annual, revenue = {}, c["rev0"]
    for i, year in enumerate(YEARS):
        rng = random.Random(f"{ticker}{year}")
        if i:
            revenue *= 1 + c["growth"][i - 1]
        margin = c["margin"] * (1 + rng.uniform(-0.06, 0.06))
        bal = _balance(c, revenue, c["shares"] * (1 - 0.01 * i))
        annual[f"FY{year}"] = _per_share_and_leases({**_flows(c, revenue, margin, bal["debt_ex_leases"]), **bal})
    fy25 = annual["FY2025"]
    rev_next = fy25["revenue"] * (1 + c["growth"][-1])
    cur = _per_share_and_leases({**_flows(c, rev_next * 0.75, c["margin"], fy25["debt_ex_leases"] * 0.75),
                                 **_balance(c, fy25["revenue"] * 1.03, fy25["shares_outstanding"] * 0.995)})
    fy24 = annual["FY2024"]
    prev = _per_share_and_leases({**_flows(c, fy25["revenue"] * 0.75, c["margin"], fy25["debt_ex_leases"] * 0.75),
                                  **_balance(c, fy24["revenue"] * 1.03, fy24["shares_outstanding"] * 0.995)})
    # Earlier Q3 reports (2021-2024): with them, the figures known at each past year end can be rebuilt for historical medians.
    history = {}
    for year in YEARS[:-1]:
        fy, before = annual[f"FY{year}"], annual.get(f"FY{year - 1}", {"revenue": c["rev0"] * 0.97, "shares_outstanding": c["shares"]})
        history[f"YTD Q3 {year}"] = _per_share_and_leases({**_flows(c, fy["revenue"] * 0.75, c["margin"], fy["debt_ex_leases"] * 0.75),
                                                           **_balance(c, before["revenue"] * 1.03, before["shares_outstanding"] * 0.995)})
    return {"annual": annual, "ytd": {"YTD Q3 2026": cur, "YTD Q3 2025": prev}, "ytd_history": history}


# ---------- rendered documents ----------

def _line(field: str, period: str, value: float) -> str:
    return f"{LABELS[field]} [{period}] ........ {value:,.1f}"


def _period_line(label: str, start: str, end: str, published: str) -> str:
    return (f"Period [{label}]: {start} to {end}, published {published}, USD millions, consolidated, US GAAP, as originally reported")


def _statement(title: str, fields: list[str], periods: list[tuple]) -> tuple[str, list[tuple]]:
    """periods: [(label, start, end, published, values)]. Returns the page text and the (field, label, value, line) entries on it."""
    rows, entries = [title], []
    for label, start, end, published, values in periods:
        rows.append(_period_line(label, start, end, published))
        for f in fields:
            if f in values:
                line = _line(f, label, values[f])
                rows.append(line)
                entries.append((f, label, values[f], line))
    return "\n".join(rows), entries


def _business_page(ticker: str) -> str:
    c = COMPANIES[ticker]
    lines = ["ITEM 1. BUSINESS", f"Products: {', '.join(c['products'])}", f"Customers: {', '.join(c['customers'])}",
             f"Segments: {', '.join(c['segments'])}", f"Operating model: {c['operating_model']}",
             "Revenue by region: " + "; ".join(f"{k} {v:.0%}" for k, v in c["regions"].items())]
    if c["competitors"]:
        lines.append("Competitors: " + ", ".join(c["competitors"]))
    return "\n".join(lines)


def _documents(ticker: str) -> tuple[list[dict], list[dict]]:
    c, f = COMPANIES[ticker], financials(ticker)
    short = ticker.split(".")[0]
    docs, index = [], []

    def add(kind, title, period, published, pages, entries_by_page):
        doc_id = f"demo-{short.lower()}-{kind}-{period.replace(' ', '').lower()}"
        docs.append({"doc_id": doc_id, "url": f"demo://{ticker}/{kind}/{period.replace(' ', '')}", "kind": kind, "title": f"{title} (demo)",
                     "period": period, "publication_date": published, "source_name": SOURCE_NAME, "demo": True, **PROVENANCE,
                     "filename": f"{short}_{kind}_{period.replace(' ', '_')}.txt", "pages": pages})
        for page_no, entries in entries_by_page.items():
            for field, label, value, line in entries:
                index.append({"doc_id": doc_id, "page": page_no, "field": field, "period": label, "value": value, "line": line})

    for year in YEARS:
        label, published, v = f"FY{year}", f"{year + 1}-02-20", f["annual"][f"FY{year}"]
        p = [(label, f"{year}-01-01", f"{year}-12-31", published, v)]
        income, e3 = _statement("CONSOLIDATED STATEMENT OF INCOME", INCOME, p)
        balance, e4 = _statement("CONSOLIDATED BALANCE SHEET", BALANCE, p)
        cash, e5 = _statement("CONSOLIDATED STATEMENT OF CASH FLOWS", CASHFLOW, p)
        cover = f"{DEMO_LABEL}\nANNUAL REPORT (Form 10-K) for the fiscal year ended December 31, {year}\n{c['name']}"
        mdna = ("MANAGEMENT'S DISCUSSION AND ANALYSIS\n"
                f"Revenue was {v['revenue']:,.1f} million in {year}.\nCommodity price volatility remains the main risk to results.")
        tax_line = _line("statutory_tax_rate", label, STATUTORY_TAX_RATE)
        tax = ("NOTES TO THE FINANCIAL STATEMENTS\nNote 9. Income taxes\n"
               "The company is incorporated and headquartered in the United States.\n" + tax_line)
        add("annual_report", f"Annual report FY{year}", label, published, [cover, _business_page(ticker), income, balance, cash, mdna, tax],
            {3: e3, 4: e4, 5: e5, 7: [("statutory_tax_rate", label, STATUTORY_TAX_RATE, tax_line)]})

    for year in YEARS[:-1]:
        label = f"YTD Q3 {year}"
        periods_q = [(label, f"{year}-01-01", f"{year}-09-30", f"{year}-10-28", f["ytd_history"][label])]
        income, e2 = _statement("CONDENSED STATEMENT OF INCOME", INCOME, periods_q)
        balance, e3 = _statement("CONDENSED BALANCE SHEET", BALANCE, periods_q)
        cash, e4 = _statement("CONDENSED STATEMENT OF CASH FLOWS", CASHFLOW, periods_q)
        cover = f"{DEMO_LABEL}\nQUARTERLY REPORT (Form 10-Q) for the quarter ended September 30, {year}\n{c['name']}"
        add("quarterly_report", f"Quarterly report Q3 {year}", f"Q3 {year}", f"{year}-10-28", [cover, income, balance, cash], {2: e2, 3: e3, 4: e4})

    cur, prev = f["ytd"]["YTD Q3 2026"], f["ytd"]["YTD Q3 2025"]
    # Prior-year Q3 report: its balance sheet is the opening balance for trailing-twelve-month averages.
    p25 = [("YTD Q3 2025", "2025-01-01", "2025-09-30", "2025-10-28", prev)]
    income, e2 = _statement("CONDENSED STATEMENT OF INCOME", INCOME, p25)
    balance, e3 = _statement("CONDENSED BALANCE SHEET", BALANCE, p25)
    cash, e4 = _statement("CONDENSED STATEMENT OF CASH FLOWS", CASHFLOW, p25)
    cover = f"{DEMO_LABEL}\nQUARTERLY REPORT (Form 10-Q) for the quarter ended September 30, 2025\n{c['name']}"
    add("quarterly_report", "Quarterly report Q3 2025", "Q3 2025", "2025-10-28", [cover, income, balance, cash], {2: e2, 3: e3, 4: e4})

    periods = [("YTD Q3 2026", "2026-01-01", "2026-09-30", LATEST_RESULTS_ANNOUNCEMENT, cur),
               ("YTD Q3 2025", "2025-01-01", "2025-09-30", "2025-10-28", prev)]
    income, e2 = _statement("CONDENSED STATEMENT OF INCOME", INCOME, periods)
    balance, e3 = _statement("CONDENSED BALANCE SHEET", BALANCE, periods[:1])
    cash, e4 = _statement("CONDENSED STATEMENT OF CASH FLOWS", CASHFLOW, periods)
    cover = f"{DEMO_LABEL}\nQUARTERLY REPORT (Form 10-Q) for the quarter ended September 30, 2026\n{c['name']}"
    mdna = ("MANAGEMENT'S DISCUSSION AND ANALYSIS\n"
            f"Revenue for the nine months ended September 30, 2026 was {cur['revenue']:,.1f} million, compared with {prev['revenue']:,.1f} million.\n"
            "Management expects capital expenditure to remain broadly in line with the prior year.")
    add("quarterly_report", "Quarterly report Q3 2026", "Q3 2026", LATEST_RESULTS_ANNOUNCEMENT, [cover, income, balance, cash, mdna],
        {2: e2, 3: e3, 4: e4})

    if ticker == TARGET:
        rev = cur["revenue"]
        p1 = (f"{DEMO_LABEL}\nQ3 2026 EARNINGS CALL TRANSCRIPT, {c['name']}\n"
              f"Maria Alvarez (CEO): Revenue for the nine months was {rev:,.1f} million, up on last year.\n"
              "Maria Alvarez (CEO): We expect fourth-quarter production to be between 410 and 430 thousand barrels per day.\n"
              "Daniel Okafor (CFO): We may increase the dividend if cash flow stays at current levels.")
        p2 = ("QUESTION AND ANSWER SESSION\n"
              "Priya Nair (Analyst): With higher commodity prices, I assume capital spending must rise sharply next year. What should we expect?\n"
              "Daniel Okafor (CFO): We expect capital expenditure to remain broadly in line with the prior year.\n"
              "Tom Becker (Analyst): New emissions rules seem likely to hurt margins. Can you quantify that?\n"
              "Maria Alvarez (CEO): It is too early to quantify the effect of the proposed regulation.")
        docs.append({"doc_id": f"demo-{short.lower()}-transcript-q32026", "url": f"demo://{ticker}/transcript/Q32026", "kind": "transcript",
                     "title": "Q3 2026 earnings call transcript (demo)", "period": "Q3 2026", "publication_date": LATEST_RESULTS_ANNOUNCEMENT,
                     "source_name": SOURCE_NAME, "demo": True, **PROVENANCE, "filename": f"{short}_transcript_Q3_2026.txt", "pages": [p1, p2]})
    return docs, index


def documents(ticker: str) -> list[dict]:
    return _documents(ticker)[0] if ticker in COMPANIES else []


def figure_index(ticker: str) -> list[dict]:
    """Where each figure sits: doc_id, page, field, period, value and the exact line. Used to check extraction and citations."""
    return _documents(ticker)[1]


# ---------- prices ----------

def price_bars(ticker: str, end: date) -> list[dict]:
    """Daily closes on US trading days from 2021. There are no splits in the demo data, so split-adjusted equals close."""
    c = COMPANIES[ticker]
    rng = random.Random(f"price-{ticker}")
    cal = calendar_for("NYSE")
    day, price, bars = date(2021, 1, 4), c["price0"], []
    while day <= end:
        if cal.is_trading_day(day):
            price = max(1.0, price * (1 + rng.gauss(0.00035, 0.016)))
            bars.append({"day": day, "close": round(price, 2), "volume": float(int(rng.uniform(0.002, 0.006) * c["shares"] * 1e6))})
        day += timedelta(days=1)
    return bars


# ---------- recorded transcription of a fictional Turkish call ----------

TURKISH_SEGMENTS = [
    {"start": 1.0, "end": 6.0, "text": "Üçüncü çeyrekte gelirimiz yüzde 12 arttı.", "speaker": None, "avg_logprob": -0.15},
    {"start": 7.0, "end": 12.0, "text": "Yıl sonuna kadar yatırım harcamalarının benzer kalmasını bekliyoruz.", "speaker": None, "avg_logprob": -0.2},
    {"start": 13.0, "end": 16.0, "text": "Temettüyü artırabiliriz.", "speaker": None, "avg_logprob": -0.3},
    {"start": 17.0, "end": 19.0, "text": "...", "speaker": None, "avg_logprob": -1.6},
]
TURKISH_TRANSLATIONS = {
    "Üçüncü çeyrekte gelirimiz yüzde 12 arttı.": "Our revenue rose 12 percent in the third quarter.",
    "Yıl sonuna kadar yatırım harcamalarının benzer kalmasını bekliyoruz.": "We expect capital expenditure to remain similar until the end of the year.",
    "Temettüyü artırabiliriz.": "We may increase the dividend. [AMBIGUOUS: 'artırabiliriz' expresses possibility, so 'may' is kept]",
    "...": "[unclear]",
}
