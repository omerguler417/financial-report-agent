# FastAPI application: serves the frontend and the API from one process (port 8000 by default).
import os
from typing import Literal
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Loads variables from a local .env if one exists; the app also starts without one.
# Values are never printed or logged.
load_dotenv()

from backend import (indicators, language, llm, peer_selection, pipeline, report_blocks, report_export, report_reader, services,  # noqa: E402
                     storage, transcription)
from backend.config import Settings, get_settings  # noqa: E402
from backend.errors import ProviderNotConfigured, ServicesNotReady  # noqa: E402
from backend.fetchers import market_data  # noqa: E402
from backend.fetchers.http_client import AccessDenied, FetchFailed, PoliteClient  # noqa: E402

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

class TranscriptionRequest(BaseModel):
    upload_id: str
    output_language: str | None = None
    check_against: list[str] = []


MAX_QUESTIONS, MAX_QUESTION_LENGTH = 3, 300


class AnalysisRequest(BaseModel):
    company: str
    output_language: str | None = None
    peers: list[str] = []
    as_of: date | None = None  # analysis date; reports published later are left out
    indicators: list[str] | None = None  # indicator ids to report; all when left out
    transcript_upload: str | None = None  # an uploaded earnings-call transcript for Agent 2 (live analyses)
    horizon_years: Literal[3, 5, 10] = 5  # fiscal years of history; also the window of the multi-year indicators
    questions: list[str] = []  # the user's own questions, at most three, answered by Agent 3 from the sources only


class PeerRequest(BaseModel):
    target: dict
    candidates: list[dict]
    index_filter: str | None = None
    requested_total: int | None = None


def create_app(settings: Settings | None = None, provider_factory=None, run=None, background_jobs: bool = True, transport=None,
               analysis_services=None) -> FastAPI:
    """analysis_services: tests only, a function (as_of, transcript id) -> stand-in services for an analysis."""
    settings = settings or get_settings()
    store = storage.Store(settings.storage_dir)
    jobs = transcription.TranscriptionJobs(
        store, settings,
        provider_factory=provider_factory or (lambda: llm.get_provider(settings)),
        run=run or transcription.subprocess.run,
        document_text=lambda meta: report_reader.plain_text(store.current_path(meta)),
    )

    @asynccontextmanager
    async def lifespan(_app):
        store.cleanup_temp(settings.temp_retention_days)
        yield

    app = FastAPI(title="Financial Report Analysis Agent", lifespan=lifespan)
    analyses = pipeline.AnalysisJobs(store, settings, transport, analysis_services)
    app.state.settings, app.state.store, app.state.jobs, app.state.analyses = settings, store, jobs, analyses

    @app.middleware("http")
    async def always_recheck_the_page(request: Request, call_next):
        """The page, script and styles are re-checked on every visit, so a browser never shows an old copy after an update."""
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    @app.exception_handler(ProviderNotConfigured)
    async def not_configured(_request, exc: ProviderNotConfigured):
        return JSONResponse(status_code=424, content={"detail": str(exc), "needs_configuration": exc.to_dict()})

    @app.exception_handler(ServicesNotReady)
    async def services_not_ready(_request, exc: ServicesNotReady):
        return JSONResponse(status_code=424, content={"detail": str(exc), "needs_configuration": exc.items})

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/")
    def index():
        return FileResponse(FRONTEND_DIR / "index.html")

    @app.get("/api/config")
    def config():
        return {**settings.public_view(), "ffmpeg_available": transcription.ffmpeg_available(),
                "services": services.service_status(settings),
                "indicators": [{"id": s.id, "name": s.name, "group": s.group} for s in indicators.SPECS]}

    @app.get("/api/services")
    def service_list():
        """Each external service with its status (configured, awaiting configuration, or no adapter yet) and setup instructions. Never includes keys."""
        return services.service_status(settings)

    # ---- uploads ----

    @app.get("/api/uploads")
    def list_files():
        return store.list_documents()

    @app.post("/api/uploads")
    def upload(request: Request, file: UploadFile = File(...), notes: str | None = Form(None),
               reporting_period: str | None = Form(None)):
        declared = int(request.headers.get("content-length") or 0)
        if declared > settings.max_upload_bytes + 1024 * 1024:
            raise HTTPException(413, f"The file is larger than {settings.max_upload_mb} MB. " + transcription.limit_advice(settings))
        try:
            meta = store.save_upload(file.file, file.filename or "upload", file.content_type or "",
                                     max_bytes=settings.max_upload_bytes, notes=notes, reporting_period=reporting_period)
        except storage.UnsupportedFileType as exc:
            raise HTTPException(415, str(exc))
        except storage.UploadTooLarge:
            raise HTTPException(413, f"The file is larger than {settings.max_upload_mb} MB. " + transcription.limit_advice(settings))
        meta["warnings"] = []
        if meta["kind"] == "recording":
            if transcription.ffmpeg_available():
                path = store.current_path(meta)
                try:
                    duration = transcription.probe_duration(path)
                    transcription.check_recording_limits(path.stat().st_size, duration, settings)
                except transcription.RecordingLimitExceeded as exc:
                    store.delete_document(meta["id"])
                    raise HTTPException(413, str(exc))
                except Exception:
                    meta["warnings"].append("The recording's length could not be read; it may not be a valid audio or video file.")
            else:
                meta["warnings"].append("FFmpeg is not installed, so the recording's length was not checked and it cannot be transcribed yet.")
        return meta

    @app.delete("/api/uploads/{doc_id}")
    def delete_file(doc_id: str):
        try:
            store.delete_document(doc_id)
        except storage.NotFound:
            raise HTTPException(404, "File not found.")
        return {"deleted": doc_id}

    # ---- transcription jobs ----

    @app.post("/api/transcriptions")
    def start_transcription(req: TranscriptionRequest):
        if provider_factory is None:
            services.require(settings, "transcription")  # setup message before any job is created
        try:
            target = language.resolve_output_language(req.output_language, settings)
            state = jobs.create(req.upload_id, target, req.check_against)
        except language.UnsupportedLanguage as exc:
            raise HTTPException(400, str(exc))
        except storage.NotFound:
            raise HTTPException(404, "Upload not found.")
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        return jobs.start(state["id"], background=background_jobs)

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str):
        try:
            return jobs.get(job_id)
        except KeyError:
            raise HTTPException(404, "Job not found.")

    @app.post("/api/jobs/{job_id}/resume")
    def resume(job_id: str):
        try:
            return jobs.start(job_id, background=background_jobs)
        except KeyError:
            raise HTTPException(404, "Job not found.")

    @app.get("/api/jobs/{job_id}/result")
    def job_result(job_id: str):
        try:
            return jobs.result(job_id)
        except KeyError:
            raise HTTPException(404, "No result yet.")

    # ---- analyses (identify, peers, Agents 1-3) ----

    @app.get("/api/analyses")
    def list_analyses():
        """Finished analyses kept on the server, newest first."""
        return analyses.saved()

    @app.delete("/api/analyses/{job_id}")
    def delete_analysis(job_id: str):
        try:
            analyses.delete(job_id)
        except KeyError:
            raise HTTPException(404, "No such analysis.")
        return {"deleted": job_id}

    @app.post("/api/analyses")
    def start_analysis(req: AnalysisRequest):
        if req.indicators is not None:
            if not req.indicators:
                raise HTTPException(400, "Choose at least one indicator.")
            unknown = sorted(set(req.indicators) - set(indicators.SPECS_BY_ID))
            if unknown:
                raise HTTPException(400, f"Unknown indicators: {', '.join(unknown)}.")
        questions = [q.strip() for q in req.questions if q.strip()]
        if len(questions) > MAX_QUESTIONS or any(len(q) > MAX_QUESTION_LENGTH for q in questions):
            raise HTTPException(400, f"Ask at most {MAX_QUESTIONS} questions of up to {MAX_QUESTION_LENGTH} characters each.")
        if req.transcript_upload:
            try:
                upload = store.get(req.transcript_upload)
            except storage.NotFound:
                raise HTTPException(404, "The transcript upload was not found.")
            if upload["kind"] != "document":
                raise HTTPException(400, "The transcript must be a text, PDF, Word or HTML file; transcribe a recording first.")
        try:
            target = language.resolve_output_language(req.output_language, settings)
            state = analyses.create(req.company, target, req.peers, req.as_of or date.today(), req.indicators,
                                    req.transcript_upload, req.horizon_years, questions)
        except language.UnsupportedLanguage as exc:
            raise HTTPException(400, str(exc))
        except pipeline.CompanyNotFound as exc:
            raise HTTPException(404, str(exc))
        except pipeline.AmbiguousCompany as exc:
            return JSONResponse(status_code=409, content={"detail": str(exc), "candidates": exc.candidates})
        return analyses.start(state["id"], background=background_jobs)

    @app.get("/api/analyses/{job_id}")
    def analysis_status(job_id: str):
        try:
            return analyses.get(job_id)
        except KeyError:
            raise HTTPException(404, "Analysis not found.")

    @app.get("/api/analyses/{job_id}/report")
    def analysis_report(job_id: str):
        try:
            return analyses.result(job_id)
        except KeyError:
            raise HTTPException(404, "No report yet.")

    @app.get("/api/analyses/{job_id}/view")
    def analysis_view(job_id: str):
        """The report as display blocks, the same ones the PDF and Word files will use."""
        try:
            return report_blocks.build(analyses.result(job_id))
        except KeyError:
            raise HTTPException(404, "No report yet.")

    DOWNLOADS = {"pdf": ("application/pdf", report_export.to_pdf),
                 "docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", report_export.to_docx)}

    @app.get("/api/analyses/{job_id}/download/{kind}")
    def analysis_download(job_id: str, kind: str):
        """The report as a PDF (default) or an editable Word file, with the same content as the website."""
        if kind not in DOWNLOADS:
            raise HTTPException(404, "Downloads are available as pdf or docx.")
        try:
            report = analyses.result(job_id)
        except KeyError:
            raise HTTPException(404, "No report yet.")
        media_type, export = DOWNLOADS[kind]
        name = f"{report['company']['ticker']}_analysis_{report['analysis_date']}.{kind}"
        return Response(export(report_blocks.build(report)), media_type=media_type,
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @app.post("/api/maintenance/cleanup")
    def cleanup():
        return {"removed_temporary_folders": store.cleanup_temp(settings.temp_retention_days)}

    # ---- prices and peers ----

    @app.get("/api/prices/{ticker}")
    def price(ticker: str):
        """The last closing price: the latest completed trading session, never a price that is still moving."""
        client = PoliteClient(settings)
        try:
            return market_data.get_closing_price(ticker, settings, client).to_dict()
        except AccessDenied as exc:
            raise HTTPException(503, f"Price unavailable: {exc}. The provider does not permit automated access; "
                                     "a provider with an official API is needed.")
        except (FetchFailed, market_data.PriceUnavailable) as exc:
            raise HTTPException(502, f"Price unavailable: {exc}")
        finally:
            client.close()

    @app.post("/api/peers/select")
    def peers(req: PeerRequest):
        target = peer_selection.Profile(**req.target)
        candidates = [peer_selection.Candidate(peer_selection.Profile(**c["profile"]), c.get("sources", []))
                      for c in req.candidates]
        return peer_selection.select_peers(target, candidates, settings, req.index_filter, req.requested_total)

    # Registered last so API routes are never shadowed by static files.
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
    return app


app = create_app()

if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="127.0.0.1", port=int(os.getenv("PORT", "8000")))
