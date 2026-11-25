# Agent 2: analyses the earnings call, keeping management statements, guidance and analyst questions apart, and reviews news since the
# latest results announcement plus older items that are still material. Each news item keeps its publisher, date and link from the
# source, not from the model. Every statement is checked (backend/validation.py); nothing may claim that news moved the share price.
from datetime import date

from backend import prompts, report_reader, validation
from backend.report_reader import Page

AGENT = "Agent 2 – earnings call and news"
KINDS = {"management", "guidance", "analyst"}


def _relabel(statement: dict) -> dict:
    statement["verified"] = not statement["issues"]
    statement["label"] = "verified" if statement["verified"] else "unverified"
    return statement


def read_transcripts(documents: list[dict], as_of: date, notes: list[str]) -> dict:
    read = {}
    for doc in documents:
        if doc.get("kind") != "transcript":
            continue
        if doc.get("publication_date") and doc["publication_date"] > as_of.isoformat():
            notes.append(f"{doc['title']} was published on {doc['publication_date']}, after the analysis date, so it is left out.")
            continue
        if "pages" in doc:
            pages = report_reader.pages_from_texts(doc["pages"])
        else:
            result = report_reader.try_read_document(doc["path"])
            pages = result.pages
            notes += result.notes
        read[doc["doc_id"]] = {"doc": {k: v for k, v in doc.items() if k not in ("pages", "path")}, "pages": pages}
    return read


def analyse_call(company: dict, read: dict, services) -> dict:
    if not read:
        return {"documents": [], "statements": []}
    pages = [{"doc_id": d, "page": p.number, "text": p.text} for d, item in read.items() for p in item["pages"]]
    request = prompts.build("analyse_call", {"ticker": company["ticker"], "company": company["name"], "pages": pages})
    statements = validation.check_statements(services.model.ask(request["task"], request["data"]).get("statements", []), read, [])
    for s in statements:
        if s.get("kind") not in KINDS:
            s["issues"].append(f"Unknown statement type {s.get('kind')!r}; it must be management, guidance or analyst.")
        speaker = s.get("speaker")
        cited = [read[c["doc_id"]]["pages"][c["page"] - 1].text for c in s["citations"] if "doc_id" in c]
        if speaker and not any(speaker in text for text in cited):
            s["issues"].append(f"The speaker '{speaker}' does not appear on the cited page.")
        _relabel(s)
    return {"documents": [item["doc"] for item in read.values()], "statements": statements}


def _news_read(items: list[dict]) -> dict:
    return {i["id"]: {"doc": {"doc_id": i["id"], "kind": "news", "title": i["title"], "url": i["url"], "publisher": i["publisher"],
                              "published": i["published"], "demo": i.get("demo", False)},
                      "pages": [Page(1, f"{i['title']}\n{i.get('summary', '')}", "item")]} for i in items}


def review_news(company: dict, services, as_of: date, since: str | None, notes: list[str]) -> tuple[dict, dict]:
    if getattr(services, "news", None) is None:
        notes.append("News is not available: no news provider is configured.")
        return {"since": since, "included": [], "excluded": []}, {}
    items = []
    for item in services.news.search(company["name"], company["ticker"]):
        if item["published"] > as_of.isoformat():
            notes.append(f"News item '{item['title']}' ({item['published']}) is after the analysis date and is left out.")
        else:
            items.append(item)
    read = _news_read(items)
    if not items:
        notes.append("No news items were found.")
        return {"since": since, "included": [], "excluded": []}, read
    request = prompts.build("review_news", {"ticker": company["ticker"], "company": company["name"], "since": since,
                                            "items": [{k: i.get(k) for k in ("id", "publisher", "published", "title", "summary")} for i in items]})
    by_id = {i["id"]: i for i in items}
    included, excluded, seen = [], [], set()
    for answer in validation.as_list(services.model.ask(request["task"], request["data"]).get("items")):
        if not isinstance(answer, dict):
            notes.append("A news assessment from the model was not in the expected form and was ignored.")
            continue
        item = by_id.get(answer.get("news_id"))
        if item is None:
            notes.append(f"The model referred to a news item that does not exist ({answer.get('news_id')}); it was ignored.")
            continue
        seen.add(item["id"])
        base = {k: item[k] for k in ("id", "publisher", "published", "title", "url")}
        base["recent"] = since is None or item["published"] >= since
        if item.get("demo"):
            base["demo"] = True
        if not answer.get("relevant"):
            excluded.append({**base, "reason": answer.get("reason") or "Judged not relevant to the business."})
            continue
        if not base["recent"] and not answer.get("still_material"):
            excluded.append({**base, "reason": "Published before the latest results announcement and not judged still material."})
            continue
        [check] = validation.check_statements([{"text": answer.get("channel", ""), "citations": [{"doc_id": item["id"], "page": 1}]}], read, [])
        included.append({**base, "channel": check["text"], "citations": check["citations"], "verified": check["verified"],
                         "label": check["label"], "issues": check["issues"]})
    for item in items:
        if item["id"] not in seen:
            excluded.append({k: item[k] for k in ("id", "publisher", "published", "title", "url")} | {"reason": "Not assessed by the model."})
    return {"since": since, "included": included, "excluded": excluded}, read


def run(company: dict, services, as_of: date, context: dict | None = None) -> dict:
    context = context if context is not None else {}
    notes: list[str] = []
    transcripts = read_transcripts(services.documents.find(company["ticker"]), as_of, notes)
    if not transcripts:
        notes.append("No earnings-call transcript was found for this period. A recording can be uploaded and transcribed once a "
                     "speech-to-text service is configured.")
    call = analyse_call(company, transcripts, services)
    news, news_read = review_news(company, services, as_of, context.get("latest_results_date"), notes)
    context.setdefault("read", {}).update(transcripts)
    context["read"].update(news_read)
    return {"agent": AGENT, "call": call, "news": news, "notes": notes}
