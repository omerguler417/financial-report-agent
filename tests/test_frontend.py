# v3 website ("folio."): the page loads with its six sections and the real form controls, unbuilt form fields are disabled and
# labelled, nothing is loaded from outside the project, and the page carries no sample figures of its own.
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import main
from tests.helpers import make_settings

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
PAGES = ["new", "workflow", "dashboard", "sources", "reports", "services"]


@pytest.fixture(scope="module")
def page(tmp_path_factory):
    client = TestClient(main.create_app(make_settings(tmp_path_factory.mktemp("frontend")), background_jobs=False))
    return client.get("/").text


def test_the_page_has_the_six_sections_and_their_menu_items(page):
    for name in PAGES:
        assert f'id="page-{name}"' in page and f'href="#{name}"' in page, name
    assert "folio" in page and "Three agents. One evidence-led report." in page


def test_the_real_form_controls_are_present_and_live_is_the_default(page):
    for control in ('id="analysis-form"', 'id="company"', 'id="language"', 'id="peers"', 'id="drop-zone"'):
        assert control in page, control
    live = re.search(r'<input[^>]*name="mode"[^>]*value="live"[^>]*>', page).group(0)
    demo = re.search(r'<input[^>]*name="mode"[^>]*value="demo"[^>]*>', page).group(0)
    assert "checked" in live and "checked" not in demo  # demo mode is the user's explicit choice


def test_fields_the_backend_does_not_use_yet_are_disabled_and_labelled(page):
    for control in ("horizon", "extra-questions"):
        tag = re.search(rf'<(?:select|textarea)[^>]*id="{control}"[^>]*>', page).group(0)
        assert "disabled" in tag, control
    assert page.count("Coming later") >= 2


def test_the_indicator_choice_is_a_working_part_of_the_form(page):
    assert 'id="indicator-picker"' in page
    script = (FRONTEND / "app.js").read_text(encoding="utf-8")
    assert "config.indicators" in script and "indicators:" in script


def test_nothing_is_loaded_from_outside_the_project():
    for name in ("index.html", "styles.css", "app.js"):
        text = (FRONTEND / name).read_text(encoding="utf-8")
        assert not re.search(r"""(src|href)=["']https?://|@import\s+url\(["']?https?://|fetch\(["']https?://""", text), name


def test_the_page_carries_no_sample_figures_of_its_own():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    text = re.sub(r"<[^>]+>", " ", html)
    figures = re.findall(r"\d+(?:\.\d+)?\s?(?:%|x\b)", text)
    assert figures == [], figures  # every figure comes from a finished analysis
