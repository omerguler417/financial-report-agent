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


def test_relative_valuation_is_allowed_only_with_its_benchmark():
    # CLAUDE.md (28 November 2026): "expensive", "cheap" and "fairly priced" may be said relative to a named benchmark
    allowed = ["On P/E the shares look expensive relative to their peers.",
               "Against its own five-year median, the stock trades cheap on EV/EBITDA." ,
               "The shares screen as cheap against their own five-year history.",
               "Overall the company looks broadly fairly priced compared with the peer median.",
               "On EV/sales it is expensive versus its historical median."]
    for text in allowed:
        assert V.wording_issues(text) == [], text
    flagged = ["The shares are cheap.", "With a P/E above the peer median, the shares look expensive.",
               "The stock looks fairly priced.", "The company is undervalued relative to its peers.",
               "The shares are expensive relative to peers, so investors should sell.",
               "Relative to its peers it is a buy.", "We recommend the shares.", "Our price target is 450.",
               "The stock is a hold relative to peers."]
    for text in flagged:
        assert V.wording_issues(text), text


def test_flagged_wording_makes_a_statement_unverified():
    [s] = V.check_statements([statement("About 70% of revenue comes from North America, so the shares look cheap.",
                                        {"doc_id": "ar", "page": 3})], READ, RESULTS)
    assert not s["verified"] and "valuation verdict" in s["issues"][0]


def test_extra_fields_such_as_the_speaker_are_kept():
    read = {"c1": {"doc": {"doc_id": "c1", "kind": "transcript", "title": "Q3 earnings call", "url": None},
                   "pages": rr.pages_from_texts(["Jane Doe (CFO): The rule would tighten limits."])}}
    [s] = V.check_statements([{"text": "The CFO said the rule would tighten limits.", "speaker": "Jane Doe", "kind": "management",
                               "citations": [{"doc_id": "c1", "page": 1}]}], read, [])
    assert s["verified"] and s["speaker"] == "Jane Doe" and s["kind"] == "management"
    assert s["citations"][0]["title"] == "Q3 earnings call"


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


def test_a_calculated_figure_quoted_without_its_citation_gets_that_citation_attached():
    """A real run (28 November 2026): a summary point quoted P/E 25.66x but cited only the reports. A number that is exactly one of
    this analysis's calculated results, as Python formats it (two decimals), is sourced to that result instead of failing."""
    [s] = V.check_statements([statement("About 70% of revenue comes from North America; P/E was 9.73x.", {"doc_id": "ar", "page": 3})],
                             READ, RESULTS, current_period="TTM to Q3 2026")
    assert s["verified"], s["issues"]
    assert {"indicator": "pe", "period": "TTM to Q3 2026", "name": None} in s["citations"]


def test_only_exact_two_decimal_figures_of_the_current_period_are_attached():
    results = RESULTS + [{"indicator": "pe", "period": "FY2024", "value": 12.3456, "unit": "x"}]
    rounded, other_period = V.check_statements([
        statement("About 70% of revenue comes from North America; P/E was about 10x.", {"doc_id": "ar", "page": 3}),
        statement("About 70% of revenue comes from North America; P/E was 12.35x.", {"doc_id": "ar", "page": 3})],
        READ, results, current_period="TTM to Q3 2026")
    assert not rounded["verified"] and "10" in rounded["issues"][0]  # a rounded figure is not matched
    assert not other_period["verified"]  # an older period's figure is not matched either


def test_a_per_share_amount_that_rose_is_not_a_share_price_claim():
    # a live Microsoft run (28 November 2026): "Book value per share rose ..." was flagged as a claim about the share price
    for text in ["Book value per share rose from 18.88 USD per share in FY2021 to 59.56 USD per share in FY2026.",
                 "Earnings per share climbed in each of the last five years.", "Dividends per share rose again."]:
        assert V.wording_issues(text) == [], text
    for text in ["The shares rose after the results.", "The stock fell sharply after the announcement.",
                 "The share price jumped on the news."]:
        assert V.wording_issues(text), text



def test_a_risk_title_is_checked_like_its_sentence():
    [s] = V.check_statements([{"title": "Shares look cheap", "text": "About 70% of revenue comes from North America.",
                               "citations": [{"doc_id": "ar", "page": 3}]}], READ, RESULTS)
    assert not s["verified"] and "without a benchmark" in s["issues"][0] and s["title"] == "Shares look cheap"


def test_above_or_below_must_match_the_numbers_it_compares():
    # a live Coca-Cola run (28 November 2026): "valuation ratios above peer medians, including P/E at 28.64x versus 36.03x peers"
    results = [{"indicator": "pe", "period": "TTM to Q3 2026", "value": 28.6421, "unit": "x", "name": "P/E"},
               {"indicator": "pe", "period": "peer median", "value": 36.0312, "unit": "x", "name": "P/E"},
               {"indicator": "p_fcf", "period": "TTM to Q3 2026", "value": 29.338, "unit": "x", "name": "P/FCF"},
               {"indicator": "p_fcf", "period": "peer median", "value": 22.46, "unit": "x", "name": "P/FCF"},
               {"indicator": "pe_hist_median", "period": "year ends 2021–2025", "value": 25.7665, "unit": "x", "name": "P/E historical median"}]
    pe = [{"indicator": "pe", "period": "TTM to Q3 2026"}, {"indicator": "pe", "period": "peer median"}]
    check = lambda text, cites: V.check_statements([statement(text, *cites)], READ, results, "TTM to Q3 2026")[0]
    wrong = check("Valuation ratios sit above peer medians, including P/E at 28.64x versus 36.03x for peers.", pe)
    assert not wrong["verified"] and "P/E" in wrong["issues"][0] and "below" in wrong["issues"][0]
    assert check("P/E at 28.64x is below the peer median of 36.03x.", pe)["verified"]
    assert check("P/E at 28.64x trades at a discount to peers at 36.03x.", pe)["verified"]
    assert not check("P/E at 28.64x is higher than its own median of 25.77x? No: at 28.64x it trails its median of 25.77x.",
                     pe + [{"indicator": "pe_hist_median", "period": "year ends 2021–2025"}])["verified"]
    mixed = pe + [{"indicator": "p_fcf", "period": "TTM to Q3 2026"}, {"indicator": "p_fcf", "period": "peer median"}]
    assert check("P/FCF at 29.34x is above peers at 22.46x, while P/E at 28.64x is below 36.03x.", mixed)["verified"]  # both directions
    assert check("P/E is 28.64x against a peer median of 36.03x.", pe)["verified"]  # no direction claimed


def test_counts_are_not_taken_for_compared_figures():
    # the same run: "2 of its 3 valuation multiples are above the peer median" matched a 2.94x ratio and its 3.04x median
    results = [{"indicator": "leverage", "period": "TTM to Q3 2026", "value": 2.94, "unit": "x", "name": "Leverage"},
               {"indicator": "leverage", "period": "peer median", "value": 3.04, "unit": "x", "name": "Leverage"}]
    assert V.direction_issues("2 of its 3 valuation multiples are more than 15% above the peer median.", results) == []


def test_an_indicator_written_as_a_document_id_is_read_as_an_indicator_citation():
    # a live Apple run (28 November 2026): the model cited {"doc_id": "pe", "page": 0} for the P/E it quoted
    [s] = V.check_statements([statement("The P/E is 9.73x.", {"doc_id": "pe", "page": 0})], READ, RESULTS, "TTM to Q3 2026")
    assert s["verified"], s["issues"]
    assert s["citations"][0]["indicator"] == "pe"
    [bad] = V.check_statements([statement("The P/E is 9.73x.", {"doc_id": "nonsense", "page": 0})], READ, RESULTS, "TTM to Q3 2026")
    assert not bad["verified"]  # an unknown id is still no source


def test_a_page_left_at_the_templates_0_is_no_citation():
    # live Microsoft and Apple runs (28 November 2026): calculated figures were cited as {"doc_id": <10-K>, "page": 0}, the answer
    # format's placeholder; the statement stands or falls on its real sources
    cited = V.check_statements([statement("The P/E is 9.73x.", {"doc_id": "ar", "page": 0}, {"indicator": "pe"})],
                               READ, RESULTS, "TTM to Q3 2026")[0]
    assert cited["verified"], cited["issues"]
    alone = V.check_statements([statement("About 70% of revenue comes from North America.", {"doc_id": "ar", "page": 0})],
                               READ, RESULTS, "TTM to Q3 2026")[0]
    assert not alone["verified"] and "No source cited" in alone["issues"][0]  # nothing real left: still unverified


def test_a_quoted_historical_median_gets_its_citation_like_the_other_calculated_figures():
    # a live Apple run (28 November 2026): "P/B at 46.48x compares with … a historical median of 33.10x" lost its citation
    results = RESULTS + [{"indicator": "pb_hist_median", "period": "year ends 2022–2026", "value": 33.1049, "unit": "x", "name": "P/B median"},
                         {"indicator": "pb", "period": "FY2019", "value": 33.1, "unit": "x"}]
    [s] = V.check_statements([statement("Its own historical median is 33.10x.")], READ, results, "TTM to Q3 2026")
    assert not s["verified"]  # no citation at all is still no source
    [s] = V.check_statements([statement("Its own historical median is 33.10x.", {"indicator": "pe"})], READ, results, "TTM to Q3 2026")
    assert s["verified"] and {"indicator": "pb_hist_median", "period": "year ends 2022–2026"} in [
        {k: c[k] for k in ("indicator", "period")} for c in s["citations"]]
    assert all(c["period"] != "FY2019" for c in s["citations"])  # an older year is not matched


HIST = [{"indicator": "pe_vs_hist", "period": "TTM to Q3 2026", "value": -0.3006, "unit": "fraction", "name": "P/E against its historical median"},
        {"indicator": "ev_ebitda_vs_hist", "period": "TTM to Q3 2026", "value": -0.2636, "unit": "fraction", "name": "EV/EBITDA against its median"},
        {"indicator": "pb_vs_hist", "period": "TTM to Q3 2026", "value": 0.1591, "unit": "fraction", "name": "P/B against its historical median"},
        {"indicator": "ps_vs_hist", "period": "peer median", "value": -0.0244, "unit": "fraction", "name": "P/S against its median, peers"}]


def test_a_difference_from_history_may_be_written_as_so_many_percent_below():
    # live Microsoft run (28 November 2026): "P/E is 30.06% below its historical median" (stored as -30.06%) was marked unverified
    check = lambda text: V.check_statements([statement(text, {"indicator": "pe"})], READ, RESULTS + HIST, "TTM to Q3 2026")[0]
    ok = check("Against its own history, P/E is 30.06% below its historical median, and EV/EBITDA is 26.36% below it.")
    assert ok["verified"], ok["issues"]
    assert not check("P/E is 30.06% above its historical median.")["verified"]  # the wrong direction
    assert not check("Revenue is 30.06% below plan.")["verified"]  # no P/E named: not this figure
    assert not check("P/S is 2.44% below its historical median.")["verified"]  # the peers' figure, not the company's


def test_a_stated_difference_from_history_must_have_the_right_direction():
    # live Apple run (28 November 2026): "P/E is below its historical median by 15.91%" while it was 15.91% above
    results = RESULTS + [dict(HIST[2], indicator="pe_vs_hist", name="P/E against its historical median")]
    [s] = V.check_statements([statement("P/E is below its historical median by 15.91%.", {"indicator": "pe"})], READ, results, "TTM to Q3 2026")
    assert not s["verified"] and any("above" in i for i in s["issues"])
    [s] = V.check_statements([statement("P/E is 15.91% above its historical median.", {"indicator": "pe"})], READ, results, "TTM to Q3 2026")
    assert s["verified"], s["issues"]


def test_the_peer_comparison_direction_is_read_clause_by_clause():
    # final Microsoft run (28 November 2026): "cheaper than its own history" was taken as the direction of the peer comparison
    results = [{"indicator": "pe", "period": "TTM to Q3 2026", "value": 25.6634, "unit": "x", "name": "P/E"},
               {"indicator": "pe", "period": "peer median", "value": 16.88, "unit": "x", "name": "P/E"}]
    fine = ("Valuation looks cheaper than its own history but still expensive relative to peers: P/E is 25.66x versus the peer "
            "median of 16.88x.")
    assert V.direction_issues(fine, results) == []
    wrong = "Valuation ratios sit below peer medians, including P/E at 25.66x versus 16.88x for peers."  # the KO pattern still caught
    assert V.direction_issues(wrong, results)
    assert V.direction_issues("The shares look cheap relative to peers, with P/E at 25.66x versus 16.88x.", results)


def test_the_peers_historical_median_is_not_the_companys():
    # final Apple run (28 November 2026): "close to its historical median of 29.33x" quoted the peers' median of their own medians
    results = RESULTS + [{"indicator": "ev_ebitda_hist_median", "period": "peer median", "value": 29.3311, "unit": "x", "name": "EV/EBITDA median"}]
    [s] = V.check_statements([statement("EV/EBITDA is close to its historical median of 29.33x.", {"indicator": "pe"})], READ, results,
                             "TTM to Q3 2026")
    assert not s["verified"] and any("peers" in i for i in s["issues"])
    [s] = V.check_statements([statement("The peers' own historical EV/EBITDA medians have a median of 29.33x.", {"indicator": "pe"})],
                             READ, results, "TTM to Q3 2026")
    assert s["verified"], s["issues"]
    # a Microsoft run: one peer's own median that equals the peers' median, named by its ticker, is not the company's
    assert V._peer_history_issues("Its 5-year EV/EBITDA median sits between ORCL at 20.10x and ADBE at 29.33x.", results) == []


def test_a_current_result_with_its_own_period_label_gets_its_citation():
    # presentation Apple run (28 November 2026): diluted EPS growth "FY2026 vs FY2025" (current) quoted as 20.38% was not matched
    results = RESULTS + [{"indicator": "eps_growth", "period": "FY2026 vs FY2025", "value": 0.2038, "unit": "fraction", "current": True},
                         {"indicator": "eps_growth", "period": "FY2024 vs FY2023", "value": 0.1111, "unit": "fraction"}]
    [s] = V.check_statements([statement("Diluted EPS grew 20.38%.", {"indicator": "pe"})], READ, results, "FY2026")
    assert s["verified"], s["issues"]
    [old] = V.check_statements([statement("Diluted EPS grew 11.11%.", {"indicator": "pe"})], READ, results, "FY2026")
    assert not old["verified"]  # an older year is still not matched


def test_a_contrast_clause_does_not_take_the_previous_direction():
    # presentation Microsoft run: "... well below the peer median of 2.94x, while interest coverage is 50.63x versus 20.09x for peers"
    results = [{"indicator": "net_debt_ebitda", "period": "TTM", "value": 0.5525, "unit": "x", "name": "Net debt/EBITDA"},
               {"indicator": "net_debt_ebitda", "period": "peer median", "value": 2.94, "unit": "x", "name": "Net debt/EBITDA"},
               {"indicator": "interest_coverage", "period": "TTM", "value": 50.63, "unit": "x", "name": "Interest coverage"},
               {"indicator": "interest_coverage", "period": "peer median", "value": 20.09, "unit": "x", "name": "Interest coverage"}]
    text = "Net debt/EBITDA is 0.55x, well below the peer median of 2.94x, while interest coverage is 50.63x versus 20.09x for peers."
    assert V.direction_issues(text, results) == []


def test_a_cited_period_that_starts_a_results_label_finds_that_result():
    # final Apple run (28 November 2026): {"indicator": "eps_growth", "period": "FY2026"} for the result "FY2026 vs FY2025"
    results = RESULTS + [{"indicator": "eps_growth", "period": "FY2026 vs FY2025", "value": 0.2038, "unit": "fraction"}]
    [s] = V.check_statements([statement("Diluted EPS grew 20.38%.", {"indicator": "eps_growth", "period": "FY2026"})], READ, results, "FY2026")
    assert s["verified"], s["issues"]
    [s] = V.check_statements([statement("Diluted EPS grew 20.38%.", {"indicator": "eps_growth", "period": "FY2019"})], READ, results, "FY2026")
    assert not s["verified"]  # a period that is not there is still not found


def test_differences_written_for_several_named_multiples_together():
    # final Microsoft run: "P/E … and EV/sales …, even though those multiples are below its own historical medians by 30.06% and 13.40%"
    results = RESULTS + [dict(HIST[0]), {"indicator": "ev_sales_vs_hist", "period": "TTM to Q3 2026", "value": -0.134, "unit": "fraction",
                                         "name": "EV/sales against its historical median"}]
    text = ("P/E is 9.73x and EV/sales is high, even though those multiples are below the company's own historical medians by 30.06% "
            "and 13.40%.")
    [s] = V.check_statements([statement(text, {"indicator": "pe"})], READ, results, "TTM to Q3 2026")
    assert s["verified"], s["issues"]
    [s] = V.check_statements([statement("Revenue is high, even though those multiples are below their medians by 30.06%.", {"indicator": "pe"})],
                             READ, results, "TTM to Q3 2026")
    assert not s["verified"]  # no multiple named in the sentence


def test_a_cited_period_finds_its_result_when_the_list_holds_it_twice():
    # final Apple run (28 November 2026): "FY2026 vs FY2025" is in both the current results and the history
    row = {"indicator": "eps_growth", "period": "FY2026 vs FY2025", "value": 0.2038, "unit": "fraction"}
    results = RESULTS + [dict(row, current=True), dict(row)]
    [s] = V.check_statements([statement("Diluted EPS grew 20.38%.", {"indicator": "eps_growth", "period": "FY2026"})], READ, results, "FY2026")
    assert s["verified"], s["issues"]


def test_a_citation_without_a_period_finds_the_current_result_whatever_its_label():
    # final Apple run (28 November 2026): {"indicator": "eps_growth"} for the current result "FY2026 vs FY2025" (also in the history)
    row = {"indicator": "eps_growth", "period": "FY2026 vs FY2025", "value": 0.2038, "unit": "fraction"}
    results = RESULTS + [dict(row, current=True), dict(row), dict(row, period="FY2025 vs FY2024", value=0.1)]
    [s] = V.check_statements([statement("Diluted EPS grew 20.38% versus FY2025.", {"indicator": "eps_growth"})], READ, results, "FY2026")
    assert s["verified"], s["issues"]


def test_the_companys_own_past_is_a_benchmark():
    # final Apple run: "a valuation that is not cheap versus its past"
    assert V.wording_issues("The own-history comparison points to a valuation that is not cheap versus its past.") == []
    assert V.wording_issues("The shares look expensive against their trading range of the last five years.") == []
    assert V.wording_issues("The shares are not cheap.")  # still flagged without a benchmark


def test_a_citation_written_as_text_inside_the_indicator_field_is_read():
    # final Apple run (28 November 2026): {"indicator": "{'indicator': 'pe', 'period': 'TTM to Q3 2026'}"}
    for written in ("{'indicator': 'pe', 'period': 'TTM to Q3 2026'}", '{"indicator": "pe", "period": "TTM to Q3 2026"}', "{'indicator': 'pe'}"):
        [s] = V.check_statements([statement("The P/E is 9.73x.", {"indicator": written})], READ, RESULTS, "TTM to Q3 2026")
        assert s["verified"], (written, s["issues"])
        assert s["citations"][0]["indicator"] == "pe"
    [s] = V.check_statements([statement("The P/E is 9.73x.", {"indicator": "{'indicator': 'nonsense'}"})], READ, RESULTS, "TTM to Q3 2026")
    assert not s["verified"]  # an unknown indicator is still no source
