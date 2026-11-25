# Runs one analysis in order: identify the company, select peers, Agent 1, Agent 2, Agent 3, save. Runs in the background with progress.
# This is the one place that switches between demo and live services: the demo folder is loaded only when the user picks demo mode.
# A live analysis needs the text model and SEC identification (it stops with HTTP 424 listing what is missing); share prices and news
# are optional and, without a provider, are shown as not available. It never falls back to demo data.
import json
import os
import re
import threading
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone

from backend import llm
from backend import services as service_registry
from backend.agents import financial_analyst, meeting_news_analyst, report_combiner
from backend.config import Settings
from backend.errors import ProviderNotConfigured, ServicesNotReady
from backend.fetchers import edgar, filings, market_data
from backend.fetchers.http_client import PoliteClient
from backend.peer_selection import SOURCE_PROVIDER, SOURCE_USER, Candidate, Profile, merge_candidates, select_peers
from backend.storage import Store

STEPS = ["identify", "peers", "agent1", "agent2", "agent3", "save"]
class CompanyNotFound(Exception):
    pass


class AmbiguousCompany(Exception):
    def __init__(self, candidates: list[dict]):
        super().__init__("Several companies match; choose one by its ticker.")
        self.candidates = candidates


def demo_services():
    from backend.demo.demo_providers import demo_services as build  # loaded only for a demo analysis the user chose
    return build()


class LiveMarket:
    """Company search, profiles and peers from EDGAR; share prices from the configured market-data provider, if there is one."""

    def __init__(self, sec, prices=None):
        self.sec, self.prices = sec, prices
        self.name = edgar.NAME + (f" + {prices.SOURCE}" if prices is not None else "")

    def search(self, query):
        return self.sec.search(query)

    def profile(self, ticker):
        return self.sec.profile(ticker)

    def peers(self, ticker):
        return self.sec.peers(ticker)

    @property
    def peer_source(self):
        return self.sec.peer_source

    def daily_series(self, ticker, start, end):
        return (self.prices or self.sec).daily_series(ticker, start, end)


@dataclass
class LiveServices:
    market: object
    documents: object
    model: object
    figures: object
    news: object = None  # no news provider yet: Agent 2 says so
    label: str | None = None  # live data carries no demo label


class EdgarDocuments:
    """The latest 10-K and 10-Q from EDGAR (downloaded through PoliteClient into the document cache) and the user's uploaded transcript."""

    name = edgar.NAME

    def __init__(self, sec, store, settings, client, as_of: date, transcript: dict | None):
        self.sec, self.store, self.settings, self.client, self.as_of, self.transcript = sec, store, settings, client, as_of, transcript

    def find(self, ticker: str) -> list[dict]:
        docs = []
        for f in self.sec.latest_reports(ticker, self.as_of):
            meta, _ = filings.retrieve_document(f["url"], self.store, self.client, self.settings, reporting_period=f["report_date"],
                                                publication_date=f["filed"])
            docs.append({"doc_id": f["accession"], "kind": "annual_report" if f["form"].startswith("10-K") else "quarterly_report",
                         "title": f"{f['form']} for the period ended {f['report_date']} (filed {f['filed']})", "period": f["report_date"],
                         "publication_date": f["filed"], "url": f["url"], "path": str(self.store.current_path(meta)), "source_name": edgar.NAME,
                         "currency": "USD", "units": "as filed", "consolidation_scope": "consolidated", "accounting_framework": "US GAAP",
                         "restatement_status": "as filed"})
        if self.transcript:
            docs.append({"doc_id": self.transcript["id"], "kind": "transcript", "title": f"Uploaded by you: {self.transcript['filename']}",
                         "period": None, "publication_date": None, "url": None, "path": str(self.store.current_path(self.transcript)),
                         "source_name": "your upload", "origin": "user_upload"})
        return docs


def live_services(settings: Settings, store: Store, as_of: date, transcript_id: str | None = None, transport=None) -> LiveServices:
    """What a live analysis uses. Stops with one error listing every required service that is not ready (text model, SEC identification)."""
    problems = []
    try:
        service_registry.require(settings, "text_model")
        if not hasattr(llm.ADAPTERS.get(settings.llm_provider), "ask"):
            problems.append({"service": service_registry.SPECS["text_model"]["label"], "missing": [],
                             "how_to_configure": f"The '{settings.llm_provider}' adapter cannot run the analysis tasks."})
    except ProviderNotConfigured as exc:
        problems.append(exc.to_dict())
    try:
        service_registry.require(settings, "sec_edgar")
    except ProviderNotConfigured as exc:
        problems.append(exc.to_dict())
    if problems:
        raise ServicesNotReady(problems)
    client = PoliteClient(settings, transport=transport)
    sec = edgar.Edgar(client, settings, as_of)
    transcript = store.get(transcript_id) if transcript_id else None
    prices = market_data.get_provider(settings, client) if service_registry.status(settings, "market_data") == service_registry.CONFIGURED else None
    return LiveServices(market=LiveMarket(sec, prices), documents=EdgarDocuments(sec, store, settings, client, as_of, transcript),
                        model=llm.get_text_model(settings, transport=transport), figures=sec.figures)


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
    try:
        tickers = market.peers(ticker)
    except Exception as exc:  # peer search must never stop an analysis; the report says why there are no peers
        tickers = []
        notes.append(f"Peer candidates could not be found ({type(exc).__name__}: {str(exc)[:160]}).")
    source = getattr(market, "peer_source", None) or {"type": SOURCE_PROVIDER, "detail": market.name}
    provider = [Candidate(_profile(market.profile(t)), [source]) for t in tickers]
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


def _write_whole(path, data: dict):
    """Write to a temporary file, then swap it in, so a reader never sees a half-written file."""
    temporary = path.with_name(path.name + f".{threading.get_ident()}.tmp")
    temporary.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    os.replace(temporary, path)


class AnalysisJobs:
    def __init__(self, store: Store, settings: Settings, transport=None):
        self.store, self.settings, self.transport = store, settings, transport
        self._threads: dict[str, threading.Thread] = {}

    def services_for(self, demo: bool, as_of: date | None = None, transcript: str | None = None):
        if demo:
            return demo_services()
        return live_services(self.settings, self.store, as_of or date.today(), transcript, self.transport)

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
        _write_whole(self._path(state["id"]), state)

    def create(self, query: str, demo: bool, output_language: str, user_peers: list[str], as_of: date, chosen: list[str] | None = None,
               transcript: str | None = None) -> dict:
        services = self.services_for(demo, as_of, transcript)  # a live analysis stops here if a required service is not ready
        company = identify(query, services.market)
        state = {"id": uuid.uuid4().hex[:12], "query": query, "company": company, "demo": demo, "output_language": output_language,
                 "user_peers": user_peers, "as_of": as_of.isoformat(), "indicators": chosen, "transcript_upload": transcript, "status": "queued", "error": None, "steps_done": ["identify"],
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
            as_of = date.fromisoformat(state["as_of"])
            services = self.services_for(state["demo"], as_of, state.get("transcript_upload"))
            company = state["company"]
            self._step(state, "peers")
            peers = choose_peers(company["ticker"], services, self.settings, state["user_peers"])
            self._step(state, "peers", done=True)
            context: dict = {}  # pages read and results, so Agent 3's citations can be checked against them
            self._step(state, "agent1")
            agent1 = financial_analyst.run(company, peers, services, as_of, context, state.get("indicators"))
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
            _write_whole(self._path(job_id, "report.json"), report)
            state["status"] = "completed"
            self._step(state, "save", done=True)
        except Exception as exc:
            state.update(status="failed", error=str(exc) or type(exc).__name__)
            self._save(state)
