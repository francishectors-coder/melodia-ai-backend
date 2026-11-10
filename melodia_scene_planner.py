
# MELODIA AI - RESUMABLE SCENE PLANNER
# Step 1189
# Supports 30-second to 10-minute videos.
# Preserves generated images and resumes interrupted jobs.

import json
import math
from pathlib import Path

from melodia_subject_scene_generator import (
    generate_scene_descriptions
)
from melodia_ai_image_generator import generate_image


ROOT = Path(__file__).resolve().parent

JOBS = ROOT / "jobs"
PLANS = ROOT / "scene_plans"
VISUALS = ROOT / "generated_visuals"

PLANS.mkdir(parents=True, exist_ok=True)
VISUALS.mkdir(parents=True, exist_ok=True)

SCENE_DURATION = 10


def save_plan(output, plan):
    temporary = output.with_suffix(".tmp")

    with temporary.open("w", encoding="utf-8") as file:
        json.dump(
            plan,
            file,
            ensure_ascii=False,
            indent=2
        )

    temporary.replace(output)


def image_is_ready(image_path):
    image = Path(image_path)

    return (
        image.is_file()
        and image.stat().st_size > 0
    )


def create_scene_plan(job):
    job_id = job["job_id"]
    settings = job["settings"]

    output = PLANS / f"{job_id}_scenes.json"

    image_folder = VISUALS / job_id
    image_folder.mkdir(parents=True, exist_ok=True)

    # Reuse an existing scene plan when available.
    if output.is_file():
        print("Resuming existing scene plan:", output)

        with output.open("r", encoding="utf-8") as file:
            plan = json.load(file)

        if plan.get("job_id") != job_id:
            raise ValueError("Scene plan job ID mismatch")

        scenes = plan["scenes"]

    else:
        # Duration is measured in minutes.
        # 0.5 minutes = 30 seconds.
        # 1 minute = 60 seconds.
        # 2 to 10 minutes are also supported.
        duration_minutes = float(settings["duration"])

        if (
            not math.isfinite(duration_minutes)
            or duration_minutes not in (
                0.5, 1, 2, 3, 4, 5,
                6, 7, 8, 9, 10
            )
        ):
            raise ValueError(
                "Unsupported video duration. "
                "Select 30 secs, 60 secs, "
                "or 2-10 mins."
            )

        total_seconds = round(
            duration_minutes * 60
        )

        scene_count = math.ceil(
            total_seconds / SCENE_DURATION
        )

        descriptions = generate_scene_descriptions(
            settings["prompt"],
            count=scene_count
        )

        if len(descriptions) < scene_count:
            raise ValueError(
                "Insufficient scene descriptions generated"
            )

        scenes = []

        for index in range(scene_count):
            start = index * SCENE_DURATION

            end = min(
                start + SCENE_DURATION,
                total_seconds
            )

            description = descriptions[index]

            scenes.append({
                "scene_number": index + 1,
                "start_seconds": start,
                "end_seconds": end,
                "duration_seconds": end - start,
                "subject": description["subject"],
                "visual_prompt": description["visual_prompt"],
                "aspect_ratio": settings["aspect_ratio"],
                "image_path": str(
                    image_folder /
                    f"scene_{index + 1:03d}.png"
                ),
                "primary_language": settings["language"],
                "caption_mode": settings["captions"],
                "second_language": settings.get(
                    "second_language"
                ),
                "music_mood": settings["music"],
                "transition": "crossfade"
            })

        plan = {
            "job_id": job_id,
            "video_prompt": settings["prompt"],
            "duration_seconds": total_seconds,
            "aspect_ratio": settings["aspect_ratio"],
            "scene_count": scene_count,
            "completed_images": 0,
            "generation_status": "preparing",
            "scenes": scenes
        }

        # Save the plan before generating images.
        save_plan(output, plan)

        print("Scene plan created:", output)

    completed = 0

    for scene in scenes:
        image_path = Path(scene["image_path"])

        if image_is_ready(image_path):
            print(
                "Preserving existing image:",
                image_path.name
            )

        else:
            print(
                "Generating missing image:",
                image_path.name
            )

            try:
                generate_image(
                    prompt=scene["visual_prompt"],
                    output_path=str(image_path),
                    aspect_ratio=scene["aspect_ratio"]
                )

                if not image_is_ready(image_path):
                    raise RuntimeError(
                        "Image was not created: "
                        + image_path.name
                    )

            except Exception as error:
                plan["completed_images"] = completed
                plan["generation_status"] = "interrupted"

                save_plan(output, plan)

                print(
                    "SCENE GENERATION PAUSED:",
                    image_path.name,
                    str(error)
                )

                raise

        completed += 1

        plan["completed_images"] = completed
        plan["generation_status"] = "generating"

        save_plan(output, plan)

        print(
            f"Images ready: {completed}/{len(scenes)}"
        )

    plan["generation_status"] = "complete"
    plan["completed_images"] = len(scenes)

    save_plan(output, plan)

    print("ALL SCENE IMAGES READY")

    return plan, output


def main():
    print("MELODIA AI - RESUMABLE SCENE PLANNER")
    print("Supported durations: 30 secs to 10 mins")

    job_files = sorted(JOBS.glob("*.json"))

    for job_file in job_files:
        with job_file.open("r", encoding="utf-8") as file:
            job = json.load(file)

        if job.get("status") not in (
            "queued",
            "preparing",
            "failed"
        ):
            continue

        plan, output = create_scene_plan(job)

        print("Job ID:", job["job_id"])
        print("Scenes:", plan["scene_count"])
        print("Images ready:", plan["completed_images"])
        print("Saved:", output)
        return

    print("NO JOBS REQUIRING SCENE GENERATION")


if __name__ == "__main__":
    main()
