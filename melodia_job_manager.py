
import json
import uuid
from pathlib import Path
from datetime import datetime, timezone

# MELODIA AI - CLOUD VIDEO JOB MANAGER
# Render-compatible version

ROOT = Path(__file__).resolve().parent
JOBS = ROOT / "jobs"

JOBS.mkdir(parents=True, exist_ok=True)


def create_video_job(settings):
    job_id = uuid.uuid4().hex

    job = {
        "job_id": job_id,
        "created_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "status": "queued",
        "progress": 0,
        "settings": settings,
        "output_file": None,
        "error": None
    }

    job_file = JOBS / f"{job_id}.json"

    temporary_file = JOBS / f"{job_id}.tmp"

    with temporary_file.open(
        "w", encoding="utf-8"
    ) as file:
        json.dump(
            job,
            file,
            ensure_ascii=False,
            indent=2
        )

    temporary_file.replace(job_file)

    return job


def get_video_job(job_id):
    if (
        not isinstance(job_id, str)
        or len(job_id) != 32
        or any(
            c not in "0123456789abcdef"
            for c in job_id
        )
    ):
        return None

    job_file = JOBS / f"{job_id}.json"

    if not job_file.is_file():
        return None

    try:
        with job_file.open(
            "r", encoding="utf-8"
        ) as file:
            return json.load(file)
    except (OSError, ValueError):
        return None


if __name__ == "__main__":
    print("MELODIA AI - CLOUD JOB MANAGER")
    print("Job directory:", JOBS)
    print("Cloud-compatible configuration ready")
