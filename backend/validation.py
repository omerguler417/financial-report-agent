# Checks on everything a text model returns before it is used. A figure must sit on the page it cites, with the same value; a statement
# must cite a real source, every number in it must appear in that source or in the cited Python result, and it must not give a
# recommendation, unbenchmarked valuation verdict or claim about what moved the share price. Figures that fail are rejected with the reason; statements that fail
# are kept but labelled unverified, never silently dropped.
import re

from backend.financials import FIELDS

NUMBER = re.compile(r"(?<![\w.,])([-−])?(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(\s?%)?")  # a minus sign right before a number belongs to it
# CLAUDE.md: "expensive", "cheap" and "fairly priced" are allowed only beside a named benchmark (peers or the company's own history);
# a mispricing claim, a recommendation or a price target is never allowed.
RELATIVE = re.compile(r"\b(cheap|expensive|fairly (?:priced|valued))\b", re.I)
BENCHMARK = re.compile(r"\b(?:relative to|compared (?:with|to)|against|versus|vs\.?)\s+(?:the |its |their )?(?:own )?(?:[\w-]+ ){0,3}?"
                       r"(?:peers?|peer (?:group|median)|history|historical (?:median|average|range)|median|average|past|"
                       r"(?:trading )?range)\b", re.I)
VERDICT = re.compile(r"\b(under-?valued|over-?valued|bargain|should (?:buy|sell|hold)|(?:buy|sell|hold|investment) (?:rating|recommendation|signal)s?"
                     r"|(?:is|are|looks?) a (?:buy|sell|hold)|(?:we|I) recommend|recommend(?:s|ed)? (?:buying|selling|holding)|price target)\b", re.I)
SENTENCE = re.compile(r"(?<=[.!?])\s+")
PRICE_MOVE = re.compile(r"(?<!per )\b(?:shares?|stock|share price)\b[^.]{0,40}?\b(?:fell|rose|dropped|jumped|slumped|surged|declined|climbed|tumbled|soared|rallied)\b"
                        r"|\bsent (?:the )?(?:shares|stock)\b", re.I)


def wording_issues(text: str) -> list[str]:
    """CLAUDE.md: no recommendations or mispricing claims, relative valuation only against a named benchmark, and no claim about
    what moved the share price."""
    issues = []
    if m := VERDICT.search(text):
        issues.append(f"Wording: '{m.group(0)}' is a valuation verdict or recommendation, which the report must not give.")
    for sentence in SENTENCE.split(text):
        if (m := RELATIVE.search(sentence)) and not BENCHMARK.search(sentence):
            issues.append(f"Wording: '{m.group(0)}' is a valuation verdict without a benchmark; say what it is measured against "
                          "(its peers or its own history).")
            break
    if PRICE_MOVE.search(text):
        issues.append("Wording: claims a cause for a share-price move; overlapping timing is not evidence of cause.")
    return issues


ACCESSION = re.compile(r"\b\d{10}-\d{2}-\d{6}\b")  # SEC filing numbers are references, never figures
AGENT_NAME = re.compile(r"\bAgents?\s+\d(?:\s*(?:,|and|&)\s*\d)*\b")  # "Agent 1", "Agents 1 and 2" name a step, not a figure
ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")  # dates such as 2026-11-24 are not figures either


def numbers_in(text: str) -> list[tuple]:
    """(as written, value, decimals, is_percent) for each number, skipping years, labels such as Q3 or FY2025, and filing numbers."""
    out = []
    text = AGENT_NAME.sub(" ", ISO_DATE.sub(" ", ACCESSION.sub(" ", text)))
    for m in NUMBER.finditer(text):
        sign, whole, fraction, percent = m.group(1), m.group(2), m.group(3) or "", bool(m.group(4))
        value = float(whole.replace(",", "") + fraction) * (-1 if sign else 1)
        if not fraction and not percent and "," not in whole and 1900 <= value <= 2100:
            continue
        out.append((m.group(0).strip(), value, len(fraction) - 1 if fraction else 0, percent))
    return out


def _source(read: dict, doc_id: str, page: int, line: str | None = None) -> dict:
    doc = read[doc_id]["doc"]
    source = {"doc_id": doc_id, "title": doc.get("title"), "page": page}
    if line is not None:
        source["line"] = line
    source["url"] = doc.get("url")
    if doc.get("page_unit"):  # a call transcript's sections are speaker turns, not pages
        source["page_unit"] = doc["page_unit"]
    if doc.get("publication_date"):  # reports: when it was published, for "what was known on a date"
        source["published"] = doc["publication_date"]
    return source


def _page_text(read: dict, doc_id, page) -> tuple[str | None, str | None]:
    """The page text, or why the citation cannot be resolved."""
    if doc_id not in read:
        return None, f"document {doc_id} was not read"
    pages = read[doc_id]["pages"]
    if not isinstance(page, int) or not 1 <= page <= len(pages):
        return None, f"page {page} of {doc_id} does not exist"
    return pages[page - 1].text, None


def as_list(items) -> list:
    """A model answer field as a list, whatever shape the model used (one item, a list, or nothing)."""
    if items is None:
        return []
    return items if isinstance(items, list) else [items]


def as_statements(items) -> list[dict]:
    """Statements as objects. A plain sentence (or number) becomes a statement without citations, so it is labelled, never lost."""
    out = []
    for item in as_list(items):
        if isinstance(item, dict):
            out.append(item)
        elif isinstance(item, (str, int, float)) and str(item).strip():
            out.append({"text": str(item)})
    return out


def check_figures(figures: list[dict], read: dict) -> dict:
    """read: {doc_id: {"doc": metadata, "pages": [Page]}}. Returns accepted figures (one per field and period, sources merged) and
    rejected ones with the reason."""
    rejected, groups = [], {}
    for f in as_list(figures):
        if not isinstance(f, dict):
            rejected.append({"value": f, "reason": "the figure was not in the expected form"})
            continue
        value, reason = f.get("value"), None
        if f.get("field") not in FIELDS:
            reason = f"unknown field {f.get('field')!r}"
        elif not f.get("period"):
            reason = "no period given"
        elif not f.get("unit"):
            reason = "no unit given"
        elif not isinstance(value, (int, float)) or isinstance(value, bool):
            reason = "the value is not a number"
        else:
            text, reason = _page_text(read, f.get("doc_id"), f.get("page"))
            if reason is None and (not f.get("line") or f["line"] not in text):
                reason = f"the cited line is not on page {f['page']} of {f['doc_id']}"
            elif reason is None and not any(abs(n[1] - value) < 1e-9 for n in numbers_in(f["line"])):
                reason = "the value does not match the cited line"
        if reason:
            rejected.append({**f, "reason": reason})
        else:
            groups.setdefault((f["field"], f["period"]), []).append(f)
    accepted = []
    for (field, period), items in groups.items():
        if len({(round(i["value"], 9), i["unit"]) for i in items}) > 1:
            rejected += [{**i, "reason": "conflicting values for the same figure and period; not used until it is clear which document takes precedence"}
                         for i in items]
            continue
        sources = []
        for i in items:
            s = _source(read, i["doc_id"], i["page"], i["line"])
            if s not in sources:
                sources.append(s)
        accepted.append({"field": field, "period": period, "value": items[0]["value"], "unit": items[0]["unit"], "sources": sources})
    return {"accepted": accepted, "rejected": rejected}


def _result_matches(number: tuple, result: dict) -> bool:
    _, value, decimals, percent = number
    if result.get("value") is None:
        return False
    shown = result["value"] * 100 if result.get("unit") == "fraction" else result["value"]
    return abs(round(shown, decimals) - value) < 1e-9 and (percent or result.get("unit") != "fraction")


def _calculated_figure(number: tuple, results: list[dict], current_period: str | None) -> list[dict]:
    """The current-period or peer-median results a number exactly is, as Python formats them (two decimals). A model that quotes a
    calculated figure but forgets its citation then still cites the right source; a rounded or older figure is not matched."""
    if number[2] != 2:
        return []
    periods = {current_period, "peer median"} if current_period else None

    def this_analysis(r):  # the current results (whatever their period label), peer medians and own historical medians
        return (periods is None or r.get("current") or r.get("period") in periods
                or str(r.get("period", "")).startswith("year ends"))
    return [r for r in results if this_analysis(r) and _result_matches(number, r)]


def _strip_references(text: str, read: dict) -> str:
    """Remove document references the model wrote into a sentence, such as "[0001193125-26-323660]", "(10-K, page 35)" or "[1]": the
    citations already carry them, and their digits are not figures."""
    ids = [re.escape(d) for d in read if len(d) > 6]
    reference = rf"(?:{'|'.join(ids)}|\d{{10}}-\d{{2}}-\d{{6}})" if ids else r"\d{10}-\d{2}-\d{6}"
    text = re.sub(rf"\s*[\[(][^\])]*{reference}[^\])]*[\])]", "", text)
    text = re.sub(r"\s*\[\s*S?\d{1,3}(?:\s*[,;–-]\s*S?\d{1,3})*\s*\]", "", text)  # footnote markers such as [1], [2, 3] or [S4]
    text = re.sub(r"\s{2,}", " ", text)
    return re.sub(r"\s+([.,;:])", r"\1", text).strip()


def _find_result(citation: dict, results: list[dict], current_period: str | None) -> dict | None:
    """A cited calculated result, by its id or its name. Without a period, the current period is used; a wrong period finds nothing."""
    ref = str(citation.get("indicator", "")).strip().lower()
    matches = [r for r in results if r["indicator"].lower() == ref or str(r.get("name", "")).strip().lower() == ref]
    period = citation.get("period")
    if period:
        exact = next((r for r in matches if r["period"] == period), None)
        starts = [r for r in matches if str(r["period"]).startswith(f"{period} vs ")]  # "FY2026" for "FY2026 vs FY2025"
        one = len({r["period"] for r in starts}) == 1  # the same result may be listed twice (current and history)
        if exact or (starts and one):
            return exact or next((r for r in starts if r.get("current")), starts[0])
        within = {r["period"]: r for r in matches if r.get("current") and re.search(rf"(?<![\w]){re.escape(period)}(?![\w])", str(r["period"]))}
        return next(iter(within.values())) if len(within) == 1 else None  # "FY2026" for the current "FY2021–FY2026"
    current = [r for r in matches if r["period"] == current_period] if current_period else []
    if current:
        return current[0]
    flagged = {r["period"]: r for r in matches if r.get("current")}  # the current result under its own label ("FY2026 vs FY2025")
    if len(flagged) == 1:
        return next(iter(flagged.values()))
    return matches[0] if len(matches) == 1 else None


WRAPPED = re.compile(r"""['"]indicator['"]\s*:\s*['"]([^'"]+)['"](?:\s*,\s*['"]period['"]\s*:\s*['"]([^'"]+)['"])?""")


def _unwrapped(c):
    """A citation the model wrote as text inside the indicator field ("{'indicator': 'pe', 'period': 'FY2026'}") as an object."""
    if isinstance(c, dict) and isinstance(c.get("indicator"), dict):  # the citation object nested inside the indicator field
        inner = c["indicator"]
        return {"indicator": str(inner.get("indicator", "")), **({"period": inner["period"]} if inner.get("period") else {})}
    if isinstance(c, dict) and isinstance(c.get("indicator"), str) and (m := WRAPPED.search(c["indicator"])):
        return {"indicator": m.group(1), **({"period": m.group(2)} if m.group(2) else {})}
    return c


def _blank(c) -> bool:
    """A placeholder copied from the answer format: no document or indicator, or a document's page left at the template's 0."""
    if not isinstance(c, dict) or str(c.get("indicator") or "").strip():
        return False
    return not str(c.get("doc_id") or "").strip() or ("page" in c and c["page"] in (0, "0") and not c.get("section"))


UP = re.compile(r"\b(?:above|higher|exceeds?|exceeding|premium|richer|expensive|ahead of|outpaces?)\b", re.I)
DOWN = re.compile(r"\b(?:below|lower|discount|cheap|cheaper|trails?|trailing|behind)\b", re.I)


def _shown(r: dict) -> str:
    return f"{r['value'] * 100:,.2f}%" if r.get("unit") == "fraction" else f"{r['value']:,.2f}{'x' if r.get('unit') == 'x' else ''}"


CLAUSE = re.compile(r",\s+|;\s+|\s+(?:and|while|whereas|but)\s+")
CONTINUES = re.compile(r"\s*(?:including|with|such as|led by|notably|e\.g\.|for example|namely)\b", re.I)


def _multiple_name(indicator: str) -> str | None:
    from backend.indicators import HIST_NAMES  # the multiples compared with their own history: "P/E", "EV/EBITDA", ...
    return HIST_NAMES.get(indicator.removesuffix("_vs_hist")) if indicator.endswith("_vs_hist") else None


def _names(name: str, text: str) -> bool:  # "EV/EBIT" is not named by "EV/EBITDA"
    return re.search(re.escape(name) + r"(?![A-Za-z])", text) is not None


def _clauses(text: str) -> list[str]:
    """Clauses of each sentence; a bare figure ("… by 30.06% and 13.40%") stays with the clause before it."""
    out = []
    for sentence in SENTENCE.split(text):
        for i, c in enumerate(CLAUSE.split(sentence)):
            if i and not re.search(r"[A-Za-z]{3,}", c):
                out[-1] = f"{out[-1]} and {c}"
            else:
                out.append(c)
    return out


def _own_difference(number: tuple, text: str, results: list[dict]) -> list[dict]:
    """"P/E is 30.06% below its historical median" for a stored -30.06%: the company's own difference from its history, matched
    only when the same clause names the multiple and says below. The peers' differences are never matched this way."""
    written, value, decimals, percent = number
    if value <= 0 or not percent:
        return []
    out = []
    for r in results:
        name = _multiple_name(r["indicator"])
        if not name or r.get("period") == "peer median" or r.get("value") is None or r["value"] >= 0:
            continue
        def names_it(clause):  # the clause names the multiple, or speaks of "those multiples" named elsewhere in its sentence
            sentence = next((x for x in SENTENCE.split(text) if clause in x), "")
            return _names(name, clause) or (re.search(r"\b(?:multiples?|medians?)\b", clause, re.I) and _names(name, sentence))
        if abs(round(-r["value"] * 100, decimals) - value) < 1e-9 and any(
                written in c and names_it(c) and DOWN.search(c) and not UP.search(c) for c in _clauses(text)):
            out.append(r)
    return out


def _history_direction(text: str, results: list[dict]) -> list[str]:
    """A stated difference from the company's own historical median must point the right way ("below … by 15.91%" for +15.91%)."""
    issues = []
    for clause in _clauses(text):
        up, down = bool(UP.search(clause)), bool(DOWN.search(clause))
        if up == down:
            continue
        numbers = [n for n in numbers_in(clause) if n[2] == 2 and n[3]]
        for r in results:
            name = _multiple_name(r["indicator"])
            if not name or not _names(name, clause) or r.get("period") == "peer median" or not r.get("value"):
                continue
            if any(abs(round(abs(r["value"]) * 100, 2) - abs(n[1])) < 1e-9 for n in numbers):
                actual = "above" if r["value"] > 0 else "below"
                if (actual == "above") != up:
                    issues.append(f"Direction: {name} is {abs(r['value']) * 100:,.2f}% {actual} its own historical median, but the "
                                  f"sentence says {'above' if up else 'below'}.")
    return issues


def direction_issues(text: str, results: list[dict]) -> list[str]:
    """A clause that quotes a figure and its peer median or own historical median must not say "above" when the figure is below
    (or the reverse). Read clause by clause: a clause without a direction word takes the previous clause's ("ratios above peer
    medians, including P/E at 28.64x versus 36.03x"); a clause with both directions is left alone."""
    issues = []
    for sentence in SENTENCE.split(text):
        previous = None
        for clause in CLAUSE.split(sentence):
            up, down = bool(UP.search(clause)), bool(DOWN.search(clause))
            if up and down:
                previous = None
                continue
            if up or down:
                previous = "above" if up else "below"
            elif not CONTINUES.match(clause):  # only "including …", "with …", "such as …" carry on the previous clause's direction
                previous = None
            if previous is None:
                continue
            numbers = [n for n in numbers_in(clause) if n[2] == 2]  # figures as Python shows them (25.66x, 18.80%), not counts

            def quoted(r):
                return r.get("value") is not None and any(_result_matches(n, r) for n in numbers)
            for r in results:
                if r.get("period") == "peer median" or r["indicator"].endswith("_hist_median") or not quoted(r):
                    continue
                for b in results:
                    is_benchmark = ((b["indicator"] == r["indicator"] and b.get("period") == "peer median")
                                    or b["indicator"] == f"{r['indicator']}_hist_median")
                    if not is_benchmark or not quoted(b) or _shown(r) == _shown(b):
                        continue
                    actual = "above" if r["value"] > b["value"] else "below"
                    if actual != previous:
                        what = "the peer median" if b.get("period") == "peer median" else "its own historical median"
                        issue = (f"Direction: {r.get('name') or r['indicator']} of {_shown(r)} is {actual} {what} of {_shown(b)}, but the "
                                 f"sentence says {previous}.")
                        if issue not in issues:
                            issues.append(issue)
    return issues + [i for i in _history_direction(text, results) if i not in issues]


def _peer_history_issues(text: str, results: list[dict]) -> list[str]:
    """The peers' median of their own historical medians must not be presented as the company's own ("its historical median of
    29.33x"). Read clause by clause; a clause that names the peers, or does not speak of the company's own, is left alone."""
    issues = []
    for clause in _clauses(text):
        if re.search(r"\bpeer", clause, re.I) or not re.search(r"\b(?:its|own|the company'?s?)\b", clause, re.I):
            continue
        for n in (n for n in numbers_in(clause) if n[2] == 2):
            peers = [r for r in results if r["indicator"].endswith("_hist_median") and r.get("period") == "peer median" and _result_matches(n, r)]
            own = [r for r in results if r.get("period") != "peer median" and _result_matches(n, r)]
            if peers and not own:
                issues.append(f"The figure {n[0]} is the peers' median of their own historical medians, not the company's; the sentence "
                              "does not say it is the peers'.")
    return issues


def check_statements(statements: list[dict], read: dict, results: list[dict], current_period: str | None = None) -> list[dict]:
    """results: calculated indicator results as dicts ({indicator, period, value, unit, ...}); current_period: the analysis's
    current period, used when a citation of a result gives none."""
    checked = []
    for s in as_statements(statements):
        s = {**s, "text": _strip_references(str(s.get("text", "")), read)}
        issues, texts, cited_results, citations = [], [], [], []
        known = {r["indicator"] for r in results}
        given = [_unwrapped(c) for c in as_list(s.get("citations"))]
        given = [({"indicator": c["doc_id"], **({"period": c["period"]} if c.get("period") else {})}  # an indicator written as a document id
                  if isinstance(c, dict) and "indicator" not in c and c.get("doc_id") not in read and c.get("doc_id") in known else c)
                 for c in given]
        given = [c for c in given if not _blank(c)]  # an empty placeholder copied from the answer format is no citation
        for c in given:
            if not isinstance(c, dict):
                issues.append(f"A citation was not in the expected form ({str(c)[:40]}).")
                continue
            if "indicator" in c:
                result = _find_result(c, results, current_period)
                if result is None:
                    issues.append(f"Cited result {c['indicator']} for {c.get('period') or 'the current period'} does not exist.")
                    continue
                cited_results.append(result)
                citations.append({"indicator": result["indicator"], "period": result["period"], "name": result.get("name")})
            else:
                text, problem = _page_text(read, c.get("doc_id"), c.get("page"))
                if problem:
                    issues.append(f"Citation {c.get('doc_id')} p. {c.get('page')} does not exist in the documents read ({problem}).")
                    continue
                texts.append(text)
                citations.append(_source(read, c["doc_id"], c["page"]))
        if not given:
            issues.append("No source cited.")
        for number in numbers_in(s.get("text", "")):
            in_text = any(abs(n[1] - number[1]) < 1e-9 for t in texts for n in numbers_in(t))
            if in_text or any(_result_matches(number, r) for r in cited_results):
                continue
            found = _calculated_figure(number, results, current_period) or _own_difference(number, s.get("text", ""), results)
            if found:  # exactly a figure Python calculated in this analysis: sourced to that result
                cited_results += found
                citations += [{"indicator": r["indicator"], "period": r["period"], "name": r.get("name")} for r in found
                              if {"indicator": r["indicator"], "period": r["period"], "name": r.get("name")} not in citations]
                continue
            issues.append(f"The number {number[0]} was not found in the cited source or the cited calculated result.")
        issues += wording_issues(s.get("text", "")) + wording_issues(str(s.get("title") or ""))  # a risk's short title too
        issues += direction_issues(s.get("text", ""), results)
        issues += _peer_history_issues(s.get("text", ""), results)
        extra = {k: v for k, v in s.items() if k not in ("text", "citations", "verified", "label", "issues")}
        checked.append({**extra, "text": str(s.get("text", "")), "citations": citations, "verified": not issues,
                        "label": "verified" if not issues else "unverified", "issues": issues})
    return checked
