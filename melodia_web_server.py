
from flask import (
    Flask, send_from_directory, send_file,
    jsonify, request
)
from pathlib import Path
import json
import re
import shutil

from melodia_job_manager import create_video_job

# MELODIA AI - WEB SERVER
# Step 801 - MP4 Preview and Download

ROOT = Path(__file__).resolve().parent
JOBS = ROOT / "jobs"
OUTPUTS = ROOT / "outputs"

# Cloud deployment: no access to local Windows videos
EXISTING_VIDEOS = ROOT / "existing_videos"

ROOT.mkdir(parents=True, exist_ok=True)
JOBS.mkdir(parents=True, exist_ok=True)
OUTPUTS.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024

LANGUAGES = {
    "English", "Tamil", "Hindi",
    "Malayalam", "Telugu"
}

CAPTION_MODES = {"single", "bilingual", "none"}

MUSIC_MODES = {
    "peaceful", "cinematic", "uplifting", "none"
}

ASPECT_RATIOS = {"16:9", "9:16"}

JOB_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")


def load_job(job_id):
    if not JOB_ID_PATTERN.fullmatch(job_id):
        return None

    path = JOBS / (job_id + ".json")

    if not path.is_file():
        return None

    try:
        with path.open("r", encoding="utf-8") as file:
            job = json.load(file)

        if not isinstance(job, dict):
            return None

        if job.get("job_id") != job_id:
            return None

        return job

    except (OSError, ValueError):
        return None


def save_job(job):
    job_id = job["job_id"]

    if not JOB_ID_PATTERN.fullmatch(job_id):
        raise ValueError("Invalid job ID")

    path = JOBS / (job_id + ".json")
    temporary = JOBS / (job_id + ".tmp")

    with temporary.open("w", encoding="utf-8") as file:
        json.dump(job, file, indent=2, ensure_ascii=False)

    temporary.replace(path)


def output_path(job_id):
    return OUTPUTS / ("MELODIA_AI_" + job_id + ".mp4")


def completed_video(job_id):
    job = load_job(job_id)

    if not job:
        return None

    if job.get("status") not in ("completed", "complete"):
        return None

    path = output_path(job_id)

    if not path.is_file() or path.stat().st_size == 0:
        return None

    return path


@app.route("/")
def home():
    return send_from_directory(ROOT, "index.html")


@app.route("/api/status")
def status():
    return jsonify({
        "application": "MELODIA AI",
        "status": "online",
        "version": "0.3",
        "video_generation": "controlled_test",
        "video_preview": True,
        "mp4_download": True
    })


@app.route("/api/generate", methods=["POST"])
def generate():

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({
            "success": False,
            "error": "Invalid JSON request"
        }), 400

    prompt = data.get("prompt", "")
    language = data.get("language", "English")
    captions = data.get("captions", "single")
    second = data.get("second_language", "Tamil")
    music = data.get("music", "peaceful")
    aspect = data.get("aspect_ratio", "16:9")

    try:
        minutes = int(data.get("duration", 3))
    except (ValueError, TypeError):
        minutes = 0

    if not isinstance(prompt, str) or not prompt.strip():
        return jsonify({
            "success": False,
            "error": "A video prompt is required"
        }), 400

    if len(prompt) > 3000:
        return jsonify({
            "success": False,
            "error": "Prompt exceeds 3000 characters"
        }), 400

    if (
        language not in LANGUAGES
        or captions not in CAPTION_MODES
        or music not in MUSIC_MODES
        or aspect not in ASPECT_RATIOS
        or not 1 <= minutes <= 10
    ):
        return jsonify({
            "success": False,
            "error": "Invalid video settings"
        }), 400

    if captions == "bilingual" and (
        second not in LANGUAGES or second == language
    ):
        return jsonify({
            "success": False,
            "error": "Select two different languages"
        }), 400

    settings = {
        "prompt": prompt.strip(),
        "language": language,
        "captions": captions,
        "second_language": (
            second if captions == "bilingual" else None
        ),
        "music": music,
        "duration": minutes,
        "aspect_ratio": aspect
    }

    job = create_video_job(settings)

    print("MELODIA AI - JOB CREATED:", job["job_id"])

    return jsonify({
        "success": True,
        "status": job["status"],
        "job_id": job["job_id"],
        "generation_started": False,
        "message": "Video request queued"
    })


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
        "job": job
    })


@app.route("/api/jobs/<job_id>/video")
def preview_video(job_id):

    path = completed_video(job_id)

    if path is None:
        return jsonify({
            "success": False,
            "error": "Completed video is not available"
        }), 404

    return send_file(
        path,
        mimetype="video/mp4",
        conditional=True
    )


@app.route("/api/jobs/<job_id>/download")
def download_video(job_id):

    path = completed_video(job_id)

    if path is None:
        return jsonify({
            "success": False,
            "error": "Completed video is not available"
        }), 404

    return send_file(
        path,
        mimetype="video/mp4",
        as_attachment=True,
        download_name=path.name,
        conditional=True
    )



if __name__ == "__main__":

    print()
    print("MELODIA AI - WEB SERVER")
    print("Video Request API: READY")
    print("Job Status API: READY")
    print("MP4 Preview: READY")
    print("MP4 Download: READY")
    print("Controlled Test API: READY")
    print()
    print("Open: http://127.0.0.1:5000")
    print()

    app.run(
    host="0.0.0.0",
    port=int(__import__("os").environ.get("PORT", 10000)),
    debug=False
)
