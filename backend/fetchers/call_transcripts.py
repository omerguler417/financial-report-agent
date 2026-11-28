# Earnings-call transcripts from a provider's API (Alpha Vantage, decided 27 November 2026; its robots.txt does not exist, so nothing
# is disallowed). One request per analysis, through PoliteClient. Each speaker turn becomes one citable section ("turn 2"); the
# provider's own sentiment score is not used, because it cannot be checked. The key goes in the request only (the API requires it as
# a parameter) and is removed from every message and never stored with the document.
from backend import services
from backend.config import Settings
from backend.fetchers.http_client import AccessDenied, FetchFailed, PoliteClient


class CallTranscriptUnavailable(Exception):
    """The provider has no transcript for the quarter, refused the request or its limit was reached; the message says which."""


class AlphaVantageTranscripts:
    name = "Alpha Vantage"

    def __init__(self, settings: Settings, client: PoliteClient):
        self.key = settings.call_transcript_api_key
        self.base_url = (settings.call_transcript_base_url or "https://www.alphavantage.co").rstrip("/")
        self.client = client

    def _clean(self, text) -> str:
        return str(text).replace(self.key, "***") if self.key else str(text)

    def fetch(self, ticker: str, quarter: str) -> dict:
        """The call for one fiscal quarter ("2027Q1") as a transcript document whose pages are the speaker turns."""
        try:
            body = self.client.get(f"{self.base_url}/query", params={"function": "EARNINGS_CALL_TRANSCRIPT", "symbol": ticker,
                                                                      "quarter": quarter, "apikey": self.key}).json()
        except (FetchFailed, AccessDenied, ValueError) as exc:
            raise CallTranscriptUnavailable(f"the request failed: {self._clean(exc)}") from None
        for field in ("Information", "Note", "Error Message"):  # limits and errors come back as a message with HTTP 200
            if field in body:
                raise CallTranscriptUnavailable(self._clean(body[field]))
        turns = [t for t in body.get("transcript") or [] if str(t.get("content", "")).strip()]
        if not turns:
            raise CallTranscriptUnavailable(f"it has no transcript for {ticker} {quarter}")
        pages = []
        for i, turn in enumerate(turns, 1):
            who = str(turn.get("speaker") or "Unknown speaker")
            title = str(turn.get("title") or "").strip()
            pages.append(f"Turn {i} of {len(turns)} · {who}{f' ({title})' if title and title != who else ''}\n{turn['content'].strip()}")
        year, part = quarter[:4], quarter[4:]
        return {"doc_id": f"alphavantage-{ticker}-{quarter}", "kind": "transcript", "pages": pages, "page_unit": "turn",
                "title": f"Earnings call transcript, {ticker} fiscal {year} {part} (Alpha Vantage)", "period": quarter,
                "publication_date": None, "url": None, "source_name": self.name, "origin": "provider"}


ADAPTERS = {"alpha_vantage": AlphaVantageTranscripts}


def get_provider(settings: Settings, client: PoliteClient):
    """The configured transcript provider, or a setup message (HTTP 424) when it is not configured."""
    services.require(settings, "call_transcripts")
    return ADAPTERS[settings.call_transcript_provider](settings, client)
