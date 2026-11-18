# Peer selection: recorded origins, verification of model suggestions, transparent criteria, user picks, index filter, no padding.
from backend.peer_selection import (SOURCE_MODEL, SOURCE_OFFICIAL_REPORT, SOURCE_PROVIDER, SOURCE_USER, Candidate, Profile,
                                    merge_candidates, select_peers)
from tests.helpers import make_settings

TARGET = Profile("TGT", "Target Co", industry="Oil & Gas", products=["crude oil", "natural gas"],
                 customer_groups=["refiners"], revenue_segments=["upstream", "downstream"], operating_model="integrated",
                 revenue_by_region={"North America": 0.7, "Europe": 0.3}, revenue=100.0, market_cap=200.0)


def peer(ticker, source=SOURCE_PROVIDER, industry="Oil & Gas", indices=(), **kw):
    defaults = dict(products=["crude oil"], customer_groups=["refiners"], revenue_segments=["upstream"],
                    operating_model="integrated", revenue_by_region={"North America": 0.6}, revenue=80.0, market_cap=150.0)
    defaults.update(kw)
    return Candidate(Profile(ticker, ticker, industry=industry, indices=list(indices), **defaults), [{"type": source, "detail": "test"}])


def test_fills_to_five_counting_user_picks_and_labels_limited_ones(tmp_path):
    settings = make_settings(tmp_path)
    user_pick = peer("BANK", SOURCE_USER, industry="Banks", products=["loans"], customer_groups=["households"],
                     revenue_segments=["lending"], operating_model="bank")
    candidates = [user_pick, peer("A"), peer("B"), peer("C"), peer("D"), peer("E"),
                  peer("GUESS", SOURCE_MODEL), peer("RETAIL", industry="Retail")]
    result = select_peers(TARGET, candidates, settings)
    tickers = [p["ticker"] for p in result["peers"]]
    assert len(tickers) == 5 and tickers[0] == "BANK"
    assert result["peers"][0]["label"] == "user-requested comparison (limited comparability)"
    assert "caution" in result["peers"][0]["explanation"]
    reasons = {e["ticker"]: e["reason"] for e in result["excluded"]}
    assert "not yet verified" in reasons["GUESS"] and reasons["RETAIL"].startswith("Not suitable")


def test_explicit_request_beyond_five_is_honoured(tmp_path):
    candidates = [peer(t) for t in "ABCDEFG"]
    result = select_peers(TARGET, candidates, make_settings(tmp_path), requested_total=7)
    assert len(result["peers"]) == 7


def test_never_pads_with_unsuitable_companies_and_discloses_missing_information(tmp_path):
    sparse = peer("SPARSE", revenue_by_region={}, revenue=None, market_cap=None)
    result = select_peers(TARGET, [sparse, peer("WRONG", industry="Software")], make_settings(tmp_path))
    assert [p["ticker"] for p in result["peers"]] == ["SPARSE"]
    assert set(result["peers"][0]["missing_information"]) == {"Geographic exposure", "Revenue", "Market capitalisation"}
    assert any("no unsuitable companies were added" in n for n in result["notes"])


def test_index_filter_is_optional_and_expands_when_too_few(tmp_path):
    candidates = [peer("IN1", indices=["S&P 500"]), peer("OUT1"), peer("OUT2"), peer("OUT3")]
    result = select_peers(TARGET, candidates, make_settings(tmp_path), index_filter="S&P 500")
    assert result["peers"][0]["ticker"] == "IN1" and len(result["peers"]) == 3
    assert any("outside the index" in n for n in result["notes"])


def test_ordering_prefers_business_then_geography_then_size(tmp_path):
    far = peer("FAR", revenue_by_region={"Asia": 0.9})
    small = peer("SMALL", revenue=1.0, market_cap=1.0)
    best = peer("BEST", products=["crude oil", "natural gas"], revenue_segments=["upstream", "downstream"])
    result = select_peers(TARGET, [far, small, best], make_settings(tmp_path), requested_total=3)
    assert [p["ticker"] for p in result["peers"]] == ["BEST", "SMALL", "FAR"]
    assert "not by a combined score" in result["method"]


def test_merge_keeps_every_origin_and_verifies_model_suggestions(tmp_path):
    merged = merge_candidates([peer("X", SOURCE_MODEL)], [peer("X", SOURCE_OFFICIAL_REPORT)])
    assert len(merged) == 1 and merged[0].verified
    assert {s["type"] for s in merged[0].sources} == {SOURCE_MODEL, SOURCE_OFFICIAL_REPORT}
    assert not select_peers(TARGET, [], make_settings(tmp_path))["peers"]
