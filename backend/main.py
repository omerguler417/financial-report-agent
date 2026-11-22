# FastAPI application: serves the frontend and the API from one process (port 8000 by default).
import os
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Loads variables from a local .env if one exists; the app also starts without one.
# Values are never printed or logged.
load_dotenv()

from backend import language, llm, peer_selection, report_reader, services, storage, transcription  # noqa: E402
from backend.config import Settings, get_settings  # noqa: E402
from backend.errors import ProviderNotConfigured  # noqa: E402
from backend.fetchers import market_data  # noqa: E402
from backend.fetchers.http_client import AccessDenied, FetchFailed, PoliteClient  # noqa: E402

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

FEATURES = {
    "working": [
        "Output language selection (English by default)",
        "Document and audio/video uploads, labelled separately from retrieved sources",
        "Recording transcription and translation (needs a configured speech-to-text provider, a text model for translation, and FFmpeg)",
        "Background processing with progress and resume",
        "Polite fetching: per-host rate and concurrency limits, robots.txt, retries",
        "Document cache with 24-hour re-check and kept versions",
        "Temporary-file cleanup after 7 days; saved reports kept until deleted",
        "Price freshness rules for US exchanges",
        "Peer selection from supplied candidate data",
        "Demo data and demo stand-ins for each service (step 1; not yet selectable on the website)",
    ],
    "awaiting_implementation": [
        "Provider adapters for the services you choose later (text model, speech-to-text, market data, news)",
        "Finding reports on investor relations sites and regulator fallbacks",
        "Gathering peer candidates automatically",
        "PDF, Word and Excel text extraction",
        "Agents 1, 2 and 3, indicator calculations and the final PDF/Word report",
    ],
}


class TranscriptionRequest(BaseModel):
    upload_id: str
    output_language: str | None = None
    check_against: list[str] = []


class PeerRequest(BaseModel):
    target: dict
    candidates: list[dict]
    index_filter: str | None = None
    requested_total: int | None = None


def create_app(settings: Settings | None = None, provider_factory=None, run=None, background_jobs: bool = True) -> FastAPI:
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
    app.state.settings, app.state.store, app.state.jobs = settings, store, jobs

    @app.exception_handler(ProviderNotConfigured)
    async def not_configured(_request, exc: ProviderNotConfigured):
        return JSONResponse(status_code=424, content={"detail": str(exc), "needs_configuration": exc.to_dict()})

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/")
    def index():
        return FileResponse(FRONTEND_DIR / "index.html")

    @app.get("/api/config")
    def config():
        return {**settings.public_view(), "ffmpeg_available": transcription.ffmpeg_available(), "features": FEATURES,
                "services": services.service_status(settings)}

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

    # ---- saved reports and maintenance ----

    @app.get("/api/reports")
    def reports():
        return store.list_reports()

    @app.delete("/api/reports/{report_id}")
    def delete_report(report_id: str):
        try:
            store.delete_report(report_id)
        except storage.NotFound:
            raise HTTPException(404, "Report not found.")
        return {"deleted": report_id}

    @app.post("/api/maintenance/cleanup")
    def cleanup():
        return {"removed_temporary_folders": store.cleanup_temp(settings.temp_retention_days)}

    # ---- prices and peers ----

    @app.get("/api/prices/{ticker}")
    def price(ticker: str, on: date | None = None):
        client = PoliteClient(settings)
        try:
            return market_data.get_closing_price(ticker, settings, client, on_date=on).to_dict()
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
