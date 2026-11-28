# Shared test helpers: settings pointed at a temporary folder, a fake clock, and fake FFmpeg / model providers.
import json
from pathlib import Path
from types import SimpleNamespace

from backend.config import Settings


def make_settings(tmp_path, **overrides) -> Settings:
    values = {"storage_dir": Path(tmp_path) / "store", "extra_market_closures": [], "sec_contact_email": "",
              "llm_provider": "", "llm_api_key": "", "llm_base_url": "", "text_model": "",
              "transcription_provider": "", "transcription_api_key": "", "transcription_base_url": "", "transcription_model": "",
              "market_data_provider": "", "market_data_api_key": "", "market_data_base_url": "",
              "call_transcript_provider": "", "call_transcript_api_key": "", "call_transcript_base_url": ""}  # never the real .env keys
    values.update(overrides)
    return Settings(**values)


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(round(seconds, 3))
        self.now += seconds


def fake_ffmpeg(duration_seconds: float):
    """Stands in for subprocess.run: ffprobe reports a duration, ffmpeg writes its output file."""
    calls = []

    def run(cmd, **_kwargs):
        calls.append(cmd)
        if cmd[0] == "ffprobe":
            return SimpleNamespace(stdout=f"{duration_seconds}\n", returncode=0)
        Path(cmd[-1]).write_bytes(b"audio")
        return SimpleNamespace(stdout="", returncode=0)

    run.calls = calls
    return run


class FakeProvider:
    """Returns two Turkish segments per chunk; can be told to fail on a given call."""

    def __init__(self, fail_on_call=None):
        self.transcribe_calls = 0
        self.translate_calls = 0
        self.fail_on_call = fail_on_call

    def transcribe(self, path, language_hint=None):
        self.transcribe_calls += 1
        if self.fail_on_call == self.transcribe_calls:
            raise RuntimeError("temporary transcription failure")
        n = Path(path).stem
        return {"language": "turkish", "model": "test-model", "timestamps": True, "speakers": False,
                "segments": [
                    {"start": 1.0, "end": 4.0, "text": f"Gelir yüzde 12 arttı {n}", "avg_logprob": -0.2},
                    {"start": 10.0, "end": 12.0, "text": f"belirsiz {n}", "avg_logprob": -1.5},
                ]}

    def translate(self, texts, source_language, target_language):
        self.translate_calls += 1
        return [f"EN: {t}" for t in texts]


def json_bytes(obj) -> bytes:
    return json.dumps(obj).encode()


def sample_services(as_of=None, transcript=None):
    """The fictional sample company's stand-in services, in place of live ones (tests only)."""
    from tests.sample.providers import demo_services
    return demo_services()


def sample_app(tmp_path, **overrides):
    """The app with the fictional sample company plugged in through the analysis runner's test hook."""
    from fastapi.testclient import TestClient
    from backend import main
    return TestClient(main.create_app(make_settings(tmp_path, **overrides), background_jobs=False, analysis_services=sample_services))
