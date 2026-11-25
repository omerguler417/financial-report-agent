# Agent 3: combines Agents 1 and 2 into one report: an overview, where the sources disagree (each position labelled with who said it),
# the main risks, and, built in Python, what is missing, what could not be verified, and the limitations. It never calculates: every
# number must come from a cited source or a Python result, and every statement is checked like the other agents' statements.
from backend import prompts, report_blocks, validation

AGENT = "Agent 3 – combined report"
US_EXCHANGES = {"NYSE", "NASDAQ", "NYSE AMERICAN", "AMEX", "NYSEARCA", "ARCA"}
ORIGINS = {"transcript": "Agent 2 (earnings call)", "news": "Agent 2 (news)"}


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
        "indicators": [{**{k: r.get(k) for k in ("indicator", "name", "period", "status")}, "value": report_blocks.display(r.get("value"), r.get("unit"))}
                       for r in results if r["period"] in (current, "peer median")],
        "call": [{k: s.get(k) for k in ("kind", "speaker", "text", "citations")} for s in agent2["call"]["statements"] if s["verified"]],
        "news": [{k: i.get(k) for k in ("id", "publisher", "published", "title", "channel")} for i in agent2["news"]["included"] if i["verified"]],
    }


def _missing(agent1: dict, agent2: dict) -> list[str]:
    items = [f"{r['name']} ({r['period']}): {r['status'].replace('_', ' ')}. {r['note']}".strip()
             for r in agent1["indicators"]["current"] if r["status"] != "calculated"]
    items += [f"Figure not used: {x.get('field')} for {x.get('period')}: {x['reason']}." for x in agent1["extraction_check"]["rejected"]]
    items += [f"Peer comparison, {row['name']}: {row['note']}" for row in agent1["peer_comparison"] if row["note"]]
    items += agent1["notes"] + agent2["notes"]
    return items


def _limitations(company: dict, demo_label: str | None, left_out: list[str] | None = None) -> list[str]:
    items = []
    if left_out:
        items.append(f"Indicators left out at your request ({len(left_out)}): {', '.join(left_out)}.")
    if demo_label:
        items.append(f"{demo_label}. The model's answers are recorded, and a few contain deliberate mistakes so the checks can be seen working.")
    items += [
        "Comparisons use standardised free cash flow (after cash interest and lease repayments), with the reported figure alongside; "
        "where those adjustments are not in the reports, the reported figure is used and labelled.",
        "Enterprise value uses non-controlling interests at book value.",
        "Multiples at past year ends (historical medians) are not calculated yet; the history covers indicators that need no share price.",
        "Indicator definitions follow docs/indicator_definitions.md v1.0.",
        "Statements labelled unverified are kept so they can be seen, but their cited source does not support them.",
    ]
    if (company.get("exchange") or "").upper() not in US_EXCHANGES:
        items.append("Market holidays are known only for US exchanges; for this exchange only weekends are excluded, so the "
                     "latest-session price check is approximate.")
    return items


def run(company: dict, agent1: dict, agent2: dict, services, context: dict) -> dict:
    read, results = context.get("read", {}), context.get("results", [])
    request = prompts.build("combine_report", _payload(company, agent1, agent2, results))
    answer = services.model.ask(request["task"], request["data"])

    def check(statements: list[dict]) -> list[dict]:
        checked = validation.check_statements(statements, read, results)
        for s in checked:
            s["based_on"] = sorted({_origin(c, read) for c in s["citations"]})
        return checked

    overview, risks = check(answer.get("overview")), check(answer.get("risks"))
    disagreements = []
    for d in validation.as_list(answer.get("disagreements")):
        if not isinstance(d, dict):  # a plain sentence: kept as a topic without positions
            d = {"topic": str(d), "positions": []}
        positions = check(d.get("positions"))
        entry = {"topic": str(d.get("topic", "")), "positions": positions}
        if len({o for p in positions for o in p["based_on"]}) < 2:
            entry["note"] = "All positions come from the same source, so this is not a disagreement between sources."
        disagreements.append(entry)

    unverified = [{"agent": "Agent 1", "text": s["text"], "issues": s["issues"]} for s in agent1["summary"] if not s["verified"]]
    unverified += [{"agent": "Agent 2", "text": s["text"], "issues": s["issues"]} for s in agent2["call"]["statements"] if not s["verified"]]
    unverified += [{"agent": "Agent 2", "text": i["channel"], "issues": i["issues"]} for i in agent2["news"]["included"] if not i["verified"]]
    own = overview + risks + [p for d in disagreements for p in d["positions"]]
    unverified += [{"agent": "Agent 3", "text": s["text"], "issues": s["issues"]} for s in own if not s["verified"]]
    total = len(agent1["summary"]) + len(agent2["call"]["statements"]) + len(agent2["news"]["included"]) + len(own)

    return {
        "agent": AGENT,
        "overview": overview,
        "disagreements": disagreements,
        "risks": risks,
        "missing_information": _missing(agent1, agent2),
        "unverified_statements": unverified,
        "limitations": _limitations(company, getattr(services, "label", None), agent1["indicators"].get("left_out")),
        "statement_check": {"checked": total, "verified": total - len(unverified), "unverified": len(unverified)},
    }
