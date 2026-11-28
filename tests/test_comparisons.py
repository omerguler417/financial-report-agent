# Comparison lines written by Python from the calculated results (approved 27 November 2026): the company against the peer median,
# against its own history, against each peer's own history, and its trend over the horizon. They describe differences only and must
# pass the same wording check as the text model's statements; every line cites the results it was built from.
from fastapi.testclient import TestClient

from backend import comparisons, main
from backend import validation as V
from tests.helpers import make_settings, sample_app


def result(indicator, name, value, unit, period="TTM to Q1 2027", status="calculated", inputs=None):
    return {"indicator": indicator, "name": name, "value": value, "unit": unit, "period": period, "status": status, "inputs": inputs or []}


def row(indicator, median, count, used, peer_values=None):
    return {"indicator": indicator, "peer_median": median, "peer_count": count, "peers_used": used, "peer_values": peer_values or {}}


def report(current, comparison, history=None, horizon=5):
    return {"agent1": {"indicators": {"current": current, "history": history or {}, "horizon_years": horizon}, "peer_comparison": comparison}}


def lines_for(out, indicator):
    return [line["text"] for line in out["by_indicator"].get(indicator, [])]


def test_the_company_is_compared_with_the_peer_median():
    out = comparisons.build(report(
        [result("pe", "P/E", 25.51, "x"), result("net_margin", "Net profit margin", 0.4117, "fraction"),
         result("current_ratio", "Current ratio", 1.22, "x")],
        [row("pe", 14.63, 2, ["ORCL", "ADBE"]), row("net_margin", 0.2887, 4, ["ORCL", "ADBE", "CRM", "INTU"]),
         row("current_ratio", 1.22, 3, ["ORCL", "ADBE", "CRM"])]))
    assert lines_for(out, "pe") == ["P/E: 25.51x, 74.4% above the peer median of 14.63x. Only 2 peer values (ORCL, ADBE); v1.0 aims for "
                                    "at least three."]
    assert lines_for(out, "net_margin") == ["Net profit margin: 41.17%, 12.30 percentage points above the peer median of 28.87%."]
    assert lines_for(out, "current_ratio") == ["Current ratio: 1.22x, the same as the peer median of 1.22x."]
    five = comparisons.build(report([result("pb", "P/B", 7.73, "x")], [row("pb", 6.22, 3, ["A", "B", "C"], {t: {} for t in "ABCDE"})]))
    assert lines_for(five, "pb") == ["P/B: 7.73x, 24.3% above the peer median of 6.22x. Based on 3 of 5 peers (A, B, C)."]
    assert out["by_indicator"]["pe"][0]["cites"] == [{"indicator": "pe", "period": "TTM to Q1 2027"}, {"indicator": "pe", "period": "peer median"}]


def test_own_history_and_each_peers_own_history_are_compared():
    median = result("pe_hist_median", "P/E historical median", 31.9, "x", "year ends 2022–2025", inputs=[{}, {}, {}, {}])
    against = result("pe_vs_hist", "P/E against its historical median", -0.2003, "fraction", "TTM to Q1 2027")
    peers = {"ORCL": {"value": 28.1, "status": "calculated"}, "ADBE": {"value": 35.0, "status": "calculated"},
             "CRM": {"value": None, "status": "missing"}}
    out = comparisons.build(report([median, against], [row("pe_hist_median", 31.55, 2, ["ORCL", "ADBE"], peers),
                                                       row("pe_vs_hist", -0.05, 2, ["ORCL", "ADBE"])]))
    assert lines_for(out, "pe_vs_hist")[0] == ("P/E is 20.0% below its own median of 31.90x over 4 year ends (2022–2025; the horizon "
                                                   "is 5 years).")
    assert lines_for(out, "pe_hist_median") == ["The company's 5-year P/E median of 31.90x is above those of 1 and below those of 1 of the 2 "
                                                "peers (ORCL 28.10x, ADBE 35.00x)."]
    assert "15.03 percentage points below the peer median of -5.00%" in lines_for(out, "pe_vs_hist")[1]


def test_the_trend_over_the_horizon_is_described():
    def year(fy, value):
        return [result("net_margin", "Net profit margin", value, "fraction", fy)]
    now = [result("net_margin", "Net profit margin", 0.37, "fraction")]
    steady = comparisons.build(report(now, [], {"FY2024": year("FY2024", 0.30), "FY2025": year("FY2025", 0.33), "FY2026": year("FY2026", 0.36)}))
    assert lines_for(steady, "net_margin") == ["Net profit margin was 30.00% in FY2024 and 36.00% in FY2026: higher each year."]
    mixed = comparisons.build(report(now, [], {"FY2024": year("FY2024", 0.30), "FY2025": year("FY2025", 0.25), "FY2026": year("FY2026", 0.36)}))
    assert lines_for(mixed, "net_margin") == ["Net profit margin was 30.00% in FY2024 and 36.00% in FY2026: higher overall, moving in "
                                              "both directions in between."]


def test_each_group_has_a_short_summary_led_by_its_key_indicators():
    out = comparisons.build(report(
        [result("roe_common", "Common ROE", 0.30, "fraction"), result("net_margin", "Net profit margin", 0.40, "fraction"),
         result("gross_margin", "Gross margin", 0.60, "fraction")],
        [row("roe_common", 0.20, 3, ["A", "B", "C"]), row("net_margin", 0.45, 3, ["A", "B", "C"]), row("gross_margin", 0.50, 3, ["A", "B", "C"])]))
    [group] = out["groups"]
    assert group["group"] == "Profitability"
    assert group["lines"][0]["text"] == "Of the 3 profitability measures that differ from the peer median, 2 are above it and 1 below it."
    assert group["lines"][1]["text"].startswith("Common ROE") and len(group["lines"]) <= comparisons.MAX_GROUP_LINES


def test_a_demo_analysis_gets_comparison_lines_that_pass_the_wording_check_and_cite_real_results(tmp_path):
    c = sample_app(tmp_path)
    state = c.post("/api/analyses", json={"company": "Northgate", "as_of": "2026-11-20"}).json()
    rep = c.get(f"/api/analyses/{state['id']}/report").json()
    view = c.get(f"/api/analyses/{state['id']}/view").json()
    out = view["comparisons"]
    lines = [line for lines in out["by_indicator"].values() for line in lines]
    assert len(lines) > 30 and {line["kind"] for line in lines} >= {"peers", "history", "trend", "peer history"}
    for line in lines + [line for g in out["groups"] for line in g["lines"]]:
        assert V.wording_issues(line["text"]) == [], line["text"]
    known = {(r["indicator"], r["period"]) for r in rep["agent1"]["indicators"]["current"]}
    known |= {(r["indicator"], r["period"]) for rows in rep["agent1"]["indicators"]["history"].values() for r in rows}
    known |= {(row["indicator"], "peer median") for row in rep["agent1"]["peer_comparison"]}
    for line in lines:
        for cite in line["cites"]:
            assert (cite["indicator"], cite["period"]) in known, (line["text"], cite)
    history_group = next(g for g in out["groups"] if g["group"] == "Historical comparison")
    assert not any(line["kind"] == "summary" for line in history_group["lines"])  # no count mixing own history with peers
    peer_rows = {row["indicator"]: row for row in rep["agent1"]["peer_comparison"]}
    assert set(peer_rows["pe_hist_median"]["peer_values"]) == {"CRBN.DEMO", "RDGE.DEMO", "SLTK.DEMO"}  # every peer's own value is kept
    headings = [b["text"] for b in view["blocks"] if b["type"] == "heading"]
    assert "Profitability" in headings and any(h.endswith("Financial analysis") for h in headings)  # the lines are in the report too


def test_the_tables_get_their_display_values_from_python():
    median = result("pe_hist_median", "P/E historical median", 31.9, "x", "year ends 2022–2025")
    against = result("pe_vs_hist", "P/E against its historical median", -0.2003, "fraction")
    margins = {fy: [result("net_margin", "Net profit margin", v, "fraction", fy)] for fy, v in (("FY2024", 0.30), ("FY2026", 0.36))}
    out = comparisons.build(report(
        [result("pe", "P/E", 25.51, "x"), median, against, result("net_margin", "Net profit margin", 0.4117, "fraction"),
         result("dividend_yield", "Dividend yield", None, "fraction", status="missing")],
        [row("pe", 14.63, 2, ["ORCL", "ADBE"], {"ORCL": {"value": 30.2, "status": "calculated"}, "CRM": {"value": None, "status": "missing"}}),
         row("net_margin", 0.2887, 3, ["A", "B", "C"]), row("dividend_yield", 0.01, 3, ["A", "B", "C"])], margins))
    cells = out["cells"]
    assert cells["pe"] == {"value": "25.51x", "peer_median": "14.63x", "difference": "+74.4%", "own_history": "median 31.90x, now -20.0%",
                           "peers": {"ORCL": "30.20x", "CRM": "missing"}}
    assert cells["net_margin"]["difference"] == "+12.30 pp" and cells["net_margin"]["own_history"] == "30.00% → 36.00% (FY2024–FY2026)"
    assert cells["dividend_yield"]["value"] == "—" and cells["dividend_yield"]["difference"] == "—"


def test_a_group_summary_also_says_how_its_key_measures_moved_over_time():
    def years(indicator, name, values):
        return {fy: [result(indicator, name, v, "fraction", fy)] for fy, v in zip(("FY2024", "FY2025", "FY2026"), values)}
    history = {fy: years("roe_common", "Common ROE", (0.2, 0.25, 0.3))[fy] + years("net_margin", "Net profit margin", (0.3, 0.28, 0.26))[fy]
               + years("gross_margin", "Gross margin", (0.5, 0.5, 0.6))[fy] for fy in ("FY2024", "FY2025", "FY2026")}
    out = comparisons.build(report(
        [result("roe_common", "Common ROE", 0.30, "fraction"), result("net_margin", "Net profit margin", 0.40, "fraction"),
         result("gross_margin", "Gross margin", 0.60, "fraction")],
        [row("roe_common", 0.20, 3, ["A", "B", "C"]), row("net_margin", 0.45, 3, ["A", "B", "C"])], history))
    [group] = out["groups"]
    trends = [line["text"] for line in group["lines"] if line["kind"] == "trend"]
    assert trends == ["Common ROE was 20.00% in FY2024 and 30.00% in FY2026: higher each year.",
                      "Net profit margin was 30.00% in FY2024 and 26.00% in FY2026: lower each year."]  # key measures first, at most two


def test_the_own_history_cell_is_short_enough_for_a_table():
    years = {fy: [result("bvps", "Book value per share", v, "USD per share", fy)] for fy, v in (("FY2021", 18.88), ("FY2026", 59.56))}
    out = comparisons.build(report([result("bvps", "Book value per share", 63.35, "USD per share")], [], years))
    assert out["cells"]["bvps"]["own_history"] == "18.88 → 59.56 (FY2021–FY2026)"
