# The fictional sample company the tests use (tests/sample): everything in it is labelled as fictional, figures sit on the pages they
# claim, the sample accounts add up, and the app never imports it, so it can never act as a fallback for a missing key.
import io
import re
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from backend import llm
from tests.sample import data as D
from tests.sample.providers import demo_services
from backend.errors import ProviderNotConfigured
from backend.fetchers import market_data
from backend.fetchers.http_client import PoliteClient
from backend.fetchers.market_data import select_quote
from backend.market_calendar import calendar_for
from backend.storage import Store
from backend.transcription import TranscriptionJobs
from tests.helpers import make_settings

NY = ZoneInfo("America/New_York")
BACKEND = Path(__file__).resolve().parent.parent / "backend"


# ---------- labelling ----------

def test_every_demo_company_is_obviously_fictional():
    assert D.TARGET in D.COMPANIES and len(D.COMPANIES) >= 4
    for ticker, c in D.COMPANIES.items():
        assert ticker.endswith(".DEMO") and "(demo)" in c["name"]


def test_every_document_and_price_series_is_labelled():
    services = demo_services()
    for ticker in D.COMPANIES:
        for doc in services.documents.find(ticker):
            assert doc["demo"] and D.DEMO_LABEL in doc["pages"][0]
    series = services.market.daily_series(D.TARGET, date(2026, 1, 1), date(2026, 11, 20))
    assert "DEMO" in series.source


# ---------- the sample reports are usable for citation checks ----------

def test_every_figure_appears_on_the_page_it_is_indexed_to():
    services = demo_services()
    checked = 0
    for ticker in D.COMPANIES:
        docs = {d["doc_id"]: d for d in services.documents.find(ticker)}
        for fig in D.figure_index(ticker):
            page_text = docs[fig["doc_id"]]["pages"][fig["page"] - 1]
            assert fig["line"] in page_text
            assert f"{fig['value']:,.1f}" in fig["line"]
            checked += 1
    assert checked > 300


def test_documents_carry_v1_provenance():
    doc = demo_services().documents.find(D.TARGET)[0]
    for key in ("doc_id", "kind", "title", "period", "publication_date", "currency", "units", "consolidation_scope",
                "accounting_framework", "restatement_status", "pages"):
        assert key in doc
    kinds = {d["kind"] for d in demo_services().documents.find(D.TARGET)}
    assert kinds == {"annual_report", "quarterly_report", "transcript"}


def test_sample_accounts_add_up():
    for ticker in D.COMPANIES:
        f = D.financials(ticker)
        for period, v in list(f["annual"].items()) + list(f["ytd"].items()):
            assert v["pretax_income"] - v["income_tax"] == pytest.approx(v["net_income_group"], abs=0.051), (ticker, period)
            assert v["net_income_group"] - v["nci_share_of_income"] == pytest.approx(v["net_income_common"], abs=0.051)
            if "equity_total" in v:
                assert v["equity_common"] + v["nci"] == pytest.approx(v["equity_total"], abs=0.051)
                assert v["assets_total"] > v["equity_total"] > 0 and v["current_assets"] < v["assets_total"]


def test_target_has_five_years_and_comparable_quarters():
    f = D.financials(D.TARGET)
    assert sorted(f["annual"]) == ["FY2021", "FY2022", "FY2023", "FY2024", "FY2025"]
    assert set(f["ytd"]) == {"YTD Q3 2026", "YTD Q3 2025"}


# ---------- prices, transcript, recording ----------

def test_prices_fall_only_on_trading_days_and_are_fresh():
    series = demo_services().market.daily_series(D.TARGET, date(2025, 1, 1), date(2026, 11, 20))
    cal = calendar_for("NYSE")
    assert series.bars and all(cal.is_trading_day(b.day) and b.close > 0 and b.volume > 0 for b in series.bars)
    q = select_quote(series, datetime(2026, 11, 20, 17, tzinfo=NY))
    assert q.price_date == "2026-11-20" and not q.stale


def test_transcript_separates_management_and_analysts():
    transcript = next(d for d in demo_services().documents.find(D.TARGET) if d["kind"] == "transcript")
    text = "\n".join(transcript["pages"])
    assert re.search(r"\((CEO|CFO)\):", text) and "(Analyst):" in text


def test_recording_stand_in_transcribes_and_translates_with_wording_kept(tmp_path):
    model = demo_services().model
    out = model.transcribe(tmp_path / "x.mp3")
    assert out["timestamps"] and out["language"] == "turkish" and "DEMO" in out["model"]
    translated = model.translate([s["text"] for s in out["segments"]], "tr", "en")
    assert any(t.startswith("We may increase the dividend") for t in translated)
    assert model.translate(["unknown sentence"], "tr", "en")[0].startswith("[demo translation not recorded]")


def test_demo_recording_runs_through_the_existing_transcription_job(tmp_path):
    settings = make_settings(tmp_path)
    store = Store(settings.storage_dir)
    services = demo_services()
    rec = store.save_upload(io.BytesIO(b"demo audio"), "demo_call.mp3", "audio/mpeg")
    jobs = TranscriptionJobs(store, settings, provider_factory=lambda: services.model, run=services.ffmpeg_run)
    state = jobs.start(jobs.create(rec["id"], "en")["id"], background=False)
    assert state["status"] == "completed", state["error"]
    result = jobs.result(state["id"])
    assert result["source_language"] == "tr" and result["segments"][0]["translation"]


# ---------- the sample is never a fallback ----------

def test_unconfigured_live_services_still_give_setup_messages(tmp_path):
    settings = make_settings(tmp_path)
    with pytest.raises(ProviderNotConfigured):
        llm.get_text_model(settings)
    with pytest.raises(ProviderNotConfigured):
        llm.get_transcriber(settings)
    with pytest.raises(ProviderNotConfigured):
        market_data.get_provider(settings, PoliteClient(settings))


def test_the_app_never_imports_the_test_sample_or_has_a_demo_mode():
    for path in BACKEND.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        imports = " ".join(re.findall(r"^\s*(?:from|import)\s+[\w.]+", source, re.M))
        assert "tests" not in imports and "demo" not in source.lower(), path.name
