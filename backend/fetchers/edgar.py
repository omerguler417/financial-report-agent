# SEC EDGAR for live analyses of SEC filers: finds the company, lists its 10-K and 10-Q filings, fetches the latest ones to be read
# into pages, and turns the SEC's XBRL company facts into report figures. Each figure cites its filing (form, period, filing date,
# statement, SEC tag, link). Every request goes through PoliteClient, which sends the SEC identification header.
# EDGAR has no share prices: price requests give a clear "no market-data provider" message, never a guess.
from datetime import date, timedelta

from backend.errors import ProviderNotConfigured

NAME = "SEC EDGAR"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{folder}/{document}"
BROWSE_URL = ("https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&SIC={sic}&type=10-K&dateb=&owner=include&count=100"
              "&output=atom&start={start}")
FRAMES_URL = "https://data.sec.gov/api/xbrl/frames/us-gaap/{tag}/USD/CY{year}.json"
REVENUE_FRAMES = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"]
MAX_PEER_CANDIDATES = 10
MAX_INDUSTRY_PAGES = 30
FORMS = {"10-K", "10-K/A", "10-Q", "10-Q/A"}
YEARS_KEPT = 6
TOLERANCE = timedelta(days=10)  # 52/53-week fiscal years end a few days either side of the stated date

INCOME, BALANCE, CASH, PER_SHARE, NOTES = "income statement", "balance sheet", "cash flow statement", "per-share data", "tax note"
# v1.0 field: (statement, SEC us-gaap tags in order of preference)
TAGS = {
    "revenue": (INCOME, ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"]),
    "cost_of_sales": (INCOME, ["CostOfRevenue", "CostOfGoodsAndServicesSold"]),
    "ebit": (INCOME, ["OperatingIncomeLoss"]),
    "depreciation_amortisation": (CASH, ["DepreciationDepletionAndAmortization", "DepreciationAmortizationAndOther", "DepreciationAndAmortization"]),
    "interest_expense": (INCOME, ["InterestExpense", "InterestExpenseNonoperating"]),
    "pretax_income": (INCOME, ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                               "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"]),
    "income_tax": (INCOME, ["IncomeTaxExpenseBenefit"]),
    "nci_share_of_income": (INCOME, ["NetIncomeLossAttributableToNoncontrollingInterest"]),
    "net_income_common": (INCOME, ["NetIncomeLossAvailableToCommonStockholdersBasic", "NetIncomeLoss"]),
    "eps_basic": (INCOME, ["EarningsPerShareBasic"]),
    "eps_diluted": (INCOME, ["EarningsPerShareDiluted"]),
    "weighted_shares_basic": (INCOME, ["WeightedAverageNumberOfSharesOutstandingBasic"]),
    "weighted_shares_diluted": (INCOME, ["WeightedAverageNumberOfDilutedSharesOutstanding"]),
    "cfo_reported": (CASH, ["NetCashProvidedByUsedInOperatingActivities"]),
    "capex": (CASH, ["PaymentsToAcquirePropertyPlantAndEquipment"]),
    "dividends_paid_common": (CASH, ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends"]),
    "dividends_per_share": (PER_SHARE, ["CommonStockDividendsPerShareCashPaid"]),
    "interest_paid_in_cfo": (CASH, ["InterestPaidNet", "InterestPaid"]),  # US GAAP classifies interest paid within operating activities
    "lease_principal_outside_cfo": (CASH, ["FinanceLeasePrincipalPayments"]),
    "assets_total": (BALANCE, ["Assets"]),
    "current_assets": (BALANCE, ["AssetsCurrent"]),
    "current_liabilities": (BALANCE, ["LiabilitiesCurrent"]),
    "cash_eligible": (BALANCE, ["CashAndCashEquivalentsAtCarryingValue"]),
    "short_term_investments": (BALANCE, ["ShortTermInvestments", "AvailableForSaleSecuritiesDebtSecuritiesCurrent"]),
    "trade_receivables": (BALANCE, ["AccountsReceivableNetCurrent"]),
    "inventories": (BALANCE, ["InventoryNet"]),
    "trade_payables": (BALANCE, ["AccountsPayableCurrent"]),
    "goodwill": (BALANCE, ["Goodwill"]),
    "intangible_assets": (BALANCE, ["IntangibleAssetsNetExcludingGoodwill", "FiniteLivedIntangibleAssetsNet"]),
    "equity_common": (BALANCE, ["StockholdersEquity"]),
    "shares_outstanding": (BALANCE, ["CommonStockSharesOutstanding"]),
    "statutory_tax_rate": (NOTES, ["EffectiveIncomeTaxRateReconciliationAtFederalStatutoryIncomeTaxRate"]),
}
# Fields that are sums of SEC figures: (statement, parts, note, only when no single figure was found). Each part lists alternatives
# (tags added together); "required" parts must exist.
COMPOSITES = {
    "debt_ex_leases": (BALANCE, [("required", [["LongTermDebt"], ["LongTermDebtNoncurrent", "LongTermDebtCurrent"]]),
                                 ("optional", [["CommercialPaper"]]), ("optional", [["ShortTermBorrowings"]])],
                       "Check that leases are not also included in borrowings.", False),
    "lease_liabilities": (BALANCE, [("optional", [["OperatingLeaseLiability"], ["OperatingLeaseLiabilityNoncurrent", "OperatingLeaseLiabilityCurrent"]]),
                                    ("optional", [["FinanceLeaseLiability"], ["FinanceLeaseLiabilityNoncurrent", "FinanceLeaseLiabilityCurrent"]])],
                          "Check that leases are not also included in borrowings.", False),
    # decided 25 November 2026: used only when no combined D&A figure is reported
    "depreciation_amortisation": (CASH, [("required", [["Depreciation", "AmortizationOfIntangibleAssets"]])],
                                  "No combined D&A figure is reported, so D&A is depreciation plus amortisation of intangible assets; "
                                  "finance-lease amortisation is not added, to avoid double counting.", True),
}
UNITS = {"USD": ("USD millions", 1e-6), "shares": ("millions of shares", 1e-6), "USD/shares": ("USD per share", 1.0), "pure": ("percent", 100.0)}


def _day(text: str) -> date:
    return date.fromisoformat(text)


class Edgar:
    name = NAME

    def __init__(self, client, settings, as_of: date | None = None):
        self.client, self.settings, self.as_of = client, settings, as_of
        self._cache: dict = {}
        self.peer_source: dict | None = None

    def _json(self, url: str) -> dict:
        if url not in self._cache:
            self._cache[url] = self.client.get(url).json()
        return self._cache[url]

    # ---------- company ----------

    def _cik(self, ticker: str) -> int:
        for row in self._json(TICKERS_URL).values():
            if row["ticker"].upper() == ticker.upper():
                return int(row["cik_str"])
        raise KeyError(ticker)

    def search(self, query: str) -> list[dict]:
        q = query.strip().lower()
        rows = list(self._json(TICKERS_URL).values())
        exact = [r for r in rows if r["ticker"].lower() == q]
        found = exact or [r for r in rows if q and q in r["title"].lower()]
        return [{"ticker": r["ticker"], "name": r["title"], "cik": int(r["cik_str"]), "exchange": None, "currency": "USD"} for r in found[:20]]

    def submissions(self, ticker: str) -> dict:
        return self._json(SUBMISSIONS_URL.format(cik=self._cik(ticker)))

    def profile(self, ticker: str) -> dict:
        sub = self.submissions(ticker)
        revenue = self._revenues().get(self._cik(ticker))
        return {"ticker": ticker.upper(), "name": sub.get("name", ticker), "industry": sub.get("sicDescription"), "sic": sub.get("sic"),
                "exchange": (sub.get("exchanges") or [None])[0], "currency": "USD", "fiscal_year_end": sub.get("fiscalYearEnd"),
                "revenue": revenue * 1e-6 if revenue else None}

    # ---------- peer candidates: listed SEC filers with the same industry code, closest in revenue first ----------

    def _industry_companies(self, sic: str) -> list[int]:
        import re
        ciks, start = [], 0
        for _ in range(MAX_INDUSTRY_PAGES):
            text = self.client.get(BROWSE_URL.format(sic=sic, start=start)).text
            ciks += [int(c) for c in re.findall(r"<cik>(\d+)</cik>", text)]
            if 'rel="next"' not in text:
                break
            start += 100
        return ciks

    def _revenues(self) -> dict:
        """Annual revenue of every SEC filer for the latest complete calendar year (the SEC's cross-company "frames"), in USD."""
        year = (self.as_of or date.today()).year - 1
        if ("revenues", year) not in self._cache:
            found: dict = {}
            for tag in REVENUE_FRAMES:
                try:
                    rows = self._json(FRAMES_URL.format(tag=tag, year=year)).get("data", [])
                except Exception:
                    continue
                for row in rows:
                    found.setdefault(int(row["cik"]), row["val"])
            self._cache[("revenues", year)] = found
        return self._cache[("revenues", year)]

    def peers(self, ticker: str) -> list[str]:
        """Listed companies with the target's SEC industry code (SIC), closest in revenue first. EDGAR has no products, customers
        or regions, so the comparison is limited to industry code and size; the selection step labels it so."""
        import math
        sic = str(self.submissions(ticker).get("sic") or "")
        if not sic:
            return []
        target = self._cik(ticker)
        listed = {}
        for row in self._json(TICKERS_URL).values():
            listed.setdefault(int(row["cik_str"]), row["ticker"])
        revenues = self._revenues()
        own = revenues.get(target)
        candidates = [(cik, revenues[cik]) for cik in self._industry_companies(sic)
                      if cik != target and cik in listed and revenues.get(cik, 0) > 0]
        if own and own > 0:
            candidates.sort(key=lambda c: abs(math.log(c[1] / own)))
        else:
            candidates.sort(key=lambda c: -c[1])
        self.peer_source = {"type": "regulator_classification", "detail": f"SEC EDGAR: same industry code (SIC {sic}), ranked by revenue"}
        return [listed[cik] for cik, _ in candidates[:MAX_PEER_CANDIDATES]]

    def daily_series(self, ticker, start, end):
        raise ProviderNotConfigured("Market data (share prices)", ["MARKET_DATA_PROVIDER", "MARKET_DATA_API_KEY"],
                                    "SEC EDGAR has no share prices; a market-data provider is chosen at the API stage.")

    # ---------- filings ----------

    def filings(self, ticker: str) -> list[dict]:
        cik = self._cik(ticker)
        recent = self.submissions(ticker)["filings"]["recent"]
        out = []
        for i, form in enumerate(recent["form"]):
            if form not in FORMS:
                continue
            accession = recent["accessionNumber"][i]
            out.append({"accession": accession, "form": form, "filed": recent["filingDate"][i], "report_date": recent["reportDate"][i],
                        "url": ARCHIVE_URL.format(cik=cik, folder=accession.replace("-", ""), document=recent["primaryDocument"][i])})
        return out

    def _filing_index(self, ticker: str) -> dict:
        return {f["accession"]: f for f in self.filings(ticker)}

    # ---------- periods ----------

    def _year_end(self, ticker: str) -> tuple[int, int]:
        fye = self.submissions(ticker).get("fiscalYearEnd") or "1231"
        return int(fye[:2]), int(fye[2:])

    @staticmethod
    def _fiscal_year(day: date, month: int, dom: int) -> int:
        shifted = day - TOLERANCE
        return shifted.year if (shifted.month, shifted.day) <= (month, dom) else shifted.year + 1

    @staticmethod
    def _fy_end(fy: int, month: int, dom: int) -> date:
        for d in (dom, 30, 29, 28):
            try:
                return date(fy, month, d)
            except ValueError:
                continue

    def _label(self, start: str | None, end: str, month: int, dom: int) -> str | None:
        """FY2025 for a full fiscal year; YTD Q3 2026 for the year to date ending with the third quarter; None for other periods."""
        end_day = _day(end)
        fy = self._fiscal_year(end_day, month, dom)
        fy_start = self._fy_end(fy - 1, month, dom) + timedelta(days=1)
        if start is None:  # balance-sheet date
            if abs(end_day - self._fy_end(fy, month, dom)) <= TOLERANCE:
                return f"FY{fy}"
            months = round((end_day - fy_start).days / 30.44)
            return f"YTD Q{months // 3} {fy}" if months in (3, 6, 9) else None
        if abs(_day(start) - fy_start) > TOLERANCE:
            return None  # a single quarter, not the year to date
        months = round((end_day - _day(start)).days / 30.44)
        if months == 12:
            return f"FY{fy}"
        return f"YTD Q{months // 3} {fy}" if months in (3, 6, 9) else None

    # ---------- figures ----------

    def _rows(self, facts: dict, tag: str, as_of: date, month: int, dom: int) -> dict:
        """{label: [(unit, row), ...]} for one SEC tag, from 10-K/10-Q filings filed by `as_of`."""
        entry = facts.get("facts", {}).get("us-gaap", {}).get(tag) or facts.get("facts", {}).get("dei", {}).get(tag)
        out = {}
        for unit, rows in (entry or {}).get("units", {}).items():
            if unit not in UNITS:
                continue
            for row in rows:
                if row.get("form") not in FORMS or row.get("filed", "9999") > as_of.isoformat():
                    continue
                label = self._label(row.get("start"), row["end"], month, dom)
                if label:
                    out.setdefault(label, []).append((unit, row))
        return out

    def _source(self, row: dict, tag: str, statement: str, index: dict) -> dict:
        filing = index.get(row["accn"], {})
        period = filing.get("report_date") or row["end"]
        return {"doc_id": row["accn"], "title": f"{row['form']} for the period ended {period} (filed {row['filed']})", "form": row["form"],
                "section": statement, "tag": f"us-gaap:{tag}", "published": row["filed"],
                "url": filing.get("url") or f"https://www.sec.gov/Archives/edgar/data/{self._cik_from(row)}/{row['accn'].replace('-', '')}/"}

    def _cik_from(self, row: dict) -> int:
        return int(row["accn"].split("-")[0])

    def _figure(self, field: str, label: str, rows: list, tag: str, statement: str, index: dict) -> dict:
        rows = sorted(rows, key=lambda ur: ur[1]["filed"])
        unit, latest = rows[-1]
        name, factor = UNITS[unit]
        same = [(u, r) for u, r in rows if abs(r["val"] - latest["val"]) <= abs(latest["val"]) * 1e-9]
        earlier = [r for u, r in rows if (u, r) not in same]
        note = f"From the SEC's XBRL data, converted to {name}." if factor != 1.0 else "From the SEC's XBRL data."
        if earlier:
            first = earlier[0]
            note += (f" Restated: the filing of {first['filed']} reported {first['val'] * factor:,.0f}; the latest filing "
                     f"({latest['filed']}) is used.")
        sources = []
        for _, r in same:
            s = self._source(r, tag, statement, index)
            if s not in sources:
                sources.append(s)
        return {"field": field, "period": label, "value": latest["val"] * factor, "unit": name, "sources": sources, "note": note}

    def figures(self, ticker: str, as_of: date) -> tuple[list[dict], list[str]]:
        """Report figures from the SEC's XBRL data, by fiscal period, as filed by `as_of`. Returns (figures, notes)."""
        facts = self._json(FACTS_URL.format(cik=self._cik(ticker)))
        month, dom = self._year_end(ticker)
        index = self._filing_index(ticker)
        found: dict = {}

        def put(fig):
            found[(fig["field"], fig["period"])] = fig

        for field, (statement, tags) in TAGS.items():
            for tag in tags:
                for label, rows in self._rows(facts, tag, as_of, month, dom).items():
                    if (field, label) not in found:
                        put(self._figure(field, label, rows, tag, statement, index))
        for field, (statement, parts, note, only_missing) in COMPOSITES.items():
            self._composite(field, statement, parts, note, only_missing, facts, as_of, month, dom, index, put, found)
        self._group_figures(facts, as_of, month, dom, index, found, put)
        return self._recent(list(found.values())), [
            "Report figures come from the SEC's XBRL data (company facts); each cites its filing, statement and SEC tag."]

    def _composite(self, field, statement, parts, note, only_missing, facts, as_of, month, dom, index, put, found):
        per_label: dict = {}
        for need, alternatives in parts:
            for tags in alternatives:
                series = [self._rows(facts, t, as_of, month, dom) for t in tags]
                labels = set.intersection(*(set(s) for s in series)) if series else set()
                if not labels:
                    continue
                for label in labels:
                    pieces = [self._figure(field, label, s[label], t, statement, index) for s, t in zip(series, tags)]
                    per_label.setdefault(label, {}).setdefault(need, []).append((tags, pieces))
                break  # the first alternative that exists is used
        for label, groups in per_label.items():
            if only_missing and (field, label) in found:
                continue
            if not groups.get("required") and any(n == "required" for n, _ in parts):
                continue
            used = [(tags, pieces) for n in ("required", "optional") for tags, pieces in groups.get(n, [])]
            if not used:
                continue
            value = sum(p["value"] for _, pieces in used for p in pieces)
            sources = []
            for _, pieces in used:
                for p in pieces:
                    sources += [s for s in p["sources"] if s not in sources]
            tags = " + ".join(t for tags, _ in used for t in tags)
            put({"field": field, "period": label, "value": value, "unit": "USD millions", "sources": sources,
                 "note": f"Sum of SEC figures {tags}, converted to USD millions. {note}"})

    def _group_figures(self, facts, as_of, month, dom, index, found, put):
        """Group net income, NCI and total equity, which filers without non-controlling interests often do not tag separately."""
        has_nci = bool(facts.get("facts", {}).get("us-gaap", {}).get("MinorityInterest"))
        for label, rows in self._rows(facts, "ProfitLoss", as_of, month, dom).items():
            put(self._figure("net_income_group", label, rows, "ProfitLoss", INCOME, index))
        for label, rows in self._rows(facts, "NetIncomeLoss", as_of, month, dom).items():
            if ("net_income_group", label) not in found:
                fig = self._figure("net_income_group", label, rows, "NetIncomeLoss", INCOME, index)
                fig["note"] += " No ProfitLoss figure: net income is used as the group figure."
                put(fig)
        if has_nci:
            for label, rows in self._rows(facts, "MinorityInterest", as_of, month, dom).items():
                put(self._figure("nci", label, rows, "MinorityInterest", BALANCE, index))
            for label, rows in self._rows(facts, "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", as_of, month, dom).items():
                put(self._figure("equity_total", label, rows, "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", BALANCE, index))
            return
        for (field, label), fig in list(found.items()):
            if field != "equity_common":
                continue
            note = "No non-controlling interests are reported in the filings (no MinorityInterest figure), so none is included."
            put({**fig, "field": "nci", "value": 0.0, "note": note})
            put({**fig, "field": "equity_total", "note": fig["note"] + " " + note + " Total equity equals common equity."})

    def _recent(self, figures: list[dict]) -> list[dict]:
        """The latest six fiscal years and their year-to-date periods."""
        years = sorted({int(f["period"][2:]) for f in figures if f["period"].startswith("FY")})
        if not years:
            return figures
        first = years[-1] - YEARS_KEPT + 1
        return [f for f in figures if int(f["period"].split()[-1][-4:]) >= first]

    # ---------- documents to read ----------

    def latest_reports(self, ticker: str, as_of: date) -> list[dict]:
        """The latest 10-K filed by `as_of`, and the latest 10-Q filed after it."""
        filed = [f for f in self.filings(ticker) if f["filed"] <= as_of.isoformat()]
        annual = next((f for f in filed if f["form"].startswith("10-K")), None)
        quarter = next((f for f in filed if f["form"].startswith("10-Q") and (annual is None or f["filed"] > annual["filed"])), None)
        return [f for f in (annual, quarter) if f]
