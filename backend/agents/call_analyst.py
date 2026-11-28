# Agent 2: summarises the earnings call into key management points, guidance, and the main analyst questions with a summary of each
# answer. Every sentence is checked (backend/validation.py), including that its speaker appears in the cited turn of the call.
from datetime import date

from backend import prompts, report_reader, validation

AGENT = "Agent 2 – earnings call"
KINDS = {"management", "guidance"}


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
        return {"documents": [], "statements": [], "questions": []}
    pages = [{"doc_id": d, "page": p.number, "text": p.text} for d, item in read.items() for p in item["pages"]]
    request = prompts.build("analyse_call", {"ticker": company["ticker"], "company": company["name"], "pages": pages})
    answer = services.model.ask(request["task"], request["data"])
    statements = validation.check_statements(answer.get("statements", []), read, [])
    for s in statements:
        if s.get("kind") not in KINDS:
            s["issues"].append(f"Unknown statement type {s.get('kind')!r}; it must be management or guidance.")
        _check_speaker(s, s.get("speaker"), read)
    questions = []
    for q in validation.as_list(answer.get("questions")):
        if not isinstance(q, dict):
            continue
        [asked, answered] = validation.check_statements(
            [{"text": q.get("question", ""), "citations": q.get("question_citations")},
             {"text": q.get("answer", ""), "citations": q.get("answer_citations")}], read, [])
        _check_speaker(asked, q.get("analyst"), read)
        _check_speaker(answered, q.get("answered_by"), read)
        questions.append({"analyst": str(q.get("analyst", "")), "answered_by": str(q.get("answered_by", "")), "question": asked, "answer": answered})
    return {"documents": [item["doc"] for item in read.values()], "statements": statements, "questions": questions}


def _speakers(names: str) -> list[str]:
    """'Satya Nadella (Chairman and CEO) and Amy Hood (CFO)' -> both names; 'and' inside brackets is part of a title."""
    parts, current, depth, i = [], "", 0, 0
    while i < len(names):
        depth += names[i] == "("
        depth -= names[i] == ")"
        for sep in (" and ", " & ", ", ", "; "):
            if depth == 0 and names.startswith(sep, i):
                parts.append(current)
                current, i = "", i + len(sep)
                break
        else:
            current += names[i]
            i += 1
    return [p.strip() for p in parts + [current] if p.strip()]


def _check_speaker(statement: dict, speaker, read: dict):
    """Every named speaker must appear in one of the cited turns (or pages) of the call."""
    cited = [read[c["doc_id"]]["pages"][c["page"] - 1].text for c in statement["citations"] if "doc_id" in c]
    missing = [name for name in _speakers(str(speaker or "")) if not any(name in text for text in cited)]
    if missing:
        statement["issues"].append(f"The speaker '{', '.join(missing)}' does not appear in the cited part of the call.")
    _relabel(statement)


def run(company: dict, services, as_of: date, context: dict | None = None) -> dict:
    context = context if context is not None else {}
    notes: list[str] = []
    transcripts = read_transcripts(services.documents.find(company["ticker"]), as_of, notes)
    notes += getattr(services.documents, "notes", [])  # why no call was fetched, when the provider had none or is not set up
    if not transcripts:
        notes.append("No earnings-call transcript was found for this period. A recording can be uploaded and transcribed once a "
                     "speech-to-text service is configured.")
    call = analyse_call(company, transcripts, services)
    context.setdefault("read", {}).update(transcripts)
    return {"agent": AGENT, "call": call, "notes": notes}
