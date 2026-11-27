# Part B: the rest of v1.0 section 5 and all of section 6, hand-checked on the sample company from test_indicators.py, then run on
# the demo data (price returns, historical multiple medians built only from what was published by each year end).
from datetime import date

import pytest

from backend import indicators as ind
from backend.demo import demo_data as D
from backend.demo.demo_providers import demo_company_inputs
from tests.test_indicators import fig, sample

EXTRA = {
    "FY2024": dict(cost_of_sales=480, interest_paid_in_cfo=10, lease_principal_outside_cfo=4, dividends_paid_common=20, dividends_per_share=0.20,
                   eps_basic=0.55, eps_diluted=0.54, short_term_investments=10, trade_receivables=60, inventories=40, trade_payables=50,
                   goodwill=30, intangible_assets=10, free_float_shares=90),
    "FY2025": dict(cost_of_sales=600, interest_paid_in_cfo=12, lease_principal_outside_cfo=6, dividends_paid_common=30, dividends_per_share=0.30,
                   eps_basic=0.90, eps_diluted=0.88, short_term_investments=20, trade_receivables=70, inventories=50, trade_payables=60,
                   goodwill=30, intangible_assets=10, free_float_shares=92),
    "YTD Q3 2026": dict(cost_of_sales=480, interest_paid_in_cfo=9, lease_principal_outside_cfo=5, dividends_paid_common=24, dividends_per_share=0.24,
                        short_term_investments=30, trade_receivables=80, inventories=55, trade_payables=65, goodwill=30, intangible_assets=10,
                        free_float_shares=95),
    "YTD Q3 2025": dict(cost_of_sales=420, interest_paid_in_cfo=9, lease_principal_outside_cfo=4, dividends_paid_common=21, dividends_per_share=0.21,
                        short_term_investments=25, trade_receivables=75, inventories=52, trade_payables=62, goodwill=30, intangible_assets=10,
                        free_float_shares=94),
}
PER_SHARE = {"eps_basic", "eps_diluted", "dividends_per_share"}


def extended(**changes):
    c = sample(**changes)
    for period, values in EXTRA.items():
        for name, value in values.items():
            unit = "USD per share" if name in PER_SHARE else "millions of shares" if name == "free_float_shares" else None
            c.periods[period][name] = fig(name, value, period, unit)
    return c


def current(c):
    return {r.indicator: r for r in ind.analyse(c)["current"]}


def test_section_6_and_the_rest_of_section_5_match_hand_calculations():
    # TTM: revenue 1100, cost of sales 660, EBIT 170, EBITDA 203, group NI 110, common NI 99, CFO 150, lease principal 7 (interest is
    # already inside CFO), standardised CFO 143, capex 60, standardised FCF 83 (reported 90), dividends 33, dividends per share 0.33.
    # At Q3 2026: market cap 2000, EV 2220, debt incl. leases 300, cash 100, short-term investments 30, receivables 80, inventories 55,
    # payables 65, current liabilities 195. Averages: assets 1200, total equity 470.
    expected = {"ev_sales": 2220 / 1100, "ev_ebit": 2220 / 170, "gross_margin": 440 / 1100, "ebit_margin": 170 / 1100,
                "cfo_margin": 143 / 1100, "fcf_margin": 83 / 1100, "cfo_conversion": 143 / 110, "accrual_ratio": (110 - 143) / 1200,
                "capex_intensity": 60 / 1100, "quick_ratio": 210 / 195, "cash_ratio": 130 / 195, "gross_debt_ebitda": 300 / 203,
                "payout_ratio": 33 / 99, "fcf_dividend_coverage": 83 / 33, "nwc_sales": (80 + 55 - 65) / 1100,
                "dividend_yield": 0.33 / 20, "graham": (2000 / 99) * (2000 / 480), "asset_turnover": 1100 / 1200,
                "dupont_leverage": 1200 / 470, "dupont_margin_turnover": 110 / 1200, "dupont_roe": 110 / 470, "free_float": 0.95,
                "p_fcf": 2000 / 83, "fcf_yield": 83 / 2000, "fcf_conversion": 83 / 110, "eps_growth": 0.88 / 0.54 - 1,
                "revenue_cagr": 1000 / 800 - 1}
    r = current(extended())
    for key, value in expected.items():
        assert r[key].status == "calculated", (key, r[key].note)
        assert r[key].value == pytest.approx(value), key
    assert r["dupont_margin_turnover"].value == pytest.approx(r["roa_group"].value)  # the DuPont identity holds
    assert r["revenue_cagr"].period == "FY2024–FY2025" and "1-year" in r["revenue_cagr"].note


def test_comparisons_use_standardised_fcf_and_keep_the_reported_figure_alongside():
    r = current(extended())
    assert r["p_fcf"].other_views["reported_basis"] == pytest.approx(2000 / 90)
    assert r["fcf_yield"].other_views["reported_basis"] == pytest.approx(90 / 2000)
    assert any(i["name"] == "fcf_standardised" for i in r["p_fcf"].inputs)
    reported_only = current(sample())["p_fcf"]  # no interest or lease classification in the inputs: reported FCF, labelled
    assert reported_only.value == pytest.approx(2000 / 90) and "reported" in reported_only.note.lower()


def test_eps_is_reported_not_rebuilt_from_cumulative_figures():
    r = current(extended())
    assert r["eps_basic"].status == "reported_only" and r["eps_basic"].value == 0.90 and r["eps_basic"].period == "FY2025"
    assert r["eps_diluted"].unit == "USD per share"


def test_the_dropped_indicators_are_not_calculated():
    ids = {s.id for s in ind.SPECS}
    assert not ids & {"interest_rate_shock", "cross_source_discrepancy"}


def test_every_indicator_belongs_to_a_group_for_the_form():
    groups = {s.group for s in ind.SPECS}
    assert groups == {"Valuation", "Historical comparison", "Debt and liquidity", "Profitability", "Cash flow and dividends", "Growth",
                      "Per share and market"}
    assert len(ind.SPECS) >= 58


# ---------- demo data: price returns and historical medians ----------

ON = date(2026, 11, 20)


def test_demo_company_has_price_returns_and_historical_medians_from_what_was_known_then():
    r = {x.indicator: x for x in ind.analyse(demo_company_inputs(D.TARGET, ON))["current"]}
    for key in ("price_return_1m", "price_return_3m", "price_return_12m", "pe_hist_median", "pe_vs_hist", "ev_ebitda_hist_median",
                "dividend_yield", "free_float", "revenue_cagr", "quick_ratio", "gross_margin"):
        assert r[key].status == "calculated", (key, r[key].note)
    median = r["pe_hist_median"]
    assert "4 of 5" in median.note  # the 2021 year end would need FY2020, which the demo does not have
    for observation in median.inputs:  # each year-end multiple uses only reports published by that year end
        published = [s["published"] for s in observation["sources"] if s.get("published")]
        assert published and max(published) <= observation["period"], observation["name"]
    assert r["pe_vs_hist"].value == pytest.approx(r["pe"].value / median.value - 1)
    assert r["revenue_cagr"].period == "FY2021–FY2025" and "4-year" in r["revenue_cagr"].note


def test_fewer_than_three_year_ends_give_no_historical_median():
    r = {x.indicator: x for x in ind.analyse(demo_company_inputs(D.TARGET, date(2023, 11, 20)))["current"]}
    assert r["pe_hist_median"].status == "missing" and "fewer than three" in r["pe_hist_median"].note


def test_the_us_gaap_interest_rule_lets_standardised_fcf_be_built_without_an_interest_amount():
    c = extended()
    for period in c.periods.values():
        period.pop("interest_paid_in_cfo", None)
    assert current(c)["p_fcf"].value == pytest.approx(2000 / 90)  # without the rule: reported basis
    c.interest_rule = "US GAAP classifies interest paid within operating activities (ASC 230), so no interest adjustment is needed."
    r = current(c)["p_fcf"]
    assert r.value == pytest.approx(2000 / 83)
    fcf = next(i for i in r.inputs if i["name"] == "fcf_standardised")
    assert fcf["value"] == pytest.approx(83)


# ---------- gaps in the source data (decided 27 November 2026) ----------

def test_without_dividends_per_share_paid_the_yield_is_estimated_from_cash_dividends():
    c = extended()
    for period in c.periods.values():
        period.pop("dividends_per_share", None)
    r = current(c)["dividend_yield"]
    # TTM common dividends paid 30 + 24 − 21 = 33 (USD millions) ÷ 100 million shares at Q3 2026 = 0.33 per share; ÷ price 20
    assert r.status == "estimated" and r.value == pytest.approx(0.33 / 20)
    assert "estimated" in r.note.lower() and "cash dividends paid" in r.note
    assert {i["name"] for i in r.inputs} >= {"dividends_paid_common", "shares_outstanding", "price"}


def test_percentages_are_compared_with_the_peer_median_in_percentage_points():
    target = ind.analyse(extended())
    peers = {f"P{i}": ind.analyse(extended(price=fig("price", p, "close 2026-11-20", "USD per share"))) for i, p in enumerate((10.0, 25.0, 40.0))}
    rows = {row["indicator"]: row for row in ind.compare_with_peers(target, peers)}
    fcf_yield = rows["fcf_yield"]
    assert fcf_yield["comparison"] == pytest.approx(fcf_yield["company_value"] - fcf_yield["peer_median"])
    assert fcf_yield["comparison_type"] == "percentage-point difference"
    assert rows["pe"]["comparison_type"].startswith("peer discount")  # multiples keep the peer discount
    assert rows["asset_turnover"]["comparison"] is None  # a multiple without a v1.0 comparison stays median only


def test_a_field_the_data_source_does_not_have_is_explained():
    c = extended()
    for period in c.periods.values():
        period.pop("free_float_shares", None)
    c.source_gaps = {"free_float_shares": "The SEC's data has no free-float share count."}
    assert "The SEC's data has no free-float share count." in current(c)["free_float"].note


def test_an_omitted_historical_median_says_what_was_missing_at_each_year_end():
    r = {x.indicator: x for x in ind.analyse(demo_company_inputs(D.TARGET, date(2023, 11, 20)))["current"]}
    note = r["pe_hist_median"].note
    assert "fewer than three" in note and "At 2021-12-31:" in note


def test_ev_sales_and_ev_ebit_are_also_compared_with_their_own_history():
    r = {x.indicator: x for x in ind.analyse(demo_company_inputs(D.TARGET, ON))["current"]}
    for base, name in (("ev_sales", "EV/sales"), ("ev_ebit", "EV/EBIT")):
        median, against = r[f"{base}_hist_median"], r[f"{base}_vs_hist"]
        assert median.status == "calculated" and median.name == f"{name} historical median", (base, median.note)
        assert against.value == pytest.approx(r[base].value / median.value - 1)
    assert ind.SPECS_BY_ID["ev_sales_hist_median"].not_for_financials  # like EV/sales itself


def test_twelve_months_never_mix_the_standard_d_and_a_with_the_companys_own_element():
    c = extended()
    del c.periods["YTD Q3 2025"]["depreciation_amortisation"]  # standard D&A missing in one part of the twelve months
    for period, value in (("FY2025", 32), ("YTD Q3 2026", 26), ("YTD Q3 2025", 23)):  # the company's broader own element, all parts
        c.periods[period]["depreciation_amortisation_own"] = fig("depreciation_amortisation_own", value, period)
    r = current(c)
    ebitda = next(i for i in r["ev_ebitda"].inputs if i["name"] == "ebitda")
    assert ebitda["value"] == pytest.approx(170 + (32 + 26 - 23))  # EBIT 170 + own D&A 35, not standard and own mixed
    assert r["ev_ebitda"].status == "calculated"
    del c.periods["YTD Q3 2026"]["depreciation_amortisation_own"]  # neither set complete: missing, never mixed
    assert current(c)["ev_ebitda"].status == "missing"


def test_a_historical_median_says_when_some_year_ends_use_the_companys_own_element():
    from backend.indicators import Figure
    c = demo_company_inputs(D.TARGET, ON)
    for period in ("FY2024", "YTD Q3 2025", "YTD Q3 2024"):  # the year end 2025-12-31 set, moved to the company's own element
        f = c.periods[period].pop("depreciation_amortisation")
        sources = [{**s, "tag": "nrth:DepreciationAmortizationAndOther"} for s in f.sources]
        c.periods[period]["depreciation_amortisation_own"] = Figure("depreciation_amortisation_own", f.value, f.unit, f.period, sources)
    r = {x.indicator: x for x in ind.analyse(c)["current"]}
    assert r["ev_ebitda_hist_median"].status == "calculated"
    assert "company's own" in r["ev_ebitda_hist_median"].note and "company's own" not in r["pe_hist_median"].note
