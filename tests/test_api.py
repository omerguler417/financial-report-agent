# API endpoints: config, uploads with limits and labels, transcription jobs, reports, prices refusal, peers.
from fastapi.testclient import TestClient

from backend import main, transcription
from backend.fetchers.http_client import AccessDenied
from tests.helpers import FakeProvider, fake_ffmpeg, make_settings


def client(tmp_path, monkeypatch, **overrides):
    monkeypatch.setattr(transcription, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(transcription, "probe_duration", lambda path, run=None: 120.0)
    app = main.create_app(make_settings(tmp_path, **overrides), provider_factory=FakeProvider, run=fake_ffmpeg(120),
                          background_jobs=False)
    return TestClient(app)


def test_config_shows_defaults_feature_status_and_services(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch, market_data_provider="someprovider", market_data_api_key="SECRET-KEY-123",
               sec_contact_email="team@example.org")
    body = c.get("/api/config").json()
    assert body["default_output_language"] == "en" and body["max_upload_mb"] == 500 and body["max_recording_hours"] == 4
    assert body["features"]["working"] and body["features"]["awaiting_implementation"]
    status = {s["key"]: s["status"] for s in body["services"]}
    assert status["text_model"] == "awaiting_configuration" and status["news"] == "awaiting_configuration"
    assert status["market_data"] == "no_adapter_yet" and status["sec_edgar"] == "configured"
    text = c.get("/api/config").text + c.get("/api/services").text
    assert "SECRET-KEY-123" not in text and "team@example.org" not in text   # keys and the contact never reach the browser


def test_unconfigured_services_give_setup_messages(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch)
    r = c.get("/api/prices/AAPL")
    assert r.status_code == 424 and "MARKET_DATA_PROVIDER" in r.json()["detail"] and "MARKET_DATA_API_KEY" in r.json()["detail"]
    live = TestClient(main.create_app(make_settings(tmp_path), background_jobs=False))   # real (unconfigured) model services
    upload = live.post("/api/uploads", files={"file": ("call.mp3", b"x", "audio/mpeg")}).json()
    r = live.post("/api/transcriptions", json={"upload_id": upload["id"]})
    assert r.status_code == 424 and "TRANSCRIPTION_PROVIDER" in r.json()["detail"]
    assert r.json()["needs_configuration"]["service"] == "Speech-to-text for recordings"
    assert live.get("/health").json() == {"ok": True}                                  # independent features keep working


def test_upload_list_and_delete(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch)
    r = c.post("/api/uploads", files={"file": ("q3.txt", b"Revenue rose 12%.", "text/plain")}, data={"notes": "IR email"})
    assert r.status_code == 200 and r.json()["origin"] == "user_upload"
    assert [m["id"] for m in c.get("/api/uploads").json()] == [r.json()["id"]]
    assert c.delete(f"/api/uploads/{r.json()['id']}").status_code == 200
    assert c.get("/api/uploads").json() == []


def test_upload_rejections(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch, max_upload_mb=1)
    assert c.post("/api/uploads", files={"file": ("x.exe", b"x", "application/octet-stream")}).status_code == 415
    big = c.post("/api/uploads", files={"file": ("big.pdf", b"x" * 1_500_000, "application/pdf")})
    assert big.status_code == 413 and "Split the recording" in big.json()["detail"]


def test_recording_too_long_is_rejected_with_advice(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch)
    monkeypatch.setattr(transcription, "probe_duration", lambda path, run=None: 5 * 3600.0)
    r = c.post("/api/uploads", files={"file": ("call.mp3", b"x", "audio/mpeg")})
    assert r.status_code == 413 and "4 hours" in r.json()["detail"]
    assert c.get("/api/uploads").json() == []


def test_transcription_job_round_trip(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch)
    upload = c.post("/api/uploads", files={"file": ("call.mp3", b"x", "audio/mpeg")}).json()
    assert c.post("/api/transcriptions", json={"upload_id": upload["id"], "output_language": "Klingon"}).status_code == 400
    job = c.post("/api/transcriptions", json={"upload_id": upload["id"]}).json()
    assert job["status"] == "completed" and job["output_language"] == "en"
    result = c.get(f"/api/jobs/{job['id']}/result").json()
    assert result["segments"][0]["translation"].startswith("EN:")


def test_reports_and_price_refusal(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch)
    assert c.get("/api/reports").json() == []
    assert c.delete("/api/reports/000000000000").status_code == 404

    def refuse(*args, **kwargs):
        raise AccessDenied("https://prices.example/... is disallowed by robots.txt")
    monkeypatch.setattr(main.market_data, "get_closing_price", refuse)
    r = c.get("/api/prices/AAPL")
    assert r.status_code == 503 and "official API" in r.json()["detail"]


def test_peer_endpoint(tmp_path, monkeypatch):
    body = {"target": {"ticker": "TGT", "industry": "Oil & Gas", "products": ["crude oil"]},
            "candidates": [{"profile": {"ticker": "A", "industry": "Oil & Gas", "products": ["crude oil"]},
                            "sources": [{"type": "market_data_provider", "detail": "test"}]}]}
    r = client(tmp_path, monkeypatch).post("/api/peers/select", json=body)
    assert r.status_code == 200 and r.json()["peers"][0]["ticker"] == "A"
