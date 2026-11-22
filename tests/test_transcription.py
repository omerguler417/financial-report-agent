# Recording processing: limits, chunk plan with overlap, de-duplicated joins on the original timeline, flags, figure checks, and resume.
import io

import pytest

from backend import transcription
from backend.storage import Store
from backend.transcription import (RecordingLimitExceeded, TranscriptionJobs, check_figures, check_recording_limits,
                                   merge_chunks, plan_chunks)
from tests.helpers import FakeProvider, fake_ffmpeg, make_settings


def test_limits_explain_how_to_split_or_compress(tmp_path):
    settings = make_settings(tmp_path)
    with pytest.raises(RecordingLimitExceeded, match="Split the recording"):
        check_recording_limits(10, 4 * 3600 + 1, settings)
    with pytest.raises(RecordingLimitExceeded, match="500 MB"):
        check_recording_limits(settings.max_upload_bytes + 1, 60, settings)


def test_chunk_plan_overlaps_and_covers_the_recording():
    assert plan_chunks(300, 600, 5) == [(0.0, 300)]
    chunks = plan_chunks(1500, 600, 5)
    assert [c[0] for c in chunks] == [0.0, 595.0, 1190.0]
    assert chunks[-1][0] + chunks[-1][1] == 1500


def test_merge_uses_original_timeline_and_drops_duplicates_at_joins():
    chunks = [
        {"start": 0.0, "timestamps": True, "segments": [
            {"start": 0, "end": 5, "text": "Welcome"}, {"start": 594, "end": 599, "text": "Revenue grew 12%"}]},
        {"start": 595.0, "timestamps": True, "segments": [
            {"start": 0, "end": 4, "text": "Revenue grew 12%"}, {"start": 10, "end": 14, "text": "Margins improved"}]},
    ]
    merged = merge_chunks(chunks, 5)
    assert [s["text"] for s in merged] == ["Welcome", "Revenue grew 12%", "Margins improved"]
    assert merged[-1]["start"] == 605.0


def test_merge_without_timestamps_removes_repeated_words():
    chunks = [{"start": 0, "timestamps": False, "segments": [{"start": 0, "end": 0, "text": "we expect revenue growth of five percent"}]},
              {"start": 595, "timestamps": False, "segments": [{"start": 0, "end": 0, "text": "growth of five percent next year"}]}]
    assert [s["text"] for s in merge_chunks(chunks, 5)] == ["we expect revenue growth of five percent", "next year"]


def test_figure_check_reports_matches_and_misses():
    segments = [{"original": "Revenue was $1,234.5 million, up 12%, margin 99%", "timestamp": "00:01:00"}]
    checks = check_figures(segments, {"q3.txt": "Revenue of 1,234.5 million rose 12% year on year."})
    status = {c["figure"]: c["found_in"] for c in checks}
    assert status["$1,234.5 million"] == ["q3.txt"] and status["12%"] == ["q3.txt"] and status["99%"] == []


def make_jobs(tmp_path, provider, monkeypatch, duration=1300):
    monkeypatch.setattr(transcription, "ffmpeg_available", lambda: True)
    settings = make_settings(tmp_path)
    store = Store(settings.storage_dir)
    run = fake_ffmpeg(duration)
    jobs = TranscriptionJobs(store, settings, provider_factory=lambda: provider, run=run,
                             document_text=lambda meta: store.current_path(meta).read_text())
    return store, jobs, run


def test_failed_job_resumes_without_repeating_completed_parts(tmp_path, monkeypatch):
    provider = FakeProvider(fail_on_call=2)
    store, jobs, _ = make_jobs(tmp_path, provider, monkeypatch)
    rec = store.save_upload(io.BytesIO(b"audio"), "call.mp4", "video/mp4")
    doc = store.save_upload(io.BytesIO(b"Revenue rose 12% in the quarter."), "q3.txt", "text/plain")
    job = jobs.create(rec["id"], "en", check_against=[doc["id"]])

    state = jobs.start(job["id"], background=False)
    assert state["status"] == "failed" and "temporary transcription failure" in state["error"]
    assert state["chunks_done"] == 1 and state["chunks_total"] == 3

    provider.fail_on_call = None
    state = jobs.start(job["id"], background=False)
    assert state["status"] == "completed" and state["progress_percent"] == 100
    assert provider.transcribe_calls == 4  # 1 ok + 1 failed + 2 remaining; part 1 was not redone

    result = jobs.result(job["id"])
    assert result["transcript_type"] == "machine-generated transcript"
    assert result["source"]["origin"] == "user_upload" and result["source_language"] == "tr"
    first = result["segments"][0]
    assert first["original"].startswith("Gelir") and first["translation"].startswith("EN: Gelir")
    assert first["timestamp"] == "00:00:01"
    assert any(s["start"] > 1190 for s in result["segments"])  # third part placed on the original timeline
    assert any(s["unclear"] for s in result["segments"])
    assert any("not available" in f for f in result["flags"])  # no speaker labels from this model
    # "yüzde 12" (Turkish for "12 percent") is checked against the English report's "12%"
    assert any(c["figure"] == "12" and c["found_in"] == ["q3.txt"] for c in result["figure_checks"])


def test_missing_ffmpeg_fails_with_install_instructions(tmp_path, monkeypatch):
    store, jobs, _ = make_jobs(tmp_path, FakeProvider(), monkeypatch)
    jobs.run = transcription.subprocess.run   # the real runner is the one that needs FFmpeg installed
    monkeypatch.setattr(transcription, "ffmpeg_available", lambda: False)
    rec = store.save_upload(io.BytesIO(b"audio"), "call.mp3", "audio/mpeg")
    state = jobs.start(jobs.create(rec["id"], "en")["id"], background=False)
    assert state["status"] == "failed" and "brew install ffmpeg" in state["error"]
