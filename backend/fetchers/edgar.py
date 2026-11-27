# SEC EDGAR for live analyses of SEC filers: finds the company, lists its 10-K and 10-Q filings, fetches the latest ones to be read
# into pages, and turns the SEC's XBRL company facts into report figures. Each figure cites its filing (form, period, filing date,
# statement, SEC tag, link). Every request goes through PoliteClient, which sends the SEC identification header.
# EDGAR has no share prices: price requests give a clear "no market-data provider" message, never a guess.
import re
import xml.etree.ElementTree as ET
from datetime import date, timedelta

from backend.errors import ProviderNotConfigured
from backend.fetchers.http_client import AccessDenied, FetchFailed

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
    "debt_ex_leases": (BALANCE, [("required", [["LongTermDebt"], ["LongTermDebtNoncurrent", "LongTermDebtCurrent"],
                                              ["LongTermNotesAndLoans", "NotesPayableCurrent"]]),  # the last: Oracle's notes and loans
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
# v1.0 inputs the SEC's company facts do not contain, with the reason shown when the indicator cannot be calculated
SOURCE_GAPS = {"free_float_shares": "The SEC's data has no free-float share count; it would need a market-data source that provides one."}
COVER_SHARES = "EntityCommonStockSharesOutstanding"
# Decided 27 November 2026: when the SEC's summary data has no standard figure for a period the analysis needs, the company's own
# element for it is read from that period's full filing (its XBRL data file). Only totals: no dimensions, exactly the period's dates.
COMPANY_LABEL_FIELDS = {"depreciation_amortisation": (CASH, re.compile(r"^Depreciation\w*Amortization"))}
STANDARD_NAMESPACES = ("fasb.org/us-gaap", "xbrl.sec.gov/dei", "fasb.org/srt", "xbrl.org/", "xbrl.sec.gov/", "ifrs.org", "w3.org")
XBRLI = "{http://www.xbrl.org/2003/instance}"  # dei: the share count on a report's cover page, dated shortly after the period
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

    def _source(self, row: dict, tag: str, statement: str, index: dict, namespace: str = "us-gaap") -> dict:
        filing = index.get(row["accn"], {})
        period = filing.get("report_date") or row["end"]
        return {"doc_id": row["accn"], "title": f"{row['form']} for the period ended {period} (filed {row['filed']})", "form": row["form"],
                "section": statement, "tag": f"{namespace}:{tag}", "published": row["filed"],
                "url": filing.get("url") or f"https://www.sec.gov/Archives/edgar/data/{self._cik_from(row)}/{row['accn'].replace('-', '')}/"}

    def _cik_from(self, row: dict) -> int:
        return int(row["accn"].split("-")[0])

    def _figure(self, field: str, label: str, rows: list, tag: str, statement: str, index: dict, namespace: str = "us-gaap") -> dict:
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
            s = self._source(r, tag, statement, index, namespace)
            if s not in sources:
                sources.append(s)
        return {"field": field, "period": label, "value": latest["val"] * factor, "unit": name, "sources": sources, "note": note}

    def figures(self, ticker: str, as_of: date, years: int = YEARS_KEPT) -> tuple[list[dict], list[str]]:
        """Report figures from the SEC's XBRL data, by fiscal period, as filed by `as_of`, for the latest `years` fiscal years (the
        horizon plus one, since growth over n years needs n + 1 annual figures). Returns (figures, notes)."""
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
        self._cover_page_shares(facts, as_of, found, put)
        self._group_figures(facts, as_of, month, dom, index, found, put)
        notes = ["Report figures come from the SEC's XBRL data (company facts); each cites its filing, statement and SEC tag."]
        kept = self._recent(list(found.values()), years)
        latest = max((f["period"] for f in kept if f["field"] == "equity_common"), default=None,
                     key=lambda p: (int(p.split()[-1][-4:]), p.startswith("FY"), p))  # FY2025 < YTD Q1 2026 < YTD Q3 2026 < FY2026
        added = self._company_label_figures(ticker, facts, as_of, month, dom, {f["period"] for f in kept}, found, notes)
        if added:
            kept += added
            notes.append("Some figures come from the company's own XBRL labels in its full filings, because the SEC's summary data has no "
                         "standard figure for those periods; each is labelled.")
        if latest and not any(f["field"] == "shares_outstanding" and f["period"] == latest for f in kept):
            notes.append(f"The SEC's data has no share count for {latest}, neither on the balance sheet nor on the cover page (companies with "
                         "several share classes often report the count by class only), so market capitalisation is not calculated.")
        return kept, notes

    @staticmethod
    def _twelve_month_sets(labels: set) -> list[tuple[str, str, str]]:
        """The (fiscal year, year to date, same period a year earlier) sets the analysis adds up into twelve months: the current one
        (as financials.build_inputs) and one per past year end (as indicators._year_end_view)."""
        def year(label):
            return int(label[-4:])
        sets = []
        fys = sorted((l for l in labels if l.startswith("FY")), key=year)
        if fys:
            latest = fys[-1]
            later = sorted((l for l in labels if l.startswith("YTD") and year(l) > year(latest)), key=lambda l: (year(l), l), reverse=True)
            if later and f"{later[0][:-4]}{year(later[0]) - 1}" in labels:
                sets.append((latest, later[0], f"{later[0][:-4]}{year(later[0]) - 1}"))
        for y in sorted({year(l) for l in labels if l.startswith("YTD")}):
            for part in sorted({l.split()[1] for l in labels if l.startswith("YTD") and year(l) == y}, reverse=True):
                cur, prior, fy = f"YTD {part} {y}", f"YTD {part} {y - 1}", f"FY{y - 1}"
                if prior in labels and fy in labels:
                    sets.append((fy, cur, prior))
                    break
        return list(dict.fromkeys(sets))

    def _company_label_figures(self, ticker, facts, as_of, month, dom, labels, found, notes) -> list[dict]:
        """Decided 27 November 2026: for each twelve-month set the analysis uses in which a standard figure is missing, the company's own
        element is read for all three periods from their full filings (the year to date's filing also gives the year-earlier period).
        Stored as a separate field, so that standard and own figures are never mixed."""
        ebit = self._rows(facts, "OperatingIncomeLoss", as_of, month, dom)
        added = []
        for field, (statement, pattern) in COMPANY_LABEL_FIELDS.items():
            own_field = f"{field}_own"
            for fy, cur, prior in self._twelve_month_sets(labels):
                parts = (fy, cur, prior)
                if all((field, l) in found for l in parts) or not all(l in ebit for l in parts):
                    continue
                dates = {l: next(((r.get("start"), r["end"]) for _, r in sorted(ebit[l], key=lambda ur: ur[1]["filed"])), None) for l in parts}
                for label, filing_of in ((cur, cur), (prior, cur), (fy, fy)):  # the year earlier comes from the same 10-Q, as published then
                    if (own_field, label) in found:
                        continue
                    first = min((r for _, r in ebit[filing_of]), key=lambda r: r["filed"])
                    try:
                        values = self._own_elements(ticker, first["accn"], pattern)
                    except (FetchFailed, AccessDenied, ValueError, KeyError, ET.ParseError) as exc:
                        notes.append(f"The full filing {first['accn']} could not be read: {exc}")
                        continue
                    hit = values.get(dates[label])
                    if hit is None:
                        continue
                    name, value = hit
                    prefix, local = name.split(":")
                    words = re.sub(r"(?<!^)(?=[A-Z])", " ", local).lower()
                    note = (f"From the company's own XBRL element {name} (\"{words}\") in its full filing, because the SEC's summary data "
                            "has no standard figure for every part of this twelve-month period; converted to USD millions. A company's own "
                            "element can be defined differently from the standard figures used for other periods")
                    note += "; this one includes other items, so it is broader." if "other" in words.split() else "."
                    fig = {"field": own_field, "period": label, "value": value * 1e-6, "unit": "USD millions", "note": note,
                           "sources": [self._source(first, local, statement, self._filing_index(ticker), prefix)]}
                    found[(own_field, label)] = fig
                    added.append(fig)
        return added

    def _own_elements(self, ticker, accession, pattern) -> dict:
        """{(start, end): (prefix:name, value)} for the company's own elements matching `pattern` in one filing's full XBRL data file,
        totals only (no dimensions). Read once per filing."""
        key = ("own", accession, pattern.pattern)
        if key in self._cache:
            return self._cache[key]
        folder = f"https://www.sec.gov/Archives/edgar/data/{self._cik(ticker)}/{accession.replace('-', '')}/"
        names = [i["name"] for i in self.client.get(folder + "index.json").json()["directory"]["item"]]
        instance = next((n for n in names if n.endswith("_htm.xml")), None) or next(
            (n for n in names if n.endswith(".xml") and not re.search(r"_(cal|def|lab|pre)\.xml$|FilingSummary", n)), None)
        out: dict = {}
        if instance is not None:
            text = self.client.get(folder + instance).text
            prefixes = {uri: prefix for prefix, uri in re.findall(r'xmlns:([\w-]+)="([^"]+)"', text[:20000])}
            root = ET.fromstring(text.encode("utf-8"))
            periods = {}
            for ctx in root.iter(f"{XBRLI}context"):
                start_, end_ = ctx.find(f".//{XBRLI}startDate"), ctx.find(f".//{XBRLI}endDate")
                if ctx.find(f".//{XBRLI}segment") is None and start_ is not None and end_ is not None:
                    periods[ctx.get("id")] = (start_.text.strip(), end_.text.strip())
            for el in root:
                if not el.tag.startswith("{") or el.get("contextRef") not in periods or not (el.text or "").strip():
                    continue
                uri, local = el.tag[1:].split("}")
                if any(std in uri for std in STANDARD_NAMESPACES) or not pattern.search(local):
                    continue
                out.setdefault(periods[el.get("contextRef")], (f"{prefixes.get(uri, 'company')}:{local}", float(el.text)))
        self._cache[key] = out
        return out

    def _cover_page_shares(self, facts, as_of, found, put):
        """Shares outstanding from a report's cover page, when its balance sheet gives no count (decided 27 November 2026). The count
        belongs to the period of the same filing and is dated shortly after it, nearer the valuation date (v1.0)."""
        rows = (facts.get("facts", {}).get("dei", {}).get(COVER_SHARES) or {}).get("units", {}).get("shares", [])
        by_filing = {}
        for row in rows:
            if row.get("form") in FORMS and row.get("filed", "9999") <= as_of.isoformat():
                if row["accn"] not in by_filing or row["end"] > by_filing[row["accn"]]["end"]:
                    by_filing[row["accn"]] = row
        for (field, label), fig in list(found.items()):
            if field != "equity_common" or ("shares_outstanding", label) in found:
                continue
            same = next((src for src in reversed(fig["sources"]) if src["doc_id"] in by_filing), None)  # the balance sheet's filing
            if same is None:
                continue
            row = by_filing[same["doc_id"]]
            put({"field": "shares_outstanding", "period": label, "value": row["val"] * 1e-6, "unit": "millions of shares",
                 "sources": [{**same, "section": "cover page", "tag": f"dei:{COVER_SHARES}"}],
                 "note": f"From the report's cover page: shares outstanding on {row['end']}, converted to millions of shares. The balance "
                         "sheet gives no count for this period."})

    def _composite(self, field, statement, parts, note, only_missing, facts, as_of, month, dom, index, put, found):
        per_label: dict = {}
        for need, alternatives in parts:
            options: dict = {}  # label -> [(tags, pieces)] in order of preference
            for tags in alternatives:
                series = [self._rows(facts, t, as_of, month, dom) for t in tags]
                for label in set.intersection(*(set(s) for s in series)) if series else set():
                    pieces = [self._figure(field, label, s[label], t, statement, index) for s, t in zip(series, tags)]
                    options.setdefault(label, []).append((tags, pieces))
            for label, found_options in options.items():  # per period: the first alternative its report uses, unless it is zero
                chosen = next((o for o in found_options if any(p["value"] for p in o[1])), found_options[0])
                per_label.setdefault(label, {}).setdefault(need, []).append(chosen)
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
        for (field, label), fig in list(found.items()):
            if field != "equity_common" or ("nci", label) in found:
                continue
            if has_nci:  # decided 27 November 2026: a report without the figure has none for that period
                note = "No minority-interest figure in this report (MinorityInterest), so none is included for this period."
            else:
                note = "No non-controlling interests are reported in the filings (no MinorityInterest figure), so none is included."
            put({**fig, "field": "nci", "value": 0.0, "note": note})
            if ("equity_total", label) not in found:
                put({**fig, "field": "equity_total", "note": fig["note"] + " " + note + " Total equity equals common equity."})

    def _recent(self, figures: list[dict], years: int = YEARS_KEPT) -> list[dict]:
        """The latest `years` fiscal years and their year-to-date periods."""
        found = sorted({int(f["period"][2:]) for f in figures if f["period"].startswith("FY")})
        if not found:
            return figures
        first = found[-1] - years + 1
        return [f for f in figures if int(f["period"].split()[-1][-4:]) >= first]

    # ---------- documents to read ----------

    def latest_reports(self, ticker: str, as_of: date) -> list[dict]:
        """The latest 10-K filed by `as_of`, and the latest 10-Q filed after it."""
        filed = [f for f in self.filings(ticker) if f["filed"] <= as_of.isoformat()]
        annual = next((f for f in filed if f["form"].startswith("10-K")), None)
        quarter = next((f for f in filed if f["form"].startswith("10-Q") and (annual is None or f["filed"] > annual["filed"])), None)
        return [f for f in (annual, quarter) if f]
