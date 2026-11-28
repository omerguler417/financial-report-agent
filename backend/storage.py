# Saved files on disk (no database): retrieved and uploaded documents with source details and versions, temporary processing files, and the analyses (jobs).
import hashlib
import json
import re
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ORIGIN_OFFICIAL = "retrieved_official_source"
ORIGIN_UPLOAD = "user_upload"

DOCUMENT_EXTENSIONS = {".pdf", ".htm", ".html", ".txt", ".docx", ".xlsx", ".csv", ".xml", ".json"}
RECORDING_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}

CHUNK_BYTES = 1024 * 1024


class UploadTooLarge(Exception):
    pass


class UnsupportedFileType(Exception):
    pass


class NotFound(Exception):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


def safe_filename(name: str) -> str:
    base = Path(name or "file").name
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
    return cleaned or "file"


def classify_file(filename: str, content_type: str = "") -> str:
    """Return "document" or "recording", or raise UnsupportedFileType."""
    ext = Path(filename or "").suffix.lower()
    if ext in RECORDING_EXTENSIONS or content_type.startswith(("audio/", "video/")):
        return "recording"
    if ext in DOCUMENT_EXTENSIONS or content_type in ("application/pdf", "text/html", "text/plain"):
        return "document"
    raise UnsupportedFileType(
        f"'{filename}' is not a supported type. Documents: {', '.join(sorted(DOCUMENT_EXTENSIONS))}. "
        f"Recordings: {', '.join(sorted(RECORDING_EXTENSIONS))}."
    )


class Store:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.documents_dir = self.root / "documents"
        self.tmp_root = self.root / "tmp"
        self.jobs_dir = self.root / "jobs"
        for d in (self.documents_dir, self.tmp_root, self.jobs_dir):
            d.mkdir(parents=True, exist_ok=True)

    # ---- documents and recordings ----

    def _doc_dir(self, doc_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{12}", doc_id or ""):
            raise NotFound(doc_id)
        return self.documents_dir / doc_id

    def _write_meta(self, meta: dict) -> None:
        path = self._doc_dir(meta["id"]) / "meta.json"
        path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    def get(self, doc_id: str) -> dict:
        path = self._doc_dir(doc_id) / "meta.json"
        if not path.exists():
            raise NotFound(doc_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def list_documents(self, origin: str | None = None) -> list[dict]:
        metas = []
        for meta_path in sorted(self.documents_dir.glob("*/meta.json")):
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if origin is None or meta["origin"] == origin:
                metas.append(meta)
        return sorted(metas, key=lambda m: m["created_at"], reverse=True)

    def current_path(self, meta: dict) -> Path:
        version = meta["versions"][-1]
        return self._doc_dir(meta["id"]) / version["file"]

    def version_path(self, meta: dict, version_number: int) -> Path:
        for version in meta["versions"]:
            if version["version"] == version_number:
                return self._doc_dir(meta["id"]) / version["file"]
        raise NotFound(f"{meta['id']} v{version_number}")

    def _new_doc(self, origin, kind, filename, content_type, now, **details) -> dict:
        doc_id = uuid.uuid4().hex[:12]
        self._doc_dir(doc_id).mkdir(parents=True)
        return {
            "id": doc_id,
            "origin": origin,
            "kind": kind,
            "filename": safe_filename(filename),
            "content_type": content_type or "",
            "source_url": details.get("source_url"),
            "reporting_period": details.get("reporting_period"),
            "publication_date": details.get("publication_date"),
            "notes": details.get("notes"),
            "created_at": _iso(now),
            "last_checked_at": _iso(now),
            "versions": [],
        }

    def _add_version(self, meta, write_file, now) -> dict:
        number = len(meta["versions"]) + 1
        file_name = f"v{number}_{meta['filename']}"
        path = self._doc_dir(meta["id"]) / file_name
        digest, size = write_file(path)
        meta["versions"].append({
            "version": number, "file": file_name, "sha256": digest, "size_bytes": size, "retrieved_at": _iso(now),
        })
        return meta

    def save_upload(self, stream, filename, content_type="", max_bytes=None, notes=None, reporting_period=None, now=None) -> dict:
        """Stream a user upload to disk, enforcing the size limit, and label it as user-supplied."""
        now = now or utcnow()
        kind = classify_file(filename, content_type or "")
        meta = self._new_doc(ORIGIN_UPLOAD, kind, filename, content_type, now, notes=notes, reporting_period=reporting_period)

        def write(path: Path):
            digest, size = hashlib.sha256(), 0
            with open(path, "wb") as out:
                while chunk := stream.read(CHUNK_BYTES):
                    size += len(chunk)
                    if max_bytes is not None and size > max_bytes:
                        raise UploadTooLarge(size)
                    digest.update(chunk)
                    out.write(chunk)
            return digest.hexdigest(), size

        try:
            self._add_version(meta, write, now)
        except Exception:
            shutil.rmtree(self._doc_dir(meta["id"]), ignore_errors=True)
            raise
        self._write_meta(meta)
        return meta

    def find_by_source_url(self, source_url: str) -> dict | None:
        for meta in self.list_documents(ORIGIN_OFFICIAL):
            if meta.get("source_url") == source_url:
                return meta
        return None

    def needs_refresh(self, meta: dict, refresh_hours: float, now=None) -> bool:
        now = now or utcnow()
        return now - _parse(meta["last_checked_at"]) >= timedelta(hours=refresh_hours)

    def save_retrieved(self, content: bytes, source_url, filename, content_type="", kind="document",
                       reporting_period=None, publication_date=None, now=None) -> dict:
        """Save an independently retrieved file. A changed source becomes a new version; old versions are kept."""
        now = now or utcnow()
        digest = hashlib.sha256(content).hexdigest()
        meta = self.find_by_source_url(source_url)
        if meta is None:
            meta = self._new_doc(ORIGIN_OFFICIAL, kind, filename, content_type, now, source_url=source_url,
                                 reporting_period=reporting_period, publication_date=publication_date)
        meta["last_checked_at"] = _iso(now)
        if reporting_period:
            meta["reporting_period"] = reporting_period
        if publication_date:
            meta["publication_date"] = publication_date
        if not meta["versions"] or meta["versions"][-1]["sha256"] != digest:
            def write(path: Path):
                path.write_bytes(content)
                return digest, len(content)
            self._add_version(meta, write, now)
        self._write_meta(meta)
        return meta

    def mark_checked(self, meta: dict, now=None) -> dict:
        meta["last_checked_at"] = _iso(now or utcnow())
        self._write_meta(meta)
        return meta

    def delete_document(self, doc_id: str) -> None:
        directory = self._doc_dir(doc_id)
        if not directory.exists():
            raise NotFound(doc_id)
        shutil.rmtree(directory)

    # ---- temporary processing files ----

    def tmp_dir(self, name: str) -> Path:
        path = self.tmp_root / safe_filename(name)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def cleanup_temp(self, retention_days: float, now=None) -> list[str]:
        """Delete temporary processing folders not modified within the retention period."""
        cutoff = (now or utcnow()).timestamp() - retention_days * 86400
        removed = []
        for path in self.tmp_root.iterdir():
            newest = max([p.stat().st_mtime for p in path.rglob("*")] + [path.stat().st_mtime])
            if newest < cutoff:
                shutil.rmtree(path, ignore_errors=True) if path.is_dir() else path.unlink(missing_ok=True)
                removed.append(path.name)
        return removed
