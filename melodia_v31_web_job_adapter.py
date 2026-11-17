"""MELODIA AI V3.1 — opt-in website job processor.

The existing V2.8/legacy routes are unchanged. This test route is English,
30 seconds, and silent until music and translation are separately verified.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

from melodia_v31_production_adapter import prepare_assets, verify_assets
from melodia_v31_full_production import produce_v31_video

ROOT = Path(__file__).resolve().parent
OUTPUTS = ROOT / "outputs"
ASSETS = ROOT / "v31_assets"

def _save(job_file, job):
    job["updated_at"] = datetime.now(timezone.utc).isoformat()
    temporary = Path(job_file).with_suffix(".tmp")
    temporary.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(job_file)

def process_v31_job(job_file, job):
    """Consume a queued opt-in job; fail closed rather than use legacy art."""
    job_id = job["job_id"]
    settings = job.get("settings") or {}
    output = OUTPUTS / f"{job_id}.mp4"
    try:
        if job.get("engine") != "v3.1":
            raise ValueError("Not a V3.1 job")
        prompt = str(settings.get("prompt") or job.get("prompt") or "")
        if "[V3.1 TEST]" not in prompt.upper():
            raise ValueError("Missing explicit V3.1 opt-in")
        if float(settings.get("duration", -1)) != 0.5:
            raise ValueError("V3.1 test duration must be 30 seconds")
        if settings.get("language") != "English" or settings.get("captions") != "single":
            raise ValueError("V3.1 test supports English single captions only")
        if settings.get("music") != "none":
            raise ValueError("V3.1 test music must be none")
        aspect = settings.get("aspect_ratio")
        if aspect not in ("16:9", "9:16"):
            raise ValueError("Invalid aspect ratio")
        OUTPUTS.mkdir(parents=True, exist_ok=True)
        if output.is_file() and output.stat().st_size > 0:
            job.update(status="completed", progress=100, video_path=str(output))
            job.pop("error", None)
            _save(job_file, job)
            return
        job.update(status="preparing", progress=5)
        _save(job_file, job)
        # Remove the control token; it must not become a visual caption.
        clean_prompt = prompt.replace("[V3.1 TEST]", "").replace("[v3.1 test]", "").strip()
        if not clean_prompt:
            raise ValueError("A scenery prompt is required")
        manifest = prepare_assets(clean_prompt, ASSETS / job_id,
                                  duration_seconds=30, aspect=aspect)
        verify_assets(manifest)
        job.update(status="rendering", progress=50)
        _save(job_file, job)
        result = produce_v31_video(manifest, output, fps=10,
                                   transition_seconds=0.5, captions=True,
                                   music=None, promo_seconds=0)
        if not output.is_file() or output.stat().st_size <= 0:
            raise RuntimeError("V3.1 MP4 missing or empty")
        job.update(status="completed", progress=100, video_path=str(output),
                   v31_scene_count=len(manifest["scenes"]),
                   v31_render_version=result.get("version"))
        job.pop("error", None)
        _save(job_file, job)
    except Exception as error:
        job.update(status="failed", error=f"{type(error).__name__}: {error}")
        _save(job_file, job)
        print("MELODIA V3.1 TEST ERROR:", job_id, str(error), flush=True)
