# The only file that calls a model. No provider is chosen: each adapter is one class, selected by name from .env, and nothing works until it is configured.
import json
import time
from pathlib import Path

import httpx2

from backend import services
from backend.config import Settings
from backend.errors import ProviderNotConfigured

AMBIGUOUS_MARK = "[AMBIGUOUS:"

TRANSLATION_RULES = """You translate financial source material for an analysis tool.
Rules:
- Translate faithfully. Do not add, drop, summarise or explain anything.
- Copy every number, percentage, currency, unit, date, minus sign and parenthesised negative exactly.
- Preserve the strength of wording: "may" stays "may", "expect" stays "expect"; never upgrade or soften commitments.
- Keep standard financial terminology (for example EBITDA, free cash flow, guidance).
- If a passage is ambiguous or unclear, translate it and append " [AMBIGUOUS: short reason]".
- Keep existing markers such as [unclear] unchanged.
Return JSON: {"translations": [...]} with exactly one string per input item, in the same order."""


ModelNotConfigured = ProviderNotConfigured  # kept for older imports


class ModelError(Exception):
    pass


class OpenAICompatibleAdapter:
    """Optional adapter for any provider that offers the widely used OpenAI-style HTTP API
    (/chat/completions and /audio/transcriptions). It is not a default: it is used only if
    LLM_PROVIDER or TRANSCRIPTION_PROVIDER is set to "openai_compatible", with that provider's address, key and model."""

    name = "openai_compatible"

    def __init__(self, settings: Settings, api_key: str, base_url: str, model: str, transport=None, sleep=time.sleep):
        self.settings, self.model, self.sleep = settings, model, sleep
        self._client = httpx2.Client(base_url=base_url, headers={"Authorization": f"Bearer {api_key}"}, timeout=600.0, transport=transport)

    def _post(self, path, **kwargs):
        attempts = self.settings.max_retries + 1
        for attempt in range(attempts):
            try:
                response = self._client.post(path, **kwargs)
            except httpx2.TransportError as exc:
                if attempt == attempts - 1:
                    raise ModelError(f"Model request failed ({type(exc).__name__}).") from None
                self.sleep(self.settings.backoff_base_seconds * 2 ** attempt)
                continue
            if response.status_code in (429, 500, 502, 503, 504) and attempt < attempts - 1:
                retry_after = response.headers.get("retry-after")
                wait = float(retry_after) if retry_after and retry_after.replace(".", "", 1).isdigit() else None
                self.sleep(wait if wait is not None else self.settings.backoff_base_seconds * 2 ** attempt)
                continue
            if response.status_code in (401, 403):
                raise ModelError(f"The provider rejected the credentials (HTTP {response.status_code}); check the key in .env.")
            if response.status_code >= 400:
                raise ModelError(f"Model request failed: HTTP {response.status_code}: {response.text[:300]}")
            return response.json()
        raise ModelError("Model request failed after retries.")

    def transcribe(self, audio_path: Path, language_hint: str | None = None) -> dict:
        """Transcribe in the original language, asking for segment timestamps; falls back to plain text if none come back."""
        data = {"model": self.model, "response_format": "verbose_json", "timestamp_granularities[]": "segment"}
        if language_hint:
            data["language"] = language_hint
        with open(audio_path, "rb") as fh:
            payload = self._post("/audio/transcriptions", data=data, files={"file": (Path(audio_path).name, fh, "audio/mpeg")})
        segments = [{
            "start": float(seg.get("start", 0.0)), "end": float(seg.get("end", 0.0)), "text": (seg.get("text") or "").strip(),
            "speaker": seg.get("speaker"), "avg_logprob": seg.get("avg_logprob"), "no_speech_prob": seg.get("no_speech_prob"),
            "compression_ratio": seg.get("compression_ratio"),
        } for seg in payload.get("segments") or []]
        has_timestamps = bool(segments)
        if not segments and payload.get("text"):
            segments = [{"start": 0.0, "end": 0.0, "text": payload["text"].strip(), "speaker": None}]
        return {"language": payload.get("language"), "segments": segments, "timestamps": has_timestamps,
                "speakers": any(s.get("speaker") for s in segments), "model": self.model}

    def translate(self, texts: list[str], source_language: str, target_language: str) -> list[str]:
        if not texts:
            return []
        body = {
            "model": self.model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": TRANSLATION_RULES},
                {"role": "user", "content": json.dumps({
                    "source_language": source_language, "target_language": target_language, "items": texts,
                }, ensure_ascii=False)},
            ],
        }
        payload = self._post("/chat/completions", json=body)
        try:
            translations = json.loads(payload["choices"][0]["message"]["content"])["translations"]
        except (KeyError, IndexError, TypeError, ValueError):
            raise ModelError("Translation response was not in the expected format.") from None
        if len(translations) != len(texts):
            raise ModelError(f"Translation returned {len(translations)} items for {len(texts)} inputs.")
        return [str(t) for t in translations]


# Adapters available in the code, by the provider name used in .env. New providers are added here once chosen.
ADAPTERS = {"openai_compatible": OpenAICompatibleAdapter}


def _build(settings: Settings, key: str, provider: str, api_key: str, base_url: str, model: str, base_url_env: str, transport=None):
    services.require(settings, key)  # clear setup message if anything is missing or the provider has no adapter
    if not base_url:
        raise ProviderNotConfigured(services.SPECS[key]["label"], [base_url_env], f"The '{provider}' adapter needs the provider's API address.")
    return ADAPTERS[provider](settings, api_key, base_url, model, transport=transport)


def get_text_model(settings: Settings, transport=None):
    return _build(settings, "text_model", settings.llm_provider, settings.llm_api_key, settings.llm_base_url, settings.text_model,
                  "LLM_BASE_URL", transport)


def get_transcriber(settings: Settings, transport=None):
    return _build(settings, "transcription", settings.transcription_provider, settings.transcription_api_key,
                  settings.transcription_base_url, settings.transcription_model, "TRANSCRIPTION_BASE_URL", transport)


class ModelServices:
    """What the transcription jobs use. Each part is resolved only when needed, so a recording in the output language
    can be transcribed without a text model, and a missing setting gives a setup message at the step that needs it."""

    def __init__(self, settings: Settings, transport=None):
        self.settings, self.transport = settings, transport

    def transcribe(self, audio_path, language_hint=None):
        return get_transcriber(self.settings, self.transport).transcribe(audio_path, language_hint)

    def translate(self, texts, source_language, target_language):
        return get_text_model(self.settings, self.transport).translate(texts, source_language, target_language)


def get_provider(settings: Settings, transport=None) -> ModelServices:
    return ModelServices(settings, transport)
