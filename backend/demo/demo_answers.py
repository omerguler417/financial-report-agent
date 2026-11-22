# DEMO recorded text-model answers: what a model would return for each analysis task on the fictional demo companies. Used only in
# demo mode; the checks, calculations and report assembly that follow are the real code.
# Four answers contain deliberate mistakes so the checks in backend/validation.py can be seen working: one figure cites the wrong page
# (Agent 1), one summary statement quotes a growth rate that differs from Python's (Agent 1), one news assessment claims the news moved
# the share price (Agent 2), and one overview statement gives a valuation verdict (Agent 3).
from backend.demo import demo_data as D

UNITS = {"shares_outstanding": "millions of shares", "statutory_tax_rate": "percent"}


def extract_figures(data: dict) -> dict:
    ticker = data["ticker"]
    docs = {d["doc_id"]: d for d in D.documents(ticker)}
    figures = []
    for item in D.figure_index(ticker):
        doc = docs[item["doc_id"]]
        figures.append({"field": item["field"], "period": item["period"], "value": item["value"],
                        "unit": UNITS.get(item["field"], f"{doc['currency']} {doc['units']}"),
                        "doc_id": item["doc_id"], "page": item["page"], "line": item["line"]})
    if ticker == D.TARGET:  # deliberate mistake: the right line, but on page 5 instead of the income statement on page 3
        wrong = next(f for f in figures if f["field"] == "pretax_income" and f["period"] == "FY2023")
        wrong["page"] = 5
    return {"figures": figures}


def _indicator(data: dict, indicator: str, period: str) -> dict | None:
    return next((r for r in data.get("indicators", []) if r["indicator"] == indicator and r["period"] == period), None)


def summarise_reports(data: dict) -> dict:
    ticker = data["ticker"]
    if ticker != D.TARGET:
        return {"statements": []}
    c, f = D.COMPANIES[ticker], D.financials(ticker)
    short = ticker.split(".")[0].lower()
    annual, quarter = f"demo-{short}-annual_report-fy2025", f"demo-{short}-quarterly_report-q32026"
    regions = " and ".join(f"{share:.0%} from {region}" for region, share in c["regions"].items())
    cur, prev = f["ytd"]["YTD Q3 2026"]["revenue"], f["ytd"]["YTD Q3 2025"]["revenue"]
    statements = [
        {"text": f"{c['name']} is an integrated oil and gas company with {', '.join(c['segments'])} segments; it earns {regions}.",
         "citations": [{"doc_id": annual, "page": 2}]},
        {"text": f"Revenue was {f['annual']['FY2025']['revenue']:,.1f} million in 2025.", "citations": [{"doc_id": annual, "page": 6}]},
        {"text": "The annual report names commodity price volatility as the main risk to results.", "citations": [{"doc_id": annual, "page": 6}]},
        {"text": f"Revenue for the nine months ended September 30, 2026 was {cur:,.1f} million, compared with {prev:,.1f} million a year earlier.",
         "citations": [{"doc_id": quarter, "page": 5}]},
        {"text": "Management expects capital expenditure to remain broadly in line with the prior year.", "citations": [{"doc_id": quarter, "page": 5}]},
    ]
    roe = _indicator(data, "roe_common", "TTM to Q3 2026")
    if roe and roe["value"] is not None:
        statements.append({"text": f"Return on common equity was {roe['value'] * 100:.1f}% over the twelve months to September 2026.",
                           "citations": [{"indicator": "roe_common", "period": "TTM to Q3 2026"}]})
    # deliberate mistake: Python calculated about 6% for FY2025
    statements.append({"text": "Revenue grew 9% in 2025.", "citations": [{"indicator": "revenue_growth", "period": "FY2025"}]})
    return {"statements": statements}


def _ids(ticker: str) -> dict:
    short = ticker.split(".")[0].lower()
    return {"annual": f"demo-{short}-annual_report-fy2025", "quarter": f"demo-{short}-quarterly_report-q32026",
            "call": f"demo-{short}-transcript-q32026"}


def analyse_call(data: dict) -> dict:
    if data["ticker"] != D.TARGET:
        return {"statements": []}
    t = _ids(data["ticker"])["call"]
    revenue = D.financials(D.TARGET)["ytd"]["YTD Q3 2026"]["revenue"]
    ceo, cfo = "Maria Alvarez (CEO)", "Daniel Okafor (CFO)"
    rows = [
        ("management", ceo, f"Revenue for the nine months was {revenue:,.1f} million, up on last year.", 1),
        ("guidance", ceo, "Fourth-quarter production is expected to be between 410 and 430 thousand barrels per day.", 1),
        ("management", cfo, "The company may increase the dividend if cash flow stays at current levels (a possibility, not a commitment).", 1),
        ("analyst", "Priya Nair (Analyst)", "Assumed that higher commodity prices mean capital spending must rise sharply next year, and asked what to expect.", 2),
        ("guidance", cfo, "Capital expenditure is expected to remain broadly in line with the prior year.", 2),
        ("analyst", "Tom Becker (Analyst)", "Suggested that new emissions rules are likely to hurt margins, and asked for a figure.", 2),
        ("management", ceo, "It is too early to quantify the effect of the proposed regulation.", 2),
    ]
    return {"statements": [{"kind": k, "speaker": who, "text": text, "citations": [{"doc_id": t, "page": page}]} for k, who, text, page in rows]}


def review_news(data: dict) -> dict:
    if data["ticker"] != D.TARGET:
        return {"items": []}
    judgements = {
        "demo-news-0": {"relevant": True, "still_material": True, "channel": "A ten-year gas supply contract with a regional utility covers "
                        "a large share of the company's gas output, which supports demand for that output."},
        "demo-news-1": {"relevant": True, "channel": "Stricter methane limits could raise compliance costs for producers, including this company."},
        # deliberate mistake: claims the news moved the share price, with a number that is not in the item
        "demo-news-2": {"relevant": True, "channel": "Officials are reviewing a pipeline leak at the company, which says it was contained. "
                        "The leak report sent shares down 3%."},
        "demo-news-3": {"relevant": True, "channel": "The chief executive said fourth-quarter guidance has not changed (a management statement "
                        "reported by the press)."},
        "demo-news-4": {"relevant": True, "channel": "Tariffs on imported drilling equipment could raise the cost of the company's capital projects."},
        "demo-news-5": {"relevant": False, "reason": "A sports result with no link to the company's business."},
    }
    return {"items": [{"news_id": i["id"], **judgements[i["id"]]} for i in data["items"] if i["id"] in judgements]}


def combine_report(data: dict) -> dict:
    if data["ticker"] != D.TARGET:
        return {"overview": [], "disagreements": [], "risks": []}
    ids, f = _ids(data["ticker"]), D.financials(D.TARGET)
    period = "TTM to Q3 2026"
    found = {(r["indicator"], r["period"]): r["value"] for r in data["indicators"]}
    cur, prev = f["ytd"]["YTD Q3 2026"]["revenue"], f["ytd"]["YTD Q3 2025"]["revenue"]

    def cite(indicator, p=period):
        return {"indicator": indicator, "period": p}

    def page(doc, number):
        return {"doc_id": ids[doc], "page": number}

    overview = [
        {"text": f"Over the twelve months to September 2026, return on common equity was {found[('roe_common', period)] * 100:.1f}% and net "
                 f"debt was {found[('net_debt_ebitda', period)]:.2f} times EBITDA.", "citations": [cite("roe_common"), cite("net_debt_ebitda")]},
        {"text": f"Revenue for the first nine months of 2026 was {cur:,.1f} million, compared with {prev:,.1f} million a year earlier; the chief "
                 "executive repeated the nine-month figure on the earnings call.", "citations": [page("quarter", 5), page("call", 1)]},
    ]
    if ("pe", "peer median") in found:
        overview.append({"text": f"The P/E of {found[('pe', period)]:.2f}x is above the median of {found[('pe', 'peer median')]:.2f}x for the "
                                 "selected peers.", "citations": [cite("pe"), cite("pe", "peer median")]})
        # deliberate mistake: a valuation verdict
        overview.append({"text": "With a P/E above the peer median, the shares look expensive.", "citations": [cite("pe"), cite("pe", "peer median")]})
    disagreements = [
        {"topic": "Capital expenditure next year", "positions": [
            {"who": "Analyst on the call (Priya Nair)", "text": "An analyst assumed that capital spending must rise sharply next year.",
             "citations": [page("call", 2)]},
            {"who": "Chief financial officer, on the call", "text": "The chief financial officer expects capital expenditure to remain broadly "
             "in line with the prior year.", "citations": [page("call", 2)]},
            {"who": "Q3 2026 report", "text": "The quarterly report says management expects capital expenditure to remain broadly in line "
             "with the prior year.", "citations": [page("quarter", 5)]},
            {"who": "News (Demo Wire)", "text": "New tariffs could raise the cost of imported drilling equipment.",
             "citations": [{"doc_id": "demo-news-4", "page": 1}]}]},
        {"topic": "Proposed methane rules", "positions": [
            {"who": "News (Demo Wire)", "text": "A regulator has proposed stricter methane rules for oil and gas producers.",
             "citations": [{"doc_id": "demo-news-1", "page": 1}]},
            {"who": "Chief executive, on the call", "text": "The chief executive said it is too early to quantify the effect of the proposed "
             "regulation.", "citations": [page("call", 2)]},
            {"who": "Annual report FY2025", "text": "The annual report names commodity price volatility, not regulation, as the main risk "
             "to results.", "citations": [page("annual", 6)]}]},
    ]
    risks = [
        {"text": "Commodity price volatility is named as the main risk to results.", "citations": [page("annual", 6)]},
        {"text": "Proposed stricter methane rules could raise compliance costs; management has not quantified the effect.",
         "citations": [{"doc_id": "demo-news-1", "page": 1}, page("call", 2)]},
        {"text": "A pipeline leak is under review; the company says it was contained.", "citations": [{"doc_id": "demo-news-2", "page": 1}]},
        {"text": "Tariffs on imported drilling equipment could raise capital costs.", "citations": [{"doc_id": "demo-news-4", "page": 1}]},
    ]
    return {"overview": overview, "disagreements": disagreements, "risks": risks}


ANSWERS = {"extract_figures": extract_figures, "summarise_reports": summarise_reports, "analyse_call": analyse_call,
           "review_news": review_news, "combine_report": combine_report}


def answer(task: str, data: dict) -> dict:
    if task not in ANSWERS:
        raise ValueError(f"No recorded demo answer exists for the task '{task}'.")
    return ANSWERS[task](data)
