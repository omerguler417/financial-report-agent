# Indicator calculations to docs/indicator_definitions.md v1.0 (step 3: the approved core set plus ROIC). All arithmetic runs here, in Python.
# Every result carries its identifier, definition version, formula, period, status, unit and each input with the sources it came from.
# Missing inputs are never zero, unsuitable metrics are not forced onto banks, and nothing here ranks companies or judges their value.
import re
import statistics
from dataclasses import asdict, dataclass, field
from typing import Callable

DEFINITION_VERSION = "v1.0"
STATUSES = ("calculated", "reported_only", "estimated", "missing", "not_applicable", "not_meaningful", "not_comparable")  # v1.0 section 3
FLOW_FIELDS = {"revenue", "ebit", "depreciation_amortisation", "interest_expense", "pretax_income", "income_tax", "net_income_group",
               "nci_share_of_income", "net_income_common", "cfo_reported", "capex", "dividends_paid_common"}
RATE_FIELDS = {"statutory_tax_rate"}
FINANCIAL_MODELS = {"bank", "insurer"}


@dataclass
class Figure:
    """One number with its unit ("USD millions", "millions of shares", "USD per share", "percent"), period and sources."""
    name: str
    value: float
    unit: str
    period: str
    sources: list = field(default_factory=list)
    note: str = ""

    def as_input(self) -> dict:
        out = {"name": self.name, "value": self.value, "unit": self.unit, "period": self.period, "sources": self.sources}
        return {**out, "note": self.note} if self.note else out


@dataclass
class CompanyInputs:
    """Figures by period label ("FY2025", "YTD Q3 2026"); interim periods hold their period-end balance sheet."""
    name: str
    periods: dict
    latest_fy: str
    ytd_current: str | None = None
    ytd_prior: str | None = None
    price: Figure | None = None
    business_model: str = "operating"  # operating | bank | insurer
    demo_label: str | None = None


@dataclass
class Result:
    indicator: str
    name: str
    period: str
    status: str
    value: float | None
    unit: str
    formula: str
    inputs: list = field(default_factory=list)
    note: str = ""
    other_views: dict = field(default_factory=dict)
    exclude_from_peer_median: bool = False
    definition_version: str = DEFINITION_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


class _Stop(Exception):
    """Ends one indicator with a non-calculated status and the reason."""
    def __init__(self, status: str, note: str, inputs=()):
        super().__init__(note)
        self.status, self.note, self.inputs = status, note, list(inputs)


# ---------- building blocks ----------

def _sources(*figs: Figure) -> list:
    out, seen = [], set()
    for f in figs:
        for s in f.sources:
            key = repr(sorted(s.items()))
            if key not in seen:
                seen.add(key)
                out.append(s)
    return out


def _check_units(*figs: Figure):
    units = sorted({f.unit for f in figs})
    if len(units) > 1:
        raise _Stop("not_comparable", f"Inputs are in different units or currencies ({', '.join(units)}), so they are not combined. "
                                      "Currency translation needs an FX source, which is not configured.", figs)


def _sum(name: str, period: str, terms: list, note: str = "") -> Figure:
    figs = [f for _, f in terms]
    _check_units(*figs)
    return Figure(name, sum(sign * f.value for sign, f in terms), figs[0].unit, period, _sources(*figs), note)


def _ttm(fy: Figure, cur: Figure, prior: Figure, period: str) -> Figure:
    return _sum(fy.name, period, [(1, fy), (1, cur), (-1, prior)], f"TTM = {fy.period} + {cur.period} − {prior.period}")


def fiscal_year(label: str) -> int | None:
    m = re.fullmatch(r"FY(\d{4})", label)
    return int(m.group(1)) if m else None


class _View:
    """One column of the analysis: the current (TTM) column or one fiscal year."""

    def __init__(self, label, flows, closing, closing_label, opening, opening_label, growth=None, price=None, tax_rate=None, annual=None):
        self.label, self.flows, self.closing, self.closing_label = label, flows, closing, closing_label
        self.opening, self.opening_label, self.growth, self.price, self.tax_rate = opening, opening_label, growth, price, tax_rate
        self.annual = annual or []  # [(fiscal year, view)] for multi-year measures
        self.not_comparable: dict = {}  # flows whose parts could not be combined, with the reason

    def flow(self, name: str) -> Figure:
        if name in self.not_comparable:
            raise self.not_comparable[name]
        f = self.flows.get(name)
        if f is None:
            raise _Stop("missing", f"Missing input: {name} for {self.label}. Missing is not treated as zero.")
        return f

    def bal(self, name: str, opening: bool = False) -> Figure:
        if opening and self.opening is None:
            raise _Stop("missing", f"Opening balance sheet ({self.opening_label}) is not available, so the average is not invented.")
        f = (self.opening if opening else self.closing).get(name)
        if f is None:
            where = self.opening_label if opening else self.closing_label
            raise _Stop("missing", f"Missing input: {name} at {where}. Missing is not treated as zero.")
        return f


def _ebitda(v: _View) -> Figure:
    return _sum("ebitda", v.label, [(1, v.flow("ebit")), (1, v.flow("depreciation_amortisation"))], "EBIT + depreciation and amortisation")


def _fcf(v: _View) -> Figure:
    return _sum("fcf_reported", v.label, [(1, v.flow("cfo_reported")), (-1, v.flow("capex"))],
                "Reported FCF = CFO − capex. Standardised FCF needs cash interest and lease-principal inputs, which are not extracted yet.")


def _debt(v: _View, opening: bool = False) -> Figure:
    where = v.opening_label if opening else v.closing_label
    return _sum("debt_inc_leases", where, [(1, v.bal("debt_ex_leases", opening)), (1, v.bal("lease_liabilities", opening))])


def _net_debt(v: _View, include_leases: bool = True) -> Figure:
    debt = _debt(v) if include_leases else v.bal("debt_ex_leases")
    return _sum("net_debt" if include_leases else "net_debt_ex_leases", v.closing_label, [(1, debt), (-1, v.bal("cash_eligible"))])


def _market_cap(v: _View) -> Figure:
    if v.price is None:
        raise _Stop("missing", "Missing input: share price. Missing is not treated as zero.")
    shares = v.bal("shares_outstanding")
    currency, scale = v.price.unit.split()[0], shares.unit.split()[0]
    return Figure("market_cap", v.price.value * shares.value, f"{currency} {scale}", f"{v.price.period} × shares at {v.closing_label}",
                  _sources(v.price, shares), "Price × common shares outstanding from the latest balance sheet; any other share class must be added.")


def _enterprise_value(v: _View) -> Figure:
    pref = v.closing.get("preferred_equity")
    terms = [(1, _market_cap(v)), (1, _debt(v)), (1, v.bal("nci")), (-1, v.bal("cash_eligible"))] + ([(1, pref)] if pref else [])
    note = "NCI at book value (proxy). " + ("Preferred capital at book value." if pref else
                                           "No preferred capital line in the balance sheet, so none is added.")
    return _sum("enterprise_value", v.closing_label, terms, note)


def _invested_capital(v: _View, opening: bool = False) -> Figure:
    where = v.opening_label if opening else v.closing_label
    side = v.opening if opening else v.closing
    terms = [(1, v.bal("equity_total", opening)), (1, _debt(v, opening)), (-1, v.bal("cash_eligible", opening))]
    investments = side.get("non_operating_investments")
    if investments:
        return _sum("invested_capital", where, terms + [(-1, investments)])
    return _sum("invested_capital", where, terms, "Approximation: non-operating financial investments are not separated in the inputs.")


def _average(v: _View, name: str, builder=None) -> Figure:
    close = builder(v) if builder else v.bal(name)
    open_ = builder(v, True) if builder else v.bal(name, opening=True)
    _check_units(open_, close)
    note = " ".join(dict.fromkeys(n for n in (open_.note, close.note) if n))
    return Figure(f"average_{name}", (open_.value + close.value) / 2, close.unit, f"average of {v.opening_label} and {v.closing_label}",
                  _sources(open_, close), note)


def _ratio(num: Figure, den: Figure, nm_note: str, *, positive_denominator: bool = True, same_unit: bool = True):
    if same_unit:
        _check_units(num, den)
    if den.value == 0 or (positive_denominator and den.value < 0):
        raise _Stop("not_meaningful", nm_note, [num, den])
    return num.value / den.value


# ---------- indicators (v1.0 section 5) ----------

def _pe(v):
    mc, e = _market_cap(v), v.flow("net_income_common")
    return _ratio(mc, e, "Earnings attributable to common shareholders are zero or negative, so P/E is NM (a negative P/E is not a cheapness signal)."), [mc, e], ""


def _ps(v):
    mc, rev = _market_cap(v), v.flow("revenue")
    return _ratio(mc, rev, "Revenue is not positive, so P/S is NM."), [mc, rev], "Does not take debt into account."


def _pb(v):
    mc, eq = _market_cap(v), v.bal("equity_common")
    return _ratio(mc, eq, "Common equity is zero or negative, so P/B is NM."), [mc, eq], ""


def _nci_scope_note(v) -> str:
    nci = v.closing.get("nci")
    return ("Consolidated FCF (including NCI) is compared with common-equity market value; NCI exists, so the scopes differ."
            if nci and nci.value else "")


def _p_fcf(v):
    mc, fcf = _market_cap(v), _fcf(v)
    return _ratio(mc, fcf, "FCF is zero or negative, so P/FCF is NM; FCF yield still shows it."), [mc, fcf], _nci_scope_note(v)


def _ev_ebitda(v):
    ev, ebitda = _enterprise_value(v), _ebitda(v)
    value = _ratio(ev, ebitda, "EBITDA is zero or negative, so EV/EBITDA is NM.")
    if ev.value < 0:
        return value, [ev, ebitda], "Enterprise value is negative: shown for information and left out of peer medians.", {}, True
    return value, [ev, ebitda], ""


def _fcf_yield(v):
    fcf, mc = _fcf(v), _market_cap(v)
    return _ratio(fcf, mc, "Market value is not positive, so FCF yield is NM."), [fcf, mc], _nci_scope_note(v)


def _debt_equity(v):
    debt, eq = _debt(v), v.bal("equity_total")
    value = _ratio(debt, eq, "Total equity is zero or negative, so debt/equity is NM.")
    return value, [debt, eq], "", {"excluding_leases": v.bal("debt_ex_leases").value / eq.value}


def _net_debt_equity(v):
    nd, eq = _net_debt(v), v.bal("equity_total")
    value = _ratio(nd, eq, "Total equity is zero or negative, so net debt/equity is NM.")
    note = "Negative: cash exceeds debt (net cash)." if nd.value < 0 else ""
    return value, [nd, eq], note, {"excluding_leases": _net_debt(v, False).value / eq.value}


def _net_debt_ebitda(v):
    nd, ebitda = _net_debt(v), _ebitda(v)
    value = _ratio(nd, ebitda, "EBITDA is zero or negative, so net debt/EBITDA is NM.")
    note = "Negative: cash exceeds debt (net cash)." if nd.value < 0 else ""
    return value, [nd, ebitda], note, {"excluding_leases": _net_debt(v, False).value / ebitda.value}


def _current_ratio(v):
    ca, cl = v.bal("current_assets"), v.bal("current_liabilities")
    return _ratio(ca, cl, "Current liabilities are zero, so the current ratio is not calculated."), [ca, cl], ""


def _interest_coverage(v):
    ebit, interest = v.flow("ebit"), v.flow("interest_expense")
    value = _ratio(ebit, interest, "No interest expense: coverage is not calculated.")
    return value, [ebit, interest], "EBIT is negative; the result is kept." if ebit.value < 0 else ""


def _roe(v):
    ni, eq = v.flow("net_income_common"), _average(v, "equity_common")
    return _ratio(ni, eq, "Average common equity is not positive, so ROE is NM."), [ni, eq], ""


def _roa(v):
    ni, assets = v.flow("net_income_group"), _average(v, "assets_total")
    return _ratio(ni, assets, "Average total assets are not positive, so ROA is NM."), [ni, assets], ""


def _roic(v):
    ebit = v.flow("ebit")
    if v.tax_rate is None:
        raise _Stop("missing", "The home-country statutory tax rate was not found in the company's report, so NOPAT and ROIC are not calculated.", [ebit])
    rate = v.tax_rate
    if ebit.value > 0:
        nopat = Figure("nopat", ebit.value * (1 - rate.value / 100), ebit.unit, ebit.period, _sources(ebit, rate),
                       f"NOPAT = EBIT × (1 − {rate.value:g}% home-country statutory rate from the {rate.period} report).")
        note = ""
    else:
        nopat = Figure("nopat", ebit.value, ebit.unit, ebit.period, _sources(ebit), "EBIT is not positive.")
        note = "No tax benefit is assumed on an operating loss."
    capital = _average(v, "invested_capital", _invested_capital)
    value = _ratio(nopat, capital, "Average invested capital is not positive, so ROIC is NM.")
    return value, [ebit, rate, nopat, capital], " ".join(n for n in (note, capital.note) if n)


def _net_margin(v):
    ni, rev = v.flow("net_income_group"), v.flow("revenue")
    return _ratio(ni, rev, "Revenue is not positive, so the margin is NM."), [ni, rev], ""


def _ebitda_margin(v):
    ebitda, rev = _ebitda(v), v.flow("revenue")
    return _ratio(ebitda, rev, "Revenue is not positive, so the margin is NM."), [ebitda, rev], ""


def _revenue_growth(v):
    if v.growth is None:
        raise _Stop("missing", f"No comparable prior-period revenue for {v.label}, so growth is not calculated.")
    cur, prior = v.growth
    _check_units(cur, prior)
    if prior.value <= 0:
        raise _Stop("not_meaningful", f"Prior-period revenue is not positive, so percentage growth is NM; absolute change {cur.value - prior.value:g} {cur.unit}.",
                    [cur, prior])
    return cur.value / prior.value - 1, [cur, prior], f"{cur.period} compared with {prior.period}."


def _fcf_conversion(v):
    fcf, ni = _fcf(v), v.flow("net_income_group")
    return _ratio(fcf, ni, "Group net income is not positive, so FCF conversion is NM."), [fcf, ni], ""


def _fcf_conversion_multi_year(v):
    years = []
    for label, view in reversed(v.annual[-5:]):  # newest first; stop at the first year with incomplete data or a gap
        try:
            fcf, ni = _fcf(view), view.flow("net_income_group")
            _check_units(fcf, ni)
        except _Stop:
            break
        if years and fiscal_year(years[-1][0]) - 1 != fiscal_year(label):
            break
        years.append((label, fcf, ni))
    if len(years) < 2:
        raise _Stop("missing", "Fewer than two consecutive fiscal years have complete FCF and net income data.")
    years.reverse()
    total_fcf = _sum("fcf_reported_total", "", [(1, f) for _, f, _ in years])
    total_ni = _sum("net_income_group_total", "", [(1, n) for _, _, n in years])
    period = f"{years[0][0]}–{years[-1][0]}"
    total_fcf.period = total_ni.period = period
    value = _ratio(total_fcf, total_ni, "Aggregate group net income is not positive, so the measure is NM.")
    note = f"Sum of FCF ÷ sum of group net income over {len(years)} years."
    if len(years) < 5:
        note += f" Only {len(years)} years are available, so this is a {len(years)}-year measure, not five."
    return value, [total_fcf, total_ni], note, {}, False, period


def _bvps(v):
    eq, shares = v.bal("equity_common"), v.bal("shares_outstanding")
    if eq.unit.split()[1:] != shares.unit.split()[:1]:
        raise _Stop("not_comparable", f"Equity ({eq.unit}) and share count ({shares.unit}) use different scales.", [eq, shares])
    value = _ratio(eq, shares, "Share count is not positive, so BVPS is not calculated.", same_unit=False)
    return value, [eq, shares], "Uses balance-sheet-date shares, not weighted-average shares."


@dataclass(frozen=True)
class Spec:
    id: str
    name: str
    group: str
    unit: str  # "x" for multiples, "fraction" for percentages (0.12 = 12%), "per share" for amounts per share
    formula: str
    fn: Callable
    needs_price: bool = False
    not_for_financials: bool = False
    peer_comparison: str = "median only"  # "peer discount", "percentage points", "median only" or "none"
    multi_year: bool = False


SPECS = [
    Spec("pe", "P/E", "Valuation", "x", "market_cap / net_income_common (TTM)", _pe, True, peer_comparison="peer discount"),
    Spec("ps", "P/S", "Valuation", "x", "market_cap / revenue (TTM)", _ps, True, peer_comparison="peer discount"),
    Spec("pb", "P/B", "Valuation", "x", "market_cap / equity_common", _pb, True, peer_comparison="peer discount"),
    Spec("p_fcf", "P/FCF", "Valuation", "x", "market_cap / fcf_reported (TTM)", _p_fcf, True, True, "peer discount"),
    Spec("ev_ebitda", "EV/EBITDA", "Valuation", "x", "enterprise_value / ebitda (TTM)", _ev_ebitda, True, True, "peer discount"),
    Spec("fcf_yield", "FCF yield", "Valuation", "fraction", "fcf_reported (TTM) / market_cap", _fcf_yield, True, True),
    Spec("debt_equity", "Debt/equity", "Debt and liquidity", "x", "debt_inc_leases / equity_total", _debt_equity, not_for_financials=True),
    Spec("net_debt_equity", "Net debt/equity", "Debt and liquidity", "x", "net_debt / equity_total", _net_debt_equity, not_for_financials=True),
    Spec("net_debt_ebitda", "Net debt/EBITDA", "Debt and liquidity", "x", "net_debt / ebitda (TTM)", _net_debt_ebitda, not_for_financials=True),
    Spec("current_ratio", "Current ratio", "Debt and liquidity", "x", "current_assets / current_liabilities", _current_ratio, not_for_financials=True),
    Spec("interest_coverage", "Interest coverage", "Debt and liquidity", "x", "ebit / interest_expense (TTM)", _interest_coverage, not_for_financials=True),
    Spec("roe_common", "Common ROE", "Profitability", "fraction", "net_income_common / average equity_common", _roe,
         peer_comparison="percentage points"),
    Spec("roa_group", "Group ROA", "Profitability", "fraction", "net_income_group / average assets_total", _roa, peer_comparison="percentage points"),
    Spec("roic", "ROIC", "Profitability", "fraction", "ebit × (1 − home-country statutory tax rate) / average invested_capital", _roic,
         not_for_financials=True, peer_comparison="percentage points"),
    Spec("net_margin", "Net profit margin", "Profitability", "fraction", "net_income_group / revenue", _net_margin, peer_comparison="percentage points"),
    Spec("ebitda_margin", "EBITDA margin", "Profitability", "fraction", "ebitda / revenue", _ebitda_margin, not_for_financials=True,
         peer_comparison="percentage points"),
    Spec("revenue_growth", "Revenue growth", "Growth and cash", "fraction", "current comparable-period revenue / prior comparable-period revenue − 1",
         _revenue_growth),
    Spec("fcf_conversion", "FCF earnings conversion", "Growth and cash", "fraction", "fcf_reported / net_income_group", _fcf_conversion,
         not_for_financials=True),
    Spec("fcf_conversion_5y", "Five-year FCF earnings conversion", "Growth and cash", "fraction",
         "sum of fcf_reported / sum of net_income_group over the same fiscal years", _fcf_conversion_multi_year, not_for_financials=True,
         multi_year=True),
    Spec("bvps", "Book value per share", "Per share", "per share", "equity_common / shares_outstanding", _bvps, peer_comparison="none"),
]
SPECS_BY_ID = {s.id: s for s in SPECS}


def _run(spec: Spec, v: _View, business_model: str) -> Result:
    unit = spec.unit
    if spec.unit == "per share":
        equity = v.closing.get("equity_common")
        unit = f"{equity.unit.split()[0]} per share" if equity else "per share"
    if spec.not_for_financials and business_model in FINANCIAL_MODELS:
        return Result(spec.id, spec.name, v.label, "not_applicable", None, unit, spec.formula,
                      note=f"Not applicable to a {business_model}: funding is part of the business model (v1.0 section 8).")
    try:
        value, inputs, note, *rest = spec.fn(v)
    except _Stop as stop:
        return Result(spec.id, spec.name, v.label, stop.status, None, unit, spec.formula, [f.as_input() for f in stop.inputs], stop.note)
    other_views = rest[0] if rest else {}
    exclude = rest[1] if len(rest) > 1 else False
    period = rest[2] if len(rest) > 2 else v.label
    return Result(spec.id, spec.name, period, "calculated", value, unit, spec.formula, [f.as_input() for f in inputs], note, other_views, exclude)


# ---------- the analysis ----------

def _split(figures: dict) -> tuple[dict, dict]:
    flows = {k: f for k, f in figures.items() if k in FLOW_FIELDS}
    balances = {k: f for k, f in figures.items() if k not in FLOW_FIELDS and k not in RATE_FIELDS}
    return flows, balances


def _annual_views(c: CompanyInputs) -> list:
    years = sorted((p for p in c.periods if fiscal_year(p)), key=fiscal_year)
    views = []
    for i, fy in enumerate(years):
        flows, closing = _split(c.periods[fy])
        prev = years[i - 1] if i and fiscal_year(years[i - 1]) == fiscal_year(fy) - 1 else None
        opening = _split(c.periods[prev])[1] if prev else None
        growth = None
        if prev and "revenue" in flows and "revenue" in c.periods[prev]:
            growth = (flows["revenue"], c.periods[prev]["revenue"])
        views.append((fy, _View(fy, flows, closing, f"{fy} year end", opening,
                                f"{prev} year end" if prev else f"FY{fiscal_year(fy) - 1} year end", growth,
                                tax_rate=c.periods[fy].get("statutory_tax_rate"))))
    return views


def _current_view(c: CompanyInputs, annual: list) -> _View:
    fy = c.periods[c.latest_fy]
    tax_rate = fy.get("statutory_tax_rate")
    if c.ytd_current and c.ytd_prior and c.ytd_current in c.periods:
        cur, prior = c.periods[c.ytd_current], c.periods.get(c.ytd_prior, {})
        label = f"TTM to {c.ytd_current.removeprefix('YTD').strip()}"
        flows, not_comparable = {}, {}
        for name in FLOW_FIELDS:
            if name in fy and name in cur and name in prior:
                try:
                    flows[name] = _ttm(fy[name], cur[name], prior[name], label)
                except _Stop as stop:
                    not_comparable[name] = stop
        closing, opening = _split(cur)[1], _split(prior)[1] or None
        growth = (cur["revenue"], prior["revenue"]) if "revenue" in cur and "revenue" in prior else None
        view = _View(label, flows, closing, f"{c.ytd_current} period end", opening, f"{c.ytd_prior} period end", growth, c.price,
                     tax_rate, annual)
        view.not_comparable = not_comparable
        return view
    view = dict(annual)[c.latest_fy]
    view.price, view.annual = c.price, annual
    return view


def analyse(c: CompanyInputs) -> dict:
    """Current-period indicators (TTM when interim reports exist) and fiscal-year history for indicators that need no share price."""
    annual = _annual_views(c)
    history = {fy: [_run(s, v, c.business_model) for s in SPECS if not s.needs_price and not s.multi_year] for fy, v in annual}
    current_view = _current_view(c, annual)
    notes = [c.demo_label] if c.demo_label else []
    if c.business_model in FINANCIAL_MODELS:
        notes.append(f"Treated as a {c.business_model}: industrial cash-flow, EBITDA, debt and liquidity measures are not applicable (v1.0 section 8).")
    if not (c.ytd_current and c.ytd_prior):
        notes.append(f"No interim reports: current values use {c.latest_fy}.")
    return {"company": c.name, "demo": bool(c.demo_label), "definition_version": DEFINITION_VERSION, "business_model": c.business_model,
            "current_period": current_view.label, "current": [_run(s, current_view, c.business_model) for s in SPECS],
            "history": history, "notes": notes}


def compare_with_peers(target: dict, peers: dict) -> list[dict]:
    """Peer medians of meaningful values (v1.0 section 10). Describes differences only; never ranks or judges value."""
    rows = []
    for r in target["current"]:
        spec = SPECS_BY_ID[r.indicator]
        if spec.peer_comparison == "none":
            continue
        used = [(t, p) for t, a in peers.items() for p in a["current"]
                if p.indicator == r.indicator and p.status == "calculated" and not p.exclude_from_peer_median]
        values = [p.value for _, p in used]
        median = statistics.median(values) if values else None
        notes = []
        if len(values) < 3:
            notes.append(f"Only {len(values)} valid peer value{'s' if len(values) != 1 else ''}; v1.0 targets at least three.")
        periods = sorted({p.period for _, p in used} - {r.period})
        if periods:
            notes.append("Peer periods differ from the company's: " + ", ".join(periods) + ".")
        comparison, kind = None, None
        if median is not None and r.status == "calculated" and not r.exclude_from_peer_median:
            if spec.peer_comparison == "peer discount" and median > 0:
                comparison, kind = 1 - r.value / median, "peer discount (1 − company ÷ peer median; positive means below the median)"
            elif spec.peer_comparison == "percentage points":
                comparison, kind = r.value - median, "percentage-point difference"
        rows.append({"indicator": r.indicator, "name": r.name, "company_value": r.value, "company_status": r.status, "unit": r.unit,
                     "peer_median": median, "peer_count": len(values), "peers_used": [t for t, _ in used], "comparison": comparison,
                     "comparison_type": kind, "note": " ".join(notes)})
    return rows
