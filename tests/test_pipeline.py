# Step 4a: running a whole analysis through the API. Demo mode runs end to end without keys; a live analysis lists every service it
# still needs (HTTP 424) before anything starts and never falls back to demo data.
from fastapi.testclient import TestClient

from backend import main
from backend.demo import demo_data as D
from tests.helpers import make_settings


def client(tmp_path, **settings):
    return TestClient(main.create_app(make_settings(tmp_path, **settings), background_jobs=False))


def test_a_demo_analysis_runs_end_to_end(tmp_path):
    c = client(tmp_path)
    response = c.post("/api/analyses", json={"company": "Northgate", "demo": True, "as_of": "2026-11-20"})
    assert response.status_code == 200
    state = response.json()
    assert state["status"] == "completed", state.get("error")
    assert state["progress_percent"] == 100 and state["steps_done"][-1] == "save"
    assert c.get(f"/api/analyses/{state['id']}").json()["status"] == "completed"

    report = c.get(f"/api/analyses/{state['id']}/report").json()
    assert report["mode"] == "demo" and report["demo_label"] == D.DEMO_LABEL
    assert report["company"]["ticker"] == D.TARGET and report["analysis_date"] == "2026-11-20"
    assert report["agent1"]["indicators"]["current"] and report["agent1"]["summary"]
    assert sorted(p["ticker"] for p in report["peers"]["peers"]) == ["CRBN.DEMO", "RDGE.DEMO", "SLTK.DEMO"]
    assert report["agent2"]["call"]["statements"] and report["agent2"]["news"]["included"]
    assert report["agent3"]["overview"] and report["agent3"]["disagreements"] and report["agent3"]["limitations"]


def test_an_exact_ticker_wins_and_unclear_or_unknown_companies_are_asked_about(tmp_path):
    c = client(tmp_path)
    assert c.post("/api/analyses", json={"company": "RDGE.DEMO", "demo": True}).json()["company"]["ticker"] == "RDGE.DEMO"
    ambiguous = c.post("/api/analyses", json={"company": "demo", "demo": True})
    assert ambiguous.status_code == 409 and len(ambiguous.json()["candidates"]) == len(D.COMPANIES)
    assert c.post("/api/analyses", json={"company": "Nonexistent Corp", "demo": True}).status_code == 404


def test_a_live_analysis_lists_every_missing_required_service_and_never_uses_demo_data(tmp_path):
    # decision c (25 November 2026): only the text model and SEC identification are required; prices and news are optional
    c = client(tmp_path)
    response = c.post("/api/analyses", json={"company": "Northgate"})
    assert response.status_code == 424
    needed = " | ".join(item["service"] for item in response.json()["needs_configuration"])
    assert "Text model" in needed and "SEC EDGAR" in needed
    assert not list((tmp_path / "store").rglob("analysis_*"))  # nothing was started


def test_a_configured_text_model_still_needs_the_sec_identification(tmp_path):
    c = client(tmp_path, llm_provider="openai_compatible", llm_api_key="test-key", text_model="test-model", llm_base_url="https://llm.invalid")
    items = c.post("/api/analyses", json={"company": "Northgate"}).json()["needs_configuration"]
    assert [i["service"] for i in items] == ["SEC EDGAR identification"]  # the adapter can now run the analysis tasks


def test_unknown_analyses_give_404(tmp_path):
    c = client(tmp_path)
    assert c.get("/api/analyses/0123456789ab").status_code == 404
    assert c.get("/api/analyses/0123456789ab/report").status_code == 404
    assert c.get("/api/analyses/not-an-id").status_code == 404


def test_progress_can_be_read_while_the_background_analysis_is_writing_it(tmp_path):
    # the page asks for progress every second while the analysis rewrites the progress file; it must never see a half-written file
    import threading
    from datetime import date

    from backend import pipeline
    from backend.storage import Store

    settings = make_settings(tmp_path)
    jobs = pipeline.AnalysisJobs(Store(settings.storage_dir), settings)
    state = jobs.create("Northgate", True, "en", [], date(2026, 11, 20))
    stop = threading.Event()

    def keep_writing():
        while not stop.is_set():
            jobs._save(dict(state))

    writer = threading.Thread(target=keep_writing)
    writer.start()
    try:
        for _ in range(2000):
            assert jobs.get(state["id"])["id"] == state["id"]
    finally:
        stop.set()
        writer.join()


def test_the_user_can_choose_which_indicators_appear(tmp_path):
    c = client(tmp_path)
    catalogue = c.get("/api/config").json()["indicators"]
    assert {"id", "name", "group"} <= set(catalogue[0]) and len(catalogue) >= 58
    state = c.post("/api/analyses", json={"company": "Northgate", "demo": True, "as_of": "2026-11-20",
                                          "indicators": ["pe", "roe_common", "graham"]}).json()
    report = c.get(f"/api/analyses/{state['id']}/report").json()
    assert {r["indicator"] for r in report["agent1"]["indicators"]["current"]} == {"pe", "roe_common", "graham"}
    assert all(r["indicator"] in {"pe", "roe_common", "graham"} for rows in report["agent1"]["indicators"]["history"].values() for r in rows)
    assert any("left out at your request" in lim for lim in report["agent3"]["limitations"])
    assert c.post("/api/analyses", json={"company": "Northgate", "demo": True, "indicators": ["not_an_indicator"]}).status_code == 400
    assert c.post("/api/analyses", json={"company": "Northgate", "demo": True, "indicators": []}).status_code == 400
