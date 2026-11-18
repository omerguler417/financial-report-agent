# Which external services exist, what each needs, and whether it is configured. No provider is chosen; this drives the setup messages and the status list on the page.
import shutil

from backend.config import Settings
from backend.errors import ProviderNotConfigured

AWAITING = "awaiting_configuration"   # required settings are missing
NO_ADAPTER = "no_adapter_yet"         # settings present, but no code exists yet for the named provider
CONFIGURED = "configured"             # settings present and an adapter exists (not yet checked against the live service)

SPECS = {
    "text_model": {
        "label": "Text model (extraction, summaries, translation)",
        "settings": [("LLM_PROVIDER", "llm_provider"), ("LLM_API_KEY", "llm_api_key"), ("TEXT_MODEL", "text_model")],
        "optional": ["LLM_BASE_URL"],
        "how": "Choose a provider, create an API key, and set LLM_PROVIDER, LLM_API_KEY and TEXT_MODEL (and LLM_BASE_URL if the provider's adapter needs it).",
    },
    "transcription": {
        "label": "Speech-to-text for recordings",
        "settings": [("TRANSCRIPTION_PROVIDER", "transcription_provider"), ("TRANSCRIPTION_API_KEY", "transcription_api_key"),
                     ("TRANSCRIPTION_MODEL", "transcription_model")],
        "optional": ["TRANSCRIPTION_BASE_URL"],
        "how": "Choose a provider, create an API key, and set TRANSCRIPTION_PROVIDER, TRANSCRIPTION_API_KEY and TRANSCRIPTION_MODEL. FFmpeg must also be installed (brew install ffmpeg).",
    },
    "market_data": {
        "label": "Market data (share prices)",
        "settings": [("MARKET_DATA_PROVIDER", "market_data_provider"), ("MARKET_DATA_API_KEY", "market_data_api_key")],
        "optional": ["MARKET_DATA_BASE_URL"],
        "how": "Choose a provider with an official API that permits automated access, create an API key, and set MARKET_DATA_PROVIDER and MARKET_DATA_API_KEY.",
    },
    "news": {
        "label": "News search",
        "settings": [("NEWS_PROVIDER", "news_provider"), ("NEWS_API_KEY", "news_api_key")],
        "optional": ["NEWS_BASE_URL"],
        "how": "Choose a news provider during API setup, create an API key, and set NEWS_PROVIDER and NEWS_API_KEY.",
    },
    "sec_edgar": {
        "label": "SEC EDGAR identification",
        "settings": [("SEC_CONTACT_EMAIL", "sec_contact_email")],
        "optional": ["SEC_APP_NAME"],
        "how": "No account or key. Set SEC_CONTACT_EMAIL in .env to a real contact address; the SEC requires automated clients to identify themselves.",
    },
}


def _adapters(key: str) -> dict:
    """Provider adapters that exist in the code for a service (imported lazily to avoid circular imports)."""
    if key in ("text_model", "transcription"):
        from backend import llm
        return llm.ADAPTERS
    if key == "market_data":
        from backend.fetchers import market_data
        return market_data.ADAPTERS
    return {}  # news: no adapter until a provider is chosen


def missing_for(settings: Settings, key: str) -> list[str]:
    if key == "sec_edgar":
        return [] if settings.sec_user_agent else ["SEC_CONTACT_EMAIL"]
    return [env for env, attr in SPECS[key]["settings"] if not str(getattr(settings, attr) or "").strip()]


def status(settings: Settings, key: str) -> str:
    if missing_for(settings, key):
        return AWAITING
    if key == "sec_edgar":
        return CONFIGURED
    provider = SPECS[key]["settings"][0][1]
    return CONFIGURED if getattr(settings, provider) in _adapters(key) else NO_ADAPTER


def require(settings: Settings, key: str) -> None:
    """Raise a clear setup message unless the service is configured and has an adapter."""
    spec = SPECS[key]
    missing = missing_for(settings, key)
    if missing:
        raise ProviderNotConfigured(spec["label"], missing, spec["how"])
    if status(settings, key) == NO_ADAPTER:
        provider_env, provider_attr = spec["settings"][0]
        available = ", ".join(sorted(_adapters(key))) or "none yet"
        raise ProviderNotConfigured(spec["label"], [provider_env],
                                    f"No adapter exists yet for provider '{getattr(settings, provider_attr)}'. Available adapters: {available}. "
                                    "An adapter is added in the code once the provider is chosen.")


def service_status(settings: Settings) -> list[dict]:
    rows = []
    for key, spec in SPECS.items():
        rows.append({"key": key, "label": spec["label"], "status": status(settings, key), "missing": missing_for(settings, key),
                     "how_to_configure": spec["how"], "optional_settings": spec["optional"]})
    rows.append({"key": "ffmpeg", "label": "FFmpeg (local tool for recordings)",
                 "status": CONFIGURED if shutil.which("ffmpeg") and shutil.which("ffprobe") else AWAITING,
                 "missing": [] if shutil.which("ffmpeg") and shutil.which("ffprobe") else ["FFmpeg installation"],
                 "how_to_configure": "Install it with: brew install ffmpeg", "optional_settings": []})
    return rows
