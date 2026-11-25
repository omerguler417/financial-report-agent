# Central, configurable settings. Every limit and default lives here and can be overridden with an environment variable.
import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _env(name, default, cast=str):
    value = os.getenv(name)
    return default if value in (None, "") else cast(value)


def _env_list(name, default):
    value = os.getenv(name)
    return default if not value else [item.strip() for item in value.split(",") if item.strip()]


# Source languages the transcription and translation steps accept (ISO 639-1 code -> name).
SUPPORTED_LANGUAGES = {
    "en": "English", "tr": "Turkish", "pt": "Portuguese", "es": "Spanish", "fr": "French",
    "de": "German", "it": "Italian", "nl": "Dutch", "sv": "Swedish", "da": "Danish",
    "no": "Norwegian", "fi": "Finnish", "pl": "Polish", "cs": "Czech", "el": "Greek",
    "ru": "Russian", "uk": "Ukrainian", "ar": "Arabic", "he": "Hebrew", "hi": "Hindi",
    "ja": "Japanese", "ko": "Korean", "zh": "Chinese", "id": "Indonesian", "ms": "Malay",
    "th": "Thai", "vi": "Vietnamese", "ro": "Romanian", "hu": "Hungarian",
}


@dataclass
class Settings:
    # Output language
    default_output_language: str = field(default_factory=lambda: _env("DEFAULT_OUTPUT_LANGUAGE", "en"))

    # External services. No provider is chosen: every provider, model, address and key is empty until configured in .env.
    # Text model (extraction, summaries, translation); provider-specific code lives only in backend/llm.py.
    llm_provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", ""))
    llm_api_key: str = field(default_factory=lambda: _env("LLM_API_KEY", ""), repr=False)
    llm_base_url: str = field(default_factory=lambda: _env("LLM_BASE_URL", ""))
    text_model: str = field(default_factory=lambda: _env("TEXT_MODEL", ""))
    # Speech-to-text for recordings.
    transcription_provider: str = field(default_factory=lambda: _env("TRANSCRIPTION_PROVIDER", ""))
    transcription_api_key: str = field(default_factory=lambda: _env("TRANSCRIPTION_API_KEY", ""), repr=False)
    transcription_base_url: str = field(default_factory=lambda: _env("TRANSCRIPTION_BASE_URL", ""))
    transcription_model: str = field(default_factory=lambda: _env("TRANSCRIPTION_MODEL", ""))
    # Market data (prices; later also profiles, peers and index membership).
    market_data_provider: str = field(default_factory=lambda: _env("MARKET_DATA_PROVIDER", ""))
    market_data_api_key: str = field(default_factory=lambda: _env("MARKET_DATA_API_KEY", ""), repr=False)
    market_data_base_url: str = field(default_factory=lambda: _env("MARKET_DATA_BASE_URL", ""))
    market_data_min_interval_seconds: float = field(default_factory=lambda: _env("MARKET_DATA_MIN_INTERVAL_SECONDS", 7.5, float))
    # News search.
    news_provider: str = field(default_factory=lambda: _env("NEWS_PROVIDER", ""))
    news_api_key: str = field(default_factory=lambda: _env("NEWS_API_KEY", ""), repr=False)
    news_base_url: str = field(default_factory=lambda: _env("NEWS_BASE_URL", ""))

    # Polite fetching
    user_agent: str = field(default_factory=lambda: _env("FETCH_USER_AGENT", "FinancialReportAnalysisAgent/0.1"))
    min_seconds_between_requests_per_host: float = field(default_factory=lambda: _env("FETCH_MIN_INTERVAL_SECONDS", 1.0, float))
    max_concurrent_downloads_per_host: int = field(default_factory=lambda: _env("FETCH_MAX_CONCURRENT_PER_HOST", 2, int))
    max_retries: int = field(default_factory=lambda: _env("FETCH_MAX_RETRIES", 3, int))
    backoff_base_seconds: float = field(default_factory=lambda: _env("FETCH_BACKOFF_BASE_SECONDS", 1.0, float))
    request_timeout_seconds: float = field(default_factory=lambda: _env("FETCH_TIMEOUT_SECONDS", 30.0, float))

    # Saved files
    storage_dir: Path = field(default_factory=lambda: Path(_env("STORAGE_DIR", str(PROJECT_ROOT / "data" / "store"))))
    source_refresh_hours: float = field(default_factory=lambda: _env("SOURCE_REFRESH_HOURS", 24.0, float))
    temp_retention_days: float = field(default_factory=lambda: _env("TEMP_RETENTION_DAYS", 7.0, float))

    # Uploads and recordings
    max_upload_mb: int = field(default_factory=lambda: _env("MAX_UPLOAD_MB", 500, int))
    max_recording_hours: float = field(default_factory=lambda: _env("MAX_RECORDING_HOURS", 4.0, float))
    chunk_seconds: int = field(default_factory=lambda: _env("TRANSCRIPTION_CHUNK_SECONDS", 600, int))
    chunk_overlap_seconds: int = field(default_factory=lambda: _env("TRANSCRIPTION_CHUNK_OVERLAP_SECONDS", 5, int))

    # Peers: the usual total, including user-selected companies
    min_peers: int = field(default_factory=lambda: _env("MIN_PEERS", 3, int))
    max_peers: int = field(default_factory=lambda: _env("MAX_PEERS", 5, int))
    size_similarity_ratio: float = field(default_factory=lambda: _env("PEER_SIZE_RATIO", 4.0, float))

    # Prices
    # Extra market closures (YYYY-MM-DD) not covered by the holiday rules, such as days of mourning.
    extra_market_closures: list = field(default_factory=lambda: _env_list("EXTRA_MARKET_CLOSURES", []))
    # Average daily trading volume and traded value: number of latest completed trading sessions.
    trading_window_sessions: int = field(default_factory=lambda: _env("TRADING_WINDOW_SESSIONS", 60, int))

    # SEC EDGAR identification. The real contact lives only in the local .env (SEC_CONTACT_EMAIL), never in tracked files.
    sec_app_name: str = field(default_factory=lambda: _env("SEC_APP_NAME", "FinancialAnalysisAgent"))
    sec_contact_email: str = field(default_factory=lambda: _env("SEC_CONTACT_EMAIL", ""), repr=False)

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def sec_user_agent(self) -> str | None:
        """The User-Agent the SEC requires for automated EDGAR access, or None when no contact is configured."""
        email = self.sec_contact_email.strip()
        if not email or "@" not in email or email.endswith("@example.com"):
            return None
        return f"{self.sec_app_name.strip() or 'FinancialAnalysisAgent'} {email}"

    def public_view(self) -> dict:
        """Settings safe to show in the browser: no keys, no contact email."""
        return {
            "default_output_language": self.default_output_language,
            "supported_languages": SUPPORTED_LANGUAGES,
            "max_upload_mb": self.max_upload_mb,
            "max_recording_hours": self.max_recording_hours,
            "source_refresh_hours": self.source_refresh_hours,
            "temp_retention_days": self.temp_retention_days,
            "providers": {  # names only, never keys
                "text_model": self.llm_provider or None, "transcription": self.transcription_provider or None,
                "market_data": self.market_data_provider or None, "news": self.news_provider or None,
            },
        }


def get_settings() -> Settings:
    return Settings()
