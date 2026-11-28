# Recorded text-model answers for the tests: what a model would return for each analysis task on the fictional sample companies. The
# checks, calculations and report assembly that follow are the real code.
# Three answers contain deliberate mistakes so the checks in backend/validation.py can be seen working: one figure cites the wrong page
# (Agent 1), one summary statement quotes a growth rate that differs from Python's (Agent 1), and one overview statement gives a
# valuation verdict (Agent 3).
from tests.sample import data as D

UNITS = {"shares_outstanding": "millions of shares", "statutory_tax_rate": "percent", "weighted_shares_basic": "millions of shares",
         "weighted_shares_diluted": "millions of shares", "free_float_shares": "millions of shares", "eps_basic": "USD per share",
         "eps_diluted": "USD per share", "dividends_per_share": "USD per share"}


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
         "citations": [{"doc_id": annual, "page": 2}], "topic": "business"},
        {"text": f"Revenue was {f['annual']['FY2025']['revenue']:,.1f} million in 2025.", "citations": [{"doc_id": annual, "page": 6}],
         "topic": "results"},
        {"text": "The annual report names commodity price volatility as the main risk to results.", "citations": [{"doc_id": annual, "page": 6}],
         "topic": "risks"},
        {"text": f"Revenue for the nine months ended September 30, 2026 was {cur:,.1f} million, compared with {prev:,.1f} million a year earlier.",
         "citations": [{"doc_id": quarter, "page": 5}], "topic": "results"},
        {"text": "Management expects capital expenditure to remain broadly in line with the prior year.", "citations": [{"doc_id": quarter, "page": 5}],
         "topic": "outlook"},
    ]
    roe = _indicator(data, "roe_common", "TTM to Q3 2026")
    if roe and roe["value"] not in (None, "—"):
        statements.append({"text": f"Return on common equity was {roe['value']} over the twelve months to September 2026.",
                           "citations": [{"indicator": "roe_common", "period": "TTM to Q3 2026"}], "topic": "results"})
    # deliberate mistake: Python calculated about 6% for FY2025
    statements.append({"text": "Revenue grew 9% in 2025.", "citations": [{"indicator": "revenue_growth", "period": "FY2025"}], "topic": "results"})
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
        ("guidance", cfo, "Capital expenditure is expected to remain broadly in line with the prior year.", 2),
    ]
    cite = [{"doc_id": t, "page": 2}]
    questions = [
        {"analyst": "Priya Nair (Analyst)", "question": "Assuming higher commodity prices, should capital spending rise sharply next year?",
         "question_citations": cite, "answered_by": cfo, "answer": "Capital expenditure is expected to remain broadly in line with the prior year.",
         "answer_citations": cite},
        {"analyst": "Tom Becker (Analyst)", "question": "Will new emissions rules hurt margins, and by how much?", "question_citations": cite,
         "answered_by": ceo, "answer": "It is too early to quantify the effect of the proposed regulation.", "answer_citations": cite},
    ]
    return {"statements": [{"kind": k, "speaker": who, "text": text, "citations": [{"doc_id": t, "page": page}]} for k, who, text, page in rows],
            "questions": questions}


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

    def shown(key):
        return found.get(key) not in (None, "—")

    overview = []
    if shown(("roe_common", period)) and shown(("net_debt_ebitda", period)):
        overview.append({"text": f"Over the twelve months to September 2026, return on common equity was {found[('roe_common', period)]} "
                                 f"and net debt/EBITDA was {found[('net_debt_ebitda', period)]}.",
                         "citations": [cite("roe_common"), cite("net_debt_ebitda")]})
    overview += [
        {"text": f"Revenue for the first nine months of 2026 was {cur:,.1f} million, compared with {prev:,.1f} million a year earlier; the chief "
                 "executive repeated the nine-month figure on the earnings call.", "citations": [page("quarter", 5), page("call", 1)]},
    ]
    if shown(("pe", period)) and shown(("pe", "peer median")):
        overview.append({"text": f"The P/E of {found[('pe', period)]} is above the median of {found[('pe', 'peer median')]} for the "
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
             "with the prior year.", "citations": [page("quarter", 5)]}]},
        {"topic": "Proposed emissions rules", "positions": [
            {"who": "Analyst on the call (Tom Becker)", "text": "An analyst said new emissions rules seem likely to hurt margins.",
             "citations": [page("call", 2)]},
            {"who": "Chief executive, on the call", "text": "The chief executive said it is too early to quantify the effect of the proposed "
             "regulation.", "citations": [page("call", 2)]},
            {"who": "Annual report FY2025", "text": "The annual report names commodity price volatility, not regulation, as the main risk "
             "to results.", "citations": [page("annual", 6)]}]},
    ]
    risks = [
        {"text": "Commodity price volatility is named as the main risk to results.", "citations": [page("annual", 6)]},
        {"text": "An analyst expects new emissions rules to hurt margins; the chief executive said it is too early to quantify the effect.",
         "citations": [page("call", 2)]},
    ]
    return {"overview": overview, "disagreements": disagreements, "risks": risks}


def answer_questions(data: dict) -> dict:
    """A recorded answer for questions about capital expenditure; any other question is not answered by the demo sources."""
    ids, answers = _ids(data["ticker"]), []
    for q in data["questions"]:
        if any(w in q["question"].lower() for w in ("capital expenditure", "capex", "capital spending", "investment")):
            answers.append({"number": q["number"], "answered": True, "statements": [
                {"text": "Management expects capital expenditure to remain broadly in line with the prior year.",
                 "citations": [{"doc_id": ids["quarter"], "page": 5}]},
                {"text": "On the earnings call, the chief financial officer said the same, while an analyst had assumed it must rise sharply.",
                 "citations": [{"doc_id": ids["call"], "page": 2}]}]})
        else:
            answers.append({"number": q["number"], "answered": False, "statements": []})
    return {"answers": answers}


ANSWERS = {"extract_figures": extract_figures, "summarise_reports": summarise_reports, "analyse_call": analyse_call,
           "combine_report": combine_report, "answer_questions": answer_questions}


def answer(task: str, data: dict) -> dict:
    if task not in ANSWERS:
        raise ValueError(f"No recorded demo answer exists for the task '{task}'.")
    return ANSWERS[task](data)
