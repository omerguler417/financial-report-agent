# DEMO stand-ins for each external service. They read only the fictional data in demo_data.py, label everything as demo, and are used
# only when the user picks demo mode for a whole analysis. Live code never imports them, so they can never act as a fallback for a missing key.
# Step 1 covers market data, news, documents, speech-to-text and translation; text-model task answers are added with the agents (step 4).
from dataclasses import dataclass
from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from backend.demo import demo_data as D
from backend.fetchers.market_data import DailyBar, PriceSeries

NY = ZoneInfo("America/New_York")


class DemoMarketData:
    name, demo = D.MARKET_NAME, True

    def search(self, query: str) -> list[dict]:
        q = query.lower()
        return [{"ticker": t, "name": c["name"], "exchange": "NYSE", "currency": "USD", "demo": True}
                for t, c in D.COMPANIES.items() if q in t.lower() or q in c["name"].lower()]

    def profile(self, ticker: str) -> dict:
        c = D.COMPANIES[ticker]
        return {"ticker": ticker, "name": c["name"], "exchange": "NYSE", "currency": "USD", "industry": c["industry"], "sector": c["sector"],
                "description": f"{c['name']} is a fictional company used only for demonstration.", "demo": True}

    def peers(self, ticker: str) -> list[str]:
        return [t for t in D.COMPANIES if t != ticker] if ticker == D.TARGET else []

    def daily_series(self, ticker: str, start: date, end: date) -> PriceSeries:
        bars = [DailyBar(b["day"], b["close"], b["close"], datetime(b["day"].year, b["day"].month, b["day"].day, 16, tzinfo=NY), b["volume"])
                for b in D.price_bars(ticker, end) if b["day"] >= start]
        return PriceSeries(ticker, "NYSE", "USD", "America/New_York", D.MARKET_NAME, bars)


class DemoNews:
    name, demo = "DEMO news (fictional)", True

    def search(self, company: str, ticker: str, since: str | None = None) -> list[dict]:
        return [i for i in D.news_items(ticker) if since is None or i["published"] >= since]


class DemoDocuments:
    name, demo = D.SOURCE_NAME, True

    def find(self, ticker: str) -> list[dict]:
        return D.documents(ticker)


class DemoModel:
    """Recorded speech-to-text and translation answers in the same shapes the live services return."""

    name, demo = "DEMO recorded responses", True

    def transcribe(self, audio_path, language_hint=None) -> dict:
        return {"language": "turkish", "model": "DEMO recorded transcription", "timestamps": True, "speakers": False,
                "segments": [dict(s) for s in D.TURKISH_SEGMENTS]}

    def translate(self, texts: list[str], source_language: str, target_language: str) -> list[str]:
        return [D.TURKISH_TRANSLATIONS.get(t, f"[demo translation not recorded] {t}") for t in texts]


def demo_ffmpeg(duration: float = 19.0):
    """Stands in for ffprobe/ffmpeg so the demo recording can be processed without FFmpeg installed."""
    def run(cmd, **_kwargs):
        if cmd[0] == "ffprobe":
            return SimpleNamespace(stdout=f"{duration}\n", returncode=0)
        open(cmd[-1], "wb").write(b"demo audio")
        return SimpleNamespace(stdout="", returncode=0)
    return run


@dataclass
class DemoServices:
    market: DemoMarketData
    news: DemoNews
    documents: DemoDocuments
    model: DemoModel
    ffmpeg_run: object
    label: str = D.DEMO_LABEL


def demo_services() -> DemoServices:
    return DemoServices(DemoMarketData(), DemoNews(), DemoDocuments(), DemoModel(), demo_ffmpeg())
