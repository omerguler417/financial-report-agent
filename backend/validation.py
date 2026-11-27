# Checks on everything a text model returns before it is used. A figure must sit on the page it cites, with the same value; a statement
# must cite a real source, every number in it must appear in that source or in the cited Python result, and it must not give a
# valuation verdict or claim that news moved the share price. Figures that fail are rejected with the reason; statements that fail
# are kept but labelled unverified, never silently dropped.
import re

from backend.financials import FIELDS

NUMBER = re.compile(r"(?<![\w.,])([-−])?(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(\s?%)?")  # a minus sign right before a number belongs to it
VERDICT = re.compile(r"\b(under-?valued|over-?valued|cheap|expensive|bargain|should (?:buy|sell)|(?:buy|sell|hold) (?:rating|recommendation|signal)"
                     r"|(?:is|are|looks?) a (?:buy|sell))\b", re.I)
PRICE_MOVE = re.compile(r"\b(?:shares?|stock|share price)\b[^.]{0,40}?\b(?:fell|rose|dropped|jumped|slumped|surged|declined|climbed|tumbled|soared|rallied)\b"
                        r"|\bsent (?:the )?(?:shares|stock)\b", re.I)


def wording_issues(text: str) -> list[str]:
    """CLAUDE.md: no valuation verdicts or recommendations, and no claim that news moved the share price."""
    issues = []
    if m := VERDICT.search(text):
        issues.append(f"Wording: '{m.group(0)}' is a valuation verdict or recommendation, which the report must not give.")
    if PRICE_MOVE.search(text):
        issues.append("Wording: links news to a share-price move; overlapping timing is not evidence of cause.")
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
    for key in ("publisher", "published"):  # news: publisher + date + link
        if doc.get(key):
            source[key] = doc[key]
    if doc.get("publication_date"):  # reports: when it was published, for "what was known on a date"
        source["published"] = doc["publication_date"]
    return {**source, "demo": True} if doc.get("demo") else source


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
        return next((r for r in matches if r["period"] == period), None)
    current = [r for r in matches if r["period"] == current_period] if current_period else []
    if current:
        return current[0]
    return matches[0] if len(matches) == 1 else None


def _blank(c) -> bool:
    return isinstance(c, dict) and not str(c.get("doc_id") or "").strip() and not str(c.get("indicator") or "").strip() \
        and not str(c.get("news_id") or "").strip()


def check_statements(statements: list[dict], read: dict, results: list[dict], current_period: str | None = None) -> list[dict]:
    """results: calculated indicator results as dicts ({indicator, period, value, unit, ...}); current_period: the analysis's
    current period, used when a citation of a result gives none."""
    checked = []
    for s in as_statements(statements):
        s = {**s, "text": _strip_references(str(s.get("text", "")), read)}
        issues, texts, cited_results, citations = [], [], [], []
        given = [c for c in as_list(s.get("citations")) if not _blank(c)]  # an empty placeholder copied from the answer format is no citation
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
            if not in_text and not any(_result_matches(number, r) for r in cited_results):
                issues.append(f"The number {number[0]} was not found in the cited source or the cited calculated result.")
        issues += wording_issues(s.get("text", ""))
        extra = {k: v for k, v in s.items() if k not in ("text", "citations", "verified", "label", "issues")}
        checked.append({**extra, "text": str(s.get("text", "")), "citations": citations, "verified": not issues,
                        "label": "verified" if not issues else "unverified", "issues": issues})
    return checked
