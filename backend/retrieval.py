# Finds the pages most relevant to a question so only those are sent to the model, each keeping its document and page reference.
# Keyword ranking (BM25) in plain Python: no external service, no key, same result every time.
import math
import re
from collections import Counter
from dataclasses import dataclass

TOKEN = re.compile(r"[\w%$€£.,-]+", re.UNICODE)
STOPWORDS = {"the", "a", "an", "of", "and", "or", "in", "to", "for", "on", "by", "is", "are", "was", "were", "with", "as", "at", "from"}


@dataclass
class Passage:
    doc_id: str
    page: int
    label: str
    text: str
    score: float


def tokenize(text: str) -> list[str]:
    return [t for t in (w.strip(".,-").lower() for w in TOKEN.findall(text)) if t and t not in STOPWORDS]


def retrieve(documents: dict, query: str, k: int = 8, k1: float = 1.5, b: float = 0.75) -> list[Passage]:
    """documents: {doc_id: [Page, ...]}. Returns up to k pages that match at least one query word, best first."""
    flat = [(doc_id, page) for doc_id, pages in documents.items() for page in pages]
    if not flat:
        return []
    counts = [Counter(tokenize(page.text)) for _, page in flat]
    lengths = [sum(c.values()) or 1 for c in counts]
    average = sum(lengths) / len(lengths)
    terms = set(tokenize(query))
    frequency = {t: sum(1 for c in counts if t in c) for t in terms}
    n = len(flat)
    scored = []
    for (doc_id, page), c, length in zip(flat, counts, lengths):
        score = 0.0
        for t in terms:
            if c[t]:
                idf = math.log(1 + (n - frequency[t] + 0.5) / (frequency[t] + 0.5))
                score += idf * c[t] * (k1 + 1) / (c[t] + k1 * (1 - b + b * length / average))
        if score > 0:
            scored.append(Passage(doc_id, page.number, page.label, page.text, score))
    return sorted(scored, key=lambda p: (-p.score, p.doc_id, p.page))[:k]
