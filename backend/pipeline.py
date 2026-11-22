# Runs one analysis in order: identify the company, select peers, Agent 1, Agent 2, Agent 3, save. Runs in the background with progress.
# This is the one place that switches between demo and live services: the demo folder is loaded only when the user picks demo mode.
# A live analysis first checks every service it needs and lists all that are not ready (HTTP 424); it never falls back to demo data.
import json
import re
import threading
import uuid
from datetime import date, datetime, timezone

from backend import services as service_registry
from backend.agents import financial_analyst, meeting_news_analyst, report_combiner
from backend.config import Settings
from backend.errors import ProviderNotConfigured, ServicesNotReady
from backend.peer_selection import SOURCE_PROVIDER, SOURCE_USER, Candidate, Profile, merge_candidates, select_peers
from backend.storage import Store

STEPS = ["identify", "peers", "agent1", "agent2", "agent3", "save"]
REPORT_DISCOVERY = {"service": "Finding company reports (investor relations sites, SEC EDGAR)", "missing": [],
                    "how_to_configure": "Not built yet: automatic report discovery is awaiting implementation. Demo mode works without it."}


class CompanyNotFound(Exception):
    pass


class AmbiguousCompany(Exception):
    def __init__(self, candidates: list[dict]):
        super().__init__("Several companies match; choose one by its ticker.")
        self.candidates = candidates


def demo_services():
    from backend.demo.demo_providers import demo_services as build  # loaded only for a demo analysis the user chose
    return build()


def live_services(settings: Settings):
    """Checks every service a live analysis needs and raises one error listing all that are not ready."""
    problems = []
    for key in ("text_model", "market_data", "news"):
        try:
            service_registry.require(settings, key)
        except ProviderNotConfigured as exc:
            problems.append(exc.to_dict())
    if not any(p["service"] == service_registry.SPECS["text_model"]["label"] for p in problems):
        from backend import llm
        if not hasattr(llm.ADAPTERS.get(settings.llm_provider), "ask"):
            problems.append({"service": service_registry.SPECS["text_model"]["label"], "missing": [],
                             "how_to_configure": f"The '{settings.llm_provider}' adapter can transcribe and translate but cannot yet run the "
                                                 "analysis tasks; that part is added once a provider is chosen."})
    problems.append(REPORT_DISCOVERY)
    raise ServicesNotReady(problems)


def identify(query: str, market) -> dict:
    """An exact ticker wins; one match is used; several matches are returned to the user to choose from."""
    results = market.search(query.strip())
    exact = [r for r in results if r["ticker"].upper() == query.strip().upper()]
    if exact:
        return exact[0]
    if len(results) == 1:
        return results[0]
    if not results:
        raise CompanyNotFound(f"No company matches '{query}'.")
    raise AmbiguousCompany(results)


def _profile(p: dict) -> Profile:
    return Profile(ticker=p["ticker"], name=p.get("name", ""), industry=p.get("industry"), products=p.get("products", []),
                   customer_groups=p.get("customer_groups", []), revenue_segments=p.get("revenue_segments", []),
                   operating_model=p.get("operating_model"), revenue_by_region=p.get("revenue_by_region", {}),
                   revenue=p.get("revenue"), market_cap=p.get("market_cap"))


def choose_peers(ticker: str, services, settings: Settings, user_peers: list[str] | None = None) -> dict:
    market, notes = services.market, []
    provider = [Candidate(_profile(market.profile(t)), [{"type": SOURCE_PROVIDER, "detail": market.name}]) for t in market.peers(ticker)]
    chosen = []
    for t in user_peers or []:
        try:
            chosen.append(Candidate(_profile(market.profile(t)), [{"type": SOURCE_USER, "detail": "chosen by the user"}]))
        except KeyError:
            notes.append(f"{t} was not found, so it could not be added as a peer.")
    result = select_peers(_profile(market.profile(ticker)), merge_candidates(provider, chosen), settings)
    result["notes"] = notes + result["notes"]
    return result


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AnalysisJobs:
    def __init__(self, store: Store, settings: Settings):
        self.store, self.settings = store, settings
        self._threads: dict[str, threading.Thread] = {}

    def services_for(self, demo: bool):
        return demo_services() if demo else live_services(self.settings)

    def _path(self, job_id: str, suffix: str = "json"):
        if not re.fullmatch(r"[0-9a-f]{12}", job_id or ""):
            raise KeyError(job_id)
        return self.store.jobs_dir / f"analysis_{job_id}.{suffix}"

    def get(self, job_id: str) -> dict:
        path = self._path(job_id)
        if not path.exists():
            raise KeyError(job_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def result(self, job_id: str) -> dict:
        path = self._path(job_id, "report.json")
        if not path.exists():
            raise KeyError(job_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def _save(self, state: dict):
        state["updated_at"] = _now()
        self._path(state["id"]).write_text(json.dumps(state, indent=2), encoding="utf-8")

    def create(self, query: str, demo: bool, output_language: str, user_peers: list[str], as_of: date) -> dict:
        services = self.services_for(demo)  # a live analysis stops here with the full list of services it still needs
        company = identify(query, services.market)
        state = {"id": uuid.uuid4().hex[:12], "query": query, "company": company, "demo": demo, "output_language": output_language,
                 "user_peers": user_peers, "as_of": as_of.isoformat(), "status": "queued", "error": None, "steps_done": ["identify"],
                 "current_step": "queued", "progress_percent": int(100 / len(STEPS)), "created_at": _now()}
        self._save(state)
        return state

    def start(self, job_id: str, background: bool = True) -> dict:
        state = self.get(job_id)
        if state["status"] == "running" and job_id in self._threads and self._threads[job_id].is_alive():
            return state
        state.update(status="running", error=None)
        self._save(state)
        if background:
            self._threads[job_id] = threading.Thread(target=self._run, args=(job_id,), daemon=True)
            self._threads[job_id].start()
        else:
            self._run(job_id)
        return self.get(job_id)

    def _step(self, state: dict, step: str, done: bool = False):
        if done:
            state["steps_done"].append(step)
        state["current_step"] = step
        state["progress_percent"] = int(100 * len(state["steps_done"]) / len(STEPS))
        self._save(state)

    def _run(self, job_id: str):
        state = self.get(job_id)
        try:
            services = self.services_for(state["demo"])
            as_of = date.fromisoformat(state["as_of"])
            company = state["company"]
            self._step(state, "peers")
            peers = choose_peers(company["ticker"], services, self.settings, state["user_peers"])
            self._step(state, "peers", done=True)
            context: dict = {}  # pages read and results, so Agent 3's citations can be checked against them
            self._step(state, "agent1")
            agent1 = financial_analyst.run(company, peers, services, as_of, context)
            self._step(state, "agent1", done=True)
            self._step(state, "agent2")
            agent2 = meeting_news_analyst.run(company, services, as_of, context)
            self._step(state, "agent2", done=True)
            self._step(state, "agent3")
            agent3 = report_combiner.run(company, agent1, agent2, services, context)
            self._step(state, "agent3", done=True)
            notes = []
            if state["demo"] and state["output_language"] != "en":
                notes.append("The demo's recorded answers are in English, so this demo report is in English.")
            report = {"id": job_id, "mode": "demo" if state["demo"] else "live", "demo_label": getattr(services, "label", None),
                      "company": company, "analysis_date": state["as_of"], "output_language": state["output_language"],
                      "created_at": _now(), "peers": peers, "agent1": agent1, "agent2": agent2, "agent3": agent3, "notes": notes}
            self._path(job_id, "report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
            state["status"] = "completed"
            self._step(state, "save", done=True)
        except Exception as exc:
            state.update(status="failed", error=str(exc) or type(exc).__name__)
            self._save(state)
