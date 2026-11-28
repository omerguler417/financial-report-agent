# Earnings-call transcripts from Alpha Vantage (approved 27 November 2026): the call of the same fiscal quarter as the latest report
# Agent 1 used, one request per analysis, each speaker turn a citable section, the key never in messages, an uploaded transcript
# first, a clear note when the provider has no transcript or its daily limit is reached, and a setup message when not configured.
import json

import httpx2
import pytest
from fastapi.testclient import TestClient

from backend import main, report_blocks
from backend.fetchers import call_transcripts
from backend.fetchers.http_client import PoliteClient
from tests.helpers import make_settings
from tests.test_edgar import FakeSEC, K25, LIVE, TRANSCRIPT, edgar_for, settings_for

KEY = "av-test-key-1234"
TURNS = [{"speaker": "Operator", "title": "Operator", "content": "Welcome to the Example Corp third quarter earnings call.", "sentiment": "0.0"},
         {"speaker": "Jane Doe", "title": "Chief Financial Officer", "content": "We expect cloud revenue to keep growing next quarter.",
          "sentiment": "0.7"},
         {"speaker": "Sam Lee", "title": "Analyst, Big Bank", "content": "Can you talk about margins?", "sentiment": "0.1"}]
AV = dict(call_transcript_provider="alpha_vantage", call_transcript_api_key=KEY, call_transcript_base_url="https://www.alphavantage.co")


class FakeAlphaVantage(FakeSEC):
    def __init__(self, answers=None, reply=None):
        super().__init__(answers)
        self.reply = reply or {"symbol": "EXMP", "quarter": "2026Q3", "transcript": TURNS}
        self.calls = []

    def __call__(self, request):
        if request.url.host == "www.alphavantage.co":
            if request.url.path == "/robots.txt":
                return httpx2.Response(404)
            self.calls.append(request)
            return httpx2.Response(200, json=self.reply)
        return super().__call__(request)


def provider(tmp_path, fake):
    settings = make_settings(tmp_path, min_seconds_between_requests_per_host=0.0, **AV)
    return call_transcripts.get_provider(settings, PoliteClient(settings, transport=httpx2.MockTransport(fake)))


def test_each_speaker_turn_becomes_a_citable_section_with_its_source(tmp_path):
    fake = FakeAlphaVantage()
    doc = provider(tmp_path, fake).fetch("EXMP", "2026Q3")
    assert doc["kind"] == "transcript" and doc["source_name"] == "Alpha Vantage" and doc["page_unit"] == "turn"
    assert doc["title"] == "Earnings call transcript, EXMP fiscal 2026 Q3 (Alpha Vantage)" and doc["url"] is None  # the API address holds the key
    assert doc["pages"][1] == "Turn 2 of 3 · Jane Doe (Chief Financial Officer)\nWe expect cloud revenue to keep growing next quarter."
    assert all("sentiment" not in page for page in doc["pages"])  # the provider's own sentiment score is not used
    [call] = fake.calls
    assert call.url.params["function"] == "EARNINGS_CALL_TRANSCRIPT" and call.url.params["symbol"] == "EXMP" and call.url.params["quarter"] == "2026Q3"


@pytest.mark.parametrize("reply, words", [({"Information": f"We have detected your API key as {KEY} and our standard API rate limit is 25 "
                                                           "requests per day."}, "25 requests per day"),
                                          ({"symbol": "EXMP", "quarter": "2026Q3", "transcript": []}, "no transcript"),
                                          ({"Error Message": "Invalid API call."}, "Invalid API call")])
def test_provider_messages_are_reported_without_the_key(tmp_path, reply, words):
    with pytest.raises(call_transcripts.CallTranscriptUnavailable) as raised:
        provider(tmp_path, FakeAlphaVantage(reply=reply)).fetch("EXMP", "2026Q3")
    assert words in str(raised.value) and KEY not in str(raised.value)


def test_the_quarter_is_the_companys_fiscal_quarter_of_the_latest_report(tmp_path):
    e, _ = edgar_for(tmp_path)  # Example Corp's fiscal year ends on 30 June
    assert e.fiscal_quarter("EXMP", "2026-03-31") == "2026Q3"
    assert e.fiscal_quarter("EXMP", "2025-06-30") == "2025Q4"
    assert e.fiscal_quarter("EXMP", "2025-09-30") == "2026Q1"  # like Microsoft's 2027Q1 for July to September 2026
    # 52/53-week quarters end a few days into the next month (Coca-Cola's Q3 2026 ended on 2 October; a live run asked for Q4)
    assert e.fiscal_quarter("EXMP", "2025-10-02") == "2026Q1"
    assert e.fiscal_quarter("EXMP", "2026-01-02") == "2026Q2"
    assert e.fiscal_quarter("EXMP", "2026-06-27") == "2026Q4"


ANSWERS = {
    "summarise_reports": {"statements": []},
    "analyse_call": {"statements": [{"kind": "guidance", "speaker": "Jane Doe", "text": "Cloud revenue is expected to keep growing.",
                                     "citations": [{"doc_id": "alphavantage-EXMP-2026Q3", "page": 2}]}]},
    "combine_report": {"overview": [], "disagreements": [], "risks": []},
}


def run_live(tmp_path, fake, settings_extra, upload=False):
    client = TestClient(main.create_app(settings_for(tmp_path, **LIVE, **settings_extra), background_jobs=False,
                                        transport=httpx2.MockTransport(fake)))
    body = {"company": "EXMP", "as_of": "2026-05-15"}
    if upload:
        body["transcript_upload"] = client.post("/api/uploads", files={"file": ("call.txt", TRANSCRIPT.encode(), "text/plain")}).json()["id"]
    state = client.post("/api/analyses", json=body).json()
    assert state["status"] == "completed", state.get("error")
    return client, client.get(f"/api/analyses/{state['id']}/report").json(), state


def test_a_live_analysis_fetches_the_call_of_the_latest_reports_quarter_once(tmp_path):
    fake = FakeAlphaVantage(json.loads(json.dumps(ANSWERS)))
    client, report, state = run_live(tmp_path, fake, AV)
    assert len(fake.calls) == 1 and fake.calls[0].url.params["quarter"] == "2026Q3"  # the 10-Q for the period ended 31 March 2026
    [doc] = report["agent2"]["call"]["documents"]
    assert doc["doc_id"] == "alphavantage-EXMP-2026Q3" and doc["source_name"] == "Alpha Vantage"
    [statement] = report["agent2"]["call"]["statements"]
    assert statement["verified"], statement["issues"]
    assert statement["citations"][0]["page_unit"] == "turn"
    view = client.get(f"/api/analyses/{state['id']}/view").json()
    assert "turn 2" in json.dumps(view)  # cited as a turn of the call, not a page
    assert KEY not in json.dumps(report) and KEY not in json.dumps(view)


def test_an_uploaded_transcript_comes_first_and_no_request_is_made(tmp_path):
    fake = FakeAlphaVantage({**ANSWERS, "analyse_call": {"statements": []}})
    _, report, _ = run_live(tmp_path, fake, AV, upload=True)
    assert fake.calls == [] and report["agent2"]["call"]["documents"][0]["origin"] == "user_upload"


def test_a_missing_transcript_or_service_is_explained(tmp_path):
    empty = FakeAlphaVantage({**ANSWERS, "analyse_call": {"statements": []}}, reply={"Information": "Thank you for using Alpha Vantage! "
                                                                                    "Our standard API rate limit is 25 requests per day."})
    _, report, _ = run_live(tmp_path, empty, AV)
    assert report["agent2"]["call"]["documents"] == []
    assert any("Alpha Vantage" in n and "25 requests per day" in n for n in report["agent2"]["notes"])
    _, unconfigured, _ = run_live(tmp_path / "none", FakeAlphaVantage({**ANSWERS, "analyse_call": {"statements": []}}), {})
    assert any("CALL_TRANSCRIPT_PROVIDER" in n for n in unconfigured["agent2"]["notes"])


def test_the_services_page_lists_the_transcript_service(tmp_path):
    client = TestClient(main.create_app(make_settings(tmp_path, **AV), background_jobs=False))
    services = json.dumps(client.get("/api/services").json())
    assert "Earnings-call transcripts" in services and KEY not in services
    assert report_blocks  # imported for the view check above
