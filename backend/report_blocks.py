# Turns a finished analysis report into an ordered list of simple display blocks (banner, heading, paragraph, statements, table, list).
# The website draws these now; the PDF and Word files (step 5b) will draw the same blocks, so all three show the same content.
# Numbers are only formatted for display here; nothing is calculated.

SECTIONS = ["Overview", "Where the sources disagree", "Key figures", "Key figures by fiscal year", "What the reports say",
            "Earnings call", "News", "Risks", "Not verified", "Missing information", "Limitations"]
KIND_LABELS = {"management": "Management", "guidance": "Guidance", "analyst": "Analyst question or assumption"}
DISCOUNT_NOTE = ("Peer discount = 1 − company ÷ peer median: negative means the company's multiple is above the peer median, positive "
                 "means below. pp = percentage points. These describe differences only; they are not valuation verdicts.")


def _number(value, unit) -> str:
    if value is None:
        return "—"
    if unit == "x":
        return f"{value:,.2f}x"
    if unit == "fraction":
        return f"{value * 100:,.2f}%"
    return f"{value:,.2f} {unit}"


def display(value, unit) -> str:
    """How a calculated value is shown everywhere (website, PDF, Word, and to the text model): 18.80%, 1.22x, 17.95 USD per share."""
    return _number(value, unit)


def _link(url):
    return url if isinstance(url, str) and url.startswith(("http://", "https://")) else None


def _cite(c: dict) -> dict:
    if "indicator" in c:
        return {"text": f"Calculated: {c.get('name') or c['indicator']} ({c.get('period')})", "url": None}
    if c.get("publisher"):
        return {"text": f"{c['publisher']}, {c.get('published', '')}".rstrip(", "), "url": _link(c.get("url"))}
    if c.get("page") is None and c.get("section"):
        return {"text": f"{c.get('title') or c.get('doc_id')}, {c['section']} ({c.get('tag', '')})", "url": _link(c.get("url"))}
    return {"text": f"{c.get('title') or c.get('doc_id')}, p. {c.get('page')}", "url": _link(c.get("url"))}


def _statement(s: dict, tag: str | None = None) -> dict:
    return {"text": s["text"], "tag": tag, "label": s.get("label", "unverified"), "issues": s.get("issues", []),
            "sources": [_cite(c) for c in s.get("citations", [])]}


def _input_sources(result: dict) -> str:
    """One line per indicator: the documents and pages (and price) its inputs came from."""
    pages, sections, others = {}, {}, []
    for item in result.get("inputs", []):
        for s in item.get("sources", []):
            if "doc_id" in s and s.get("page") is None and s.get("section"):  # SEC XBRL figures: statement and tag, no page
                where = f"{s['section']} ({s['tag']})" if s.get("tag") else s["section"]
                found = sections.setdefault(s.get("title") or s["doc_id"], [])
                if where not in found:
                    found.append(where)
            elif "doc_id" in s:
                pages.setdefault(s.get("title") or s["doc_id"], set()).add(s.get("page"))
            elif s.get("publisher"):
                text = f"{s['publisher']}, close {s.get('date')}"
                if text not in others:
                    others.append(text)
    parts = [f"{title}, {'pp.' if len(p) > 1 else 'p.'} {', '.join(str(n) for n in sorted(p))}" for title, p in pages.items()]
    parts += [f"{title}, {'; '.join(where)}" for title, where in sections.items()] + others
    return "; ".join(parts) or "no sources (not calculated)"


def _status(result: dict) -> str:
    parts = [result["status"].replace("_", " ")]
    if result.get("note"):
        parts.append(result["note"])
    for name, value in (result.get("other_views") or {}).items():
        parts.append(f"{name.replace('_', ' ').capitalize()}: {_number(value, result['unit'])}")
    return ". ".join(p.rstrip(".") for p in parts) + "."


def _comparison(row: dict | None) -> str:
    if not row or row.get("comparison") is None:
        return "—"
    if row["comparison_type"].startswith("peer discount"):
        return f"{row['comparison'] * 100:,.1f}% peer discount"
    return f"{row['comparison'] * 100:+,.2f} pp"


def build(report: dict) -> dict:
    company, a1, a2, a3 = report["company"], report["agent1"], report["agent2"], report["agent3"]
    indicators = a1["indicators"]
    blocks: list[dict] = []
    number = iter(range(1, len(SECTIONS) + 1))

    def section(name):
        blocks.append({"type": "heading", "level": 2, "text": f"{next(number)}. {name}"})

    if report.get("demo_label"):
        blocks.append({"type": "banner", "text": report["demo_label"]})
    title = f"Financial analysis: {company['name']} ({company['ticker']})"
    blocks.append({"type": "heading", "level": 1, "text": title})
    blocks.append({"type": "paragraph", "text": f"Analysis date {report['analysis_date']} · {report['mode']} mode · current period "
                                                f"{indicators['current_period']} · indicator definitions {indicators['definition_version']}"})

    section("Overview")
    blocks.append({"type": "statements", "items": [_statement(s, "Based on " + ", ".join(s.get("based_on", []))) for s in a3["overview"]]})

    section("Where the sources disagree")
    if not a3["disagreements"]:
        blocks.append({"type": "paragraph", "text": "No disagreements were identified."})
    for d in a3["disagreements"]:
        blocks.append({"type": "heading", "level": 3, "text": d["topic"]})
        blocks.append({"type": "statements", "items": [_statement(p, p.get("who")) for p in d["positions"]]})
        if d.get("note"):
            blocks.append({"type": "paragraph", "text": d["note"]})

    section("Key figures")
    peers = report["peers"]
    if peers["peers"]:
        blocks.append({"type": "paragraph", "text": "Peers: " + "; ".join(f"{p['name']} ({p['label']})" for p in peers["peers"]) + "."})
    for e in peers.get("excluded", []):
        blocks.append({"type": "paragraph", "text": f"Not used as a peer: {e['ticker']}. {e['reason']}"})
    comparison = {row["indicator"]: row for row in a1["peer_comparison"]}
    blocks.append({"type": "table", "columns": ["Indicator", "Value", "Peer median", "Compared with peers", "Status and notes"],
                   "rows": [[r["name"], _number(r["value"], r["unit"]),
                             _number(comparison[r["indicator"]]["peer_median"], r["unit"]) if r["indicator"] in comparison else "—",
                             _comparison(comparison.get(r["indicator"])), _status(r)] for r in indicators["current"]],
                   "notes": [f"Period: {indicators['current_period']}. " + DISCOUNT_NOTE]})
    blocks.append({"type": "list", "title": "Sources of the key figures",
                   "items": [f"{r['name']}: {_input_sources(r)}" for r in indicators["current"]]})

    section("Key figures by fiscal year")
    years = list(indicators["history"])
    if years:
        rows = {}
        for fy in years:
            for r in indicators["history"][fy]:
                cell = _number(r["value"], r["unit"]) if r["status"] == "calculated" else r["status"].replace("_", " ")
                rows.setdefault(r["name"], {})[fy] = cell
        blocks.append({"type": "table", "columns": ["Indicator"] + years, "rows": [[name] + [cells.get(fy, "—") for fy in years]
                                                                                    for name, cells in rows.items()],
                       "notes": ["Indicators that need a share price are shown for the current period only."]})
    else:
        blocks.append({"type": "paragraph", "text": "No fiscal-year history is available."})

    section("What the reports say")
    blocks.append({"type": "paragraph", "text": "Agent 1, from the company's reports."})
    blocks.append({"type": "statements", "items": [_statement(s) for s in a1["summary"]]})

    section("Earnings call")
    call = a2["call"]["statements"]
    blocks.append({"type": "paragraph", "text": "Agent 2. Management statements, guidance and analysts' questions are kept apart; "
                                                "an analyst's assumption is not a fact." if call else "No earnings-call material was available."})
    blocks.append({"type": "statements", "items": [_statement(s, f"{KIND_LABELS.get(s.get('kind'), s.get('kind'))} · {s.get('speaker')}")
                                                   for s in call]})

    section("News")
    news = a2["news"]
    blocks.append({"type": "paragraph", "text": f"Agent 2. News since the latest results announcement ({news['since']}), plus older items "
                                                "that are still material. Timing alone does not show that news moved the share price."})
    blocks.append({"type": "statements", "items": [
        _statement({**i, "text": f"{i['title']}. {i['channel']}"}, f"{i['published']} · {i['publisher']}" + ("" if i["recent"] else " · older item"))
        for i in news["included"]]})
    if news["excluded"]:
        blocks.append({"type": "list", "title": "News left out", "items": [f"{e['published']} · {e['title']}: {e['reason']}" for e in news["excluded"]]})

    section("Risks")
    blocks.append({"type": "statements", "items": [_statement(s, "Based on " + ", ".join(s.get("based_on", []))) for s in a3["risks"]]})

    section("Not verified")
    blocks.append({"type": "list", "style": "warn", "items": [f"{u['agent']}: “{u['text']}” — {' '.join(u['issues'])}"
                                                              for u in a3["unverified_statements"]] or ["Every statement was verified."]})

    section("Missing information")
    blocks.append({"type": "list", "items": a3["missing_information"] or ["Nothing missing was recorded."]})

    section("Limitations")
    blocks.append({"type": "list", "items": a3["limitations"] + report.get("notes", [])})

    return {"title": title, "demo_label": report.get("demo_label"), "blocks": blocks}
