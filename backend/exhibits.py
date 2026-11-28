# The investment-banking-style exhibits of the report (approved 28 November 2026): key market data, a financial summary by fiscal year
# plus the last twelve months, and trading comparables with each peer and the median. Built and formatted here from Agent 1's results,
# for the dashboard and the report, PDF and Word alike. Nothing is calculated; there is no rating, target or verdict.
from backend.report_blocks import display

SUMMARY_ROWS = [("revenue", "Revenue"), ("ebitda", "EBITDA"), ("ebit", "EBIT"), ("net_income_common", "Net income to common shareholders"),
                ("cfo", "Operating cash flow (reported)"), ("capex", "Capital expenditure"), ("fcf", "Free cash flow (standardised)")]
COMPS = [("pe", "P/E"), ("ev_ebitda", "EV/EBITDA"), ("ev_sales", "EV/sales"), ("pb", "P/B"), ("fcf_yield", "FCF yield"),
         ("ebitda_margin", "EBITDA margin"), ("net_margin", "Net margin"), ("roe_common", "ROE"), ("revenue_growth", "Rev. growth")]
USABLE = {"calculated", "estimated", "reported_only"}


def _period(label: str) -> str:
    return label.replace("TTM to ", "LTM ")  # banks call the last twelve months LTM


def _millions(item: dict | None) -> str:
    return "—" if not item or item.get("value") is None else f"{item['value']:,.0f}"


def _sources(items) -> list[dict]:
    out = []
    for item in items:
        for s in (item or {}).get("sources", []):
            if s not in out:
                out.append(s)
    return out


def _amount(item: dict) -> str:
    """Banker style for amounts held in millions: USD 3,660.4bn or USD 850m."""
    currency, value = item["unit"].split()[0], item["value"]
    return f"{currency} {value / 1000:,.1f}bn" if abs(value) >= 1000 else f"{currency} {value:,.0f}m"


def _key_data(indicators: dict) -> list[dict]:
    market = indicators.get("market") or {}
    rows = []
    price = market.get("price")
    if price:
        rows.append({"label": f"Share price ({price['period']})", "value": f"{price['unit'].split()[0]} {price['value']:,.2f}",
                     "sources": price["sources"]})
    for key, label in (("market_cap", "Market capitalisation"), ("enterprise_value", "Enterprise value")):
        item = market.get(key)
        if item:
            rows.append({"label": label, "value": _amount(item), "sources": item["sources"]})
    rows.append({"label": "Current period", "value": _period(indicators["current_period"]), "sources": []})
    rows.append({"label": "Horizon", "value": f"{indicators.get('horizon_years', 5)} fiscal years", "sources": []})
    return rows


def _financial_summary(indicators: dict) -> dict:
    periods = indicators.get("financial_summary") or []
    if not periods:
        return {"columns": [], "rows": [], "sources": []}
    rows = [[label] + [_millions(p["items"].get(key)) for p in periods] for key, label in SUMMARY_ROWS]
    rows = [row for row in rows if any(cell != "—" for cell in row[1:])]  # a line with no figure in any period is left out
    return {"columns": ["USD millions"] + [_period(p["period"]) for p in periods], "rows": rows,
            "sources": _sources(item for p in periods for item in p["items"].values())}


def _comparables(report: dict) -> dict:
    current = {r["indicator"]: r for r in report["agent1"]["indicators"]["current"]}
    comparison = {row["indicator"]: row for row in report["agent1"].get("peer_comparison", [])}
    columns = [(key, label) for key, label in COMPS if key in current]
    company = report["company"]

    def cell(result):
        return display(result["value"], result["unit"]) if result and result.get("status") in USABLE and result.get("value") is not None else "—"

    rows = [[f"{company['name']} ({company['ticker']})"] + [cell(current[key]) for key, _ in columns]]
    for peer in report.get("peers", {}).get("peers", []):
        row = [f"{peer['name']} ({peer['ticker']})"]
        for key, _ in columns:
            value = (comparison.get(key, {}).get("peer_values") or {}).get(peer["ticker"])
            row.append(cell({**value, "unit": current[key]["unit"]}) if value else "—")
        rows.append(row)
    if len(rows) > 1:
        rows.append(["Peer median"] + [display(comparison[key]["peer_median"], current[key]["unit"])
                                       if comparison.get(key, {}).get("peer_median") is not None else "—" for key, _ in columns])
    keep = [0] + [i for i in range(1, len(columns) + 1) if any(row[i] != "—" for row in rows)]  # a column with no figure is left out
    return {"columns": [(["Company"] + [label for _, label in columns])[i] for i in keep], "rows": [[row[i] for i in keep] for row in rows],
            "period": _period(report["agent1"]["indicators"]["current_period"])}


def _historical(report: dict) -> dict:
    """Each multiple now, its own historical median, the difference, and the median of the peers' own historical medians."""
    from backend.indicators import HIST_NAMES
    current = {r["indicator"]: r for r in report["agent1"]["indicators"]["current"]}
    comparison = {row["indicator"]: row for row in report["agent1"].get("peer_comparison", [])}
    horizon = report["agent1"]["indicators"].get("horizon_years", 5)
    rows = []
    for base, name in HIST_NAMES.items():
        median, against = current.get(f"{base}_hist_median"), current.get(f"{base}_vs_hist")
        if not median or median["status"] != "calculated":  # no own median: the row would be empty
            continue
        peers = comparison.get(f"{base}_hist_median", {}).get("peer_median")
        rows.append([name, display(current[base]["value"], "x") if current.get(base, {}).get("status") in USABLE else "—",
                     display(median["value"], "x") if median["status"] == "calculated" else "—",
                     f"{against['value'] * 100:+,.1f}%" if against and against["status"] == "calculated" else "—",
                     display(peers, "x") if peers is not None else "—"])
    return {"columns": ["Multiple", "Current", f"Own {horizon}-year median", "Current vs median", "Peers' median of own medians"],
            "rows": rows}


def build(report: dict) -> dict:
    indicators = report["agent1"]["indicators"]
    return {"key_data": _key_data(indicators), "financial_summary": _financial_summary(indicators), "comparables": _comparables(report),
            "historical": _historical(report)}
