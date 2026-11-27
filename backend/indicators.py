# Indicator calculations to docs/indicator_definitions.md v1.0 (step 3: the approved core set plus ROIC). All arithmetic runs here, in Python.
# Every result carries its identifier, definition version, formula, period, status, unit and each input with the sources it came from.
# Missing inputs are never zero, unsuitable metrics are not forced onto banks, and nothing here ranks companies or judges their value.
import re
import statistics
from dataclasses import asdict, dataclass, field
from typing import Callable

DEFINITION_VERSION = "v1.1"
STATUSES = ("calculated", "reported_only", "estimated", "missing", "not_applicable", "not_meaningful", "not_comparable")  # v1.0 section 3
FLOW_FIELDS = {"revenue", "ebit", "depreciation_amortisation", "interest_expense", "pretax_income", "income_tax", "net_income_group",
               "nci_share_of_income", "net_income_common", "cfo_reported", "capex", "dividends_paid_common", "cost_of_sales",
               "interest_paid_in_cfo", "interest_paid_outside_cfo", "lease_principal_outside_cfo", "dividends_paid_in_cfo", "dividends_per_share",
               "depreciation_amortisation_own"}  # the company's own D&A element, used only as a complete replacement (see _own_d_and_a)
# Reported for each period but never added up into twelve months (v1.0: no blind adding of per-share figures on different share bases).
PERIOD_ONLY_FIELDS = {"eps_basic", "eps_diluted", "weighted_shares_basic", "weighted_shares_diluted"}
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
    alternative: "Figure | None" = None  # the reported-basis figure kept alongside a standardised one

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
    price_points: dict = field(default_factory=dict)  # "end", "1m", "3m", "12m" (split-adjusted) and "year end YYYY-12-31" closes
    price_note: str = ""  # why there is no price, for example "no market-data provider is configured"
    interest_rule: str = ""  # set for US GAAP filers: interest paid is classified within operating cash flow
    horizon_years: int = 5  # fiscal years of history chosen for the analysis: 3, 5 (default) or 10
    source_gaps: dict = field(default_factory=dict)  # inputs the data source does not have, with the reason shown to the reader


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

    def __init__(self, label, flows, closing, closing_label, opening, opening_label, growth=None, price=None, tax_rate=None, annual=None,
                 prior_flows=None, price_points=None):
        self.label, self.flows, self.closing, self.closing_label = label, flows, closing, closing_label
        self.opening, self.opening_label, self.growth, self.price, self.tax_rate = opening, opening_label, growth, price, tax_rate
        self.annual = annual or []  # [(fiscal year, view)] for multi-year measures
        self.prior_flows = prior_flows or {}  # the previous fiscal year's flows, for year-on-year measures in the history
        self.price_points = price_points or {}
        self.price_note = ""
        self.interest_rule = ""
        self.not_comparable: dict = {}  # flows whose parts could not be combined, with the reason
        self.horizon = 5  # fiscal years for multi-year measures (the analysis horizon)

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


def _cfo_standardised(v: _View) -> Figure:
    """v1.0: CFO after cash interest and lease principal; dividends paid inside CFO are added back. Missing classification stops it."""
    terms, notes = [(1, v.flow("cfo_reported"))], []
    if "interest_paid_outside_cfo" in v.flows:
        terms.append((-1, v.flows["interest_paid_outside_cfo"]))
    elif "interest_paid_in_cfo" in v.flows:
        notes.append("Interest paid is already within operating cash flow.")
    elif v.interest_rule:
        notes.append(v.interest_rule)
    else:
        raise _Stop("missing", "where interest paid is classified")
    leases = v.closing.get("lease_liabilities")
    if "lease_principal_outside_cfo" in v.flows:
        terms.append((-1, v.flows["lease_principal_outside_cfo"]))
    elif not (leases is not None and leases.value == 0):
        raise _Stop("missing", "the lease principal payments")
    if "dividends_paid_in_cfo" in v.flows:
        terms.append((1, v.flows["dividends_paid_in_cfo"]))
    return _sum("cfo_standardised", v.label, terms, " ".join(["Standardised CFO: after cash interest and lease principal."] + notes))


def _cfo(v: _View) -> Figure:
    """Standardised CFO for comparisons with the reported figure alongside; the reported figure, labelled, when adjustments are missing."""
    reported = v.flow("cfo_reported")
    try:
        standardised = _cfo_standardised(v)
    except _Stop as stop:
        if stop.status != "missing":
            raise
        return Figure(reported.name, reported.value, reported.unit, reported.period, reported.sources,
                      f"Reported basis: the standardised figure needs {stop.note}, which is not in the inputs.")
    standardised.alternative = reported
    return standardised


def _fcf(v: _View) -> Figure:
    capex = v.flow("capex")
    cfo = _cfo(v)
    reported = _sum("fcf_reported", v.label, [(1, v.flow("cfo_reported")), (-1, capex)], "Reported FCF = reported CFO − capex.")
    if cfo.alternative is None:
        reported.note = cfo.note.replace("Reported basis:", "Reported basis (CFO − capex):")
        return reported
    standardised = _sum("fcf_standardised", v.label, [(1, cfo), (-1, capex)], "Standardised FCF = standardised CFO − capex.")
    standardised.alternative = reported
    return standardised


def _reported_view(numerator_alt, denominator_alt) -> dict:
    """The same ratio on the reported basis, shown alongside (only when it is defined)."""
    if numerator_alt is None or denominator_alt is None or denominator_alt.value <= 0:
        return {}
    return {"reported_basis": numerator_alt.value / denominator_alt.value}


def _debt(v: _View, opening: bool = False) -> Figure:
    where = v.opening_label if opening else v.closing_label
    return _sum("debt_inc_leases", where, [(1, v.bal("debt_ex_leases", opening)), (1, v.bal("lease_liabilities", opening))])


def _net_debt(v: _View, include_leases: bool = True) -> Figure:
    debt = _debt(v) if include_leases else v.bal("debt_ex_leases")
    return _sum("net_debt" if include_leases else "net_debt_ex_leases", v.closing_label, [(1, debt), (-1, v.bal("cash_eligible"))])


def _market_cap(v: _View) -> Figure:
    if v.price is None:
        why = f" ({v.price_note})" if v.price_note else ""
        raise _Stop("missing", f"Missing input: share price{why}. Missing is not treated as zero.")
    shares = v.bal("shares_outstanding")
    currency, scale = v.price.unit.split()[0], shares.unit.split()[0]
    return Figure("market_cap", v.price.value * shares.value, f"{currency} {scale}", f"{v.price.period} × shares at {v.closing_label}",
                  _sources(v.price, shares), "Price × common shares outstanding from the latest balance sheet (or the report's cover page when "
                  "the balance sheet gives none); any other share class must be added.")


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


def _fcf_note(v, fcf, scope=True):
    basis = "Standardised FCF; the reported basis is shown alongside." if fcf.alternative else fcf.note
    return " ".join(n for n in (basis, _nci_scope_note(v) if scope else "") if n)


def _p_fcf(v):
    mc, fcf = _market_cap(v), _fcf(v)
    value = _ratio(mc, fcf, "FCF is zero or negative, so P/FCF is NM; FCF yield still shows it.")
    return value, [mc, fcf], _fcf_note(v, fcf), _reported_view(mc, fcf.alternative)


def _ev_ebitda(v):
    ev, ebitda = _enterprise_value(v), _ebitda(v)
    value = _ratio(ev, ebitda, "EBITDA is zero or negative, so EV/EBITDA is NM.")
    if ev.value < 0:
        return value, [ev, ebitda], "Enterprise value is negative: shown for information and left out of peer medians.", {}, True
    return value, [ev, ebitda], ""


def _fcf_yield(v):
    fcf, mc = _fcf(v), _market_cap(v)
    value = _ratio(fcf, mc, "Market value is not positive, so FCF yield is NM.")
    return value, [fcf, mc], _fcf_note(v, fcf), _reported_view(fcf.alternative, mc)


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
    value = _ratio(fcf, ni, "Group net income is not positive, so FCF conversion is NM.")
    return value, [fcf, ni], _fcf_note(v, fcf, scope=False), _reported_view(fcf.alternative, ni)


def _fcf_conversion_multi_year(v):
    years = []
    for label, view in reversed(v.annual[-v.horizon:]):  # newest first; stop at the first year with incomplete data or a gap
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
    total_fcf = _sum("fcf_total", "", [(1, f) for _, f, _ in years])
    total_ni = _sum("net_income_group_total", "", [(1, n) for _, _, n in years])
    period = f"{years[0][0]}–{years[-1][0]}"
    total_fcf.period = total_ni.period = period
    value = _ratio(total_fcf, total_ni, "Aggregate group net income is not positive, so the measure is NM.")
    note = f"Sum of FCF ÷ sum of group net income over {len(years)} years."
    if len(years) < v.horizon:
        note += f" Only {len(years)} years are available, so this is a {len(years)}-year measure, not {v.horizon}."
    views = {}
    if all(f.alternative for _, f, _ in years):
        views = {"reported_basis": sum(f.alternative.value for _, f, _ in years) / total_ni.value}
        note += " Standardised FCF; the reported basis is shown alongside."
    return value, [total_fcf, total_ni], note, views, False, period


def _bvps(v):
    eq, shares = v.bal("equity_common"), v.bal("shares_outstanding")
    if eq.unit.split()[1:] != shares.unit.split()[:1]:
        raise _Stop("not_comparable", f"Equity ({eq.unit}) and share count ({shares.unit}) use different scales.", [eq, shares])
    value = _ratio(eq, shares, "Share count is not positive, so BVPS is not calculated.", same_unit=False)
    return value, [eq, shares], "Uses balance-sheet-date shares, not weighted-average shares."


# ---------- section 5 (rest) and section 6 ----------

def _ev_sales(v):
    ev, rev = _enterprise_value(v), v.flow("revenue")
    return _ratio(ev, rev, "Revenue is not positive, so EV/sales is NM."), [ev, rev], ""


def _ev_ebit(v):
    ev, ebit = _enterprise_value(v), v.flow("ebit")
    return _ratio(ev, ebit, "EBIT is zero or negative, so EV/EBIT is NM."), [ev, ebit], "Keeps depreciation as a cost."


def _dividend_yield(v):
    if "dividends_per_share" not in v.flows and "dividends_paid_common" in v.flows:
        return _dividend_yield_estimated(v)
    dps = v.flow("dividends_per_share")
    if v.price is None:
        why = f" ({v.price_note})" if v.price_note else ""
        raise _Stop("missing", f"Missing input: share price{why}. Missing is not treated as zero.", [dps])
    value = _ratio(dps, v.price, "The share price is not positive.")
    return value, [dps, v.price], ("Dividends per share paid over the period ÷ the share price. Per-share amounts are combined across "
                                   "reports, which holds only if there was no share split in the period. Forward dividends are a separate measure.")


def _dividend_yield_estimated(v):
    """Decided 27 November 2026: without dividends per share paid, cash dividends paid ÷ shares outstanding, labelled estimated."""
    paid, shares = v.flow("dividends_paid_common"), v.bal("shares_outstanding")
    if v.price is None:
        why = f" ({v.price_note})" if v.price_note else ""
        raise _Stop("missing", f"Missing input: share price{why}. Missing is not treated as zero.", [paid, shares])
    _check_units(v.price)
    if shares.value <= 0 or v.price.value <= 0:
        raise _Stop("not_meaningful", "Shares outstanding or the share price are not positive.", [paid, shares, v.price])
    per_share = paid.value / shares.value  # USD millions ÷ millions of shares = USD per share
    return {"value": per_share / v.price.value, "status": "estimated", "inputs": [paid, shares, v.price], "period": v.label,
            "note": (f"Estimated: no dividends per share paid are reported, so cash dividends paid to common shareholders "
                     f"({paid.value:,.0f}) ÷ shares outstanding at {v.closing_label} ({shares.value:,.0f}) ≈ {per_share:.2f} per share, "
                     "÷ the share price. The share count at the period end can differ from the counts on the payment dates.")}


def _graham(v):
    mc, ni, eq = _market_cap(v), v.flow("net_income_common"), v.bal("equity_common")
    pe = _ratio(mc, ni, "Earnings are not positive, so the Graham multiple is NM.")
    pb = _ratio(mc, eq, "Common equity is not positive, so the Graham multiple is NM.")
    if pe <= 0:
        raise _Stop("not_meaningful", "Earnings are not positive, so the Graham multiple is NM.", [mc, ni, eq])
    return pe * pb, [mc, ni, eq], "P/E × P/B. The 22.5 threshold from the literature is not a universal rule."


def _asset_turnover(v):
    rev, assets = v.flow("revenue"), _average(v, "assets_total")
    return _ratio(rev, assets, "Average total assets are not positive."), [rev, assets], ""


def _dupont_leverage(v):
    assets, equity = _average(v, "assets_total"), _average(v, "equity_total")
    return _ratio(assets, equity, "Average total equity is not positive, so leverage is NM."), [assets, equity], "Consolidated scope."


def _dupont_parts(v):
    ni, rev, assets = v.flow("net_income_group"), v.flow("revenue"), _average(v, "assets_total")
    return ni, rev, assets, _ratio(ni, rev, "Revenue is not positive."), _ratio(rev, assets, "Average total assets are not positive.")


def _dupont_margin_turnover(v):
    ni, rev, assets, margin, turnover = _dupont_parts(v)
    return margin * turnover, [ni, rev, assets], ("Group net margin × asset turnover; equals group ROA. It is after financing costs, "
                                                  "not an unlevered return.")


def _dupont_roe(v):
    ni, rev, assets, margin, turnover = _dupont_parts(v)
    equity = _average(v, "equity_total")
    leverage = _ratio(assets, equity, "Average total equity is not positive, so DuPont ROE is NM.")
    return margin * turnover * leverage, [ni, rev, assets, equity], ("Net margin × asset turnover × leverage; equals group net income ÷ "
                                                                     "average total equity. Not the same as common ROE when NCI matters.")


def _gross_margin(v):
    rev, cos = v.flow("revenue"), v.flow("cost_of_sales")
    gross = _sum("gross_profit", v.label, [(1, rev), (-1, cos)])
    return _ratio(gross, rev, "Revenue is not positive, so the margin is NM."), [rev, cos], ""


def _ebit_margin(v):
    ebit, rev = v.flow("ebit"), v.flow("revenue")
    return _ratio(ebit, rev, "Revenue is not positive, so the margin is NM."), [ebit, rev], ""


def _cfo_note(cfo):
    return "Standardised CFO; the reported basis is shown alongside." if cfo.alternative else cfo.note


def _cfo_margin(v):
    cfo, rev = _cfo(v), v.flow("revenue")
    return _ratio(cfo, rev, "Revenue is not positive, so the margin is NM."), [cfo, rev], _cfo_note(cfo), _reported_view(cfo.alternative, rev)


def _fcf_margin(v):
    fcf, rev = _fcf(v), v.flow("revenue")
    value = _ratio(fcf, rev, "Revenue is not positive, so the margin is NM.")
    return value, [fcf, rev], _fcf_note(v, fcf, scope=False), _reported_view(fcf.alternative, rev)


def _cfo_conversion(v):
    cfo, ni = _cfo(v), v.flow("net_income_group")
    value = _ratio(cfo, ni, "Group net income is not positive, so CFO conversion is NM.")
    return value, [cfo, ni], _cfo_note(cfo), _reported_view(cfo.alternative, ni)


def _accrual_ratio(v):
    ni, cfo, assets = v.flow("net_income_group"), _cfo(v), _average(v, "assets_total")
    accruals = _sum("accruals", v.label, [(1, ni), (-1, cfo)], "Group net income − CFO.")
    value = _ratio(accruals, assets, "Average total assets are not positive.")
    views = {"reported_basis": (ni.value - cfo.alternative.value) / assets.value} if cfo.alternative is not None else {}
    return value, [ni, cfo, assets], "Shows how far earnings and cash differ; on its own it is not evidence of manipulation.", views


def _capex_intensity(v):
    capex, rev = v.flow("capex"), v.flow("revenue")
    return _ratio(capex, rev, "Revenue is not positive."), [capex, rev], ""


def _quick_ratio(v):
    quick = _sum("quick_assets", v.closing_label, [(1, v.bal("cash_eligible")), (1, v.bal("short_term_investments")),
                                                   (1, v.bal("trade_receivables"))])
    cl = v.bal("current_liabilities")
    return _ratio(quick, cl, "Current liabilities are zero."), [quick, cl], ("Excludes inventory and prepayments; short-term investments "
                                                                            "are taken as reported liquid.")


def _cash_ratio(v):
    cash = _sum("cash_and_investments", v.closing_label, [(1, v.bal("cash_eligible")), (1, v.bal("short_term_investments"))])
    cl = v.bal("current_liabilities")
    return _ratio(cash, cl, "Current liabilities are zero."), [cash, cl], ""


def _gross_debt_ebitda(v):
    debt, ebitda = _debt(v), _ebitda(v)
    return _ratio(debt, ebitda, "EBITDA is zero or negative, so the ratio is NM."), [debt, ebitda], "Gross borrowing including leases."


def _payout_ratio(v):
    div, ni = v.flow("dividends_paid_common"), v.flow("net_income_common")
    return _ratio(div, ni, "Earnings attributable to common shareholders are not positive, so the payout ratio is NM."), [div, ni], ""


def _fcf_dividend_coverage(v):
    fcf, div = _fcf(v), v.flow("dividends_paid_common")
    value = _ratio(fcf, div, "No common dividends were paid, so coverage is not calculated.")
    return value, [fcf, div], _fcf_note(v, fcf), _reported_view(fcf.alternative, div)


def _nwc_sales(v):
    nwc = _sum("operating_nwc", v.closing_label, [(1, v.bal("trade_receivables")), (1, v.bal("inventories")), (-1, v.bal("trade_payables"))],
               "Approximation: receivables + inventories − payables; other operating items are not separated.")
    rev = v.flow("revenue")
    return _ratio(nwc, rev, "Revenue is not positive."), [nwc, rev], nwc.note + " A negative value can be structural."


def _free_float(v):
    free, shares = v.bal("free_float_shares"), v.bal("shares_outstanding")
    value = _ratio(free, shares, "Shares outstanding are not positive.")
    return value, [free, shares], "Definitions of free float differ by market; it does not change market capitalisation."


def _reported(field_name, label):
    def fn(v):
        source = v.annual[-1][1] if v.annual else v
        f = source.flows.get(field_name)
        if f is None:
            raise _Stop("missing", f"Missing input: {label} for {source.label}. Missing is not treated as zero.")
        note = "As reported."
        if v.annual:
            note += " Latest fiscal year: a twelve-month figure would need quarterly EPS on the same share basis."
        return {"value": f.value, "inputs": [f], "note": note, "period": f.period, "status": "reported_only"}
    return fn


def _eps_growth(v):
    if v.annual:
        (fy, view), prev = v.annual[-1], (v.annual[-2] if len(v.annual) > 1 else None)
        cur = view.flows.get("eps_diluted")
        prior = prev[1].flows.get("eps_diluted") if prev and fiscal_year(prev[0]) == fiscal_year(fy) - 1 else None
    else:
        cur, prior = v.flows.get("eps_diluted"), v.prior_flows.get("eps_diluted")
    if cur is None or prior is None:
        raise _Stop("missing", "Reported diluted EPS for two consecutive fiscal years is needed.")
    _check_units(cur, prior)
    if cur.value <= 0 or prior.value <= 0:
        raise _Stop("not_meaningful", "EPS is not positive in both years; a move between loss and profit is described, not given as a "
                                      "percentage.", [cur, prior])
    return {"value": cur.value / prior.value - 1, "inputs": [cur, prior], "period": f"{cur.period} vs {prior.period}",
            "note": f"Reported diluted EPS, {cur.period} compared with {prior.period}."}


def _revenue_cagr(v):
    years = []
    for label, view in reversed(v.annual[-(v.horizon + 1):]):
        f = view.flows.get("revenue")
        if f is None or (years and fiscal_year(years[-1][0]) - 1 != fiscal_year(label)):
            break
        years.append((label, f))
    if len(years) < 2:
        raise _Stop("missing", "Fewer than two consecutive fiscal years of revenue are available.")
    years.reverse()
    (first, begin), (last, end) = years[0], years[-1]
    n = len(years) - 1
    _check_units(begin, end)
    if begin.value <= 0 or end.value <= 0:
        raise _Stop("not_meaningful", "Revenue is not positive at the start or the end, so a growth rate is NM.", [begin, end])
    note = f"{n}-year CAGR from {first} to {last}."
    if n < v.horizon:
        note += f" A {v.horizon}-year CAGR needs {v.horizon + 1} annual observations."
    return {"value": (end.value / begin.value) ** (1 / n) - 1, "inputs": [begin, end], "note": note, "period": f"{first}–{last}"}


def _price_return(key, words):
    def fn(v):
        end, begin = v.price_points.get("end"), v.price_points.get(key)
        if end is None or begin is None:
            why = f" ({v.price_note})" if v.price_note else ""
            raise _Stop("missing", f"A split-adjusted closing price from {words} ago is not available{why}.")
        _check_units(begin, end)
        if begin.value <= 0:
            raise _Stop("not_meaningful", "The starting price is not positive.", [begin, end])
        return {"value": end.value / begin.value - 1, "inputs": [begin, end], "period": f"{begin.period} to {end.period}",
                "note": "Split-adjusted closes, without dividends. A price move does not by itself show its cause."}
    return fn


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
    historical: bool = False  # median at past fiscal year ends, or the current value against it


HISTORICAL = ["pe", "ps", "pb", "ev_ebitda", "p_fcf", "ev_sales", "ev_ebit"]  # EV/sales and EV/EBIT added 27 November 2026

HIST_NAMES = {"pe": "P/E", "ps": "P/S", "pb": "P/B", "ev_ebitda": "EV/EBITDA", "p_fcf": "P/FCF", "ev_sales": "EV/sales", "ev_ebit": "EV/EBIT"}
HIST_NOT_FOR_FINANCIALS = ("ev_ebitda", "p_fcf", "ev_sales", "ev_ebit")  # as the multiples themselves
HORIZONS = (3, 5, 10)  # fiscal years of history the user can choose; 5 is the default
YEAR_WORDS = {3: "Three", 5: "Five", 10: "Ten"}
HIST_FORMULA = ("median of the multiple at the preceding fiscal year ends in the horizon (3, 5 or 10; default 5), each from the price and "
                "the reports published by that date")

SPECS = [
    # Valuation
    Spec("pe", "P/E", "Valuation", "x", "market_cap / net_income_common (TTM)", _pe, True, peer_comparison="peer discount"),
    Spec("ps", "P/S", "Valuation", "x", "market_cap / revenue (TTM)", _ps, True, peer_comparison="peer discount"),
    Spec("pb", "P/B", "Valuation", "x", "market_cap / equity_common", _pb, True, peer_comparison="peer discount"),
    Spec("p_fcf", "P/FCF", "Valuation", "x", "market_cap / standardised FCF (TTM); reported basis alongside", _p_fcf, True, True, "peer discount"),
    Spec("ev_ebitda", "EV/EBITDA", "Valuation", "x", "enterprise_value / ebitda (TTM)", _ev_ebitda, True, True, "peer discount"),
    Spec("ev_sales", "EV/sales", "Valuation", "x", "enterprise_value / revenue (TTM)", _ev_sales, True, True, "peer discount"),
    Spec("ev_ebit", "EV/EBIT", "Valuation", "x", "enterprise_value / ebit (TTM)", _ev_ebit, True, True, "peer discount"),
    Spec("fcf_yield", "FCF yield", "Valuation", "fraction", "standardised FCF (TTM) / market_cap; reported basis alongside", _fcf_yield, True, True),
    Spec("dividend_yield", "Dividend yield", "Valuation", "fraction", "dividends per share paid (TTM) / share price", _dividend_yield, True),
    Spec("graham", "Graham multiple", "Valuation", "x", "P/E × P/B", _graham, True),
    # Historical comparison (calculated in _historical)
    *[s for base, name in HIST_NAMES.items() for s in (
        Spec(f"{base}_hist_median", f"{name} historical median", "Historical comparison", "x", HIST_FORMULA, None, True,
             base in HIST_NOT_FOR_FINANCIALS, "peer discount", historical=True),  # v1.1: against the peers' own historical medians
        Spec(f"{base}_vs_hist", f"{name} against its historical median", "Historical comparison", "fraction",
             f"current {name} / historical median − 1", None, True, base in HIST_NOT_FOR_FINANCIALS, "median only", historical=True))],
    # Debt and liquidity
    Spec("debt_equity", "Debt/equity", "Debt and liquidity", "x", "debt_inc_leases / equity_total", _debt_equity, not_for_financials=True),
    Spec("net_debt_equity", "Net debt/equity", "Debt and liquidity", "x", "net_debt / equity_total", _net_debt_equity, not_for_financials=True),
    Spec("net_debt_ebitda", "Net debt/EBITDA", "Debt and liquidity", "x", "net_debt / ebitda (TTM)", _net_debt_ebitda, not_for_financials=True),
    Spec("gross_debt_ebitda", "Gross debt/EBITDA", "Debt and liquidity", "x", "debt_inc_leases / ebitda (TTM)", _gross_debt_ebitda,
         not_for_financials=True),
    Spec("current_ratio", "Current ratio", "Debt and liquidity", "x", "current_assets / current_liabilities", _current_ratio, not_for_financials=True),
    Spec("quick_ratio", "Quick ratio", "Debt and liquidity", "x", "(cash + short-term investments + trade receivables) / current_liabilities",
         _quick_ratio, not_for_financials=True),
    Spec("cash_ratio", "Cash ratio", "Debt and liquidity", "x", "(cash + short-term investments) / current_liabilities", _cash_ratio,
         not_for_financials=True),
    Spec("interest_coverage", "Interest coverage", "Debt and liquidity", "x", "ebit / interest_expense (TTM)", _interest_coverage, not_for_financials=True),
    # Profitability
    Spec("roe_common", "Common ROE", "Profitability", "fraction", "net_income_common / average equity_common", _roe,
         peer_comparison="percentage points"),
    Spec("roa_group", "Group ROA", "Profitability", "fraction", "net_income_group / average assets_total", _roa, peer_comparison="percentage points"),
    Spec("roic", "ROIC", "Profitability", "fraction", "ebit × (1 − home-country statutory tax rate) / average invested_capital", _roic,
         not_for_financials=True, peer_comparison="percentage points"),
    Spec("net_margin", "Net profit margin", "Profitability", "fraction", "net_income_group / revenue", _net_margin, peer_comparison="percentage points"),
    Spec("ebitda_margin", "EBITDA margin", "Profitability", "fraction", "ebitda / revenue", _ebitda_margin, not_for_financials=True,
         peer_comparison="percentage points"),
    Spec("ebit_margin", "EBIT margin", "Profitability", "fraction", "ebit / revenue", _ebit_margin, not_for_financials=True,
         peer_comparison="percentage points"),
    Spec("gross_margin", "Gross margin", "Profitability", "fraction", "(revenue − cost_of_sales) / revenue", _gross_margin, not_for_financials=True,
         peer_comparison="percentage points"),
    Spec("asset_turnover", "Asset turnover", "Profitability", "x", "revenue / average assets_total", _asset_turnover),
    Spec("dupont_leverage", "DuPont financial leverage", "Profitability", "x", "average assets_total / average equity_total", _dupont_leverage),
    Spec("dupont_margin_turnover", "DuPont margin × turnover", "Profitability", "fraction", "group net margin × asset turnover",
         _dupont_margin_turnover),
    Spec("dupont_roe", "Group DuPont ROE", "Profitability", "fraction", "group net margin × asset turnover × DuPont financial leverage", _dupont_roe),
    # Cash flow and dividends
    Spec("fcf_conversion", "FCF earnings conversion", "Cash flow and dividends", "fraction", "standardised FCF / net_income_group", _fcf_conversion,
         not_for_financials=True),
    Spec("fcf_conversion_5y", "Multi-year FCF earnings conversion", "Cash flow and dividends", "fraction",
         "sum of standardised FCF / sum of net_income_group over the same fiscal years", _fcf_conversion_multi_year, not_for_financials=True,
         multi_year=True),
    Spec("cfo_conversion", "CFO earnings conversion", "Cash flow and dividends", "fraction", "standardised CFO / net_income_group",
         _cfo_conversion, not_for_financials=True),
    Spec("cfo_margin", "CFO margin", "Cash flow and dividends", "fraction", "standardised CFO / revenue", _cfo_margin, not_for_financials=True,
         peer_comparison="percentage points"),
    Spec("fcf_margin", "FCF margin", "Cash flow and dividends", "fraction", "standardised FCF / revenue", _fcf_margin, not_for_financials=True,
         peer_comparison="percentage points"),
    Spec("capex_intensity", "Capex intensity", "Cash flow and dividends", "fraction", "capex / revenue", _capex_intensity),
    Spec("accrual_ratio", "Accrual ratio", "Cash flow and dividends", "fraction", "(net_income_group − standardised CFO) / average assets_total",
         _accrual_ratio, not_for_financials=True),
    Spec("nwc_sales", "Operating NWC/sales", "Cash flow and dividends", "fraction", "operating NWC / revenue", _nwc_sales, not_for_financials=True),
    Spec("payout_ratio", "Dividend payout ratio", "Cash flow and dividends", "fraction", "dividends_paid_common / net_income_common", _payout_ratio),
    Spec("fcf_dividend_coverage", "FCF dividend coverage", "Cash flow and dividends", "x", "standardised FCF / dividends_paid_common",
         _fcf_dividend_coverage, not_for_financials=True),
    # Growth
    Spec("revenue_growth", "Revenue growth", "Growth", "fraction", "current comparable-period revenue / prior comparable-period revenue − 1",
         _revenue_growth),
    Spec("revenue_cagr", "Revenue CAGR", "Growth", "fraction", "(ending annual revenue / beginning annual revenue)^(1/n) − 1", _revenue_cagr,
         multi_year=True),
    Spec("eps_growth", "Diluted EPS growth", "Growth", "fraction", "reported diluted EPS / prior-year reported diluted EPS − 1", _eps_growth),
    # Per share and market
    Spec("bvps", "Book value per share", "Per share and market", "per share", "equity_common / shares_outstanding", _bvps, peer_comparison="none"),
    Spec("eps_basic", "Basic EPS", "Per share and market", "per share", "as reported", _reported("eps_basic", "basic EPS"), peer_comparison="none"),
    Spec("eps_diluted", "Diluted EPS", "Per share and market", "per share", "as reported", _reported("eps_diluted", "diluted EPS"),
         peer_comparison="none"),
    Spec("free_float", "Free-float percentage", "Per share and market", "fraction", "free_float_shares / shares_outstanding", _free_float),
    Spec("price_return_1m", "Price return, 1 month", "Per share and market", "fraction", "split-adjusted end price / price 1 month earlier − 1",
         _price_return("1m", "one month"), True),
    Spec("price_return_3m", "Price return, 3 months", "Per share and market", "fraction", "split-adjusted end price / price 3 months earlier − 1",
         _price_return("3m", "three months"), True),
    Spec("price_return_12m", "Price return, 12 months", "Per share and market", "fraction",
         "split-adjusted end price / price 12 months earlier − 1", _price_return("12m", "twelve months"), True),
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
        out = spec.fn(v)
    except _Stop as stop:
        return Result(spec.id, spec.name, v.label, stop.status, None, unit, spec.formula, [f.as_input() for f in stop.inputs], stop.note)
    if isinstance(out, dict):  # reported figures and measures with their own period
        return Result(spec.id, spec.name, out.get("period", v.label), out.get("status", "calculated"), out["value"], unit, spec.formula,
                      [f.as_input() for f in out["inputs"]], out.get("note", ""), out.get("views", {}))
    value, inputs, note, *rest = out
    other_views = rest[0] if rest else {}
    exclude = rest[1] if len(rest) > 1 else False
    period = rest[2] if len(rest) > 2 else v.label
    return Result(spec.id, spec.name, period, "calculated", value, unit, spec.formula, [f.as_input() for f in inputs], note, other_views, exclude)


# ---------- the analysis ----------

def _split(figures: dict) -> tuple[dict, dict]:
    period_fields = FLOW_FIELDS | PERIOD_ONLY_FIELDS
    flows = {k: f for k, f in figures.items() if k in period_fields}
    balances = {k: f for k, f in figures.items() if k not in period_fields and k not in RATE_FIELDS}
    return flows, balances


def _own_d_and_a(flows: dict) -> dict:
    """Decided 27 November 2026: when the standard D&A is missing for a period (or for any part of a twelve-month sum), the company's own
    element is used instead, only if it exists for the whole period; standard and own figures are never mixed in one sum."""
    own = flows.pop("depreciation_amortisation_own", None)
    if "depreciation_amortisation" not in flows and own is not None:
        flows["depreciation_amortisation"] = Figure("depreciation_amortisation", own.value, own.unit, own.period, own.sources,
                                                    (own.note + " " if own.note else "") + "D&A from the company's own XBRL element (see the "
                                                    "source tag), because no standard figure covers the whole period; it can be defined "
                                                    "more broadly than the standard figure used for other periods.")
    return flows


def _annual_views(c: CompanyInputs) -> list:
    years = sorted((p for p in c.periods if fiscal_year(p)), key=fiscal_year)
    views = []
    for i, fy in enumerate(years):
        flows, closing = _split(c.periods[fy])
        flows = _own_d_and_a(dict(flows))
        prev = years[i - 1] if i and fiscal_year(years[i - 1]) == fiscal_year(fy) - 1 else None
        opening = _split(c.periods[prev])[1] if prev else None
        growth = None
        if prev and "revenue" in flows and "revenue" in c.periods[prev]:
            growth = (flows["revenue"], c.periods[prev]["revenue"])
        views.append((fy, _View(fy, flows, closing, f"{fy} year end", opening,
                                f"{prev} year end" if prev else f"FY{fiscal_year(fy) - 1} year end", growth,
                                tax_rate=c.periods[fy].get("statutory_tax_rate"),
                                prior_flows=_split(c.periods[prev])[0] if prev else None)))
    for _, view in views:
        view.interest_rule = c.interest_rule
    return views


def _published_by(f: Figure, day: str | None) -> Figure | None:
    """The figure as known on `day`: only sources published by then. None when every dated source came later."""
    if day is None:
        return f
    dated = [src for src in f.sources if src.get("published")]
    if not dated:
        return f
    known = [src for src in f.sources if not src.get("published") or src["published"] <= day]
    if not any(src.get("published") for src in known):
        return None
    return Figure(f.name, f.value, f.unit, f.period, known, f.note)


def _ttm_view(c: CompanyInputs, fy_label: str, cur_label: str, prior_label: str, price, label: str, annual=None, known_by=None,
              price_points=None) -> _View:
    def known(period):
        figures = {k: _published_by(f, known_by) for k, f in c.periods.get(period, {}).items()}
        return {k: f for k, f in figures.items() if f is not None}
    fy, cur, prior = known(fy_label), known(cur_label), known(prior_label)
    flows, not_comparable = {}, {}
    for name in FLOW_FIELDS:
        if name in fy and name in cur and name in prior:
            try:
                flows[name] = _ttm(fy[name], cur[name], prior[name], label)
            except _Stop as stop:
                not_comparable[name] = stop
    flows = _own_d_and_a(flows)
    closing, opening = _split(cur)[1], _split(prior)[1] or None
    growth = (cur["revenue"], prior["revenue"]) if "revenue" in cur and "revenue" in prior else None
    view = _View(label, flows, closing, f"{cur_label} period end", opening, f"{prior_label} period end", growth, price,
                 fy.get("statutory_tax_rate"), annual, price_points=price_points)
    view.not_comparable = not_comparable
    view.interest_rule = c.interest_rule
    return view


def _current_view(c: CompanyInputs, annual: list) -> _View:
    if c.ytd_current and c.ytd_prior and c.ytd_current in c.periods:
        label = f"TTM to {c.ytd_current.removeprefix('YTD').strip()}"
        return _ttm_view(c, c.latest_fy, c.ytd_current, c.ytd_prior, c.price, label, annual, price_points=c.price_points)
    view = dict(annual)[c.latest_fy]
    view.price, view.annual, view.price_points = c.price, annual, c.price_points
    return view


def _year_end_view(c: CompanyInputs, key: str) -> _View | None:
    """The trailing twelve months as known at a past fiscal year end: the prior annual report plus that year's latest interim report."""
    day = key.removeprefix("year end ")
    year = int(day[:4])
    fy = f"FY{year - 1}"
    parts = sorted({m.group(1) for p in c.periods if (m := re.fullmatch(rf"YTD (Q[1-4]|H[12]) {year}", p))}, reverse=True)
    for part in parts:
        cur, prior = f"YTD {part} {year}", f"YTD {part} {year - 1}"
        if fy in c.periods and prior in c.periods:
            return _ttm_view(c, fy, cur, prior, c.price_points[key], f"TTM to {part} {year}, as known on {day}", known_by=day)
    return None


def _historical(c: CompanyInputs, current: dict) -> dict:
    """Median of each multiple at the preceding fiscal year ends in the horizon (v1.1), and the current multiple against it."""
    n = c.horizon_years
    keys = sorted(k for k in c.price_points if k.startswith("year end "))[-n:]
    observations = {base: [] for base in HISTORICAL}
    gaps = {base: [] for base in HISTORICAL}  # (year end, why no value), shown when the median is omitted
    for key in keys:
        view = _year_end_view(c, key)
        day = key.removeprefix("year end ")
        if view is None:
            for base in HISTORICAL:
                gaps[base].append((day, "no annual and interim reports covering the twelve months to that date"))
            continue
        for base in HISTORICAL:
            r = _run(SPECS_BY_ID[base], view, c.business_model)
            if not (r.status == "calculated" and not r.exclude_from_peer_median and r.value > 0):
                gaps[base].append((day, r.note.split(". Missing is not treated as zero")[0].rstrip(".") if r.note else r.status.replace("_", " ")))
            if r.status == "calculated" and not r.exclude_from_peer_median and r.value > 0:
                sources = []
                for item in r.inputs:
                    sources += [src for src in item["sources"] if src not in sources]
                observations[base].append(Figure(f"{r.name} at {day}", r.value, "x", day, sources, f"From {view.label}."))
    out = {}
    for base in HISTORICAL:
        median_spec, against_spec = SPECS_BY_ID[f"{base}_hist_median"], SPECS_BY_ID[f"{base}_vs_hist"]
        if median_spec.not_for_financials and c.business_model in FINANCIAL_MODELS:
            note = f"Not applicable to a {c.business_model} (v1.0 section 8)."
            for spec in (median_spec, against_spec):
                out[spec.id] = Result(spec.id, spec.name, "preceding fiscal year ends", "not_applicable", None, spec.unit, spec.formula, note=note)
            continue
        found = observations[base]
        period = f"year ends {found[0].period[:4]}–{found[-1].period[:4]}" if found else "preceding fiscal year ends"
        inputs = [o.as_input() for o in found]
        if len(found) < 3:
            note = (f"Only {len(found)} meaningful year-end value{'s' if len(found) != 1 else ''}; with fewer than three the historical "
                    "comparison is omitted (v1.1).")
            if gaps[base]:
                note += " " + " ".join(f"At {day}: {why}." for day, why in sorted(gaps[base])[-3:])
            out[median_spec.id] = Result(median_spec.id, median_spec.name, period, "missing", None, "x", median_spec.formula, inputs, note)
            out[against_spec.id] = Result(against_spec.id, against_spec.name, period, "missing", None, "fraction", against_spec.formula, [], note)
            continue
        median = statistics.median(o.value for o in found)
        note = (f"Median of {len(found)} of {n} preceding fiscal year ends ({', '.join(o.period for o in found)}), each from the price and the "
                "reports published by that date.")
        if len(found) < n:
            note += f" Actual coverage is {len(found)} year ends, not {n}."
        own = [o.period for o in found if any(":" in str(src.get("tag", "")) and not str(src["tag"]).startswith(("us-gaap:", "dei:"))
                                              for src in o.sources)]
        if own:
            note += (f" At {', '.join(own)} a figure comes from the company's own XBRL element (see the sources), which can be defined "
                     "more broadly than the standard figure used at the other year ends.")
        out[median_spec.id] = Result(median_spec.id, median_spec.name, period, "calculated", median, "x", median_spec.formula, inputs, note)
        now = current.get(base)
        if now is None or now.status != "calculated":
            out[against_spec.id] = Result(against_spec.id, against_spec.name, period, now.status if now else "missing", None, "fraction",
                                          against_spec.formula, [], "The current multiple is not calculated, so it is not compared.")
        else:
            sources = []
            for item in now.inputs:
                sources += [src for src in item["sources"] if src not in sources]
            current_figure = Figure(f"{now.name} ({now.period})", now.value, "x", now.period, sources)
            median_sources = []
            for o in found:
                median_sources += [src for src in o.sources if src not in median_sources]
            median_figure = Figure(median_spec.name, median, "x", period, median_sources, note)
            out[against_spec.id] = Result(against_spec.id, against_spec.name, now.period, "calculated", now.value / median - 1, "fraction",
                                          against_spec.formula, [current_figure.as_input(), median_figure.as_input()],
                                          "Negative means below the historical median. A description of the difference, not a valuation verdict.")
    return out


def analyse(c: CompanyInputs) -> dict:
    """Current-period indicators (TTM when interim reports exist), historical medians, and fiscal-year history for indicators that need
    no share price."""
    annual = _annual_views(c)
    history = {fy: [_run(s, v, c.business_model) for s in SPECS if not (s.needs_price or s.multi_year or s.historical)] for fy, v in annual}
    current_view = _current_view(c, annual)
    current_view.price_note = c.price_note
    current_view.horizon = c.horizon_years
    current = {s.id: _run(s, current_view, c.business_model) for s in SPECS if not s.historical}
    conversion = current["fcf_conversion_5y"]  # named for the years actually used: the horizon, or fewer when data is missing
    used = c.horizon_years
    if conversion.status == "calculated" and (m := re.fullmatch(r"FY(\d{4})–FY(\d{4})", conversion.period)):
        used = int(m.group(2)) - int(m.group(1)) + 1
    conversion.name = f"{YEAR_WORDS.get(used, used)}-year FCF earnings conversion"
    current.update(_historical(c, current))
    for r in current.values():  # say why an input is missing when the data source never has it
        for name, reason in c.source_gaps.items():
            if r.status == "missing" and f"Missing input: {name}" in r.note and reason not in r.note:
                r.note += " " + reason
    notes = [c.demo_label] if c.demo_label else []
    if c.business_model in FINANCIAL_MODELS:
        notes.append(f"Treated as a {c.business_model}: industrial cash-flow, EBITDA, debt and liquidity measures are not applicable (v1.0 section 8).")
    if not (c.ytd_current and c.ytd_prior):
        notes.append(f"No interim reports: current values use {c.latest_fy}.")
    return {"company": c.name, "demo": bool(c.demo_label), "definition_version": DEFINITION_VERSION, "business_model": c.business_model,
            "current_period": current_view.label, "horizon_years": c.horizon_years, "current": [current[s.id] for s in SPECS],
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
            elif spec.peer_comparison == "percentage points" or (spec.peer_comparison == "median only" and spec.unit == "fraction"):
                comparison, kind = r.value - median, "percentage-point difference"  # v1.1: every percentage measure
        each = {}  # every peer's own result, so each peer can be compared with the company one by one
        for t, a in peers.items():
            p = next((x for x in a["current"] if x.indicator == r.indicator), None)
            if p is not None:
                each[t] = {"value": p.value, "status": p.status, "period": p.period, "in_median": (t, p) in used}
        rows.append({"indicator": r.indicator, "name": r.name, "company_value": r.value, "company_status": r.status, "unit": r.unit,
                     "peer_median": median, "peer_count": len(values), "peers_used": [t for t, _ in used], "comparison": comparison,
                     "comparison_type": kind, "note": " ".join(notes), "peer_values": each})
    return rows
