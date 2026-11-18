# Settings: the EDGAR User-Agent is built from configuration, and a missing or placeholder contact gives no User-Agent.
from backend.config import Settings


def test_edgar_user_agent_is_built_from_configuration(tmp_path):
    s = Settings(storage_dir=tmp_path, sec_contact_email="team@example.org", sec_app_name="FinancialAnalysisAgent")
    assert s.sec_user_agent == "FinancialAnalysisAgent team@example.org"
    assert "team@example.org" not in repr(s)          # the contact is not shown in printed settings


def test_missing_or_placeholder_contact_means_not_configured(tmp_path):
    assert Settings(storage_dir=tmp_path, sec_contact_email="").sec_user_agent is None
    assert Settings(storage_dir=tmp_path, sec_contact_email="your-contact@example.com").sec_user_agent is None
    assert Settings(storage_dir=tmp_path, sec_contact_email="not-an-email").sec_user_agent is None


def test_trading_window_default_is_60_sessions(tmp_path, monkeypatch):
    monkeypatch.delenv("TRADING_WINDOW_SESSIONS", raising=False)
    assert Settings(storage_dir=tmp_path).trading_window_sessions == 60
