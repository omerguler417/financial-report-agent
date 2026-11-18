# Saved files: uploads labelled separately, size limits, temporary-file cleanup after 7 days, reports kept with their source copies.
import io
import os
import time

import pytest

from backend.storage import ORIGIN_UPLOAD, Store, UnsupportedFileType, UploadTooLarge
from tests.helpers import make_settings


def test_uploads_are_labelled_and_classified(tmp_path):
    store = Store(make_settings(tmp_path).storage_dir)
    doc = store.save_upload(io.BytesIO(b"text"), "Q3 report.txt", "text/plain", notes="from IR email")
    rec = store.save_upload(io.BytesIO(b"\x00" * 10), "call.m4a", "audio/mp4")
    assert doc["origin"] == ORIGIN_UPLOAD and doc["kind"] == "document" and doc["filename"] == "Q3_report.txt"
    assert rec["kind"] == "recording"
    assert {m["id"] for m in store.list_documents(ORIGIN_UPLOAD)} == {doc["id"], rec["id"]}


def test_oversized_and_unsupported_uploads_leave_nothing_behind(tmp_path):
    store = Store(make_settings(tmp_path).storage_dir)
    with pytest.raises(UploadTooLarge):
        store.save_upload(io.BytesIO(b"x" * 3_000_000), "big.pdf", "application/pdf", max_bytes=1_000_000)
    with pytest.raises(UnsupportedFileType):
        store.save_upload(io.BytesIO(b"x"), "tool.exe", "application/octet-stream")
    assert store.list_documents() == []


def test_temporary_files_are_deleted_after_retention(tmp_path):
    store = Store(make_settings(tmp_path).storage_dir)
    old, recent = store.tmp_dir("job_old"), store.tmp_dir("job_recent")
    (old / "chunk.mp3").write_bytes(b"x")
    (recent / "chunk.mp3").write_bytes(b"x")
    eight_days_ago = time.time() - 8 * 86400
    for p in (old, old / "chunk.mp3"):
        os.utime(p, (eight_days_ago, eight_days_ago))
    assert store.cleanup_temp(7) == ["job_old"]
    assert not old.exists() and recent.exists()


def test_saved_report_keeps_its_source_versions_until_deleted(tmp_path):
    store = Store(make_settings(tmp_path).storage_dir)
    meta = store.save_retrieved(b"v1 text", "https://ir.example.com/a.txt", "a.txt", "text/plain")
    store.save_retrieved(b"v2 text", "https://ir.example.com/a.txt", "a.txt", "text/plain")
    report = store.save_report("Test report", {"summary": "x"}, [{"doc_id": meta["id"], "version": 1, "location": "p. 3"}])
    assert report["citations"][0]["version"] == 1 and report["citations"][0]["location"] == "p. 3"

    store.delete_document(meta["id"])  # the report still has its own copy of the cited version
    copy = store.reports_dir / report["id"] / report["citations"][0]["copy"]
    assert copy.read_bytes() == b"v1 text"

    assert store.list_reports()[0]["id"] == report["id"]
    store.delete_report(report["id"])
    assert store.list_reports() == []
