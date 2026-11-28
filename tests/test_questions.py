# The user's own questions (approved 27 November 2026): up to three per analysis, answered only from the reports and the earnings call
# that were read and from the calculated indicators, every sentence checked like the agents' statements; a question the sources do not
# answer says so instead of guessing. Shown on the Overview and in the report, PDF and Word.
import json

import httpx2
from fastapi.testclient import TestClient

from backend import main, prompts
from tests.helpers import make_settings, sample_app
from tests.test_edgar import K25, LIVE, FakeSEC, settings_for

CAPEX = "What does management expect for capital expenditure?"
OTHER = "How many employees work in Antarctica?"


def demo_client(tmp_path):
    return sample_app(tmp_path)


def test_questions_are_limited_to_three_short_ones(tmp_path):
    c = demo_client(tmp_path)
    assert c.post("/api/analyses", json={"company": "Northgate", "questions": ["a?"] * 4}).status_code == 400
    assert c.post("/api/analyses", json={"company": "Northgate", "questions": ["x" * 301]}).status_code == 400
    ok = c.post("/api/analyses", json={"company": "Northgate", "as_of": "2026-11-20", "questions": [" ", CAPEX]}).json()
    assert ok["status"] == "completed" and ok["questions"] == [CAPEX]  # blank lines are dropped


def test_a_question_is_answered_from_the_sources_and_an_unanswerable_one_says_so(tmp_path):
    c = demo_client(tmp_path)
    state = c.post("/api/analyses", json={"company": "Northgate", "as_of": "2026-11-20", "questions": [CAPEX, OTHER]}).json()
    report = c.get(f"/api/analyses/{state['id']}/report").json()
    answered, unanswered = report["agent3"]["questions"]
    assert answered["question"] == CAPEX and answered["answered"]
    assert answered["statements"] and all(s["verified"] for s in answered["statements"])
    assert unanswered["question"] == OTHER and not unanswered["answered"] and unanswered["statements"] == []
    assert "do not answer this question" in unanswered["note"]
    view = c.get(f"/api/analyses/{state['id']}/view").json()
    text = json.dumps(view)
    assert "Your questions" in text and CAPEX in text and "do not answer this question" in text  # in the report, PDF and Word too


def test_without_questions_nothing_is_asked_and_no_section_is_added(tmp_path):
    c = demo_client(tmp_path)
    state = c.post("/api/analyses", json={"company": "Northgate", "as_of": "2026-11-20"}).json()
    report = c.get(f"/api/analyses/{state['id']}/report").json()
    assert report["agent3"]["questions"] == []
    assert "Your questions" not in json.dumps(c.get(f"/api/analyses/{state['id']}/view").json())


def test_answers_are_checked_like_every_other_statement(tmp_path):
    answers = {
        "summarise_reports": {"statements": []},
        "combine_report": {"overview": [], "disagreements": [], "risks": []},
        "answer_questions": {"answers": [
            {"number": 1, "answered": True, "statements": [
                {"text": "Management says revenue grew with cloud services.", "citations": [{"doc_id": K25[0], "page": 2}]},
                {"text": "So the shares look cheap.", "citations": [{"doc_id": K25[0], "page": 2}]}]}]},
    }
    fake = FakeSEC(answers)
    client = TestClient(main.create_app(settings_for(tmp_path, **LIVE), background_jobs=False, transport=httpx2.MockTransport(fake)))
    state = client.post("/api/analyses", json={"company": "EXMP", "as_of": "2026-05-15", "questions": ["How did revenue develop?"]}).json()
    assert state["status"] == "completed", state.get("error")
    report = client.get(f"/api/analyses/{state['id']}/report").json()
    [q] = report["agent3"]["questions"]
    good, verdict = q["statements"]
    assert good["verified"] and not verdict["verified"] and "valuation verdict" in verdict["issues"][0]
    asked = [json.loads(r.content) for r in fake.requests if str(r.url).endswith("/chat/completions")]
    data = next(json.loads(m["messages"][1]["content"].split("\n", 1)[1]) for m in asked if "answer_questions" in m["messages"][0]["content"])
    assert data["questions"][0]["question"] == "How did revenue develop?" and data["questions"][0]["pages"]  # with the relevant pages


def test_the_task_tells_the_model_to_use_only_the_data_and_to_say_when_it_cannot_answer():
    spec = prompts.TASKS["answer_questions"]
    assert spec["agent"] == "Agent 3" and "only" in spec["instructions"] and "answered" in json.dumps(spec["answer_format"])
