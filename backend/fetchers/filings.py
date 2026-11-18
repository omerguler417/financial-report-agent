# Retrieves report documents into the cache with source details. Source order: investor relations site, then regulator or exchange (such as SEC EDGAR), then user upload.
# Working: download-and-cache of a known document URL, 24-hour re-check, versioning.
# Awaiting implementation: discovering report URLs on investor relations sites and regulator fallbacks.
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from backend.config import Settings
from backend.fetchers.http_client import PoliteClient
from backend.storage import Store

SOURCE_ORDER = ("investor_relations_site", "regulator_or_exchange", "user_upload")


def _filename_for(url: str, content_type: str) -> str:
    name = PurePosixPath(urlsplit(url).path).name
    if name:
        return name
    return "document.pdf" if "pdf" in content_type else "document.html"


def retrieve_document(url: str, store: Store, client: PoliteClient, settings: Settings,
                      reporting_period: str | None = None, publication_date: str | None = None, now=None):
    """Return (meta, status). status is "cached", "unchanged", "updated" or "new"."""
    existing = store.find_by_source_url(url)
    if existing and not store.needs_refresh(existing, settings.source_refresh_hours, now):
        return existing, "cached"
    response = client.get(url)
    content_type = response.headers.get("content-type", "").split(";")[0].strip()
    versions_before = len(existing["versions"]) if existing else 0
    meta = store.save_retrieved(
        response.content, source_url=url, filename=_filename_for(url, content_type), content_type=content_type,
        reporting_period=reporting_period, publication_date=publication_date, now=now,
    )
    if existing is None:
        return meta, "new"
    return meta, "updated" if len(meta["versions"]) > versions_before else "unchanged"


def missing_document_notice(description: str, tried: list[str]) -> dict:
    """What to tell the user when a document cannot be found anywhere: name it and offer an upload."""
    return {
        "missing": description,
        "sources_tried": tried,
        "next_step": "Upload the document if you have it. Another reporting period will not be substituted.",
    }
