# Model services: nothing works until configured (clear setup messages), the optional OpenAI-style adapter is used only when chosen, and output-language handling.
import json

import httpx2
import pytest

from backend import language, llm
from backend.errors import ProviderNotConfigured
from tests.helpers import make_settings

TEXT = dict(llm_provider="openai_compatible", llm_api_key="k", llm_base_url="https://llm.example/v1", text_model="my-text-model")
AUDIO = dict(transcription_provider="openai_compatible", transcription_api_key="k", transcription_base_url="https://audio.example/v1",
             transcription_model="my-audio-model")


def test_unconfigured_services_name_exactly_what_to_add(tmp_path):
    with pytest.raises(ProviderNotConfigured) as exc:
        llm.get_text_model(make_settings(tmp_path))
    assert exc.value.missing == ["LLM_PROVIDER", "LLM_API_KEY", "TEXT_MODEL"]
    with pytest.raises(ProviderNotConfigured) as exc:
        llm.get_transcriber(make_settings(tmp_path))
    assert exc.value.missing == ["TRANSCRIPTION_PROVIDER", "TRANSCRIPTION_API_KEY", "TRANSCRIPTION_MODEL"]


def test_unknown_provider_and_missing_address(tmp_path):
    with pytest.raises(ProviderNotConfigured, match="No adapter exists yet for provider 'other'"):
        llm.get_text_model(make_settings(tmp_path, **{**TEXT, "llm_provider": "other"}))
    with pytest.raises(ProviderNotConfigured) as exc:
        llm.get_text_model(make_settings(tmp_path, **{**TEXT, "llm_base_url": ""}))
    assert exc.value.missing == ["LLM_BASE_URL"]


def test_transcription_uses_the_configured_provider_address_and_model(tmp_path):
    seen = {}

    def handler(req):
        seen["host"], seen["path"], seen["auth"] = req.url.host, req.url.path, req.headers["authorization"]
        seen["body"] = req.content.decode("latin-1")
        return httpx2.Response(200, json={"language": "turkish", "segments": [{"start": 0.0, "end": 2.5, "text": " Merhaba ", "avg_logprob": -0.1}]})

    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"x")
    out = llm.get_transcriber(make_settings(tmp_path, **AUDIO), transport=httpx2.MockTransport(handler)).transcribe(audio)
    assert seen["host"] == "audio.example" and seen["path"].endswith("/audio/transcriptions") and seen["auth"] == "Bearer k"
    assert "my-audio-model" in seen["body"]
    assert out["segments"][0]["text"] == "Merhaba" and out["timestamps"] and out["language"] == "turkish"


def test_translation_rules_and_count_check(tmp_path):
    seen = {}

    def handler(req):
        seen["body"] = json.loads(req.content)
        return httpx2.Response(200, json={"choices": [{"message": {"content": json.dumps({"translations": ["Revenue may rise."]})}}]})

    provider = llm.get_text_model(make_settings(tmp_path, **TEXT), transport=httpx2.MockTransport(handler))
    assert provider.translate(["Gelir artabilir."], "tr", "en") == ["Revenue may rise."]
    assert seen["body"]["model"] == "my-text-model"
    assert '"may" stays "may"' in seen["body"]["messages"][0]["content"]
    with pytest.raises(llm.ModelError, match="1 items for 2 inputs"):
        provider.translate(["a", "b"], "tr", "en")


def test_model_services_resolve_each_part_only_when_needed(tmp_path):
    def handler(req):
        return httpx2.Response(200, json={"language": "english", "segments": [{"start": 0, "end": 1, "text": "Hello"}]})

    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"x")
    services = llm.get_provider(make_settings(tmp_path, **AUDIO), transport=httpx2.MockTransport(handler))
    assert services.transcribe(audio)["segments"][0]["text"] == "Hello"      # works without a text model
    with pytest.raises(ProviderNotConfigured, match="LLM_PROVIDER"):
        services.translate(["x"], "tr", "en")                                 # setup message only when translation is needed


def test_output_language_defaults_to_english_and_rejects_unknown(tmp_path):
    settings = make_settings(tmp_path)
    assert language.resolve_output_language(None, settings) == "en"
    assert language.resolve_output_language("Turkish", settings) == "tr"
    with pytest.raises(language.UnsupportedLanguage):
        language.resolve_output_language("Klingon", settings)
    assert language.source_language_flags("klingon")
    assert language.source_language_flags("portuguese") == []
