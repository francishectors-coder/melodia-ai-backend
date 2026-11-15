
"""MELODIA AI V2.8 web-job adapter.

Runs a V2.8 prompt-to-MP4 job using the existing JSON job format.
Does not change the legacy worker or its quota-recovery behavior.
"""
from __future__ import annotations

import json
import math
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from melodia_v28_mp4_integration import produce_v28_video

ROOT = Path(__file__).resolve().parent
JOBS = ROOT / "jobs"
OUTPUTS = ROOT / "outputs"
JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")
LANGUAGE_CODES = {
    "Tamil": "ta", "Hindi": "hi", "Malayalam": "ml", "Telugu": "te",
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _save_job(job_file: Path, job: dict) -> None:
    """Atomically save progress in the format used by the existing server."""
    job["updated_at"] = _now()
    job_file.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=job_file.stem + "_", suffix=".tmp", dir=job_file.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(job, stream, ensure_ascii=False, indent=2)
        os.replace(temporary, job_file)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _settings(job: dict) -> dict:
    settings = job.get("settings")
    if not isinstance(settings, dict):
        raise ValueError("Missing video settings")
    prompt = settings.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("Video prompt is required")
    if len(prompt) > 3000:
        raise ValueError("Video prompt exceeds 3000 characters")
    if settings.get("language", "English") != "English":
        raise ValueError("V2.8 requires English as the primary caption language")

    duration = settings.get("duration", 1)
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration):
        raise ValueError("Duration must be a finite number of minutes")
    if not 0 < duration <= 10:
        raise ValueError("Duration must be between 0 and 10 minutes")
    aspect = settings.get("aspect_ratio", "16:9")
    if aspect not in ("16:9", "9:16"):
        raise ValueError("Unsupported aspect ratio")

    caption_mode = settings.get("captions", "single")
    if caption_mode not in ("single", "bilingual", "none"):
        raise ValueError("Invalid caption mode")
    language = None
    translations = None
    if caption_mode == "bilingual":
        second = settings.get("second_language")
        language = LANGUAGE_CODES.get(second)
        if language is None:
            raise ValueError("Unsupported second language")
        # None requests automatic translation in the V2.8 MP4 integration.
        # A supplied mapping or JSON path remains supported for compatibility.
        translations = settings.get("bilingual_captions")
        if translations is not None and not isinstance(translations, (dict, str)):
            raise ValueError("Invalid bilingual caption source")

    music_mode = settings.get("music", "peaceful")
    if music_mode not in ("peaceful", "cinematic", "uplifting", "none"):
        raise ValueError("Invalid music mode")

    return {
        "prompt": prompt.strip(),
        "duration_seconds": float(duration) * 60.0,
        "aspect_ratio": aspect,
        "bilingual_language": language,
        "bilingual_captions": translations,
        "captions": caption_mode != "none",
        "auto_music": music_mode != "none",
    }


def process_v28_job(job_file, job):
    """Render one queued V2.8 job; persist completed/failed status.

    Call from the web server's existing background worker after routing a
    job to V2.8. The existing server's preview/download routes expect
    outputs/<job_id>.mp4 and a completed status.
    """
    job_file = Path(job_file)
    if not isinstance(job, dict):
        raise ValueError("Job must be a dictionary")
    job_id = job.get("job_id")
    if not isinstance(job_id, str) or not JOB_ID_RE.fullmatch(job_id):
        raise ValueError("Invalid job ID")
    expected = JOBS / f"{job_id}.json"
    if job_file.resolve() != expected.resolve():
        raise ValueError("Job file does not match job ID")
    if job.get("status") != "queued":
        raise ValueError("Only queued jobs can be processed")

    OUTPUTS.mkdir(parents=True, exist_ok=True)
    output = OUTPUTS / f"{job_id}.mp4"
    staging = OUTPUTS / f"{job_id}.rendering.mp4"
    try:
        options = _settings(job)
        job["status"] = "processing"
        job["progress"] = 10
        job["error"] = None
        _save_job(job_file, job)

        # The V2.8 renderer is synchronous; progress moves to completion
        # only after produce_v28_video returns successfully.
        result = produce_v28_video(output=str(staging), **options)
        if not staging.is_file() or staging.stat().st_size == 0:
            raise RuntimeError("V2.8 renderer did not produce an MP4")
        os.replace(staging, output)

        job["status"] = "completed"
        job["progress"] = 100
        job["output_file"] = str(output)
        job["video_path"] = str(output)
        job["engine"] = "v2.8"
        job["production_result"] = result
        job["error"] = None
        _save_job(job_file, job)
        return job
    except Exception as exc:
        job["status"] = "failed"
        job["error"] = f"{type(exc).__name__}: {exc}"
        job["progress"] = min(int(job.get("progress", 0)), 99)
        _save_job(job_file, job)
        raise
    finally:
        if staging.exists():
            staging.unlink()


if __name__ == "__main__":
    print("MELODIA AI V2.8 web-job adapter: ready for server integration")
