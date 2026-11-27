# Step 4a: checks on what the text model returns. A figure must sit on the page it cites; a statement must cite a real source,
# and every number in it must appear in that source or in the cited Python result. Anything else is rejected or labelled unverified.
from backend import report_reader as rr
from backend import validation as V

READ = {"ar": {"doc": {"doc_id": "ar", "title": "Annual report FY2025", "url": "https://example.com/ar.pdf", "demo": False},
               "pages": rr.pages_from_texts([
                   "Cover",
                   "Total revenues [FY2025] ........ 1,234.5\nNet income [FY2025] ........ 98.0",
                   "Revenue by region: North America 70%; Europe 30%",
                   "Total revenues [FY2025] ........ 1,240.0"])}}
RESULTS = [{"indicator": "roe_common", "period": "TTM to Q3 2026", "value": 0.18287, "unit": "fraction"},
           {"indicator": "pe", "period": "TTM to Q3 2026", "value": 9.7312, "unit": "x"}]


def figure(**changes):
    base = {"field": "revenue", "period": "FY2025", "value": 1234.5, "unit": "USD millions", "doc_id": "ar", "page": 2,
            "line": "Total revenues [FY2025] ........ 1,234.5"}
    return {**base, **changes}


# ---------- figures ----------

def test_a_figure_on_its_cited_page_is_accepted_with_its_source():
    check = V.check_figures([figure()], READ)
    assert check["rejected"] == [] and len(check["accepted"]) == 1
    accepted = check["accepted"][0]
    assert accepted["value"] == 1234.5 and accepted["unit"] == "USD millions"
    assert accepted["sources"] == [{"doc_id": "ar", "title": "Annual report FY2025", "page": 2, "line": "Total revenues [FY2025] ........ 1,234.5",
                                    "url": "https://example.com/ar.pdf"}]


def test_figures_that_do_not_match_their_source_are_rejected_with_a_reason():
    cases = {"not on page 3": figure(page=3), "was not read": figure(doc_id="other"), "does not exist": figure(page=9),
             "does not match": figure(value=1234.6), "unknown field": figure(field="ebitda_adjusted"), "no unit": figure(unit="")}
    for reason, bad in cases.items():
        check = V.check_figures([bad], READ)
        assert check["accepted"] == [] and reason in check["rejected"][0]["reason"], reason


def test_the_same_figure_twice_is_merged_and_conflicting_values_are_not_used():
    assert len(V.check_figures([figure(), figure()], READ)["accepted"]) == 1
    conflict = V.check_figures([figure(), figure(value=1240.0, page=4, line="Total revenues [FY2025] ........ 1,240.0")], READ)
    assert conflict["accepted"] == [] and all("conflicting" in r["reason"] for r in conflict["rejected"])


# ---------- statements ----------

def statement(text, *citations):
    return {"text": text, "citations": list(citations)}


def test_statements_whose_numbers_are_in_the_cited_page_are_verified():
    [s] = V.check_statements([statement("About 70% of revenue comes from North America.", {"doc_id": "ar", "page": 3})], READ, RESULTS)
    assert s["verified"] and s["label"] == "verified" and s["issues"] == []
    assert s["citations"][0]["title"] == "Annual report FY2025" and s["citations"][0]["page"] == 3


def test_numbers_missing_from_the_source_make_a_statement_unverified():
    [s] = V.check_statements([statement("About 75% of revenue comes from North America.", {"doc_id": "ar", "page": 3})], READ, RESULTS)
    assert not s["verified"] and s["label"] == "unverified" and "75%" in s["issues"][0]


def test_citations_must_exist_and_be_present():
    [missing, none] = V.check_statements([statement("Revenue rose.", {"doc_id": "ar", "page": 12}), statement("Revenue rose.")], READ, RESULTS)
    assert not missing["verified"] and "does not exist" in missing["issues"][0]
    assert not none["verified"] and "No source" in none["issues"][0]


def test_calculated_numbers_are_checked_against_the_cited_python_result():
    ok, wrong = V.check_statements([
        statement("Common ROE was 18.3% over the twelve months to Q3 2026.", {"indicator": "roe_common", "period": "TTM to Q3 2026"}),
        statement("P/E was 12.5x.", {"indicator": "pe", "period": "TTM to Q3 2026"})], READ, RESULTS)
    assert ok["verified"] and ok["citations"][0]["indicator"] == "roe_common"
    assert not wrong["verified"] and "12.5" in wrong["issues"][0]


def test_years_and_quarter_labels_are_not_treated_as_figures():
    assert V.numbers_in("In Q3 2026 and FY2025, revenue was 1,234.5 (up 12%).") == [("1,234.5", 1234.5, 1, False), ("12%", 12.0, 0, True)]


# ---------- wording (step 4b) ----------

def test_valuation_verdicts_and_price_move_claims_are_flagged():
    flagged = ["With a P/E above the peer median, the shares look expensive.", "Investors should buy the stock.",
               "The company is undervalued.", "The leak report sent shares down.", "The stock fell sharply after the announcement."]
    for text in flagged:
        assert V.wording_issues(text), text
    fine = ["Commodity price volatility remains the main risk.", "Capital expenditure should remain broadly in line.",
            "A negative P/E is not a cheapness signal.", "Management may hold the dividend steady."]
    for text in fine:
        assert V.wording_issues(text) == [], text


def test_flagged_wording_makes_a_statement_unverified():
    [s] = V.check_statements([statement("About 70% of revenue comes from North America, so the shares look cheap.",
                                        {"doc_id": "ar", "page": 3})], READ, RESULTS)
    assert not s["verified"] and "valuation verdict" in s["issues"][0]


def test_extra_fields_are_kept_and_news_sources_show_publisher_and_date():
    read = {"n1": {"doc": {"doc_id": "n1", "kind": "news", "title": "Regulator proposes rules", "url": "https://news.example/1",
                           "publisher": "Example Wire", "published": "2026-10-30"},
                   "pages": rr.pages_from_texts(["Regulator proposes rules\nThe rule would tighten limits."])}}
    [s] = V.check_statements([{"text": "A regulator proposed tighter limits.", "speaker": "News", "citations": [{"doc_id": "n1", "page": 1}]}], read, [])
    assert s["verified"] and s["speaker"] == "News"
    assert s["citations"][0]["publisher"] == "Example Wire" and s["citations"][0]["published"] == "2026-10-30"


def test_document_references_in_the_text_are_removed_not_mistaken_for_figures():
    read = {**READ, "0001193125-26-323660": {"doc": {"doc_id": "0001193125-26-323660", "title": "10-K"},
                                              "pages": rr.pages_from_texts(["Microsoft Cloud revenue increased 27% to $214.4 billion."])}}
    [s] = V.check_statements([statement("Microsoft Cloud revenue increased 27% to $214.4 billion. [0001193125-26-323660] "
                                        "(0001193125-26-323660, page 1)", {"doc_id": "0001193125-26-323660", "page": 1})], read, RESULTS)
    assert s["verified"], s["issues"]
    assert s["text"] == "Microsoft Cloud revenue increased 27% to $214.4 billion."
    assert V.numbers_in("Filing 0001193125-26-323660 shows 27%.") == [("27%", 27.0, 0, True)]


def test_a_calculated_result_can_be_cited_by_its_name_or_without_its_period():
    results = [{"indicator": "net_margin", "name": "Net profit margin", "period": "TTM to Q1 2027", "value": 0.411698, "unit": "fraction"},
               {"indicator": "net_margin", "name": "Net profit margin", "period": "FY2025", "value": 0.36, "unit": "fraction"},
               {"indicator": "pe", "name": "P/E", "period": "TTM to Q1 2027", "value": 25.8312, "unit": "x"}]
    by_name, no_period, wrong = V.check_statements([
        statement("The net profit margin was 41.17%.", {"indicator": "Net profit margin", "period": "TTM to Q1 2027"}),
        statement("P/E was 25.83x.", {"indicator": "pe"}),  # no period: the current one is used
        statement("P/E was 30.00x.", {"indicator": "P/E"})], READ, results, current_period="TTM to Q1 2027")
    assert by_name["verified"] and no_period["verified"], (by_name["issues"], no_period["issues"])
    assert not wrong["verified"]  # the number must still match


def test_negative_numbers_keep_their_sign():
    assert V.numbers_in("P/E against its historical median of -29.76%, dated 2026-11-24.") == [("-29.76%", -29.76, 2, True)]
    results = [{"indicator": "pe_vs_hist", "name": "P/E against its historical median", "period": "TTM to Q1 2027", "value": -0.297612,
                "unit": "fraction"}]
    ok, wrong_sign = V.check_statements([statement("P/E is -29.76% against its historical median.", {"indicator": "pe_vs_hist"}),
                                         statement("P/E is 29.76% against its historical median.", {"indicator": "pe_vs_hist"})],
                                        READ, results, current_period="TTM to Q1 2027")
    assert ok["verified"] and not wrong_sign["verified"]


def test_agent_names_are_not_mistaken_for_figures():
    assert [n[1] for n in V.numbers_in("Agent 1's calculated indicators show a P/FCF of 64.41x; Agent 3 agrees.")] == [64.41]


def test_reference_markers_such_as_1_are_removed_not_mistaken_for_figures():
    [s] = V.check_statements([statement("About 70% of revenue comes from North America. [1]", {"doc_id": "ar", "page": 3}),
                              ], READ, RESULTS)
    assert s["verified"], s["issues"]
    assert s["text"] == "About 70% of revenue comes from North America."
    [t] = V.check_statements([statement("Common ROE was 18.3% [2, 3] over the twelve months [S4].",
                                        {"indicator": "roe_common", "period": "TTM to Q3 2026"})], READ, RESULTS)
    assert t["verified"] and t["text"] == "Common ROE was 18.3% over the twelve months."
    assert V.numbers_in("Revenue [FY2025] was 1,234.5.") == [("1,234.5", 1234.5, 1, False)]  # a period label in brackets is kept


def test_an_empty_placeholder_citation_is_ignored_but_a_real_one_is_still_required():
    blank = {"doc_id": "", "page": 0}
    ok, none = V.check_statements([statement("Common ROE was 18.3%.", {"indicator": "roe_common", "period": "TTM to Q3 2026"}, blank),
                                   statement("Revenue rose.", blank, {"indicator": ""})], READ, RESULTS)
    assert ok["verified"], ok["issues"]
    assert ok["citations"] == [{"indicator": "roe_common", "period": "TTM to Q3 2026", "name": None}]
    assert not none["verified"] and none["issues"] == ["No source cited."]
