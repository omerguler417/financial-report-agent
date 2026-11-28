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


def test_the_real_form_controls_are_present_and_there_is_no_demo_mode(page):
    for control in ('id="analysis-form"', 'id="company"', 'id="language"', 'id="peers"', 'id="drop-zone"'):
        assert control in page, control
    script = (FRONTEND / "app.js").read_text(encoding="utf-8")
    assert 'name="mode"' not in page and "demo" not in page.lower() and "demo" not in script.lower()


def test_every_form_field_is_working_and_nothing_is_labelled_coming_later(page):
    tag = re.search(r'<textarea[^>]*id="extra-questions"[^>]*>', page).group(0)
    assert "disabled" not in tag and "Coming later" not in page
    script = (FRONTEND / "app.js").read_text(encoding="utf-8")
    assert 'questions: $("extra-questions").value.split' in script and "function questionsCard" in script


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
    for part in ("function proseItem", "function byTopic", '"Why unverified?"', "Key comparisons", "prose-heading"):
        assert part in script, part
    overview = script[script.index("function renderOverviewTab"):script.index("// ---------- footnotes")]
    assert "citeButtons" not in overview and "notes.box()" in overview  # footnote numbers and a sources box, no [S1] buttons


def test_news_and_the_integrated_assessment_tab_are_not_on_the_website(page):
    """Decided 27 November 2026: news is removed for the presentation, and the Integrated assessment tab with it."""
    script = (FRONTEND / "app.js").read_text(encoding="utf-8")
    css = (FRONTEND / "styles.css").read_text(encoding="utf-8")
    for text in (page, script, css):
        assert "news" not in text.lower()
    assert 'data-tab="call">Earnings call<' in page and "assessment" not in page.lower() and "renderAssessmentTab" not in script
    assert "disagreementsCard" in script  # disagreements, when there are any, are shown on the Overview


def test_the_dashboard_shows_the_bank_style_exhibits_without_grey_disclaimers():
    script = (FRONTEND / "app.js").read_text(encoding="utf-8")
    for part in ("function exhibitCards", "function keyDataBox", "exhibit-source", "Trading comparables", "Financial summary"):
        assert part in script, part
    for disclaimer in ("Click a row for its formula", "Missing years are left as gaps", "Each value is the median of the multiple"):
        assert disclaimer not in script, disclaimer
    css = (FRONTEND / "styles.css").read_text(encoding="utf-8")
    assert "table.exhibit-table th" in css and ".key-data" in css


def test_the_share_price_check_is_on_the_first_page_and_there_is_no_feature_list(page):
    new_page = page[page.index('id="page-new"'):page.index('id="page-workflow"')]
    assert 'id="price-form"' in new_page and 'id="price-date"' not in page  # the last close only, no date to pick
    assert "Feature status" not in page and 'id="working"' not in page and 'id="awaiting"' not in page
    script = (FRONTEND / "app.js").read_text(encoding="utf-8")
    assert "features" not in script


def test_my_reports_lists_the_analyses_kept_on_the_server(page):
    script = (FRONTEND / "app.js").read_text(encoding="utf-8")
    reports = script[script.index("async function renderMyReports"):script.index("// ---------- services and setup")]
    assert 'api("/api/analyses")' in reports and 'method: "DELETE"' in reports
    assert "folio.analyses" not in script and "/api/reports" not in script and "Saved analyses" in page


def test_the_examples_on_the_form_name_a_real_company_not_the_old_demo(page):
    assert "e.g. Microsoft or MSFT" in page and "Northgate" not in page


def test_indicators_without_data_are_not_shown_on_the_dashboard():
    script = (FRONTEND / "app.js").read_text(encoding="utf-8")
    assert "const NO_DATA" in script and "NO_DATA.includes" in script


def test_the_dashboard_opens_like_a_research_note(page):
    script = (FRONTEND / "app.js").read_text(encoding="utf-8")
    assert 'id="dash-eyebrow"' in page and "overview-top" in script and "Key comparisons" in script
    assert "function verifiedFirst" in script


def test_the_overview_lists_the_peers_chosen_beside_the_key_comparisons():
    script = (FRONTEND / "app.js").read_text(encoding="utf-8")
    assert "function peersChosenCard" in script and '"Peers chosen"' in script and "overview-side" in script
    css = (FRONTEND / "styles.css").read_text(encoding="utf-8")
    assert "grid-template-columns: minmax(0, 1fr) auto" in css  # the key-data box fits its card instead of overflowing


def test_the_earnings_call_tab_shows_key_points_and_questions_with_answers():
    script = (FRONTEND / "app.js").read_text(encoding="utf-8")
    call = script[script.index("function renderCallTab"):script.index("function disagreementsCard")]
    assert "Questions and answers" in call and "a2.call.questions" in call and '["management", "Key points"]' in script
