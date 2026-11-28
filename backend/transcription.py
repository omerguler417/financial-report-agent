# Transcribes earnings-call recordings in the original language, then translates: FFmpeg chunking with overlap, de-duplicated joins, timestamps on the original timeline, background jobs with progress and resume.
import json
import os
import re
import shutil
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend import language
from backend.config import Settings
from backend.storage import Store

UNCLEAR_LOGPROB = -1.0
UNCLEAR_NO_SPEECH = 0.6
UNCLEAR_COMPRESSION = 2.4
TRANSLATION_BATCH = 40


class RecordingLimitExceeded(Exception):
    pass


class FFmpegMissing(Exception):
    pass


# ---------- FFmpeg ----------

def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _require_ffmpeg(run=subprocess.run):
    """Only the real runner needs FFmpeg installed; a stand-in runner (tests) replaces it."""
    if run is subprocess.run and not ffmpeg_available():
        raise FFmpegMissing("FFmpeg is not installed, so recordings cannot be processed. On macOS run: brew install ffmpeg")


def probe_duration(path: Path, run=subprocess.run) -> float:
    _require_ffmpeg(run)
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
              capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def extract_audio(src: Path, dst: Path, run=subprocess.run) -> None:
    _require_ffmpeg(run)
    run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k", str(dst)],
        check=True, capture_output=True)


def cut_chunk(audio: Path, start: float, length: float, dst: Path, run=subprocess.run) -> None:
    _require_ffmpeg(run)
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{length:.3f}", "-i", str(audio),
         "-ac", "1", "-ar", "16000", "-b:a", "64k", str(dst)], check=True, capture_output=True)


def limit_advice(settings: Settings) -> str:
    hours = settings.max_recording_hours
    return (f"Split the recording into parts shorter than {hours:g} hours, for example "
            f"'ffmpeg -i input.mp4 -f segment -segment_time 3600 -c copy part%02d.mp4', "
            f"or keep only the audio to shrink it: 'ffmpeg -i input.mp4 -vn -ac 1 -b:a 64k audio.mp3'. "
            f"These are current operational limits ({settings.max_upload_mb} MB per file, {hours:g} hours per recording) "
            f"and can be raised in the settings.")


def check_recording_limits(size_bytes: int, duration_seconds: float | None, settings: Settings) -> None:
    if size_bytes > settings.max_upload_bytes:
        raise RecordingLimitExceeded(f"The file is larger than {settings.max_upload_mb} MB. " + limit_advice(settings))
    if duration_seconds is not None and duration_seconds > settings.max_recording_hours * 3600:
        raise RecordingLimitExceeded(f"The recording is longer than {settings.max_recording_hours:g} hours. " + limit_advice(settings))


# ---------- chunking and merging ----------

def plan_chunks(duration: float, chunk_seconds: float, overlap_seconds: float) -> list[tuple[float, float]]:
    """(start, length) pairs covering the recording; neighbours overlap by overlap_seconds."""
    if duration <= chunk_seconds:
        return [(0.0, duration)]
    step = chunk_seconds - overlap_seconds
    chunks, start = [], 0.0
    while start < duration:
        length = min(chunk_seconds, duration - start)
        chunks.append((start, length))
        if start + length >= duration:
            break
        start += step
    return chunks


def _norm(text: str) -> str:
    return re.sub(r"[^\w%.,-]+", " ", text.lower()).strip()


def _strip_repeated_prefix(previous: str, current: str, min_words: int = 3) -> str:
    """Remove words at the start of `current` that repeat the end of `previous` (text-only joins)."""
    prev_words, cur_words = previous.split(), current.split()
    for size in range(min(len(prev_words), len(cur_words)), min_words - 1, -1):
        if [_norm(w) for w in prev_words[-size:]] == [_norm(w) for w in cur_words[:size]]:
            return " ".join(cur_words[size:])
    return current


def merge_chunks(chunk_results: list[dict], overlap_seconds: float) -> list[dict]:
    """chunk_results: [{"start": chunk_start, "timestamps": bool, "segments": [...relative times...]}].
    Returns segments on the original recording's timeline with duplicates at joins removed."""
    merged: list[dict] = []
    for index, chunk in enumerate(chunk_results):
        offset = chunk["start"]
        prev_cut = chunk["start"] + overlap_seconds / 2 if index > 0 else float("-inf")
        nxt = chunk_results[index + 1] if index + 1 < len(chunk_results) else None
        next_cut = nxt["start"] + overlap_seconds / 2 if nxt else float("inf")
        for seg in chunk["segments"]:
            item = dict(seg)
            if chunk.get("timestamps", True):
                item["start"] = round(seg["start"] + offset, 3)
                item["end"] = round(seg["end"] + offset, 3)
                midpoint = (item["start"] + item["end"]) / 2
                if not (prev_cut <= midpoint < next_cut):
                    continue
            else:
                item["start"] = item["end"] = None
            if merged:
                if _norm(item["text"]) == _norm(merged[-1]["text"]):
                    continue
                item["text"] = _strip_repeated_prefix(merged[-1]["text"], item["text"])
                if not item["text"]:
                    continue
            merged.append(item)
    return merged


def is_unclear(seg: dict) -> bool:
    return ((seg.get("avg_logprob") is not None and seg["avg_logprob"] < UNCLEAR_LOGPROB)
            or (seg.get("no_speech_prob") is not None and seg["no_speech_prob"] > UNCLEAR_NO_SPEECH)
            or (seg.get("compression_ratio") is not None and seg["compression_ratio"] > UNCLEAR_COMPRESSION))


def timestamp(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    s = int(seconds)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


# ---------- checking figures against published documents ----------

FIGURE_PATTERN = re.compile(
    r"(?:[$€£¥]|USD|EUR|TRY|BRL)?\s?-?\d[\d,]*(?:\.\d+)?\s?(?:%|percent|billion|million|thousand|bn|mn|m\b)?",
    re.IGNORECASE)


def extract_figures(text: str) -> list[str]:
    figures = []
    for match in FIGURE_PATTERN.finditer(text):
        token = match.group(0).strip()
        digits = re.sub(r"[^\d.]", "", token)
        if len(digits.replace(".", "")) >= 2 or "%" in token or "percent" in token.lower():
            figures.append(token)
    return figures


def _number_core(figure: str) -> str:
    return re.sub(r"[^\d.]", "", figure).rstrip(".")


def check_figures(segments: list[dict], document_texts: dict[str, str]) -> list[dict]:
    """For each figure spoken in the recording, report whether the same number appears in the published documents.
    This is a consistency aid, not proof: a match means the number appears, not that the context agrees."""
    cores = {name: re.sub(r"(?<=\d),(?=\d)", "", text) for name, text in document_texts.items()}
    checks = []
    for seg in segments:
        for figure in extract_figures(seg.get("original") or seg.get("text", "")):
            core = _number_core(figure)
            if not core:
                continue
            found = [name for name, text in cores.items() if re.search(rf"(?<![\d.]){re.escape(core)}(?![\d])", text)]
            checks.append({"figure": figure, "timestamp": seg.get("timestamp"), "found_in": found,
                           "status": "appears in published documents" if found else "not found in published documents; check before relying on it"})
    return checks


# ---------- background jobs with progress and resume ----------

def _write_whole(path: Path, text: str) -> None:
    """Write to a temporary file, then swap it in, so the page never reads a half-written file."""
    temporary = path.with_name(path.name + f".{threading.get_ident()}.tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


class TranscriptionJobs:
    def __init__(self, store: Store, settings: Settings, provider_factory, run=subprocess.run, document_text=None):
        self.store = store
        self.settings = settings
        self.provider_factory = provider_factory
        self.run = run
        self.document_text = document_text or (lambda meta: None)
        self._threads: dict[str, threading.Thread] = {}

    def _state_path(self, job_id):
        if not re.fullmatch(r"[0-9a-f]{12}", job_id or ""):
            raise KeyError(job_id)
        return self.store.jobs_dir / f"{job_id}.json"

    def result_path(self, job_id):
        return self.store.jobs_dir / f"{job_id}.result.json"

    def get(self, job_id) -> dict:
        path = self._state_path(job_id)
        if not path.exists():
            raise KeyError(job_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def _save(self, state):
        state["updated_at"] = _now_iso()
        _write_whole(self._state_path(state["id"]), json.dumps(state, indent=2))

    def create(self, upload_id: str, output_language: str, check_against: list[str] | None = None) -> dict:
        meta = self.store.get(upload_id)
        if meta["kind"] != "recording":
            raise ValueError("Only recordings can be transcribed.")
        state = {
            "id": uuid.uuid4().hex[:12], "upload_id": upload_id, "filename": meta["filename"],
            "output_language": output_language, "check_against": check_against or [],
            "status": "queued", "error": None, "steps_done": [], "chunks_total": None, "chunks_done": 0,
            "progress_percent": 0, "current_step": "queued", "created_at": _now_iso(),
        }
        self._save(state)
        return state

    def start(self, job_id: str, background: bool = True) -> dict:
        state = self.get(job_id)
        if state["status"] == "running" and job_id in self._threads and self._threads[job_id].is_alive():
            return state
        state.update(status="running", error=None)
        self._save(state)
        if background:
            thread = threading.Thread(target=self._run, args=(job_id,), daemon=True)
            self._threads[job_id] = thread
            thread.start()
        else:
            self._run(job_id)
        return self.get(job_id)

    def _progress(self, state, step):
        state["current_step"] = step
        total = (state["chunks_total"] or 1) + 4
        done = len([s for s in state["steps_done"] if not s.startswith("chunk_")]) + state["chunks_done"]
        state["progress_percent"] = min(100, int(100 * done / total))
        self._save(state)

    def _run(self, job_id: str):
        state = self.get(job_id)
        work = self.store.tmp_dir(f"job_{job_id}")
        try:
            meta = self.store.get(state["upload_id"])
            source = self.store.current_path(meta)
            provider = self.provider_factory()

            if "probe" not in state["steps_done"]:
                self._progress(state, "checking recording length")
                state["duration_seconds"] = probe_duration(source, self.run)
                check_recording_limits(source.stat().st_size, state["duration_seconds"], self.settings)
                state["steps_done"].append("probe")
            audio = work / "audio.mp3"
            if "extract" not in state["steps_done"] or not audio.exists():
                self._progress(state, "extracting audio")
                extract_audio(source, audio, self.run)
                if "extract" not in state["steps_done"]:
                    state["steps_done"].append("extract")

            chunks = plan_chunks(state["duration_seconds"], self.settings.chunk_seconds, self.settings.chunk_overlap_seconds)
            state["chunks_total"] = len(chunks)
            results = []
            for i, (start, length) in enumerate(chunks):
                result_file = work / f"chunk_{i:03d}.json"
                if not result_file.exists():
                    self._progress(state, f"transcribing part {i + 1} of {len(chunks)}")
                    chunk_audio = work / f"chunk_{i:03d}.mp3"
                    if len(chunks) == 1:
                        chunk_audio = audio
                    else:
                        cut_chunk(audio, start, length, chunk_audio, self.run)
                    hint = language.normalize(state.get("source_language"))
                    out = provider.transcribe(chunk_audio, hint)
                    out["start"] = start
                    result_file.write_text(json.dumps(out), encoding="utf-8")
                    state.setdefault("source_language", out.get("language"))
                results.append(json.loads(result_file.read_text(encoding="utf-8")))
                state["chunks_done"] = i + 1
                self._progress(state, f"transcribed part {i + 1} of {len(chunks)}")

            self._progress(state, "joining parts")
            merged = merge_chunks(results, self.settings.chunk_overlap_seconds)
            source_lang = language.normalize(results[0].get("language")) or results[0].get("language")
            if "merge" not in state["steps_done"]:
                state["steps_done"].append("merge")

            target = state["output_language"]
            translated_file = work / "translated.json"
            translations = None
            if source_lang and language.normalize(source_lang) != target:
                if translated_file.exists():
                    translations = json.loads(translated_file.read_text(encoding="utf-8"))
                else:
                    self._progress(state, "translating")
                    translations = []
                    for b in range(0, len(merged), TRANSLATION_BATCH):
                        batch = [s["text"] for s in merged[b:b + TRANSLATION_BATCH]]
                        translations.extend(provider.translate(batch, source_lang, target))
                    translated_file.write_text(json.dumps(translations), encoding="utf-8")
            if "translate" not in state["steps_done"]:
                state["steps_done"].append("translate")

            segments = []
            for i, seg in enumerate(merged):
                translation = translations[i] if translations else None
                segments.append({
                    "start": seg["start"], "end": seg["end"], "timestamp": timestamp(seg["start"]),
                    "speaker": seg.get("speaker"), "original": seg["text"], "translation": translation,
                    "unclear": is_unclear(seg),
                    "translation_ambiguous": bool(translation and "[AMBIGUOUS:" in translation),
                })

            flags = language.source_language_flags(results[0].get("language"))
            timestamps_ok = all(r.get("timestamps", True) for r in results)
            if not timestamps_ok:
                flags.append(f"The transcription model '{results[0].get('model')}' did not return timestamps; claims cannot cite exact times.")
            if any(r.get("speakers") for r in results):
                flags.append("Speaker labels are machine-assigned and not verified; confirm identities before attributing statements.")
            else:
                flags.append("Speaker labels are not available from this transcription model; statements are not attributed to individuals.")
            if any(s["unclear"] for s in segments):
                flags.append("Some passages are marked unclear; check them against the recording.")
            if any(s["translation_ambiguous"] for s in segments):
                flags.append("Some translated passages are marked ambiguous; the original text is kept beside each translation.")

            document_texts, skipped = {}, []
            for doc_id in state["check_against"]:
                doc = self.store.get(doc_id)
                text = self.document_text(doc)
                if text is None:
                    skipped.append(doc["filename"])
                else:
                    document_texts[doc["filename"]] = text
            if skipped:
                flags.append("Figures were not checked against: " + ", ".join(skipped) + " (text extraction for this file type is not implemented yet).")

            result = {
                "job_id": job_id,
                "source": {"upload_id": meta["id"], "filename": meta["filename"], "origin": meta["origin"]},
                "transcript_type": "machine-generated transcript",
                "translation_type": "machine translation" if translations else None,
                "transcription_model": results[0].get("model"),
                "source_language": source_lang,
                "output_language": target,
                "duration_seconds": state["duration_seconds"],
                "flags": flags,
                "segments": segments,
                "figure_checks": check_figures(segments, document_texts) if document_texts else [],
            }
            _write_whole(self.result_path(job_id), json.dumps(result, indent=2, ensure_ascii=False))
            state["steps_done"].append("done")
            state.update(status="completed", current_step="completed", progress_percent=100)
            self._save(state)
        except Exception as exc:  # recorded so the user can fix the cause and resume
            state.update(status="failed", error=str(exc), current_step="failed")
            self._save(state)

    def result(self, job_id: str) -> dict:
        path = self.result_path(job_id)
        if not path.exists():
            raise KeyError(job_id)
        return json.loads(path.read_text(encoding="utf-8"))
