# Checks on everything a text model returns before it is used. A figure must sit on the page it cites, with the same value; a statement
# must cite a real source, every number in it must appear in that source or in the cited Python result, and it must not give a
# valuation verdict or claim that news moved the share price. Figures that fail are rejected with the reason; statements that fail
# are kept but labelled unverified, never silently dropped.
import re

from backend.financials import FIELDS

NUMBER = re.compile(r"(?<![\w.,])(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(\s?%)?")
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


def numbers_in(text: str) -> list[tuple]:
    """(as written, value, decimals, is_percent) for each number, skipping years and labels such as Q3 or FY2025."""
    out = []
    for m in NUMBER.finditer(text):
        whole, fraction, percent = m.group(1), m.group(2) or "", bool(m.group(3))
        value = float(whole.replace(",", "") + fraction)
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


def check_figures(figures: list[dict], read: dict) -> dict:
    """read: {doc_id: {"doc": metadata, "pages": [Page]}}. Returns accepted figures (one per field and period, sources merged) and
    rejected ones with the reason."""
    rejected, groups = [], {}
    for f in figures:
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


def check_statements(statements: list[dict], read: dict, results: list[dict]) -> list[dict]:
    """results: calculated indicator results as dicts ({indicator, period, value, unit, ...})."""
    by_key = {(r["indicator"], r["period"]): r for r in results}
    checked = []
    for s in statements:
        issues, texts, cited_results, citations = [], [], [], []
        for c in s.get("citations") or []:
            if "indicator" in c:
                result = by_key.get((c["indicator"], c.get("period")))
                if result is None:
                    issues.append(f"Cited result {c['indicator']} for {c.get('period')} does not exist.")
                    continue
                cited_results.append(result)
                citations.append({"indicator": c["indicator"], "period": c.get("period"), "name": result.get("name")})
            else:
                text, problem = _page_text(read, c.get("doc_id"), c.get("page"))
                if problem:
                    issues.append(f"Citation {c.get('doc_id')} p. {c.get('page')} does not exist in the documents read ({problem}).")
                    continue
                texts.append(text)
                citations.append(_source(read, c["doc_id"], c["page"]))
        if not s.get("citations"):
            issues.append("No source cited.")
        for number in numbers_in(s.get("text", "")):
            in_text = any(abs(n[1] - number[1]) < 1e-9 for t in texts for n in numbers_in(t))
            if not in_text and not any(_result_matches(number, r) for r in cited_results):
                issues.append(f"The number {number[0]} was not found in the cited source or the cited calculated result.")
        issues += wording_issues(s.get("text", ""))
        extra = {k: v for k, v in s.items() if k not in ("text", "citations", "verified", "label", "issues")}
        checked.append({**extra, "text": s.get("text", ""), "citations": citations, "verified": not issues,
                        "label": "verified" if not issues else "unverified", "issues": issues})
    return checked
