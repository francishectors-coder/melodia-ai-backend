
"""MELODIA AI V2.3 — deterministic cinematic scene orchestration.

Coordinates the existing V1.9 depth, V2.0 continuity, V2.1 camera and
V2.2 transition planners. Produces JSON planning metadata, not an MP4.
Earlier engines are imported unchanged.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path

from melodia_scene_continuity_engine import plan_continuity
from melodia_camera_movement_engine import plan_camera_movements
from melodia_cinematic_transition_engine import plan_cinematic_transitions

VERSION = "2.3"


def _finite(value, label):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise ValueError(f"{label} must be a finite number")
    return float(value)


def _prepare_scenes(scenes, default_duration):
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("scenes must be a nonempty list")

    prepared = copy.deepcopy(scenes)

    for index, scene in enumerate(prepared):
        if not isinstance(scene, dict) or not isinstance(
            scene.get("objects"), list
        ):
            raise ValueError(f"scene {index} must have an objects list")

        duration = _finite(
            scene.get("duration", default_duration),
            f"scene {index} duration",
        )

        if duration <= 0:
            raise ValueError("scene durations must be positive")

        scene["duration"] = duration

        for obj in scene["objects"]:
            if not isinstance(obj, dict):
                raise ValueError(
                    f"scene {index} contains an invalid object"
                )

            # V2.0 permits missing centers; V2.1 requires a
            # normalized center. Use the canvas center for
            # camera planning when a center is absent.
            if obj.get("center") is None:
                obj["center"] = {"x": 0.5, "y": 0.5}

    return prepared


def orchestrate_scenes(
    scenes,
    *,
    seed=1337,
    default_duration=10.0,
    camera_intensity=0.35,
    transition_duration=1.0,
    preferred_transition=None,
):
    """Build a synchronized, non-mutating cinematic plan."""

    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")

    default_duration = _finite(
        default_duration, "default_duration"
    )

    if default_duration <= 0:
        raise ValueError("default_duration must be positive")

    prepared = _prepare_scenes(scenes, default_duration)

    continuity = plan_continuity(prepared, seed=seed)
    annotated = continuity["scenes"]

    camera = plan_camera_movements(
        annotated,
        seed=seed,
        default_duration=default_duration,
        intensity=camera_intensity,
    )

    # Pass selected camera movements to V2.2.
    transition_scenes = copy.deepcopy(annotated)

    for scene, camera_plan in zip(
        transition_scenes, camera["camera_plans"]
    ):
        scene["camera_movement"] = camera_plan["movement"]

    cinematic = plan_cinematic_transitions(
        transition_scenes,
        transition_duration=transition_duration,
        preferred_transition=preferred_transition,
        seed=seed,
    )

    # Account for overlapping cinematic transitions.
    overlaps = [
        item["duration_seconds"]
        for item in cinematic["transitions"]
    ]

    elapsed = 0.0
    timeline = []
    synchronized_camera = copy.deepcopy(
        camera["camera_plans"]
    )

    for index, (scene, camera_plan) in enumerate(
        zip(annotated, synchronized_camera)
    ):
        duration = scene["duration"]
        start = round(elapsed, 6)
        end = round(elapsed + duration, 6)

        camera_plan["start_seconds"] = start

        timeline.append({
            "scene_index": index,
            "start_seconds": start,
            "end_seconds": end,
            "duration_seconds": duration,
            "camera_movement": camera_plan["movement"],
        })

        elapsed += duration

        if index < len(overlaps):
            elapsed -= overlaps[index]

    output_duration = round(elapsed, 6)

    if (
        abs(
            output_duration
            - cinematic["total_output_duration_seconds"]
        )
        > 0.00001
    ):
        raise RuntimeError(
            "cinematic timeline duration mismatch"
        )

    return {
        "project": "MELODIA AI",
        "version": VERSION,
        "seed": seed,
        "scene_count": len(annotated),
        "total_source_duration_seconds": (
            cinematic["total_source_duration_seconds"]
        ),
        "total_output_duration_seconds": output_duration,
        "scenes": annotated,
        "scene_timeline": timeline,
        "object_tracks": continuity["tracks"],
        "continuity_transitions": continuity["transitions"],
        "camera_plans": synchronized_camera,
        "cinematic_transitions": cinematic["transitions"],
        "engine_versions": {
            "continuity": continuity["version"],
            "camera": camera["version"],
            "transitions": cinematic["version"],
        },
    }


def orchestrate_prompts(
    prompts,
    *,
    seed=1337,
    variation=0.5,
    default_duration=10.0,
    **kwargs,
):
    """Generate V1.9 scenes and orchestrate them.

    Unsupported prompts raise ValueError with diagnostic details.
    """

    if (
        not isinstance(prompts, list)
        or not prompts
        or not all(
            isinstance(prompt, str) and prompt.strip()
            for prompt in prompts
        )
    ):
        raise ValueError(
            "prompts must be a nonempty list of strings"
        )

    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")

    from melodia_geometric_object_learner import EXAMPLES
    from melodia_automatic_structure_learner import learn_all
    from melodia_scene_depth_engine import generate_depth_scene

    learned = learn_all(EXAMPLES)
    scenes = []

    for index, prompt in enumerate(prompts):
        scene = generate_depth_scene(
            prompt,
            learned,
            seed=seed + index,
            variation=variation,
        )

        if scene.get("status") != "generated":
            raise ValueError(
                f"Prompt {index} failed: "
                f"status={scene.get('status')}, "
                f"reason={scene.get('reason', 'not provided')}, "
                f"prompt={prompt!r}"
            )

        scene["duration"] = default_duration
        scenes.append(scene)

    result = orchestrate_scenes(
        scenes,
        seed=seed,
        default_duration=default_duration,
        **kwargs,
    )

    result["engine_versions"]["depth"] = "1.9"

    return result


def main():
    parser = argparse.ArgumentParser(
        description="MELODIA AI V2.3 scene orchestration"
    )

    parser.add_argument(
        "--input",
        required=True,
        help="JSON object with scenes or prompts",
    )

    parser.add_argument(
        "--output",
        required=True,
        help="Output JSON plan",
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=1337,
    )

    parser.add_argument(
        "--duration",
        type=float,
        default=10.0,
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
        "--transition",
        default=None,
        choices=(
            "cut",
            "crossfade",
            "dissolve",
            "fade_through_black",
        ),
    )

    args = parser.parse_args()

    payload = json.loads(
        Path(args.input).read_text(encoding="utf-8")
    )

    if not isinstance(payload, dict):
        parser.error("input must be a JSON object")

    options = dict(
        seed=args.seed,
        default_duration=args.duration,
        camera_intensity=args.camera_intensity,
        transition_duration=args.transition_duration,
        preferred_transition=args.transition,
    )

    if "scenes" in payload:
        result = orchestrate_scenes(
            payload["scenes"],
            **options,
        )

    elif "prompts" in payload:
        result = orchestrate_prompts(
            payload["prompts"],
            **options,
        )

    else:
        parser.error(
            "input requires 'scenes' or 'prompts'"
        )

    destination = Path(args.output)

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination.write_text(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(
        f"MELODIA AI V{VERSION}: "
        f"{result['scene_count']} scenes; "
        f"output duration "
        f"{result['total_output_duration_seconds']} seconds"
    )


if __name__ == "__main__":
    main()
