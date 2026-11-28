# Turns a finished analysis report into an ordered list of simple display blocks (heading, paragraph, statements, table, list).
# The website draws these now; the PDF and Word files (step 5b) will draw the same blocks, so all three show the same content.
# Numbers are only formatted for display here; nothing is calculated.

SECTIONS = ["Executive summary", "Your questions", "Financial summary", "Trading comparables", "Historical valuation", "Financial analysis",
            "Business overview and outlook", "Earnings call highlights", "Where the sources disagree", "Key risks"]
TOPICS = [("business", "Business"), ("results", "Results"), ("outlook", "Outlook")]
SUMMARY_GROUPS = ["Valuation", "Profitability", "Debt and liquidity", "Cash flow and dividends", "Growth"]
REPORT_SOURCE = "Source: company reports and filings; folio. calculations."
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
    unit = "turn" if c.get("page_unit") == "turn" else "p."
    return {"text": f"{c.get('title') or c.get('doc_id')}, {unit} {c.get('page')}", "url": _link(c.get("url"))}


def _statement(s: dict, tag: str | None = None) -> dict:
    return {"text": s["text"], "tag": tag, "label": s.get("label", "unverified"), "issues": s.get("issues", []),
            "sources": [_cite(c) for c in s.get("citations", [])]}


def _sources_by_document(results: list[dict]) -> list[str]:
    """Appendix C: one line per document (its pages, or its statements and tags), and one line for the share prices."""
    pages, sections, prices = {}, {}, {}
    for result in results:
        for item in result.get("inputs", []):
            for s in item.get("sources", []):
                if "doc_id" in s and s.get("page") is None and s.get("section"):
                    sections.setdefault(s.get("title") or s["doc_id"], set()).add(s["section"])
                elif "doc_id" in s:
                    pages.setdefault(s.get("title") or s["doc_id"], set()).add(s.get("page"))
                elif s.get("publisher"):
                    prices.setdefault(s["publisher"], set()).add(str(s.get("date")))
    lines = [f"{title}: {'pp.' if len(p) > 1 else 'p.'} {', '.join(str(n) for n in sorted(p, key=lambda x: (x is None, x)))}"
             for title, p in sorted(pages.items())]
    lines += [f"{title}: {', '.join(sorted(where))}" for title, where in sorted(sections.items())]
    lines += [f"{publisher}: closing prices, {len(days)} dates from {min(days)} to {max(days)} (latest close {max(days)})" if len(days) > 1
              else f"{publisher}: close {next(iter(days))}" for publisher, days in sorted(prices.items())]
    return lines or ["No sources: no indicator was calculated."]


def _comparison(row: dict | None) -> str:
    if not row or row.get("comparison") is None:
        return "—"
    if row["comparison_type"].startswith("peer discount"):
        return f"{row['comparison'] * 100:,.1f}% peer discount"
    return f"{row['comparison'] * 100:+,.2f} pp"


def _verified_first(statements: list[dict]) -> list[dict]:
    """Verified statements first; unverified ones stay in the report, labelled, after them."""
    return sorted(statements, key=lambda s: not s.get("verified", s.get("label") == "verified"))


def _commentary(lines: list[dict]) -> list[dict]:
    """Comparison lines as short report paragraphs: the summary as a bold lead, then the peer comparison, own history and trend."""
    out = [{"type": "paragraph", "style": "lead", "text": l["text"]} for l in lines if l["kind"] == "summary"]
    for kinds in (("peers",), ("history", "peer history"), ("trend",)):
        chosen = [l["text"] for l in lines if l["kind"] in kinds]
        if chosen:
            out.append({"type": "paragraph", "text": " ".join(chosen)})
    return out


def build(report: dict) -> dict:
    """The report in the order of a bank's company report: summary and key data, numbered exhibits, analysis, commentary, risks, and
    appendices. It describes and compares; it gives no rating, target or recommendation."""
    from backend import comparisons, exhibits
    company, a1, a2, a3 = report["company"], report["agent1"], report["agent2"], report["agent3"]
    indicators = a1["indicators"]
    lines, ex = comparisons.build(report), exhibits.build(report)
    groups = {g["group"]: g["lines"] for g in lines["groups"]}
    blocks: list[dict] = []
    number, exhibit = iter(range(1, len(SECTIONS) + 1)), iter(range(1, 10))

    def section(name):
        blocks.append({"type": "heading", "level": 2, "text": f"{next(number)}. {name}"})

    def appendix(letter, name):
        blocks.append({"type": "heading", "level": 2, "text": f"Appendix {letter}. {name}"})

    def table(title, data, source):
        blocks.append({"type": "table", "title": f"Exhibit {next(exhibit)}: {title}", "columns": data["columns"], "rows": data["rows"],
                       "source": source})

    price_sources = sorted({s_.get("publisher") for s_ in ((indicators.get("market") or {}).get("price") or {}).get("sources", [])} - {None})
    price_source = f"share prices from {', '.join(price_sources)}; " if price_sources else ""

    title = f"Financial analysis: {company['name']} ({company['ticker']})"
    blocks.append({"type": "heading", "level": 1, "text": company["name"]})  # a research note leads with the company
    blocks.append({"type": "paragraph", "text": f"{company['ticker']} · analysis date {report['analysis_date']} · "
                                                f"{indicators['current_period'].replace('TTM to ', 'LTM ')} · "
                                                f"{indicators.get('horizon_years', 5)}-year horizon · definitions {indicators['definition_version']}"})
    key_lines = [next((l["text"] for l in groups.get(g, []) if l["kind"] == "peers"), None) for g in SUMMARY_GROUPS]
    blocks.append({"type": "summarybox", "comparisons": [t for t in key_lines if t],  # the research note's first-page box
                   "key_data": [[row["label"], row["value"]] for row in ex["key_data"]],
                   "peers": ", ".join(p["ticker"] for p in report["peers"]["peers"]) or "none"})

    section("Executive summary")
    blocks.append({"type": "statements", "items": [_statement(s_, "Based on " + ", ".join(s_.get("based_on", [])))
                                                   for s_ in _verified_first(a3["overview"])]})

    if a3.get("questions"):  # only when the user asked any
        section("Your questions")
        for q in a3["questions"]:
            blocks.append({"type": "heading", "level": 3, "text": q["question"]})
            if q["statements"]:
                blocks.append({"type": "statements", "items": [_statement(s_) for s_ in q["statements"]]})
            else:
                blocks.append({"type": "paragraph", "text": q["note"]})

    section("Financial summary")
    if ex["financial_summary"]["rows"]:
        table("Financial summary (USD millions)", ex["financial_summary"], REPORT_SOURCE)
    else:
        blocks.append({"type": "paragraph", "text": "No financial summary is available for this analysis."})

    section("Trading comparables")
    peers = report["peers"]
    table(f"Trading comparables ({ex['comparables']['period']})", ex["comparables"],
          f"Source: company reports and filings; {price_source}folio. calculations.")
    if peers["peers"]:
        blocks.append({"type": "paragraph", "text": "Peers: " + "; ".join(f"{p['name']} ({p['label']})" for p in peers["peers"]) + "."})
    for e in peers.get("excluded", []):
        blocks.append({"type": "paragraph", "text": f"Not used as a peer: {e['ticker']}. {e['reason']}"})

    section("Historical valuation")
    if ex["historical"]["rows"]:
        table("Valuation against own history and peers' history", ex["historical"],
              f"Source: company reports and filings; {price_source}folio. calculations at past fiscal year ends.")
    if groups.get("Historical comparison"):
        blocks += _commentary(groups["Historical comparison"])

    section("Financial analysis")
    for group, group_lines in groups.items():  # written by Python from the results, never by the text model
        if group == "Historical comparison":
            continue
        blocks.append({"type": "heading", "level": 3, "text": group})
        blocks += _commentary(group_lines)

    section("Business overview and outlook")
    summary = a1["summary"]
    known = [key for key, _ in TOPICS] + ["risks"]
    for key, heading in TOPICS + [("other", "Other")]:
        chosen = [s_ for s_ in summary if (s_.get("topic") not in known if key == "other" else s_.get("topic") == key)]
        if chosen:
            blocks.append({"type": "heading", "level": 3, "text": heading})
            blocks.append({"type": "statements", "items": [_statement(s_) for s_ in chosen]})

    section("Earnings call highlights")
    call = a2["call"]["statements"]
    if not call:
        blocks.append({"type": "paragraph", "text": "No earnings-call material was available."})
    for kind, heading in (("management", "Key points"), ("guidance", "Guidance"), ("analyst", "Analyst questions and assumptions")):
        chosen = [s_ for s_ in call if s_.get("kind") == kind]
        if chosen:
            blocks.append({"type": "heading", "level": 3, "text": heading})
            blocks.append({"type": "statements", "items": [_statement(s_, s_.get("speaker")) for s_ in chosen]})
    questions = a2["call"].get("questions", [])
    if questions:
        blocks.append({"type": "heading", "level": 3, "text": "Questions and answers"})
        blocks.append({"type": "statements", "items": [item for q in questions for item in
                                                       (_statement(q["question"], f"Question · {q['analyst']}"),
                                                        _statement(q["answer"], f"Answer · {q['answered_by']}"))]})

    section("Where the sources disagree")
    if not a3["disagreements"]:
        blocks.append({"type": "paragraph", "text": "No disagreements were identified."})
    for d in a3["disagreements"]:
        blocks.append({"type": "heading", "level": 3, "text": d["topic"]})
        blocks.append({"type": "statements", "items": [_statement(p, p.get("who")) for p in d["positions"]]})
        if d.get("note"):
            blocks.append({"type": "paragraph", "text": d["note"]})

    section("Key risks")
    blocks.append({"type": "statements", "items": [_statement(s_, "Based on " + ", ".join(s_.get("based_on", [])))
                                                   for s_ in _verified_first(a3["risks"])]
                   + [_statement(s_, "From the reports") for s_ in summary if s_.get("topic") == "risks"]})

    comparison = {row["indicator"]: row for row in a1["peer_comparison"]}
    appendix("A", "All indicators")
    blocks.append({"type": "table", "columns": ["Indicator", "Value", "Peer median", "Compared with peers", "Status"],
                   "rows": [[r["name"], _number(r["value"], r["unit"]),
                             _number(comparison[r["indicator"]]["peer_median"], r["unit"]) if r["indicator"] in comparison else "—",
                             _comparison(comparison.get(r["indicator"])), r["status"].replace("_", " ")] for r in indicators["current"]],
                   "notes": [f"Period: {indicators['current_period']}. " + DISCOUNT_NOTE]})

    appendix("B", "Indicators by fiscal year")
    years = list(indicators["history"])
    if years:
        rows = {}
        for fy in years:
            for r in indicators["history"][fy]:
                has_value = r["status"] in ("calculated", "reported_only", "estimated") and r.get("value") is not None
                per_share = r["unit"] not in ("x", "fraction")  # amounts per share: the currency goes in the row name
                name = f"{r['name']} ({r['unit'].split()[0]})" if per_share else r["name"]
                rows.setdefault(name, {})[fy] = ("—" if not has_value else f"{r['value']:,.2f}" if per_share else _number(r["value"], r["unit"]))
        table_rows = [[name] + [cells.get(fy, "—") for fy in years] for name, cells in rows.items()]
        blocks.append({"type": "table", "columns": ["Indicator"] + years, "rows": [row for row in table_rows if any(c != "—" for c in row[1:])],
                       "notes": ["Indicators that need a share price are shown for the current period only."]})
    else:
        blocks.append({"type": "paragraph", "text": "No fiscal-year history is available."})

    appendix("C", "Sources of the indicators")
    blocks.append({"type": "list", "style": "small", "title": "Sources of each indicator", "items": _sources_by_document(indicators["current"])})

    appendix("D", "Not verified")
    blocks.append({"type": "list", "style": "warn-small", "items": [f"{u['agent']}: “{u['text']}” — {' '.join(u['issues'])}"
                                                              for u in a3["unverified_statements"]] or ["Every statement was verified."]})

    appendix("E", "Missing information")
    blocks.append({"type": "list", "style": "small", "items": list(dict.fromkeys(a3["missing_information"])) or ["Nothing missing was recorded."]})

    appendix("F", "Methodology and limitations")
    blocks.append({"type": "list", "style": "small", "items": a3["limitations"]})

    return {"title": title, "blocks": blocks, "comparisons": lines, "exhibits": ex}
