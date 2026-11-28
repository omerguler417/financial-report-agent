# Plain-language comparison lines for the dashboard and the report, written by Python from the calculated results (never by the text
# model): the company against the peer median, against its own history, against each peer's own history, and its trend over the
# horizon. Wording describes differences only ("above", "below", "higher", "lower"); it never judges value or recommends anything.
# Every line cites the calculated results it was built from. Works on saved reports, so older analyses get the lines too.
from backend.report_blocks import display

USABLE = {"calculated", "estimated", "reported_only"}
from backend.indicators import HIST_NAMES as HIST_BASES  # noqa: E402  the multiples compared with their own history
# Indicators whose lines lead each group's summary, in this order
KEY = {
    "Valuation": ["pe", "ev_ebitda", "p_fcf", "fcf_yield"],
    "Historical comparison": ["pe_vs_hist", "ev_ebitda_vs_hist", "pe_hist_median"],
    "Debt and liquidity": ["net_debt_ebitda", "current_ratio", "interest_coverage"],
    "Profitability": ["roe_common", "net_margin", "roic"],
    "Cash flow and dividends": ["fcf_margin", "fcf_conversion", "dividend_yield"],
    "Growth": ["revenue_growth", "revenue_cagr", "eps_growth"],
    "Per share and market": ["price_return_12m", "price_return_3m"],
}
MAX_GROUP_LINES = 4  # comparison lines (peers and own history) in a group's summary
MAX_TREND_LINES = 2  # plus how its key measures moved over the horizon


def _cite(result: dict) -> dict:
    return {"indicator": result["indicator"], "period": result["period"]}


def _peer_cite(row: dict) -> dict:
    return {"indicator": row["indicator"], "period": "peer median"}


def _line(text: str, kind: str, *cites) -> dict:
    return {"text": text, "kind": kind, "cites": list(cites)}


def _same(a: float, b: float, unit: str) -> bool:
    return display(a, unit) == display(b, unit)


def _estimated(result: dict) -> str:
    return " (estimated)" if result["status"] == "estimated" else ""


def _peer_line(result: dict, row: dict) -> dict | None:
    """The company against the peer median: a relative difference for multiples, percentage points for percentages."""
    median, value, unit = row.get("peer_median"), result.get("value"), result["unit"]
    if median is None or value is None or result["status"] not in USABLE:
        return None
    name, shown, shown_median = result["name"], display(value, unit), display(median, unit)
    head = f"{name}: {shown}{_estimated(result)}, "
    if _same(value, median, unit):
        text = head + f"the same as the peer median of {shown_median}."
    elif unit == "fraction":
        diff = (value - median) * 100
        text = head + f"{abs(diff):,.2f} percentage points {'above' if diff > 0 else 'below'} the peer median of {shown_median}."
    elif median > 0 and value > 0:
        diff = (value / median - 1) * 100
        text = head + f"{abs(diff):,.1f}% {'above' if diff > 0 else 'below'} the peer median of {shown_median}."
    else:
        text = head + f"{'higher' if value > median else 'lower'} than the peer median of {shown_median}."
    count, used = row.get("peer_count", 0), row.get("peers_used", [])
    total = max(len(row.get("peer_values") or {}), count)
    if count < 3:
        text += f" Only {count} peer value{'s' if count != 1 else ''} ({', '.join(used)}); v1.0 aims for at least three."
    elif count < total:
        text += f" Based on {count} of {total} peers ({', '.join(used)})."
    return _line(text, "peers", _cite(result), _peer_cite(row))


def _history_line(against: dict, median: dict, horizon: int) -> dict | None:
    """The current multiple against the company's own median at past year ends."""
    if against["status"] != "calculated" or median["status"] != "calculated":
        return None
    base = against["indicator"].removesuffix("_vs_hist")
    diff = against["value"] * 100
    observations = len(median.get("inputs") or []) or horizon
    years = median["period"].removeprefix("year ends ")
    span = f"{observations} year ends ({years}{'; the horizon is ' + str(horizon) + ' years' if observations < horizon else ''})"
    where = "the same as" if abs(diff) < 0.05 else f"{abs(diff):,.1f}% {'above' if diff > 0 else 'below'}"
    return _line(f"{HIST_BASES[base]} is {where} its own median of {display(median['value'], 'x')} over {span}.",
                 "history", _cite(against), _cite(median))


def _peer_history_line(median: dict, row: dict | None, horizon: int) -> dict | None:
    """The company's own historical median against each peer's own historical median."""
    if median["status"] != "calculated" or not row:
        return None
    peers = {t: p for t, p in (row.get("peer_values") or {}).items() if p.get("status") == "calculated" and p.get("value") is not None}
    if not peers:
        return None
    base = median["indicator"].removesuffix("_hist_median")
    value = median["value"]
    higher = [t for t, p in peers.items() if value > p["value"] and not _same(value, p["value"], "x")]
    lower = [t for t, p in peers.items() if value < p["value"] and not _same(value, p["value"], "x")]
    listed = ", ".join(f"{t} {display(p['value'], 'x')}" for t, p in peers.items())
    n = len(peers)
    if len(higher) == n:
        where = f"above those of all {n} peers" if n > 1 else "above that of the one peer"
    elif len(lower) == n:
        where = f"below those of all {n} peers" if n > 1 else "below that of the one peer"
    else:
        where = f"above those of {len(higher)} and below those of {len(lower)} of the {n} peers"
    text = f"The company's {horizon}-year {HIST_BASES[base]} median of {display(value, 'x')} is {where} ({listed})."
    return _line(text, "peer history", _cite(median), _peer_cite(row))


def _trend_line(indicator: str, history: dict) -> dict | None:
    """How a fiscal-year measure moved over the horizon: first and last year, and whether it moved one way throughout."""
    points = []
    for fy, rows in history.items():
        r = next((x for x in rows if x["indicator"] == indicator), None)
        if r and r["status"] in USABLE and r.get("value") is not None:
            points.append((fy, r))
    points.sort(key=lambda p: p[0])
    if len(points) < 2:
        return None
    (first_fy, first), (last_fy, last) = points[0], points[-1]
    unit, values = first["unit"], [r["value"] for _, r in points]
    steps = [b - a for a, b in zip(values, values[1:])]
    a, b = display(first["value"], unit), display(last["value"], unit)
    if a == b:
        text = f"{first['name']} was {a} in both {first_fy} and {last_fy}."
    else:  # "higher" and "lower", never "rose" or "fell": the wording check reserves those for share-price claims
        direction = "higher" if last["value"] > first["value"] else "lower"
        steady = all(s > 0 for s in steps) or all(s < 0 for s in steps)
        if len(points) == 2:
            how = f"{direction}"
        elif steady:
            how = f"{direction} each year"
        else:
            how = f"{direction} overall, moving in both directions in between"
        text = f"{first['name']} was {a} in {first_fy} and {b} in {last_fy}: {how}."
    return _line(text, "trend", *[_cite(r) for _, r in (points[0], points[-1])])


def _count_line(group: str, rows: list[tuple[dict, dict]]) -> dict | None:
    above = below = 0
    for result, row in rows:
        if row.get("peer_median") is None or result.get("value") is None or result["status"] not in USABLE:
            continue
        if _same(result["value"], row["peer_median"], result["unit"]):
            continue
        if result["value"] > row["peer_median"]:
            above += 1
        else:
            below += 1
    total = above + below
    if total < 2:
        return None
    verb = "is" if above == 1 else "are"
    return _line(f"Of the {total} {group.lower()} measures that differ from the peer median, {above} {verb} above it and {below} below it.",
                 "summary")


def _difference(value, median, unit) -> str:
    """The table's short form of the peer comparison, the same arithmetic as the lines: +74.4%, −12.30 pp, same."""
    if value is None or median is None:
        return "—"
    if _same(value, median, unit):
        return "same"
    if unit == "fraction":
        return f"{(value - median) * 100:+,.2f} pp"
    if median > 0 and value > 0:
        return f"{(value / median - 1) * 100:+,.1f}%"
    return "higher" if value > median else "lower"


def _own_history(ind: str, current: dict, history: dict) -> str:
    """The table's short form of the company's own history: its historical median for multiples, otherwise first and last year."""
    median = current.get(f"{ind}_hist_median")
    against = current.get(f"{ind}_vs_hist")
    if median and median["status"] == "calculated":
        text = f"median {display(median['value'], 'x')}"
        if against and against["status"] == "calculated":
            text += f", now {against['value'] * 100:+,.1f}%"
        return text
    points = sorted((fy, r) for fy, rows in history.items() for r in rows
                    if r["indicator"] == ind and r["status"] in USABLE and r.get("value") is not None)
    if len(points) < 2:
        return "—"
    (fy1, a), (fy2, b) = points[0], points[-1]

    def short(r):  # the unit is in the row's value already; per-share amounts lose their long label here
        return display(r["value"], r["unit"]) if r["unit"] in ("x", "fraction") else f"{r['value']:,.2f}"
    return f"{short(a)} → {short(b)} ({fy1}–{fy2})"


def _cells(current: dict, comparison: dict, history: dict) -> dict:
    """Display values for the dashboard tables, formatted here so that every number on the page comes from Python."""
    cells = {}
    for ind, r in current.items():
        row = comparison.get(ind, {})
        usable = r["status"] in USABLE and r.get("value") is not None
        cells[ind] = {"value": display(r["value"], r["unit"]) if usable else "—",
                      "peer_median": display(row.get("peer_median"), r["unit"]) if row.get("peer_median") is not None else "—",
                      "difference": _difference(r["value"] if usable else None, row.get("peer_median"), r["unit"]),
                      "own_history": _own_history(ind, current, history),
                      "peers": {t: (display(p["value"], r["unit"]) if p.get("status") == "calculated" and p.get("value") is not None
                                    else p.get("status", "missing").replace("_", " "))
                                for t, p in (row.get("peer_values") or {}).items()}}
    return cells


def build(report: dict) -> dict:
    """{"groups": [{"group", "lines"}], "by_indicator": {id: [lines]}, "cells": {id: display values}, "peers": [tickers]};
    each line is {"text", "kind", "cites"}."""
    indicators = report["agent1"]["indicators"]
    horizon = indicators.get("horizon_years", 5)
    current = {r["indicator"]: r for r in indicators["current"]}
    comparison = {row["indicator"]: row for row in report["agent1"].get("peer_comparison", [])}
    history = indicators.get("history", {})
    from backend.indicators import SPECS_BY_ID
    by_indicator: dict = {}
    for ind, result in current.items():
        lines = []
        if ind.endswith("_vs_hist") and f"{ind.removesuffix('_vs_hist')}_hist_median" in current:
            lines.append(_history_line(result, current[f"{ind.removesuffix('_vs_hist')}_hist_median"], horizon))
        elif ind.endswith("_hist_median"):
            lines.append(_peer_history_line(result, comparison.get(ind), horizon))
        if ind in comparison and not ind.endswith("_hist_median"):
            lines.append(_peer_line(result, comparison[ind]))
        lines.append(_trend_line(ind, history))
        if any(lines):
            by_indicator[ind] = [line for line in lines if line]
    groups = []
    for spec_group in dict.fromkeys(SPECS_BY_ID[i].group for i in current if i in SPECS_BY_ID):
        ids = [i for i in current if i in SPECS_BY_ID and SPECS_BY_ID[i].group == spec_group]
        lines = []
        count = None if spec_group == "Historical comparison" else _count_line(  # a count would mix own-history and peer comparisons
            spec_group, [(current[i], comparison[i]) for i in ids if i in comparison])
        if count:
            lines.append(count)
        for ind in dict.fromkeys(KEY.get(spec_group, []) + ids):  # one line per indicator, key indicators first
            first = (by_indicator.get(ind) or [None])[0]
            if first and first["kind"] != "trend" and len(lines) < MAX_GROUP_LINES:
                lines.append(first)
        trends = [line for ind in dict.fromkeys(KEY.get(spec_group, []) + ids) for line in by_indicator.get(ind, []) if line["kind"] == "trend"]
        lines += trends[:MAX_TREND_LINES]
        if lines:
            groups.append({"group": spec_group, "lines": lines})
    peers = [p["ticker"] for p in report.get("peers", {}).get("peers", [])]
    return {"groups": groups, "by_indicator": by_indicator, "cells": _cells(current, comparison, history), "peers": peers}
