# Runs one analysis in order: identify the company, select peers, Agent 1, Agent 2, Agent 3, save. Runs in the background with progress.
# Every analysis uses live services (SEC EDGAR, the text model, and the price and call-transcript providers when configured); the tests
# pass their own stand-ins through AnalysisJobs(services=...).
# A live analysis needs the text model and SEC identification (it stops with HTTP 424 listing what is missing); share prices and call
# transcripts are optional and, without a provider, are shown as not available. It never falls back to other data.
import json
import os
import re
import threading
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone

from backend import llm
from backend import services as service_registry
from backend.agents import call_analyst, financial_analyst, report_combiner
from backend.config import Settings
from backend.errors import ProviderNotConfigured, ServicesNotReady
from backend.fetchers import call_transcripts, edgar, filings, market_data
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


class EdgarDocuments:
    """The latest 10-K and 10-Q from EDGAR (downloaded through PoliteClient into the document cache) and the user's uploaded transcript."""

    name = edgar.NAME

    def __init__(self, sec, store, settings, client, as_of: date, transcript: dict | None, calls=None):
        self.sec, self.store, self.settings, self.client, self.as_of, self.transcript = sec, store, settings, client, as_of, transcript
        self.calls = calls  # the earnings-call transcript provider, when configured
        self.notes: list[str] = []
        self._fetched: dict = {}

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
        if self.transcript:  # the user's upload comes first: no provider request is made
            docs.append({"doc_id": self.transcript["id"], "kind": "transcript", "title": f"Uploaded by you: {self.transcript['filename']}",
                         "period": None, "publication_date": None, "url": None, "path": str(self.store.current_path(self.transcript)),
                         "source_name": "your upload", "origin": "user_upload"})
        else:
            docs += self._provider_call(ticker, docs)
        return docs

    def _provider_call(self, ticker: str, reports: list[dict]) -> list[dict]:
        """The call of the same fiscal quarter as the latest report, fetched once per analysis; otherwise a note says why there is none."""
        if ticker in self._fetched:
            return self._fetched[ticker]
        self._fetched[ticker] = []
        if self.calls is None:
            self._note("Earnings-call transcripts are not fetched automatically: " + service_registry.SPECS["call_transcripts"]["how"])
        elif reports:
            latest = max(reports, key=lambda d: d["period"])
            quarter = self.sec.fiscal_quarter(ticker, latest["period"])
            try:
                self._fetched[ticker] = [self.calls.fetch(ticker, quarter)]
            except call_transcripts.CallTranscriptUnavailable as exc:
                self._note(f"The earnings call for fiscal {quarter} could not be fetched from {self.calls.name}: {exc}")
        return self._fetched[ticker]

    def _note(self, text: str):
        if text not in self.notes:
            self.notes.append(text)


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
    calls = (call_transcripts.get_provider(settings, client)
             if service_registry.status(settings, "call_transcripts") == service_registry.CONFIGURED else None)
    return LiveServices(market=LiveMarket(sec, prices), documents=EdgarDocuments(sec, store, settings, client, as_of, transcript, calls),
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
    def __init__(self, store: Store, settings: Settings, transport=None, services=None):
        self.store, self.settings, self.transport = store, settings, transport
        self._services = services  # tests only: a function (as_of, transcript id) -> stand-in services; live services otherwise
        self._threads: dict[str, threading.Thread] = {}

    def services_for(self, as_of: date | None = None, transcript: str | None = None):
        if self._services is not None:
            return self._services(as_of, transcript)
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

    def saved(self) -> list[dict]:
        """Finished analyses kept on the server, newest first: what "My reports" shows in any browser."""
        out = []
        for path in self.store.jobs_dir.glob("analysis_*.report.json"):
            job_id = path.name.removeprefix("analysis_").removesuffix(".report.json")
            try:
                state = self.get(job_id)
            except (KeyError, ValueError):
                continue
            out.append({"id": job_id, "ticker": state["company"]["ticker"], "name": state["company"]["name"],
                        "analysis_date": state["as_of"], "created_at": state["created_at"]})
        return sorted(out, key=lambda a: a["created_at"], reverse=True)

    def delete(self, job_id: str):
        """Removes an analysis and its report from the server."""
        paths = [self._path(job_id), self._path(job_id, "report.json")]
        if not paths[0].exists():
            raise KeyError(job_id)
        for path in paths:
            path.unlink(missing_ok=True)

    def _save(self, state: dict):
        state["updated_at"] = _now()
        _write_whole(self._path(state["id"]), state)

    def create(self, query: str, output_language: str, user_peers: list[str], as_of: date, chosen: list[str] | None = None,
               transcript: str | None = None, horizon: int = 5, questions: list[str] | None = None) -> dict:
        services = self.services_for(as_of, transcript)  # stops here if a required service is not ready
        company = identify(query, services.market)
        state = {"id": uuid.uuid4().hex[:12], "query": query, "company": company, "output_language": output_language,
                 "user_peers": user_peers, "as_of": as_of.isoformat(), "indicators": chosen, "horizon_years": horizon, "questions": questions or [], "transcript_upload": transcript, "status": "queued", "error": None, "steps_done": ["identify"],
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
            services = self.services_for(as_of, state.get("transcript_upload"))
            company = state["company"]
            self._step(state, "peers")
            peers = choose_peers(company["ticker"], services, self.settings, state["user_peers"])
            self._step(state, "peers", done=True)
            context: dict = {}  # pages read and results, so Agent 3's citations can be checked against them
            self._step(state, "agent1")
            agent1 = financial_analyst.run(company, peers, services, as_of, context, state.get("indicators"), state.get("horizon_years", 5))
            self._step(state, "agent1", done=True)
            self._step(state, "agent2")
            agent2 = call_analyst.run(company, services, as_of, context)
            self._step(state, "agent2", done=True)
            self._step(state, "agent3")
            agent3 = report_combiner.run(company, agent1, agent2, services, context, state.get("questions", []))
            self._step(state, "agent3", done=True)
            report = {"id": job_id, "company": company, "analysis_date": state["as_of"], "output_language": state["output_language"],
                      "created_at": _now(), "peers": peers, "agent1": agent1, "agent2": agent2, "agent3": agent3}
            _write_whole(self._path(job_id, "report.json"), report)
            state["status"] = "completed"
            self._step(state, "save", done=True)
        except Exception as exc:
            state.update(status="failed", error=str(exc) or type(exc).__name__)
            self._save(state)
