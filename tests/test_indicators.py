# Step 3: indicator calculations to docs/indicator_definitions.md v1.0. Hand-checked on a small sample company, then run on the demo data.
import statistics
from datetime import date

import pytest

from backend import indicators as ind
from backend.demo import demo_data as D
from backend.demo.demo_providers import demo_company_inputs
from backend.indicators import CompanyInputs, Figure

M = "USD millions"
UNITS = {"shares_outstanding": "millions of shares", "statutory_tax_rate": "percent"}


def fig(name, value, period, unit=None):
    return Figure(name, value, unit or UNITS.get(name, M), period, [{"doc_id": f"doc-{period}", "page": 3, "line": f"{name} [{period}] {value}"}])


def period(label, **values):
    return {k: fig(k, v, label) for k, v in values.items()}


def price(value, unit="USD per share"):
    return Figure("price", value, unit, "close 2026-11-20", [{"publisher": "Test prices", "date": "2026-11-20"}])


def sample(**changes) -> CompanyInputs:
    """A small company whose results are easy to check by hand. TTM = FY2025 + YTD Q3 2026 − YTD Q3 2025."""
    periods = {
        "FY2024": period("FY2024", revenue=800, ebit=100, depreciation_amortisation=20, interest_expense=10, net_income_group=60,
                         net_income_common=55, cfo_reported=90, capex=40, assets_total=1000, equity_common=380, nci=20, equity_total=400,
                         debt_ex_leases=200, lease_liabilities=20, cash_eligible=50, current_assets=300, current_liabilities=150,
                         shares_outstanding=100, statutory_tax_rate=21),
        "FY2025": period("FY2025", revenue=1000, ebit=150, depreciation_amortisation=30, interest_expense=12, net_income_group=100,
                         net_income_common=90, cfo_reported=140, capex=50, assets_total=1200, equity_common=450, nci=50, equity_total=500,
                         debt_ex_leases=250, lease_liabilities=30, cash_eligible=80, current_assets=360, current_liabilities=180,
                         shares_outstanding=100, statutory_tax_rate=21),
        "YTD Q3 2026": period("YTD Q3 2026", revenue=800, ebit=120, depreciation_amortisation=24, interest_expense=9, net_income_group=80,
                              net_income_common=72, cfo_reported=110, capex=45, assets_total=1300, equity_common=480, nci=20, equity_total=500,
                              debt_ex_leases=260, lease_liabilities=40, cash_eligible=100, current_assets=390, current_liabilities=195,
                              shares_outstanding=100),
        "YTD Q3 2025": period("YTD Q3 2025", revenue=700, ebit=100, depreciation_amortisation=21, interest_expense=9, net_income_group=70,
                              net_income_common=63, cfo_reported=100, capex=35, assets_total=1100, equity_common=420, nci=20, equity_total=440,
                              debt_ex_leases=240, lease_liabilities=25, cash_eligible=70, current_assets=330, current_liabilities=165,
                              shares_outstanding=100),
    }
    base = dict(name="Sample Co", periods=periods, latest_fy="FY2025", ytd_current="YTD Q3 2026", ytd_prior="YTD Q3 2025", price=price(20.0))
    return CompanyInputs(**{**base, **changes})


def current(c):
    return {r.indicator: r for r in ind.analyse(c)["current"]}


# ---------- hand-checked values ----------

def test_core_indicators_match_hand_calculations():
    # TTM: revenue 1100, EBIT 170, D&A 33 (EBITDA 203), interest 12, group NI 110, common NI 99, CFO 150, capex 60 (FCF 90).
    # At Q3 2026: market cap 20 × 100 = 2000, debt incl. leases 300, net debt 200, EV 2000 + 300 + NCI 20 − cash 100 = 2220.
    # Averages of Q3 2025 and Q3 2026: common equity 450, assets 1200, invested capital (635 + 700) / 2 = 667.5.
    expected = {"pe": 2000 / 99, "ps": 2000 / 1100, "pb": 2000 / 480, "p_fcf": 2000 / 90, "ev_ebitda": 2220 / 203, "fcf_yield": 90 / 2000,
                "debt_equity": 300 / 500, "net_debt_equity": 200 / 500, "net_debt_ebitda": 200 / 203, "current_ratio": 2.0,
                "interest_coverage": 170 / 12, "roe_common": 99 / 450, "roa_group": 110 / 1200, "roic": 170 * 0.79 / 667.5,
                "net_margin": 0.1, "ebitda_margin": 203 / 1100, "revenue_growth": 800 / 700 - 1, "fcf_conversion": 90 / 110, "bvps": 4.8}
    r = current(sample())
    for key, value in expected.items():
        assert r[key].status == "calculated", (key, r[key].note)
        assert r[key].value == pytest.approx(value), key
    assert r["pe"].unit == "x" and r["roe_common"].unit == "fraction" and r["bvps"].unit == "USD per share"
    assert r["debt_equity"].other_views["excluding_leases"] == pytest.approx(260 / 500)  # borrowings at Q3 2026
    assert all(x.definition_version == "v1.0" and x.formula for x in r.values())


def test_ttm_combines_three_reports_and_cites_each_of_them():
    ps = current(sample())["ps"]
    revenue = next(i for i in ps.inputs if i["name"] == "revenue")
    assert revenue["value"] == 1100 and ps.period.startswith("TTM")
    assert {s["doc_id"] for s in revenue["sources"]} == {"doc-FY2025", "doc-YTD Q3 2026", "doc-YTD Q3 2025"}
    market_cap = next(i for i in ps.inputs if i["name"] == "market_cap")
    assert any(s.get("publisher") == "Test prices" for s in market_cap["sources"])
    assert any(s.get("doc_id") == "doc-YTD Q3 2026" for s in market_cap["sources"])  # the share count's page


def test_history_uses_year_end_averages_and_never_invents_an_opening_balance():
    history = ind.analyse(sample())["history"]
    fy25, fy24 = ({r.indicator: r for r in history[y]} for y in ("FY2025", "FY2024"))
    assert fy25["roe_common"].value == pytest.approx(90 / ((380 + 450) / 2))
    assert fy25["revenue_growth"].value == pytest.approx(0.25)
    assert fy24["roe_common"].status == "missing" and "not invented" in fy24["roe_common"].note
    assert fy24["revenue_growth"].status == "missing"
    assert "pe" not in fy25  # multiples at past year ends need the prices and reports available then; not in this step


def test_multi_year_fcf_conversion_sums_the_years_and_labels_a_shorter_window():
    r = current(sample())["fcf_conversion_5y"]
    assert r.value == pytest.approx((50 + 90) / (60 + 100))  # not the average of the yearly ratios
    assert r.period == "FY2024–FY2025" and "2 years" in r.note


# ---------- statuses ----------

def test_not_meaningful_cases_are_explained_not_hidden():
    c = sample()
    c.periods["YTD Q3 2026"]["net_income_common"] = fig("net_income_common", -200, "YTD Q3 2026")
    pe = current(c)["pe"]
    assert pe.status == "not_meaningful" and pe.value is None and "not a cheapness signal" in pe.note and pe.inputs

    c = sample()
    c.periods["FY2025"]["interest_expense"] = fig("interest_expense", 0, "FY2025")  # TTM 0 + 9 − 9 = 0
    cover = current(c)["interest_coverage"]
    assert cover.status == "not_meaningful" and "No interest expense" in cover.note

    c = sample()
    c.periods["YTD Q3 2026"]["cash_eligible"] = fig("cash_eligible", 500, "YTD Q3 2026")
    nde = current(c)["net_debt_equity"]
    assert nde.status == "calculated" and nde.value == pytest.approx(-200 / 500) and "net cash" in nde.note


def test_missing_inputs_are_never_treated_as_zero():
    c = sample()
    del c.periods["YTD Q3 2025"]["capex"]
    r = current(c)
    assert r["p_fcf"].status == "missing" and r["p_fcf"].value is None
    assert "capex" in r["p_fcf"].note and "not treated as zero" in r["p_fcf"].note
    assert r["pe"].status == "calculated"
    assert current(sample(price=None))["pe"].status == "missing"


def test_different_currencies_or_scales_are_not_combined():
    assert current(sample(price=price(20.0, "EUR per share")))["pe"].status == "not_comparable"
    c = sample()
    c.periods["FY2025"]["capex"] = fig("capex", 50000, "FY2025", "USD thousands")
    r = current(c)
    assert r["p_fcf"].status == "not_comparable" and "USD thousands" in r["p_fcf"].note


def test_banks_do_not_get_industrial_metrics():
    r = current(sample(business_model="bank"))
    for key in ("ev_ebitda", "net_debt_ebitda", "current_ratio", "p_fcf", "fcf_yield", "fcf_conversion", "ebitda_margin", "roic",
                "debt_equity", "net_debt_equity", "interest_coverage"):
        assert r[key].status == "not_applicable" and "section 8" in r[key].note, key
    for key in ("pe", "pb", "roe_common", "roa_group", "bvps"):
        assert r[key].status == "calculated", key


def test_negative_enterprise_value_is_shown_but_kept_out_of_peer_medians():
    c = sample()
    c.periods["YTD Q3 2026"]["cash_eligible"] = fig("cash_eligible", 3000, "YTD Q3 2026")  # EV 2000 + 300 + 20 − 3000 = −680
    ev = current(c)["ev_ebitda"]
    assert ev.status == "calculated" and ev.value == pytest.approx(-680 / 203) and ev.exclude_from_peer_median


def test_roic_uses_the_home_country_rate_stated_in_the_report():
    roic = current(sample())["roic"]
    rate = next(i for i in roic.inputs if i["name"] == "statutory_tax_rate")
    assert rate["value"] == 21 and rate["period"] == "FY2025" and rate["sources"]

    c = sample()
    del c.periods["FY2025"]["statutory_tax_rate"]  # never borrowed from another year
    roic = current(c)["roic"]
    assert roic.status == "missing" and "statutory" in roic.note

    c = sample()
    c.periods["FY2025"]["ebit"] = fig("ebit", -500, "FY2025")  # TTM EBIT −480
    roic = current(c)["roic"]
    assert roic.value == pytest.approx(-480 / 667.5) and "No tax benefit" in roic.note


def test_only_the_seven_v1_statuses_are_ever_used():
    cases = [sample(), sample(price=None), sample(business_model="bank"), sample(price=price(1.0, "EUR per share"))]
    for c in cases:
        analysis = ind.analyse(c)
        results = analysis["current"] + [r for rs in analysis["history"].values() for r in rs]
        assert {r.status for r in results} <= set(ind.STATUSES)


# ---------- peers ----------

def test_peer_medians_use_only_meaningful_values_and_flag_small_groups():
    loss_maker = sample()
    loss_maker.periods["YTD Q3 2026"]["net_income_common"] = fig("net_income_common", -200, "YTD Q3 2026")
    peers = {"P1": ind.analyse(sample(price=price(30.0))), "P2": ind.analyse(sample(price=price(50.0))), "P3": ind.analyse(loss_maker)}
    rows = {row["indicator"]: row for row in ind.compare_with_peers(ind.analyse(sample()), peers)}
    pe = rows["pe"]
    assert pe["peer_count"] == 2 and pe["peers_used"] == ["P1", "P2"]  # the loss-maker's NM P/E is left out
    assert pe["peer_median"] == pytest.approx(statistics.median([3000 / 99, 5000 / 99]))
    assert pe["comparison"] == pytest.approx(1 - (2000 / 99) / (4000 / 99)) and "peer discount" in pe["comparison_type"]
    assert "Only 2" in pe["note"]
    roe = rows["roe_common"]
    assert roe["comparison_type"] == "percentage-point difference" and roe["comparison"] == pytest.approx(0.0)
    assert "bvps" not in rows  # per-share amounts depend on share counts and are not compared across companies


# ---------- demo data ----------

ON = date(2026, 11, 20)


def test_demo_company_runs_end_to_end_with_every_number_sourced():
    c = demo_company_inputs(D.TARGET, ON)
    analysis = ind.analyse(c)
    r = {x.indicator: x for x in analysis["current"]}
    assert analysis["demo"] and D.DEMO_LABEL in analysis["notes"][0]
    assert all(x.status == "calculated" for x in r.values()), {k: x.note for k, x in r.items() if x.status != "calculated"}

    f = D.financials(D.TARGET)
    fy, cur, prev = f["annual"]["FY2025"], f["ytd"]["YTD Q3 2026"], f["ytd"]["YTD Q3 2025"]
    close = [b for b in D.price_bars(D.TARGET, ON) if b["day"] <= ON][-1]["close"]
    assert c.price.value == close
    net_common = fy["net_income_common"] + cur["net_income_common"] - prev["net_income_common"]
    assert r["pe"].value == pytest.approx(close * cur["shares_outstanding"] / net_common)
    assert r["fcf_conversion_5y"].period == "FY2021–FY2025"

    docs = {d["doc_id"]: d for d in D.documents(D.TARGET)}
    for x in r.values():
        for i in x.inputs:
            assert i["sources"] and all(s.get("demo") for s in i["sources"]), (x.indicator, i["name"])
            for s in i["sources"]:
                if "doc_id" in s:  # the cited page really contains the cited line
                    assert s["line"] in docs[s["doc_id"]]["pages"][s["page"] - 1]


def test_demo_bank_and_demo_peers():
    bank = {x.indicator: x for x in ind.analyse(demo_company_inputs("LKSB.DEMO", ON))["current"]}
    assert bank["ev_ebitda"].status == "not_applicable" and bank["pe"].status == "calculated"
    target = ind.analyse(demo_company_inputs(D.TARGET, ON))
    peers = {t: ind.analyse(demo_company_inputs(t, ON)) for t in ("RDGE.DEMO", "SLTK.DEMO", "CRBN.DEMO")}
    pe = next(row for row in ind.compare_with_peers(target, peers) if row["indicator"] == "pe")
    assert pe["peer_count"] == 3 and "Only" not in pe["note"]
