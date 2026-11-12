
"""
MELODIA AI V2.2
Automatic Cinematic Scene Transition Engine

Plans cinematic transitions between consecutive scenes.
Preserves earlier MELODIA AI versions.
Python 3.11 compatible. Standard library only.
"""

import argparse
import copy
import json
import math
from pathlib import Path

VERSION = "2.2"

TRANSITIONS = (
    "cut",
    "crossfade",
    "dissolve",
    "fade_through_black",
)

DEFAULT_TRANSITION = "crossfade"
DEFAULT_DURATION = 1.0
MAX_TRANSITION_DURATION = 3.0


def _number(value, name, minimum=0.0):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < minimum
    ):
        raise ValueError(f"Invalid {name}")
    return float(value)


def _identity(obj):
    return obj.get("continuity_id", obj["id"])


def _validate_scene(scene, index):
    if not isinstance(scene, dict):
        raise ValueError(f"Invalid scene {index}")

    objects = scene.get("objects")

    if not isinstance(objects, list):
        raise ValueError(f"Missing objects in scene {index}")

    identities = set()

    for obj in objects:
        if not isinstance(obj, dict):
            raise ValueError("Invalid scene object")

        identity = obj.get("continuity_id", obj.get("id"))

        if not isinstance(identity, str) or not identity:
            raise ValueError("Invalid object identity")

        if identity in identities:
            raise ValueError("Duplicate continuity identity")

        identities.add(identity)

    duration = _number(
        scene.get("duration", 10.0),
        "scene duration",
        0.001,
    )

    return duration, identities


def _camera_movement(scene):
    camera = scene.get("camera_movement", "static")

    if not isinstance(camera, str) or not camera:
        raise ValueError("Invalid camera movement")

    return camera


def _select_transition(
    current,
    following,
    shared,
    preferred,
):
    if preferred is not None:
        if preferred not in TRANSITIONS:
            raise ValueError("Unsupported transition")
        return preferred

    if not shared:
        return "fade_through_black"

    first_camera = _camera_movement(current)
    next_camera = _camera_movement(following)

    if first_camera == next_camera:
        return "crossfade"

    return "dissolve"


def plan_cinematic_transitions(
    scenes,
    transition_duration=DEFAULT_DURATION,
    preferred_transition=None,
    seed=1337,
):
    """Generate a deterministic cinematic transition plan."""

    if not isinstance(scenes, list) or not scenes:
        raise ValueError("Scenes must be a nonempty list")

    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("Seed must be an integer")

    duration = _number(
        transition_duration,
        "transition duration",
    )

    if duration > MAX_TRANSITION_DURATION:
        raise ValueError("Transition duration too large")

    if (
        preferred_transition is not None
        and preferred_transition not in TRANSITIONS
    ):
        raise ValueError("Unsupported transition")

    source = copy.deepcopy(scenes)

    validated = [
        _validate_scene(scene, index)
        for index, scene in enumerate(source)
    ]

    for scene in source:
        _camera_movement(scene)

    transitions = []
    elapsed = 0.0
    total_duration = sum(item[0] for item in validated)

    for index in range(len(source) - 1):
        current = source[index]
        following = source[index + 1]

        current_duration, current_ids = validated[index]
        next_duration, next_ids = validated[index + 1]

        shared = sorted(current_ids & next_ids)
        entering = sorted(next_ids - current_ids)
        exiting = sorted(current_ids - next_ids)

        selected = _select_transition(
            current,
            following,
            shared,
            preferred_transition,
        )

        overlap = (
            0.0 if selected == "cut"
            else min(
                duration,
                current_duration / 2.0,
                next_duration / 2.0,
            )
        )

        elapsed += current_duration

        transitions.append({
            "from_scene": index,
            "to_scene": index + 1,
            "transition": selected,
            "duration_seconds": round(overlap, 6),
            "start_seconds": round(
                elapsed - overlap, 6
            ),
            "end_seconds": round(elapsed, 6),
            "shared_objects": shared,
            "entering_objects": entering,
            "exiting_objects": exiting,
            "camera_from": _camera_movement(current),
            "camera_to": _camera_movement(following),
            "preserves_identity": bool(shared),
        })

        elapsed -= overlap

    overlap_total = sum(
        item["duration_seconds"]
        for item in transitions
    )

    return {
        "project": "MELODIA AI",
        "version": VERSION,
        "seed": seed,
        "scene_count": len(source),
        "transition_count": len(transitions),
        "total_source_duration_seconds": round(
            total_duration, 6
        ),
        "total_output_duration_seconds": round(
            total_duration - overlap_total, 6
        ),
        "transitions": transitions,
    }


def main():
    parser = argparse.ArgumentParser(
        description="MELODIA AI Cinematic Transition Engine"
    )

    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--duration",
        type=float,
        default=DEFAULT_DURATION,
    )
    parser.add_argument(
        "--transition",
        choices=TRANSITIONS,
        default=None,
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=1337,
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    data = json.loads(
        input_path.read_text(encoding="utf-8")
    )

    if not isinstance(data, dict):
        raise ValueError("Input must be a JSON object")

    result = plan_cinematic_transitions(
        data["scenes"],
        transition_duration=args.duration,
        preferred_transition=args.transition,
        seed=args.seed,
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )

    print(
        "MELODIA AI V2.2 transition plan generated"
    )
    print(
        "Transitions:", result["transition_count"]
    )
    print(
        "Output duration:",
        result["total_output_duration_seconds"],
    )


if __name__ == "__main__":
    main()
