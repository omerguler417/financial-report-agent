# The only file that calls a model. Provider-specific code is isolated in one class per provider so it can be replaced.
import json
import time
from pathlib import Path

import httpx2

from backend.config import Settings

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


class ModelNotConfigured(Exception):
    pass


class ModelError(Exception):
    pass


class OpenAIProvider:
    name = "openai"

    def __init__(self, settings: Settings, transport=None, sleep=time.sleep):
        self.settings = settings
        self.sleep = sleep
        self._client = httpx2.Client(
            base_url=settings.openai_base_url,
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            timeout=600.0,
            transport=transport,
        )

    def _post(self, path, **kwargs):
        attempts = self.settings.max_retries + 1
        for attempt in range(attempts):
            try:
                response = self._client.post(path, **kwargs)
            except httpx2.TransportError as exc:
                if attempt == attempts - 1:
                    raise ModelError(f"Model request failed: {exc}") from exc
                self.sleep(self.settings.backoff_base_seconds * 2 ** attempt)
                continue
            if response.status_code in (429, 500, 502, 503, 504) and attempt < attempts - 1:
                retry_after = response.headers.get("retry-after")
                wait = float(retry_after) if retry_after and retry_after.replace(".", "", 1).isdigit() else None
                self.sleep(wait if wait is not None else self.settings.backoff_base_seconds * 2 ** attempt)
                continue
            if response.status_code >= 400:
                raise ModelError(f"Model request failed: HTTP {response.status_code}: {response.text[:300]}")
            return response.json()
        raise ModelError("Model request failed after retries.")

    def transcribe(self, audio_path: Path, language_hint: str | None = None) -> dict:
        """Transcribe in the original language. Returns segments with timestamps and speakers when the model supplies them."""
        model = self.settings.transcription_model
        data = {"model": model}
        if "diarize" in model:
            data.update({"response_format": "diarized_json", "chunking_strategy": "auto"})
        elif model.startswith("whisper"):
            data.update({"response_format": "verbose_json", "timestamp_granularities[]": "segment"})
        else:
            data["response_format"] = "json"
        if language_hint:
            data["language"] = language_hint
        with open(audio_path, "rb") as fh:
            payload = self._post("/audio/transcriptions", data=data, files={"file": (Path(audio_path).name, fh, "audio/mpeg")})
        segments = []
        for seg in payload.get("segments") or []:
            segments.append({
                "start": float(seg.get("start", 0.0)),
                "end": float(seg.get("end", 0.0)),
                "text": (seg.get("text") or "").strip(),
                "speaker": seg.get("speaker"),
                "avg_logprob": seg.get("avg_logprob"),
                "no_speech_prob": seg.get("no_speech_prob"),
                "compression_ratio": seg.get("compression_ratio"),
            })
        has_timestamps = bool(segments)
        if not segments and payload.get("text"):
            segments = [{"start": 0.0, "end": 0.0, "text": payload["text"].strip(), "speaker": None}]
        return {
            "language": payload.get("language"),
            "segments": segments,
            "timestamps": has_timestamps,
            "speakers": any(s.get("speaker") for s in segments),
            "model": model,
        }

    def translate(self, texts: list[str], source_language: str, target_language: str) -> list[str]:
        if not texts:
            return []
        body = {
            "model": self.settings.text_model,
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
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ModelError("Translation response was not in the expected format.") from exc
        if len(translations) != len(texts):
            raise ModelError(f"Translation returned {len(translations)} items for {len(texts)} inputs.")
        return [str(t) for t in translations]


def get_provider(settings: Settings, transport=None):
    if settings.model_provider != "openai":
        raise ModelNotConfigured(f"Unknown model provider '{settings.model_provider}'.")
    if not settings.openai_api_key:
        raise ModelNotConfigured("No model API key configured. Add OPENAI_API_KEY to .env and restart the server.")
    return OpenAIProvider(settings, transport=transport)
