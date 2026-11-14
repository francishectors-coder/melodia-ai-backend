
"""
MELODIA AI V2.8
Prompt-to-Cinematic Integration Engine

Connects:
- V2.8 automatic prompt-to-scene generation
- V2.3 cinematic orchestration

Features:
- Deterministic cinematic planning
- Exact requested output duration
- Automatic transition-overlap compensation
- Landscape and portrait support
- Scene continuity validation

Existing MELODIA AI engines remain unchanged.

Python 3.11+
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from melodia_prompt_scene_engine import (
    generate_prompt_scenes,
)

from melodia_cinematic_orchestration_engine import (
    orchestrate_scenes,
)

VERSION = "2.8"
DURATION_TOLERANCE = 0.001


def _valid_number(value):
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
    )


def _validate_plan(plan):
    """Validate the generated cinematic plan."""

    if not isinstance(plan, dict):
        raise ValueError(
            "Cinematic plan must be a dictionary"
        )

    scenes = plan.get("scenes")

    if not isinstance(scenes, list) or not scenes:
        raise ValueError(
            "Cinematic plan must contain scenes"
        )

    for index, scene in enumerate(scenes):

        if not isinstance(scene, dict):
            raise ValueError(
                f"Scene {index + 1} is invalid"
            )

        objects = scene.get("objects")

        if not isinstance(objects, list):
            raise ValueError(
                f"Scene {index + 1} has invalid objects"
            )

        duration = scene.get("duration")

        if (
            not _valid_number(duration)
            or duration <= 0
        ):
            raise ValueError(
                f"Scene {index + 1} has invalid duration"
            )

        identities = set()

        for obj in objects:

            if not isinstance(obj, dict):
                raise ValueError(
                    "Invalid scene object"
                )

            identity = obj.get("continuity_id")

            if (
                not isinstance(identity, str)
                or not identity
            ):
                raise ValueError(
                    "Missing continuity identity"
                )

            if identity in identities:
                raise ValueError(
                    "Duplicate continuity identity"
                )

            identities.add(identity)

            center = obj.get("center")

            if not isinstance(center, dict):
                raise ValueError(
                    "Invalid object center"
                )

            for axis in ("x", "y"):

                value = center.get(axis)

                if (
                    not _valid_number(value)
                    or not 0 <= value <= 1
                ):
                    raise ValueError(
                        f"Invalid object {axis} coordinate"
                    )

    return True


def _compensate_scene_durations(
    scenes,
    requested_duration,
    transition_duration,
):
    """
    Compensate for overlapping scene transitions.

    The V2.3 engine uses overlapping transitions.
    The total scene duration must therefore include
    the overlap that will be removed during assembly.
    """

    scene_count = len(scenes)

    if scene_count == 0:
        raise ValueError(
            "Cannot compensate an empty scene list"
        )

    if (
        not _valid_number(requested_duration)
        or requested_duration <= 0
    ):
        raise ValueError(
            "Requested duration must be positive"
        )

    overlap_count = max(0, scene_count - 1)

    total_overlap = (
        overlap_count * transition_duration
    )

    adjusted_total = (
        requested_duration + total_overlap
    )

    original_total = sum(
        float(scene["duration"])
        for scene in scenes
    )

    if original_total <= 0:
        raise ValueError(
            "Original scene duration is invalid"
        )

    scale = adjusted_total / original_total

    compensated = []

    for scene in scenes:

        updated_scene = dict(scene)

        updated_scene["duration"] = (
            float(scene["duration"]) * scale
        )

        compensated.append(updated_scene)

    return compensated


def generate_cinematic_plan(
    prompt,
    duration_seconds=60,
    aspect_ratio="16:9",
    scene_seconds=10,
    camera_intensity=0.35,
    transition_duration=1.0,
    seed=None,
):
    """
    Generate a deterministic cinematic plan.

    Transition overlap is compensated so the
    resulting cinematic timeline matches the
    requested playback duration.
    """

    scene_plan = generate_prompt_scenes(
        prompt=prompt,
        duration_seconds=duration_seconds,
        aspect_ratio=aspect_ratio,
        scene_seconds=scene_seconds,
    )

    if seed is None:
        seed = scene_plan["seed"]

    if (
        isinstance(seed, bool)
        or not isinstance(seed, int)
    ):
        raise ValueError(
            "Seed must be an integer"
        )

    if (
        not _valid_number(camera_intensity)
        or not 0 <= camera_intensity <= 1
    ):
        raise ValueError(
            "Camera intensity must be between 0 and 1"
        )

    if (
        not _valid_number(transition_duration)
        or not 0 <= transition_duration <= 3
    ):
        raise ValueError(
            "Transition duration must be between 0 and 3"
        )

    requested_duration = float(
        scene_plan["duration_seconds"]
    )

    source_scenes = scene_plan["scenes"]

    compensated_scenes = (
        _compensate_scene_durations(
            source_scenes,
            requested_duration,
            transition_duration,
        )
    )

    cinematic = orchestrate_scenes(
        compensated_scenes,
        seed=seed,
        default_duration=scene_seconds,
        camera_intensity=camera_intensity,
        transition_duration=transition_duration,
    )

    _validate_plan(cinematic)

    actual_duration = cinematic.get(
        "total_output_duration_seconds"
    )

    if not _valid_number(actual_duration):
        raise ValueError(
            "Cinematic output duration is missing"
        )

    duration_error = (
        float(actual_duration)
        - requested_duration
    )

    if abs(duration_error) > DURATION_TOLERANCE:
        raise ValueError(
            "Cinematic duration mismatch: "
            f"requested={requested_duration}, "
            f"actual={actual_duration}"
        )

    result = {
        "project": "MELODIA AI",
        "version": VERSION,
        "engine": "prompt_cinematic_integration",
        "prompt": scene_plan["prompt"],
        "seed": seed,
        "aspect_ratio": scene_plan["aspect_ratio"],
        "width": scene_plan["width"],
        "height": scene_plan["height"],
        "requested_duration_seconds": (
            requested_duration
        ),
        "actual_duration_seconds": (
            float(actual_duration)
        ),
        "duration_error_seconds": (
            duration_error
        ),
        "transition_overlap_compensated": True,
        "scene_count": len(cinematic["scenes"]),
        "cinematic_plan": cinematic,
    }

    return result


def save_cinematic_plan(plan, output):
    """Save the complete cinematic plan as JSON."""

    destination = Path(output)

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination.write_text(
        json.dumps(
            plan,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return destination


def main():

    parser = argparse.ArgumentParser(
        description=(
            "MELODIA AI V2.8 "
            "Exact-Duration Cinematic Integration"
        )
    )

    parser.add_argument(
        "--prompt",
        required=True,
    )

    parser.add_argument(
        "--output",
        required=True,
    )

    parser.add_argument(
        "--duration",
        type=float,
        default=60,
    )

    parser.add_argument(
        "--aspect",
        choices=("16:9", "9:16"),
        default="16:9",
    )

    parser.add_argument(
        "--scene-seconds",
        type=float,
        default=10,
    )

    parser.add_argument(
        "--camera-intensity",
        type=float,
        default=0.35,
    )

    parser.add_argument(
        "--transition-duration",
        type=float,
        default=1.0,
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=None,
    )

    args = parser.parse_args()

    result = generate_cinematic_plan(
        prompt=args.prompt,
        duration_seconds=args.duration,
        aspect_ratio=args.aspect,
        scene_seconds=args.scene_seconds,
        camera_intensity=args.camera_intensity,
        transition_duration=args.transition_duration,
        seed=args.seed,
    )

    destination = save_cinematic_plan(
        result,
        args.output,
    )

    print(
        "MELODIA AI V2.8 "
        "EXACT-DURATION CINEMATIC INTEGRATION"
    )

    print("Status: Plan generated")
    print("Scenes:", result["scene_count"])

    print(
        "Requested duration:",
        result["requested_duration_seconds"],
    )

    print(
        "Actual duration:",
        result["actual_duration_seconds"],
    )

    print(
        "Duration error:",
        result["duration_error_seconds"],
    )

    print("Aspect:", result["aspect_ratio"])
    print("Output:", destination)


if __name__ == "__main__":
    main()
