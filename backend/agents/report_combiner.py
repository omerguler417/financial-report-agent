# Agent 3: combines Agents 1 and 2 into one report: an overview, where the sources disagree (each position labelled with who said it),
# the main risks, commentary on each comparison section and on the valuation summary, and, built in Python, what is missing, what could not be verified, and the limitations. It never calculates: every
# number must come from a cited source or a Python result, and every statement is checked like the other agents' statements.
from backend import comparisons, prompts, report_blocks, retrieval, validation
from backend.report_reader import Page

AGENT = "Agent 3 – combined report"
US_EXCHANGES = {"NYSE", "NASDAQ", "NYSE AMERICAN", "AMEX", "NYSEARCA", "ARCA"}
ORIGINS = {"transcript": "Agent 2 (earnings call)"}


def _origin(citation: dict, read: dict) -> str:
    if "indicator" in citation:
        return "Agent 1 (calculated)"
    kind = read.get(citation.get("doc_id"), {}).get("doc", {}).get("kind")
    return ORIGINS.get(kind, "Agent 1 (reports)")


def _payload(company: dict, agent1: dict, agent2: dict, results: list[dict]) -> dict:
    current = agent1["indicators"]["current_period"]
    return {
        "ticker": company["ticker"], "company": company["name"],
        "agent1_summary": [{"text": s["text"], "citations": s["citations"]} for s in agent1["summary"] if s["verified"]],
        "indicators": [{**{k: r.get(k) for k in ("indicator", "name", "period", "status")}, "value": report_blocks.display(r.get("value"), r.get("unit")),
                        "cite_as": {"indicator": r.get("indicator"), "period": r.get("period")}}
                       for r in results if r["period"] in (current, "peer median")],
        "call": [{k: s.get(k) for k in ("kind", "speaker", "text", "citations")} for s in agent2["call"]["statements"] if s["verified"]],
        "call_questions": [{"analyst": q["analyst"], "question": q["question"]["text"], "question_citations": q["question"]["citations"],
                            "answered_by": q["answered_by"], "answer": q["answer"]["text"], "answer_citations": q["answer"]["citations"]}
                           for q in agent2["call"].get("questions", []) if q["question"]["verified"] and q["answer"]["verified"]],
    }


def _missing(agent1: dict, agent2: dict) -> list[str]:
    items = [f"{r['name']} ({r['period']}): {r['status'].replace('_', ' ')}. {r['note']}".strip()
             for r in agent1["indicators"]["current"] if r["status"] != "calculated"]
    items += [f"Figure not used: {x.get('field')} for {x.get('period')}: {x['reason']}." for x in agent1["extraction_check"]["rejected"]]
    items += [f"Peer comparison, {row['name']}: {row['note']}" for row in agent1["peer_comparison"] if row["note"]]
    items += agent1["notes"] + agent2["notes"]
    return items


def _limitations(company: dict, agent1: dict) -> list[str]:
    items = []
    left_out = agent1["indicators"].get("left_out")
    if left_out:
        items.append(f"Indicators left out at your request ({len(left_out)}): {', '.join(left_out)}.")
    items += [
        "Comparisons use standardised free cash flow (after cash interest and lease repayments), with the reported figure alongside; "
        "where those adjustments are not in the reports, the reported figure is used and labelled.",
        "Enterprise value uses non-controlling interests at book value.",
        "The fiscal-year history covers indicators that need no share price; price-based multiples are compared with their own past "
        "through the historical medians.",
        "Indicator definitions follow docs/indicator_definitions.md v1.1.",
        "Statements labelled unverified are kept so they can be seen, but their cited source does not support them.",
    ]
    # the price check uses the calendar of the exchange the prices came from (the company's own field is often empty)
    price = ((agent1["indicators"].get("market") or {}).get("price") or {})
    exchanges = {(src.get("exchange") or "").upper() for src in price.get("sources", [])} or ({(company.get("exchange") or "").upper()} if price else set())
    if exchanges - US_EXCHANGES:
        items.append("Market holidays are known only for US exchanges; for this exchange only weekends are excluded, so the "
                     "latest-session price check is approximate.")
    return items


PAGES_PER_QUESTION = 6
UNANSWERED = "The reports and the call do not answer this question."


def answer_questions(company: dict, questions: list[str], payload: dict, services, check) -> list[dict]:
    """The user's own questions, answered only from the most relevant pages read (reports and call) and the calculated indicators.
    Every sentence is checked like the other statements; a question the sources do not answer says so."""
    if not questions:
        return []
    read = payload["read"]
    pages = {doc_id: item["pages"] for doc_id, item in read.items()}
    data = {"ticker": company["ticker"], "company": company["name"], "indicators": payload["indicators"],
            "questions": [{"number": i, "question": q,
                           "pages": [{"doc_id": p.doc_id, "page": p.page, "text": p.text} for p in retrieval.retrieve(pages, q, k=PAGES_PER_QUESTION)]}
                          for i, q in enumerate(questions, 1)]}
    request = prompts.build("answer_questions", data)
    given = {}
    for a in validation.as_list(services.model.ask(request["task"], request["data"]).get("answers")):
        if isinstance(a, dict) and str(a.get("number", "")).isdigit():
            given[int(a["number"])] = a
    out = []
    for i, q in enumerate(questions, 1):
        a = given.get(i, {})
        statements = check(a.get("statements")) if a.get("answered") else []
        answered = bool(statements)
        out.append({"question": q, "answered": answered, "statements": statements, "note": "" if answered else UNANSWERED})
    return out


LINES_DOC = "comparison-lines"  # the Python comparison lines, shown to the checker as one page per section


def _with_period(citation, section_cites: list[dict]):
    """A citation of a calculated result without a period gets the period the section's comparison lines used for it."""
    if not isinstance(citation, dict) or "indicator" not in citation or citation.get("period"):
        return citation
    used = next((c for c in section_cites if c["indicator"] == citation["indicator"] and c["period"] != "peer median"), None)
    return {**citation, "period": used["period"]} if used else citation


def write_commentary(company: dict, agent1: dict, services, read: dict, results: list[dict], indicators: list[dict], check) -> dict:
    """A headline and a short paragraph for each comparison section, and two or three sentences on the valuation summary, in the
    style of a research note. The model explains what the Python comparison lines mean; each sentence is checked like every other
    statement. A sentence that cites a section's lines may quote their numbers; its citation then becomes the calculated results
    those lines were built from. A section the model does not cover keeps its Python lines only."""
    built = comparisons.build({"agent1": agent1})
    groups, valuation = built["groups"], built["valuation"]
    if not groups:
        return {"sections": {}, "valuation": []}
    pages = [Page(i + 1, " ".join(line["text"] for line in g["lines"]), f"section {i + 1}") for i, g in enumerate(groups)]
    pages.append(Page(len(pages) + 1, " ".join([p["text"] for p in valuation["parts"]] + [valuation["overall"]]), "valuation summary"))
    lines_read = {**read, LINES_DOC: {"doc": {"title": "Comparison lines"}, "pages": pages}}
    behind = [[c for line in g["lines"] for c in line["cites"]] for g in groups] + [[c for p in valuation["parts"] for c in p["cites"]]]
    names = {(r["indicator"], r["period"]): r.get("name") for r in results}

    def checked(statements, section: int) -> list[dict]:
        given = validation.as_statements(statements)
        for s in given:  # a result cited without its period takes the period this section's lines used (e.g. "FY2025 vs FY2024")
            cites = validation.as_list(s.get("citations"))
            s["citations"] = [_with_period(c, behind[section]) for c in cites]
        out = check(given, lines_read)
        for s in out:  # a citation of the lines becomes the calculated results they were built from
            cites = []
            for c in s["citations"]:
                swap = ([{**x, "name": names.get((x["indicator"], x["period"]))} for x in behind[c["page"] - 1]]
                        if c.get("doc_id") == LINES_DOC else [c])
                cites += [x for x in swap if x not in cites]
            s["citations"] = cites
            s["based_on"] = sorted({_origin(c, read) for c in cites})
        return out

    data = {"ticker": company["ticker"], "company": company["name"], "indicators": indicators,
            "sections": [{"group": g["group"], "lines": [line["text"] for line in g["lines"]], "cite_as": {"doc_id": LINES_DOC, "page": i + 1}}
                         for i, g in enumerate(groups)],
            "valuation_summary": {"parts": [{"against": p["benchmark"], "label": p["label"], "text": p["text"]} for p in valuation["parts"]],
                                  "overall": valuation["overall"], "cite_as": {"doc_id": LINES_DOC, "page": len(pages)}}}
    request = prompts.build("write_commentary", data)
    answer = services.model.ask(request["task"], request["data"])
    known = {g["group"] for g in groups}
    sections = {}
    for item in validation.as_list(answer.get("sections")):
        if not isinstance(item, dict) or item.get("group") not in known or item["group"] in sections:
            continue
        section = next(i for i, g in enumerate(groups) if g["group"] == item["group"])
        headline = checked(item.get("headline"), section)
        paragraph = checked(item.get("paragraph"), section)
        if headline or paragraph:
            sections[item["group"]] = {"headline": headline[0] if headline else None, "paragraph": paragraph}
    return {"sections": sections, "valuation": checked(answer.get("valuation"), len(groups)) if valuation["parts"] else []}


def run(company: dict, agent1: dict, agent2: dict, services, context: dict, questions: list[str] | None = None) -> dict:
    read, results = context.get("read", {}), context.get("results", [])
    request = prompts.build("combine_report", _payload(company, agent1, agent2, results))
    answer = services.model.ask(request["task"], request["data"])

    def check(statements: list[dict], pages: dict | None = None) -> list[dict]:
        checked = validation.check_statements(statements, pages or read, results, agent1["indicators"]["current_period"])
        for s in checked:
            s["based_on"] = sorted({_origin(c, read) for c in s["citations"]})
        return checked

    overview, risks = check(answer.get("overview")), check(answer.get("risks"))
    disagreements = []
    for d in validation.as_list(answer.get("disagreements")):
        if not isinstance(d, dict):  # a plain sentence: kept as a topic without positions
            d = {"topic": str(d), "positions": []}
        positions = check(d.get("positions"))
        if not positions:  # a topic with no positions is not a disagreement (for example "there are no disagreements")
            continue
        if len({o for p in positions for o in p["based_on"]}) < 2:  # one source does not disagree with itself
            continue
        disagreements.append({"topic": str(d.get("topic", "")), "positions": positions})

    payload = _payload(company, agent1, agent2, results)
    answers = answer_questions(company, questions or [], {"read": read, "indicators": payload["indicators"]}, services, check)
    commentary = write_commentary(company, agent1, services, read, results, payload["indicators"], check)
    written = [s for c in commentary["sections"].values() for s in ([c["headline"]] if c["headline"] else []) + c["paragraph"]]
    written += commentary["valuation"]

    unverified = [{"agent": "Agent 1", "text": s["text"], "issues": s["issues"]} for s in agent1["summary"] if not s["verified"]]
    call_items = agent2["call"]["statements"] + [s for q in agent2["call"].get("questions", []) for s in (q["question"], q["answer"])]
    unverified += [{"agent": "Agent 2", "text": s["text"], "issues": s["issues"]} for s in call_items if not s["verified"]]
    own = overview + risks + [p for d in disagreements for p in d["positions"]] + [s for a in answers for s in a["statements"]] + written
    unverified += [{"agent": "Agent 3", "text": s["text"], "issues": s["issues"]} for s in own if not s["verified"]]
    total = len(agent1["summary"]) + len(call_items) + len(own)

    return {
        "agent": AGENT,
        "overview": overview,
        "disagreements": disagreements,
        "risks": risks,
        "questions": answers,
        "commentary": commentary,
        "missing_information": _missing(agent1, agent2),
        "unverified_statements": unverified,
        "limitations": _limitations(company, agent1),
        "statement_check": {"checked": total, "verified": total - len(unverified), "unverified": len(unverified)},
    }
