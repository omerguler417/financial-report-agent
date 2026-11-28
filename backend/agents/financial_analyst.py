# Agent 1: reads the company's reports into numbered pages, has the text model copy out the figures and summarise the reports (both
# checked in backend/validation.py), and calculates the indicators, history and peer medians in Python (backend/indicators.py).
# The model never calculates. Documents published after the analysis date are left out.
from datetime import date

from backend import financials, indicators, prompts, report_blocks, report_reader, retrieval, validation
from backend.errors import ProviderNotConfigured
from backend.fetchers.edgar import SOURCE_GAPS
from backend.fetchers.http_client import AccessDenied, FetchFailed
from backend.fetchers.market_data import PriceUnavailable

AGENT = "Agent 1 – reports and indicators"
REPORT_KINDS = {"annual_report", "quarterly_report"}
EXTRACTION_QUERIES = [
    "consolidated statement of income revenues operating income net income attributable interest expense taxes",
    "balance sheet total assets current liabilities borrowings lease liabilities equity noncontrolling shares outstanding cash",
    "statement of cash flows operating activities capital expenditures dividends paid depreciation amortisation",
    "income taxes statutory tax rate",
]
SUMMARY_QUERY = "business segments products customers regions management discussion revenue outlook expects risk"


def read_reports(documents: list[dict], as_of: date) -> tuple[dict, list[dict], list[str]]:
    """Reports published on or before `as_of`, read into pages. Returns ({doc_id: {doc, pages}}, document list, notes)."""
    read, listed, notes = {}, [], []
    for doc in documents:
        if doc.get("kind") not in REPORT_KINDS:
            continue
        if doc.get("publication_date") and doc["publication_date"] > as_of.isoformat():
            notes.append(f"{doc['title']} was published on {doc['publication_date']}, after the analysis date, so it is not yet published "
                         "for this analysis and is left out.")
            continue
        if "pages" in doc:
            pages = report_reader.pages_from_texts(doc["pages"])
        else:
            result = report_reader.try_read_document(doc["path"])
            pages = result.pages
            notes += result.notes
        meta = {k: v for k, v in doc.items() if k not in ("pages", "path")}
        read[doc["doc_id"]] = {"doc": meta, "pages": pages}
        listed.append(meta)
    return read, listed, notes


def _passages(read: dict, queries: list[str], per_query: int) -> list[dict]:
    pages = {doc_id: item["pages"] for doc_id, item in read.items()}
    chosen = {}
    for doc_id in pages:
        for query in queries:
            for p in retrieval.retrieve({doc_id: pages[doc_id]}, query, k=per_query):
                chosen[(p.doc_id, p.page)] = {"doc_id": p.doc_id, "page": p.page, "label": p.label, "text": p.text}
    return [chosen[k] for k in sorted(chosen)]


def company_inputs(company: dict, services, as_of: date, read_documents: bool = True, horizon: int = 5) -> tuple:
    """Figures for one company, checked and turned into calculation inputs. Returns (inputs, read, documents, check, notes).
    With structured figures (EDGAR), a peer's reports are not downloaded: only its figures and price are needed.
    horizon: the fiscal years of history chosen for the analysis (3, 5 or 10)."""
    structured = getattr(services, "figures", None)
    if read_documents or not structured:
        read, documents, notes = read_reports(services.documents.find(company["ticker"]), as_of)
    else:
        read, documents, notes = {}, [], []
    if structured:  # SEC filers: figures from the SEC's XBRL data, no model needed
        accepted, figure_notes = structured(company["ticker"], as_of, years=horizon + 1)  # n years of growth need n + 1 years
        check, notes = {"accepted": accepted, "rejected": []}, notes + figure_notes
    else:
        request = prompts.build("extract_figures", {"ticker": company["ticker"], "company": company["name"], "fields": financials.FIELDS,
                                                    "pages": _passages(read, EXTRACTION_QUERIES, 2)})
        answer = services.model.ask(request["task"], request["data"])
        check = validation.check_figures(answer.get("figures", []), read)
    price, points, price_note = None, {}, ""
    try:
        price = financials.closing_price(services.market, company["ticker"], as_of)
        points = financials.price_points(services.market, company["ticker"], as_of, years=horizon)
    except ProviderNotConfigured:
        price_note = "no market-data provider is configured"
        notes.append("Share prices are not available: no market-data provider is configured, so price-based indicators and peers "
                     "are not calculated.")
    except (PriceUnavailable, FetchFailed, AccessDenied) as exc:  # the provider answered with an error: reported, never guessed
        price_note = "the market-data provider returned no price"
        notes.append(f"Share prices are not available: {exc}")
    model = financials.business_model(services.market.profile(company["ticker"]))
    inputs = financials.build_inputs(company["name"], check["accepted"], price, model, points)
    inputs.price_note = price_note
    inputs.horizon_years = horizon
    if structured:  # 10-K and 10-Q filers report under US GAAP
        inputs.source_gaps = dict(SOURCE_GAPS)
        inputs.interest_rule = ("US GAAP classifies interest paid within operating activities (ASC 230), so no interest adjustment is "
                                "needed.")
    return inputs, read, documents, check, notes


def _results(analysis: dict) -> list[dict]:
    rows = [r.to_dict() for r in analysis["current"]]
    return rows + [r.to_dict() for fy in analysis["history"].values() for r in fy]


def _keep(analysis: dict, chosen: set | None) -> dict:
    """Only the indicators the user chose; everything is still calculated, because some indicators build on others."""
    if not chosen:
        return analysis
    return {**analysis, "current": [r for r in analysis["current"] if r.indicator in chosen],
            "history": {fy: [r for r in rows if r.indicator in chosen] for fy, rows in analysis["history"].items()}}


def _can_be_valued(inputs) -> bool:
    current = inputs.ytd_current or inputs.latest_fy
    return inputs.price is not None and "shares_outstanding" in inputs.periods.get(current, {})


def _analyse_peers(peer_selection: dict, services, as_of: date, horizon: int, chosen, target_inputs, notes: list[str]) -> dict:
    """Each peer's analysis. Decided 28 November 2026: when the company itself can be valued, a peer without a share count or price
    is skipped and the next-closest suitable company from the reserve takes its place (user-requested peers are kept). The peer list
    in peer_selection is updated in place, so the report shows who was used and who was skipped and why."""
    wanted = len(peer_selection.get("peers", []))
    queue = list(peer_selection.get("peers", [])) + list(peer_selection.get("reserve", []))
    used, analyses = [], {}
    for peer in queue:
        if len(used) >= wanted:
            break
        try:
            peer_inputs = company_inputs({"ticker": peer["ticker"], "name": peer["name"]}, services, as_of, read_documents=False,
                                         horizon=horizon)[0]
        except Exception as exc:  # one peer's missing data must not stop the analysis; it is reported instead
            notes.append(f"Peer {peer['ticker']} could not be analysed: {exc}")
            continue
        user_pick = str(peer.get("label", "")).startswith("user-requested")
        if _can_be_valued(target_inputs) and not _can_be_valued(peer_inputs) and not user_pick:
            missing = "share count" if peer_inputs.price is not None else "share price"
            peer_selection.setdefault("excluded", []).append(
                {"ticker": peer["ticker"], "reason": f"Skipped: no {missing} in the available data, so it cannot be compared on valuation; "
                                                     "the next-closest company was used instead."})
            continue
        used.append(peer)
        analyses[peer["ticker"]] = _keep(indicators.analyse(peer_inputs), chosen)
    peer_selection["peers"] = used
    return analyses


def run(company: dict, peer_selection: dict, services, as_of: date, context: dict | None = None, chosen: list[str] | None = None,
        horizon: int = 5) -> dict:
    """context, when given, receives what Agent 3 needs to check its citations: the pages read and the calculated results.
    chosen: the indicator ids the user wants reported (all when None). horizon: fiscal years of history (3, 5 or 10)."""
    chosen = set(chosen) if chosen else None
    inputs, read, documents, check, notes = company_inputs(company, services, as_of, horizon=horizon)
    analysis = _keep(indicators.analyse(inputs), chosen)

    peer_analyses = _analyse_peers(peer_selection, services, as_of, horizon, chosen, inputs, notes)
    comparison = indicators.compare_with_peers(analysis, peer_analyses) if peer_analyses else []

    results = _results(analysis) + [
        {"indicator": row["indicator"], "name": f"{row['name']} peer median", "period": "peer median", "status": "calculated",
         "value": row["peer_median"], "unit": row["unit"]} for row in comparison if row["peer_median"] is not None]
    if context is not None:
        context.setdefault("read", {}).update(read)
        context["results"] = results
    request = prompts.build("summarise_reports", {
        "ticker": company["ticker"], "company": company["name"], "pages": _passages(read, [SUMMARY_QUERY], 3),
        "indicators": [{**{k: r[k] for k in ("indicator", "name", "period", "status")}, "value": report_blocks.display(r["value"], r["unit"]),
                        "cite_as": {"indicator": r["indicator"], "period": r["period"]}}
                       for r in [x.to_dict() for x in analysis["current"]] + [r for r in results if r["period"] == "peer median"]]})
    summary = validation.check_statements(services.model.ask(request["task"], request["data"]).get("statements", []), read, results,
                                          analysis["current_period"])

    return {
        "agent": AGENT,
        "documents": documents,
        "summary": summary,
        "indicators": {"definition_version": analysis["definition_version"], "business_model": analysis["business_model"],
                       "current_period": analysis["current_period"], "horizon_years": analysis["horizon_years"],
                       "financial_summary": analysis["financial_summary"], "market": analysis["market"],
                       "current": [r.to_dict() for r in analysis["current"]],
                       "history": {fy: [r.to_dict() for r in rs] for fy, rs in analysis["history"].items()}, "notes": analysis["notes"],
                       "left_out": [s.name for s in indicators.SPECS if chosen and s.id not in chosen]},
        "peer_comparison": comparison,
        "extraction_check": {"accepted": len(check["accepted"]), "rejected": check["rejected"]},
        "notes": notes,
    }
