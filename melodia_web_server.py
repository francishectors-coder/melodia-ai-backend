
# MELODIA AI - WEB SERVER
# Step 1336.70 - Free test bypass for prompt analysis
# Default and Advanced Mode Support

import json
import math
import os
import re
import threading
from pathlib import Path
from datetime import datetime, timezone

from flask import (
    Flask,
    jsonify,
    request,
    send_file,
    send_from_directory
)

from melodia_prompt_analyzer import analyze_prompt
from melodia_job_manager import create_video_job
from melodia_video_worker import (
    find_pending_jobs,
    process_job
)

ROOT = Path(__file__).resolve().parent
JOBS = ROOT / "jobs"
PLANS = ROOT / "scene_plans"
OUTPUTS = ROOT / "outputs"

for folder in (JOBS, PLANS, OUTPUTS):
    folder.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024

LANGUAGES = {
    "English", "Tamil", "Hindi",
    "Malayalam", "Telugu"
}

CAPTION_MODES = {
    "single", "bilingual", "none"
}

MUSIC_MODES = {
    "peaceful", "cinematic", "uplifting", "none"
}

ASPECT_RATIOS = {"16:9", "9:16"}

JOB_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")
SUPPORTED_DURATIONS = {0.5, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10}

worker_thread = None
worker_lock = threading.Lock()
worker_stop = threading.Event()
job_lock = threading.RLock()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def valid_job_id(job_id):
    return (
        isinstance(job_id, str)
        and bool(JOB_ID_PATTERN.fullmatch(job_id))
    )


def load_job(job_id):
    if not valid_job_id(job_id):
        return None

    path = JOBS / f"{job_id}.json"

    if not path.is_file():
        return None

    try:
        with path.open(
            "r", encoding="utf-8"
        ) as file:
            job = json.load(file)

        if not isinstance(job, dict):
            return None

        if job.get("job_id") != job_id:
            return None

        return job

    except (OSError, ValueError, TypeError):
        return None


def save_job(job):
    job_id = job["job_id"]

    if not valid_job_id(job_id):
        raise ValueError("Invalid job ID")

    job["updated_at"] = utc_now()

    path = JOBS / f"{job_id}.json"
    temporary = JOBS / f"{job_id}.tmp"

    with temporary.open(
        "w", encoding="utf-8"
    ) as file:
        json.dump(
            job,
            file,
            ensure_ascii=False,
            indent=2
        )

    temporary.replace(path)


def public_job(job):
    safe = dict(job)
    safe.pop("video_path", None)

    job_id = safe["job_id"]

    if safe.get("status") in (
        "completed", "complete"
    ):
        safe["video_url"] = (
            f"/api/jobs/{job_id}/video"
        )
        safe["download_url"] = (
            f"/api/jobs/{job_id}/download"
        )

    return safe


def output_path(job_id):
    if not valid_job_id(job_id):
        return None

    return OUTPUTS / f"{job_id}.mp4"


def completed_video(job_id):
    job = load_job(job_id)

    if not job:
        return None

    if job.get("status") not in (
        "completed", "complete"
    ):
        return None

    path = output_path(job_id)

    if path is None or not path.is_file():
        return None

    if path.stat().st_size == 0:
        return None

    return path


def background_worker():
    print(
        "MELODIA AI - BACKGROUND WORKER STARTED"
    )

    while not worker_stop.is_set():
        try:
            pending = find_pending_jobs()

            if pending:
                job_file, job = pending[0]

                print(
                    "Processing video job:",
                    job.get("job_id")
                )

                process_job(job_file, job)

            else:
                worker_stop.wait(3)

        except Exception as error:
            print(
                "BACKGROUND WORKER ERROR:",
                type(error).__name__,
                str(error)
            )
            worker_stop.wait(5)

    print(
        "MELODIA AI - BACKGROUND WORKER STOPPED"
    )


def start_background_worker():
    global worker_thread

    with worker_lock:
        if (
            worker_thread is not None
            and worker_thread.is_alive()
        ):
            return

        worker_stop.clear()

        worker_thread = threading.Thread(
            target=background_worker,
            name="MELODIA-Video-Worker",
            daemon=True
        )

        worker_thread.start()


def validate_settings(settings):
    language = settings.get("language")
    captions = settings.get("captions")
    second = settings.get("second_language")
    music = settings.get("music")
    aspect = settings.get("aspect_ratio")
    minutes = settings.get("duration")

    if (
        language not in LANGUAGES
        or captions not in CAPTION_MODES
        or music not in MUSIC_MODES
        or aspect not in ASPECT_RATIOS
        or isinstance(minutes, bool)
        or not isinstance(minutes, (int, float))
        or not math.isfinite(minutes)
        or minutes not in SUPPORTED_DURATIONS
    ):
        return "Invalid video settings"

    if captions == "bilingual":
        if (
            second not in LANGUAGES
            or second == language
        ):
            return (
                "Select two different languages"
            )

    return None


def prepare_video_settings(data):
    prompt = data.get("prompt", "")

    if (
        not isinstance(prompt, str)
        or not prompt.strip()
    ):
        raise ValueError(
            "A video prompt is required"
        )

    prompt = prompt.strip()

    if len(prompt) > 3000:
        raise ValueError(
            "Prompt exceeds 3000 characters"
        )

    mode = data.get(
        "mode",
        data.get("generation_mode", "advanced")
    )

    if mode not in ("default", "advanced"):
        raise ValueError(
            "Invalid generation mode"
        )

    raw_duration = data.get("duration", 3)

    if isinstance(raw_duration, bool):
        raise ValueError("Invalid video duration")

    try:
        minutes = float(raw_duration)
    except (ValueError, TypeError, OverflowError):
        raise ValueError("Invalid video duration")

    if not math.isfinite(minutes) or minutes not in SUPPORTED_DURATIONS:
        raise ValueError(
            "Select 30 secs, 60 secs, or 2-10 mins"
        )

    # Keep existing whole-minute jobs in their original integer format.
    if minutes.is_integer():
        minutes = int(minutes)

    # Explicit no-Gemini test. This bypasses prompt analysis and forces
    # the exact settings expected by the isolated worker test path.
    # It is activated only when the prompt contains [FREE TEST].
    if "[FREE TEST]" in prompt.upper():
        settings = {
            "prompt": prompt,
            "language": "English",
            "captions": "single",
            "second_language": None,
            "music": "none",
            "duration": 0.5,
            "aspect_ratio": "16:9",
            "audio": "none"
        }
        error = validate_settings(settings)
        if error:
            raise ValueError(error)
        return settings, {
            "mode": mode,
            "recommendation_source": "free_test",
            "subject": "free_test",
            "recommended_style": "test",
            "background": "local_test_images",
            "audio": "none"
        }

    if mode == "default":
        analysis = analyze_prompt(prompt)

        language = analysis["language"]
        captions = analysis["captions"]
        second = analysis["second_language"]
        music = analysis["music"]
        aspect = analysis["aspect_ratio"]

        # Only the settings supported by the
        # existing video pipeline are passed.
        settings = {
            "prompt": prompt,
            "language": language,
            "captions": captions,
            "second_language": (
                second
                if captions == "bilingual"
                else None
            ),
            "music": music,
            "duration": minutes,
            "aspect_ratio": aspect
        }

        error = validate_settings(settings)

        if error:
            raise ValueError(error)

        return settings, {
            "mode": "default",
            "subject": analysis["subject"],
            "recommended_style": (
                analysis["recommended_style"]
            ),
            "background": analysis["background"],
            "audio": analysis["audio"],
            "recommendation_source": (
                analysis["recommendation_source"]
            )
        }

    # Advanced mode keeps the established
    # manually selected settings.

    settings = {
        "prompt": prompt,
        "language": data.get(
            "language", "English"
        ),
        "captions": data.get(
            "captions", "single"
        ),
        "second_language": data.get(
            "second_language", "Tamil"
        ),
        "music": data.get(
            "music", "peaceful"
        ),
        "duration": minutes,
        "aspect_ratio": data.get(
            "aspect_ratio", "16:9"
        )
    }

    if settings["captions"] != "bilingual":
        settings["second_language"] = None

    error = validate_settings(settings)

    if error:
        raise ValueError(error)

    return settings, {
        "mode": "advanced",
        "recommendation_source": "user_settings"
    }


@app.route("/")
def home():
    return send_from_directory(
        ROOT, "index.html"
    )


@app.route("/api/status")
def status():
    return jsonify({
        "application": "MELODIA AI",
        "status": "online",
        "version": "0.7",
        "video_generation": "automatic_local",
        "worker_running": (
            worker_thread is not None
            and worker_thread.is_alive()
        ),
        "controlled_resume": True,
        "video_preview": True,
        "mp4_download": True,
        "prompt_interpretation": True,
        "generation_modes": [
            "default", "advanced"
        ]
    })


@app.route(
    "/api/generate",
    methods=["POST"]
)
def generate():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({
            "success": False,
            "error": "Invalid JSON request"
        }), 400

    try:
        settings, recommendation = (
            prepare_video_settings(data)
        )

    except (ValueError, TypeError) as error:
        return jsonify({
            "success": False,
            "error": str(error)
        }), 400

    # Create a job using the existing
    # working job manager.
    job = create_video_job(settings)

    start_background_worker()

    return jsonify({
        "success": True,
        "job_id": job["job_id"],
        "status": job["status"],
        "generation_started": True,
        "mode": recommendation["mode"],
        "recommendation": recommendation,
        "settings": settings,
        "message": (
            "Video queued for processing"
        )
    }), 202


@app.route("/api/jobs/<job_id>")
def job_status(job_id):
    job = load_job(job_id)

    if job is None:
        return jsonify({
            "success": False,
            "error": "Video job not found"
        }), 404

    return jsonify({
        "success": True,
        "job": public_job(job)
    })


@app.route(
    "/api/jobs/<job_id>/resume",
    methods=["POST"]
)
def resume_video(job_id):
    if not valid_job_id(job_id):
        return jsonify({
            "success": False,
            "error": "Invalid job ID"
        }), 400

    with job_lock:
        job = load_job(job_id)

        if job is None:
            return jsonify({
                "success": False,
                "error": "Video job not found"
            }), 404

        if job.get("status") != "paused_quota":
            return jsonify({
                "success": False,
                "error": (
                    "Only quota-paused jobs "
                    "can be resumed"
                ),
                "status": job.get("status")
            }), 409

        plan_path = (
            PLANS / f"{job_id}_scenes.json"
        )

        if not plan_path.is_file():
            return jsonify({
                "success": False,
                "error": (
                    "Recovery scene plan is missing"
                )
            }), 409

        try:
            with plan_path.open(
                "r", encoding="utf-8"
            ) as file:
                plan = json.load(file)

            if (
                plan.get("job_id") != job_id
                or not isinstance(
                    plan.get("scenes"), list
                )
                or not plan["scenes"]
            ):
                raise ValueError(
                    "Invalid recovery scene plan"
                )

        except (
            OSError, ValueError, TypeError
        ):
            return jsonify({
                "success": False,
                "error": (
                    "Recovery scene plan is invalid"
                )
            }), 409

        completed = 0

        for scene in plan["scenes"]:
            image_path = Path(
                scene["image_path"]
            )

            if (
                image_path.is_file()
                and image_path.stat().st_size > 0
            ):
                completed += 1

        job["status"] = "queued"
        job["progress"] = min(
            39,
            int(
                40 * completed
                / len(plan["scenes"])
            )
        )
        job["completed_images"] = completed
        job["total_images"] = len(
            plan["scenes"]
        )
        job.pop("error", None)

        save_job(job)

    start_background_worker()

    return jsonify({
        "success": True,
        "job_id": job_id,
        "status": "queued",
        "completed_images": completed,
        "total_images": len(
            plan["scenes"]
        ),
        "message": (
            "Resume accepted. "
            "Existing images will be reused."
        )
    }), 202


@app.route(
    "/api/jobs/<job_id>/video"
)
def preview_video(job_id):
    path = completed_video(job_id)

    if path is None:
        return jsonify({
            "success": False,
            "error": (
                "Completed video is not available"
            )
        }), 404

    return send_file(
        path,
        mimetype="video/mp4",
        conditional=True
    )


@app.route(
    "/api/jobs/<job_id>/download"
)
def download_video(job_id):
    path = completed_video(job_id)

    if path is None:
        return jsonify({
            "success": False,
            "error": (
                "Completed video is not available"
            )
        }), 404

    return send_file(
        path,
        mimetype="video/mp4",
        as_attachment=True,
        download_name=(
            f"MELODIA_AI_{job_id}.mp4"
        ),
        conditional=True
    )


if __name__ == "__main__":
    print()
    print("MELODIA AI - WEB SERVER")
    print("Automatic Prompt Interpretation: READY")
    print("Default Mode API: READY")
    print("Advanced Mode API: READY")
    print("Video Request API: READY")
    print("Job Status API: READY")
    print("MP4 Preview: READY")
    print("MP4 Download: READY")
    print("Background Worker: AUTOMATIC")
    print("Controlled Resume API: READY")
    print()
    print(
        "Open: http://127.0.0.1:10000"
    )
    print()

    start_background_worker()

    try:
        app.run(
            host="127.0.0.1",
            port=int(
                os.environ.get(
                    "PORT", 10000
                )
            ),
            debug=False
        )

    finally:
        worker_stop.set()
