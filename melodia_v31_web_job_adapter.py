"""MELODIA AI V3.1 — opt-in website job processor.

Only explicit [V3.1 TEST] jobs are handled here. Existing V2.8/legacy
routing remains the responsibility of melodia_web_server.py.

V3.1 test scope: 30 seconds, English single captions, optional procedural
instrumental music, and a five-second promotional ending.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from melodia_instrumental_music_engine import generate_instrumental
from melodia_v31_production_adapter import prepare_assets, verify_assets
from melodia_v31_full_production import produce_v31_video

ROOT = Path(__file__).resolve().parent
OUTPUTS = ROOT / "outputs"
ASSETS = ROOT / "v31_assets"
TEST_MARKER = re.compile(r"\[V3\.1\s+TEST\]", flags=re.IGNORECASE)
MUSIC_MOODS = {
    "peaceful": "peaceful",
    "uplifting": "uplifting",
    "cinematic": "reflective",
}


def _save(job_file, job):
    job["updated_at"] = datetime.now(timezone.utc).isoformat()
    temporary = Path(job_file).with_suffix(".tmp")
    temporary.write_text(
        json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(job_file)


def process_v31_job(job_file, job):
    """Process a queued opt-in job; never fall back to legacy artwork."""
    job_id = job["job_id"]
    settings = job.get("settings") or {}
    output = OUTPUTS / f"{job_id}.mp4"
    try:
        if job.get("engine") != "v3.1":
            raise ValueError("Not a V3.1 job")
        prompt = str(settings.get("prompt") or job.get("prompt") or "")
        if not TEST_MARKER.search(prompt):
            raise ValueError("Missing explicit V3.1 opt-in")
        if float(settings.get("duration", -1)) != 0.5:
            raise ValueError("V3.1 test duration must be 30 seconds")
        if settings.get("language") != "English" or settings.get("captions") != "single":
            raise ValueError("V3.1 test supports English single captions only")

        selected_music = settings.get("music", "none")
        if selected_music not in (*MUSIC_MOODS, "none"):
            raise ValueError("Unsupported V3.1 test music selection")
        aspect = settings.get("aspect_ratio")
        if aspect not in ("16:9", "9:16"):
            raise ValueError("Invalid aspect ratio")

        clean_prompt = TEST_MARKER.sub("", prompt).strip()
        if not clean_prompt:
            raise ValueError("A scenery prompt is required")

        OUTPUTS.mkdir(parents=True, exist_ok=True)
        if output.is_file() and output.stat().st_size > 0:
            job.update(status="completed", progress=100, video_path=str(output))
            job.pop("error", None)
            _save(job_file, job)
            return

        job.update(status="preparing", progress=5)
        _save(job_file, job)
        manifest = prepare_assets(
            clean_prompt, ASSETS / job_id, duration_seconds=30, aspect=aspect
        )
        if not verify_assets(manifest):
            raise RuntimeError("V3.1 scene asset verification failed")

        music_file = None
        if selected_music != "none":
            music_file = ASSETS / job_id / "melodia_instrumental.wav"
            generate_instrumental(
                prompt=clean_prompt,
                output=music_file,
                duration_seconds=30,
                mood=MUSIC_MOODS[selected_music],
                volume=0.42,
            )
            if not music_file.is_file() or music_file.stat().st_size == 0:
                raise RuntimeError("V3.1 instrumental soundtrack missing")

        job.update(status="rendering", progress=50)
        _save(job_file, job)
        result = produce_v31_video(
            manifest,
            output,
            fps=10,
            transition_seconds=0.5,
            captions=True,
            music=music_file,
            promo_seconds=5,
        )
        if not output.is_file() or output.stat().st_size <= 0:
            raise RuntimeError("V3.1 MP4 missing or empty")

        job.update(
            status="completed",
            progress=100,
            video_path=str(output),
            v31_scene_count=len(manifest["scenes"]),
            v31_render_version=result.get("version") if isinstance(result, dict) else None,
        )
        job.pop("error", None)
        _save(job_file, job)
    except Exception as error:
        job.update(status="failed", error=f"{type(error).__name__}: {error}")
        _save(job_file, job)
        print("MELODIA V3.1 TEST ERROR:", job_id, str(error), flush=True)
