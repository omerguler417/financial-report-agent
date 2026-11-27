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
    tag = re.search(r'<textarea[^>]*id="extra-questions"[^>]*>', page).group(0)
    assert "disabled" in tag
    assert page.count("Coming later") >= 1


def test_the_horizon_offers_3_5_or_10_years_with_5_as_the_default(page):
    select = re.search(r'<select[^>]*id="horizon"[^>]*>(.*?)</select>', page, re.S)
    assert "disabled" not in select.group(0).split(">")[0]
    options = re.findall(r'<option value="(\d+)"([^>]*)>', select.group(1))
    assert [v for v, _ in options] == ["3", "5", "10"] and "selected" in dict(options)["5"]
    script = (FRONTEND / "app.js").read_text(encoding="utf-8")
    assert "horizon_years:" in script


def test_the_new_analysis_button_opens_an_empty_form(page):
    assert re.search(r'<a[^>]*id="new-analysis-button"[^>]*href="#new"', page)
    script = (FRONTEND / "app.js").read_text(encoding="utf-8")
    reset = script[script.index("function resetForm"):]
    reset = reset[:reset.index("\n}\n")]
    for part in ('$("company").value = ""', '$("peers").value = ""', '$("analysis-status").replaceChildren()', "renderIndicatorPicker",
                 '$("horizon").value = "5"'):
        assert part in reset, part
    assert '$("new-analysis-button").addEventListener("click"' in script


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


def test_the_financials_page_is_built_from_topic_cards_with_python_comparison_lines_and_footnotes():
    script = (FRONTEND / "app.js").read_text(encoding="utf-8")
    financials = script[script.index("function renderFinancialsTab"):script.index("function simpleTable")]
    for part in ("FIN_GROUPS", "groupCard", "findingsPanel", "historyAgainstPeersCard", "notes.box()", "notes.mark(", "row-details",
                 "cmp.cells", "Show all"):
        assert part in financials, part
    assert '"Sources"]' not in financials  # no Sources column: footnote numbers and one sources box per card instead
    assert "comparisons" in script and "S.view.comparisons" in script  # lines and display values come from Python
    css = (FRONTEND / "styles.css").read_text(encoding="utf-8")
    assert "details.sources-box" in css and "sup.fn" in css and ".findings-panel" in css
    card = financials[financials.index("function groupCard"):financials.index("function details(")]
    assert card.index("t.append(tr, more)") < card.index("findingsPanel(")  # the explanation comes after its table


def test_statements_read_as_text_under_topics_with_unverified_reasons_on_request():
    script = (FRONTEND / "app.js").read_text(encoding="utf-8")
    for part in ("function proseItem", "function byTopic", '"Why unverified?"', "What the numbers show", "prose-heading"):
        assert part in script, part
    overview = script[script.index("function renderOverviewTab"):script.index("// ---------- footnotes")]
    assert "citeButtons" not in overview and "notes.box()" in overview  # footnote numbers and a sources box, no [S1] buttons
