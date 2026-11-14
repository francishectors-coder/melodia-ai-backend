
"""
MELODIA AI V2.8
Prompt-to-Cinematic Integration Engine

Connects:
- V2.8 automatic prompt-to-scene generation
- V2.3 cinematic orchestration

Produces a deterministic cinematic JSON plan.

Python 3.11+
Standard library for this integration module.

Existing MELODIA AI engines remain unchanged.
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


def _validate_plan(plan):
    """Check essential integration output."""

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
            isinstance(duration, bool)
            or not isinstance(duration, (int, float))
            or not math.isfinite(duration)
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

            if not isinstance(identity, str) or not identity:
                raise ValueError(
                    "Missing continuity identity"
                )

            if identity in identities:
                raise ValueError(
                    "Duplicate continuity identity"
                )

            identities.add(identity)

            center = obj.get("center", {})

            if not isinstance(center, dict):
                raise ValueError(
                    "Invalid object center"
                )

            for axis in ("x", "y"):
                value = center.get(axis)

                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    or not 0 <= value <= 1
                ):
                    raise ValueError(
                        f"Invalid object {axis} coordinate"
                    )

    return True


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
    Generate and orchestrate scenes from one prompt.

    Note:
    The final cinematic timeline can be shorter than
    the sum of scene durations because transitions
    may overlap adjacent scenes.
    """

    scene_plan = generate_prompt_scenes(
        prompt=prompt,
        duration_seconds=duration_seconds,
        aspect_ratio=aspect_ratio,
        scene_seconds=scene_seconds,
    )

    if seed is None:
        seed = scene_plan["seed"]

    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError(
            "Seed must be an integer"
        )

    if (
        isinstance(camera_intensity, bool)
        or not isinstance(camera_intensity, (int, float))
        or not math.isfinite(camera_intensity)
        or not 0 <= camera_intensity <= 1
    ):
        raise ValueError(
            "Camera intensity must be between 0 and 1"
        )

    if (
        isinstance(transition_duration, bool)
        or not isinstance(transition_duration, (int, float))
        or not math.isfinite(transition_duration)
        or not 0 <= transition_duration <= 3
    ):
        raise ValueError(
            "Transition duration must be between 0 and 3"
        )

    source_scenes = scene_plan["scenes"]

    cinematic = orchestrate_scenes(
        source_scenes,
        seed=seed,
        default_duration=scene_seconds,
        camera_intensity=camera_intensity,
        transition_duration=transition_duration,
    )

    _validate_plan(cinematic)

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
            scene_plan["duration_seconds"]
        ),
        "scene_count": len(cinematic["scenes"]),
        "cinematic_plan": cinematic,
    }

    return result


def save_cinematic_plan(plan, output):
    """Write cinematic plan to JSON."""

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
            "MELODIA AI V2.8 Prompt-to-Cinematic "
            "Integration"
        )
    )

    parser.add_argument(
        "--prompt",
        required=True,
        help="Natural-language video prompt",
    )

    parser.add_argument(
        "--output",
        required=True,
        help="Destination JSON file",
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

    print("MELODIA AI V2.8 CINEMATIC INTEGRATION")
    print("Status: Plan generated")
    print("Scenes:", result["scene_count"])
    print(
        "Requested duration:",
        result["requested_duration_seconds"],
    )
    print("Aspect:", result["aspect_ratio"])
    print("Output:", destination)


if __name__ == "__main__":
    main()
