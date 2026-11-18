# Model provider isolation (OpenAI request shapes, configurable models, no key -> clear error) and output-language handling.
import json

import httpx2
import pytest

from backend import language, llm
from tests.helpers import make_settings


def test_no_api_key_gives_a_clear_error(tmp_path):
    with pytest.raises(llm.ModelNotConfigured, match="OPENAI_API_KEY"):
        llm.get_provider(make_settings(tmp_path))


def test_transcription_request_uses_configured_model_and_keeps_segments(tmp_path):
    seen = {}

    def handler(req):
        seen["path"] = req.url.path
        seen["body"] = req.content.decode("latin-1")
        return httpx2.Response(200, json={"language": "turkish", "segments": [
            {"start": 0.0, "end": 2.5, "text": " Merhaba ", "avg_logprob": -0.1}]})

    settings = make_settings(tmp_path, openai_api_key="test-key", transcription_model="whisper-1")
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"x")
    out = llm.get_provider(settings, transport=httpx2.MockTransport(handler)).transcribe(audio)
    assert seen["path"].endswith("/audio/transcriptions")
    assert "whisper-1" in seen["body"] and "verbose_json" in seen["body"]
    assert out["segments"][0]["text"] == "Merhaba" and out["timestamps"] and out["language"] == "turkish"


def test_translation_rules_and_count_check(tmp_path):
    seen = {}

    def handler(req):
        seen["body"] = json.loads(req.content)
        return httpx2.Response(200, json={"choices": [{"message": {"content": json.dumps({"translations": ["Revenue may rise."]})}}]})

    settings = make_settings(tmp_path, openai_api_key="k", text_model="my-text-model")
    provider = llm.get_provider(settings, transport=httpx2.MockTransport(handler))
    assert provider.translate(["Gelir artabilir."], "tr", "en") == ["Revenue may rise."]
    assert seen["body"]["model"] == "my-text-model"
    assert '"may" stays "may"' in seen["body"]["messages"][0]["content"]
    with pytest.raises(llm.ModelError, match="1 items for 2 inputs"):
        provider.translate(["a", "b"], "tr", "en")


def test_output_language_defaults_to_english_and_rejects_unknown(tmp_path):
    settings = make_settings(tmp_path)
    assert language.resolve_output_language(None, settings) == "en"
    assert language.resolve_output_language("Turkish", settings) == "tr"
    with pytest.raises(language.UnsupportedLanguage):
        language.resolve_output_language("Klingon", settings)
    assert language.source_language_flags("klingon")
    assert language.source_language_flags("portuguese") == []
