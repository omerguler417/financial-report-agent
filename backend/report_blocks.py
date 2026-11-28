# Turns a finished analysis report into an ordered list of simple display blocks (heading, paragraph, statements, table, list).
# The website draws these now; the PDF and Word files (step 5b) will draw the same blocks, so all three show the same content.
# Numbers are only formatted for display here; nothing is calculated.

import re

SECTIONS = ["Executive summary", "Your questions", "Financial summary", "Trading comparables", "Historical valuation", "Financial analysis",
            "Business overview and outlook", "Earnings call highlights", "Where the sources disagree", "Key risks", "Valuation summary"]
TOPICS = [("business", "Business"), ("results", "Results"), ("outlook", "Outlook")]
SUMMARY_GROUPS = ["Valuation", "Profitability", "Debt and liquidity", "Cash flow and dividends", "Growth"]
REPORT_SOURCE = "Source: Company filings, Verity."
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


MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
FILING = re.compile(r"^(10-K|10-Q|20-F|40-F|6-K|8-K)\b.*?period ended (\d{4})-(\d{2})-\d{2}")
CALL = re.compile(r"^Earnings call transcript, \S+ fiscal (\d{4}) (Q[1-4])")


def _short_title(title: str) -> str:
    """A document's short name for footnotes: "10-Q, quarter ended Sep 2026", "Q1 FY2027 earnings call"; the full title is in
    Appendix C."""
    if m := FILING.match(title or ""):
        form, year, month = m.groups()
        kind = "quarter ended" if form == "10-Q" else "fiscal year ended" if form in ("10-K", "20-F", "40-F") else "period ended"
        return f"{form}, {kind} {MONTHS[int(month) - 1]} {year}"
    if m := CALL.match(title or ""):
        return f"{m.group(2)} FY{m.group(1)} earnings call"
    return title


def _cite(c: dict) -> dict:
    if "indicator" in c:
        return {"text": f"Calculated: {c.get('name') or c['indicator']} ({c.get('period')})", "url": None,
                "calc": [c.get("name") or c["indicator"], c.get("period")]}
    if c.get("publisher"):
        return {"text": f"{c['publisher']}, {c.get('published', '')}".rstrip(", "), "url": _link(c.get("url"))}
    if c.get("page") is None and c.get("section"):
        return {"text": f"{c.get('title') or c.get('doc_id')}, {c['section']} ({c.get('tag', '')})", "url": _link(c.get("url"))}
    unit = "turn" if c.get("page_unit") == "turn" else "p."
    title = c.get("title") or c.get("doc_id")
    return {"text": f"{title}, {unit} {c.get('page')}", "note": f"{_short_title(title)}, {unit} {c.get('page')}", "url": _link(c.get("url"))}


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


def _footnotes(blocks: list[dict]) -> list[dict]:
    """Research-note citations: each point and commentary paragraph gets footnote numbers, and each section ends with one short list
    of its sources, numbered from 1. A source cited by several points gets one number; the calculated results a section cites share
    one note naming each indicator by period, pointing to the appendices for their inputs and sources."""
    out: list[dict] = []
    numbers: dict = {}
    notes: list[dict] = []
    calculated: dict = {}

    def flush():
        if not notes:
            return
        for note in notes:
            if note.get("calc"):
                periods = [p for p in calculated if p != "peer median"] + (["peer medians"] if "peer median" in calculated else [])
                note["text"] = (f"Company filings and market prices, {', '.join(periods)}; "
                                "calculations in Appendix A, sources in Appendix C.")
                note.pop("calc")
        out.append({"type": "footnotes", "items": notes[:]})
        numbers.clear(), notes.clear(), calculated.clear()

    def number(source: dict) -> int:
        if source.get("calc"):
            name, period = source["calc"]
            names = calculated.setdefault(period, [])
            if name not in names:
                names.append(name)
            key = "calc"
        else:
            key = (source["text"], source.get("url"))
        if key not in numbers:
            numbers[key] = len(notes) + 1
            notes.append({"number": numbers[key], "text": source.get("note") or source["text"], "url": source.get("url"), "calc": key == "calc"})
        return numbers[key]

    for b in blocks:
        if b["type"] == "heading" and b["level"] == 2:
            flush()
        if b["type"] == "statements":
            for item in b["items"]:
                item["notes"] = sorted({number(src) for src in item["sources"]})
        elif b["type"] == "commentary":
            b["notes"] = sorted({number(src) for src in b["sources"]})
        out.append(b)
    flush()
    return out


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


def _written(commentary: dict | None, lines: list[dict]) -> list[dict]:
    """A section's commentary as written by Agent 3 (headline and paragraph, verified sentences only; unverified ones are listed in
    Appendix D), or, when there is none, the Python comparison lines."""
    if commentary:
        headline = commentary.get("headline")
        sentences = [s for s in commentary.get("paragraph", []) if s.get("verified")]
        if sentences:
            return [_commentary_block(sentences, headline["text"] if headline and headline.get("verified") else None)]
    return _commentary(lines)


def _commentary_block(sentences: list[dict], headline: str | None = None) -> dict:
    sources = []
    for s in sentences:
        sources += [c for c in (_cite(x) for x in s.get("citations", [])) if c not in sources]
    return {"type": "commentary", "headline": headline, "text": " ".join(s["text"] for s in sentences), "sources": sources}


def _valuation_section(valuation: dict, written: list[dict]) -> list[dict]:
    """The end-of-report summary: Python decides each label (±15% band), Agent 3 explains it, and the note says what it is not."""
    out = [{"type": "paragraph", "style": "lead", "text": valuation["overall"]}]
    if valuation["parts"]:
        rows = {}
        for part in valuation["parts"]:
            for r in part["rows"]:
                row = rows.setdefault(r["name"], {"current": r["value"]})
                row[part["benchmark"]] = (r["benchmark"], r["difference"])
        out.append({"type": "table", "columns": ["Multiple", "Current", "Peer median", "Against peers", "Own median", "Against own history"],
                    "rows": [[name, row["current"], *row.get("peers", ("—", "—")), *row.get("own history", ("—", "—"))]
                             for name, row in rows.items()],
                    "notes": [f"Within ±{valuation['band'] * 100:.0f}% of the benchmark counts as in line. Negative multiples are not compared."]})
        out += [{"type": "paragraph", "text": part["text"]} for part in valuation["parts"]]
    verified = [s for s in written if s.get("verified")]
    if verified:
        out.append(_commentary_block(verified))
    out.append({"type": "paragraph", "style": "note", "text": valuation["note"]})
    return out


def build(report: dict) -> dict:
    """The report in the order of a bank's company report: summary and key data, numbered exhibits, analysis, commentary, risks, and
    appendices. It describes and compares; it gives no rating, target or recommendation."""
    from backend import comparisons, exhibits
    company, a1, a2, a3 = report["company"], report["agent1"], report["agent2"], report["agent3"]
    indicators = a1["indicators"]
    lines, ex = comparisons.build(report), exhibits.build(report)
    groups = {g["group"]: g["lines"] for g in lines["groups"]}
    written = (a3.get("commentary") or {}).get("sections", {})  # older reports have no commentary: their Python lines are shown
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
    price_source = f"{', '.join(price_sources)}, " if price_sources else ""  # the share-price provider, named as a bank's note does

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
    blocks.append({"type": "statements", "items": [_statement(s_) for s_ in _verified_first(a3["overview"])]})

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
          f"Source: Company filings, {price_source}Verity.")
    if peers["peers"]:
        blocks.append({"type": "paragraph", "text": "Peers: " + "; ".join(f"{p['name']} ({p['label']})" for p in peers["peers"]) + "."})
    for e in peers.get("excluded", []):
        blocks.append({"type": "paragraph", "text": f"Not used as a peer: {e['ticker']}. {e['reason']}"})

    section("Historical valuation")
    if ex["historical"]["rows"]:
        table("Valuation against own history and peers' history", ex["historical"],
              f"Source: Company filings, {price_source}Verity; multiples at past fiscal year ends.")
    if groups.get("Historical comparison"):
        blocks += _written(written.get("Historical comparison"), groups["Historical comparison"])

    section("Financial analysis")
    for group, group_lines in groups.items():
        if group == "Historical comparison":
            continue
        blocks.append({"type": "heading", "level": 3, "text": group})
        blocks += _written(written.get(group), group_lines)

    section("Business overview and outlook")
    summary = a1["summary"]
    known = [key for key, _ in TOPICS] + ["risks"]
    for key, heading in TOPICS + [("other", "Other")]:
        chosen = [s_ for s_ in summary if (s_.get("topic") not in known if key == "other" else s_.get("topic") == key)]
        if chosen:
            blocks.append({"type": "heading", "level": 3, "text": heading})
            if key == "results":  # results come grouped by the period they cover, the period named once above its group
                periods = list(dict.fromkeys(s_.get("period") or "" for s_ in chosen))
                for period in periods:
                    if period:
                        blocks.append({"type": "paragraph", "style": "lead", "text": period})
                    blocks.append({"type": "statements", "items": [_statement(s_) for s_ in chosen if (s_.get("period") or "") == period]})
            else:
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
    real = [d for d in a3["disagreements"] if not d.get("note")]  # reports saved earlier kept same-source items with a note
    if not real:
        blocks.append({"type": "paragraph", "text": "No disagreements were identified."})
    for d in real:
        blocks.append({"type": "heading", "level": 3, "text": d["topic"]})
        blocks.append({"type": "statements", "items": [_statement(p, p.get("who")) for p in d["positions"]]})

    section("Key risks")
    blocks.append({"type": "statements", "items": [_statement(s_, s_.get("title") or None) for s_ in _verified_first(a3["risks"])]
                   + [_statement(s_, s_.get("title") or None) for s_ in summary if s_.get("topic") == "risks"]})

    section("Valuation summary")
    blocks += _valuation_section(lines["valuation"], (a3.get("commentary") or {}).get("valuation", []))

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
    blocks.append({"type": "list", "style": "warn-small", "items": [f"“{u['text']}” — {' '.join(u['issues'])}"
                                                              for u in a3["unverified_statements"]] or ["Every statement was verified."]})

    appendix("E", "Missing information")
    blocks.append({"type": "list", "style": "small", "items": list(dict.fromkeys(a3["missing_information"])) or ["Nothing missing was recorded."]})

    appendix("F", "Methodology and limitations")
    blocks.append({"type": "list", "style": "small", "items": a3["limitations"]})

    return {"title": title, "blocks": _footnotes(blocks), "comparisons": lines, "exhibits": ex}
