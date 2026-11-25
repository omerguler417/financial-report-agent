# Selects three to five suitable peers with transparent criteria: business model and industry first, then geographic exposure, then size.
# Working: candidate merging with recorded origins, verification of model suggestions, criteria assessment, user-selected peers, optional index filter.
# Awaiting implementation: automatically gathering candidates from a market-data provider and from competitors named in official reports.
from dataclasses import dataclass, field

from backend.config import Settings

SOURCE_PROVIDER = "market_data_provider"
SOURCE_OFFICIAL_REPORT = "official_report"
SOURCE_INVESTOR_PRESENTATION = "investor_presentation"
SOURCE_MODEL = "model_suggestion"
SOURCE_USER = "user_selected"
SOURCE_REGULATOR = "regulator_classification"  # for example the SEC's industry code (SIC)
VERIFYING_SOURCES = {SOURCE_PROVIDER, SOURCE_OFFICIAL_REPORT, SOURCE_INVESTOR_PRESENTATION, SOURCE_REGULATOR}
LIMITED_NOTE = "It could not be compared on products, customers and regions, which the available data does not include."

METHOD = ("Peers are ordered by these criteria in turn, not by a combined score: (1) same industry and the number of "
          "business-model criteria that match (products, customer groups, revenue segments, operating model); "
          "(2) geographic revenue exposure; (3) size by revenue and market capitalisation. A company is suitable only "
          "if its industry is not different and at least as many business criteria match as differ.")


@dataclass
class Profile:
    ticker: str
    name: str = ""
    industry: str | None = None
    products: list[str] = field(default_factory=list)
    customer_groups: list[str] = field(default_factory=list)
    revenue_segments: list[str] = field(default_factory=list)
    operating_model: str | None = None
    revenue_by_region: dict[str, float] = field(default_factory=dict)  # region -> share of revenue (0-1)
    revenue: float | None = None       # same currency for all companies being compared
    market_cap: float | None = None
    indices: list[str] = field(default_factory=list)


@dataclass
class Candidate:
    profile: Profile
    sources: list[dict] = field(default_factory=list)  # [{"type": ..., "detail": ...}]

    @property
    def verified(self) -> bool:
        return any(s["type"] in VERIFYING_SOURCES | {SOURCE_USER} for s in self.sources)

    @property
    def user_selected(self) -> bool:
        return any(s["type"] == SOURCE_USER for s in self.sources)


def merge_candidates(*groups: list[Candidate]) -> list[Candidate]:
    """Combine candidate lists from different sources, keeping every recorded origin."""
    merged: dict[str, Candidate] = {}
    for group in groups:
        for cand in group:
            key = cand.profile.ticker.upper()
            if key not in merged:
                merged[key] = Candidate(cand.profile, list(cand.sources))
            else:
                existing = merged[key]
                existing.sources.extend(s for s in cand.sources if s not in existing.sources)
                for attr, value in vars(cand.profile).items():
                    if value not in (None, "", [], {}) and getattr(existing.profile, attr) in (None, "", [], {}):
                        setattr(existing.profile, attr, value)
    return list(merged.values())


def _norm_set(items):
    return {i.strip().lower() for i in items if i and i.strip()}


def _overlap(label, target_items, cand_items):
    t, c = _norm_set(target_items), _norm_set(cand_items)
    if not t or not c:
        return {"criterion": label, "result": "unknown", "evidence": f"{label} not available for {'the target' if not t else 'this company'}."}
    shared = sorted(t & c)
    if shared:
        return {"criterion": label, "result": "match", "evidence": f"Shares {len(shared)} of the target's {len(t)}: {', '.join(shared)}."}
    return {"criterion": label, "result": "differs", "evidence": f"None of the target's {len(t)} {label.lower()} listed."}


def _primary_region(regions: dict[str, float]):
    return max(regions.items(), key=lambda kv: kv[1]) if regions else None


def assess(target: Profile, cand: Profile, settings: Settings) -> dict:
    business = [
        _overlap("Products", target.products, cand.products),
        _overlap("Customer groups", target.customer_groups, cand.customer_groups),
        _overlap("Revenue segments", target.revenue_segments, cand.revenue_segments),
    ]
    if target.operating_model and cand.operating_model:
        same = target.operating_model.strip().lower() == cand.operating_model.strip().lower()
        business.append({"criterion": "Operating model", "result": "match" if same else "differs",
                         "evidence": f"Target: {target.operating_model}; this company: {cand.operating_model}."})
    else:
        business.append({"criterion": "Operating model", "result": "unknown", "evidence": "Operating model not available."})

    if target.industry and cand.industry:
        industry = {"criterion": "Industry", "result": "match" if target.industry.lower() == cand.industry.lower() else "differs",
                    "evidence": f"Target: {target.industry}; this company: {cand.industry}."}
    else:
        industry = {"criterion": "Industry", "result": "unknown", "evidence": "Industry classification not available."}

    tp, cp = _primary_region(target.revenue_by_region), _primary_region(cand.revenue_by_region)
    if tp and cp:
        geography = {"criterion": "Geographic exposure", "result": "match" if tp[0].lower() == cp[0].lower() else "differs",
                     "evidence": f"Largest revenue region: target {tp[0]} ({tp[1]:.0%}); this company {cp[0]} ({cp[1]:.0%})."}
    else:
        geography = {"criterion": "Geographic exposure", "result": "unknown", "evidence": "Revenue by region not available."}

    size = []
    for label, a, b in (("Revenue", target.revenue, cand.revenue), ("Market capitalisation", target.market_cap, cand.market_cap)):
        if a and b and a > 0 and b > 0:
            ratio = b / a
            similar = 1 / settings.size_similarity_ratio <= ratio <= settings.size_similarity_ratio
            size.append({"criterion": label, "result": "match" if similar else "differs",
                         "evidence": f"{ratio:.2f} times the target's {label.lower()}."})
        else:
            size.append({"criterion": label, "result": "unknown", "evidence": f"{label} not available."})

    matches = sum(c["result"] == "match" for c in business)
    differs = sum(c["result"] == "differs" for c in business)
    suitable = industry["result"] != "differs" and matches >= 1 and matches >= differs
    # decided 25 November 2026: with no business information at all, the same official industry code counts, as limited comparability
    limited = not suitable and industry["result"] == "match" and all(c["result"] == "unknown" for c in business)
    all_criteria = [industry, *business, geography, *size]
    return {
        "suitable": suitable or limited,
        "limited": limited,
        "criteria": all_criteria,
        "missing_information": [c["criterion"] for c in all_criteria if c["result"] == "unknown"],
        "order_key": (
            0 if industry["result"] == "match" else 1,
            -matches,
            0 if geography["result"] == "match" else (1 if geography["result"] == "unknown" else 2),
            -sum(c["result"] == "match" for c in size),
        ),
    }


def _explain(cand: Candidate, assessment: dict) -> str:
    matched = [c["criterion"].lower() for c in assessment["criteria"] if c["result"] == "match"]
    differs = [c["criterion"].lower() for c in assessment["criteria"] if c["result"] == "differs"]
    text = f"Matches on: {', '.join(matched) or 'no criteria'}."
    if differs:
        text += f" Material differences: {', '.join(differs)}."
    return text


def select_peers(target: Profile, candidates: list[Candidate], settings: Settings,
                 index_filter: str | None = None, requested_total: int | None = None) -> dict:
    notes, excluded = [], []
    user_picks = [c for c in candidates if c.user_selected and c.profile.ticker.upper() != target.ticker.upper()]
    total = max(len(user_picks), settings.max_peers, requested_total or 0)
    if requested_total and requested_total < settings.max_peers:
        total = max(requested_total, len(user_picks))

    peers = []
    for cand in user_picks:
        a = assess(target, cand.profile, settings)
        label = "user-requested" if a["suitable"] else "user-requested comparison (limited comparability)"
        explanation = _explain(cand, a)
        if not a["suitable"]:
            explanation += " Kept because you asked for it; treat the comparison with caution."
        peers.append({"ticker": cand.profile.ticker, "name": cand.profile.name, "label": label, "sources": cand.sources,
                      "criteria": a["criteria"], "missing_information": a["missing_information"], "explanation": explanation})

    pool = []
    for position, cand in enumerate(candidates):
        if cand in user_picks or cand.profile.ticker.upper() == target.ticker.upper():
            continue
        if not cand.verified:
            excluded.append({"ticker": cand.profile.ticker, "reason": "Model suggestion not yet verified by a market-data provider or official report.",
                             "sources": cand.sources})
            continue
        a = assess(target, cand.profile, settings)
        if not a["suitable"]:
            excluded.append({"ticker": cand.profile.ticker, "reason": "Not suitable: " + _explain(cand, a), "sources": cand.sources})
            continue
        pool.append((cand, a, position))
    pool.sort(key=lambda entry: (entry[1]["order_key"], entry[2]))  # ties keep the candidates' order (for example closest in size)
    pool = [(cand, a) for cand, a, _ in pool]

    places = max(0, total - len(peers))
    if index_filter:
        in_index = [p for p in pool if index_filter.lower() in (i.lower() for i in p[0].profile.indices)]
        chosen = in_index[:places]
        if len(peers) + len(chosen) < settings.min_peers:
            extra = [p for p in pool if p not in in_index][: settings.min_peers - len(peers) - len(chosen)]
            if extra:
                notes.append(f"Too few suitable peers in {index_filter}; added {len(extra)} from outside the index.")
            chosen += extra
    else:
        chosen = pool[:places]

    for cand, a in chosen:
        limited = a.get("limited")
        peers.append({"ticker": cand.profile.ticker, "name": cand.profile.name,
                      "label": "selected (matched on SEC industry code and size only)" if limited else "selected", "sources": cand.sources,
                      "criteria": a["criteria"], "missing_information": a["missing_information"],
                      "explanation": _explain(cand, a) + (" " + LIMITED_NOTE if limited else "")})

    minimum = min(settings.min_peers, total)
    if len(peers) < minimum:
        notes.append(f"Only {len(peers)} suitable peer(s) found; no unsuitable companies were added to reach {minimum}.")
    if not peers:
        notes.append("No suitable peers: the company is compared with its own history only.")
    return {"target": target.ticker, "method": METHOD, "index_filter": index_filter, "peers": peers,
            "excluded": excluded, "notes": notes}
