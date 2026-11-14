
"""MELODIA AI V2.0 — deterministic scene continuity planning.

Tracks objects across sequential scenes using explicit continuity
identities when supplied, and category-aware spatial matching
otherwise.

Prevents automatically numbered scene objects from being incorrectly
treated as the same object when their categories differ.

Produces JSON planning metadata without modifying source scenes.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path

VERSION = "2.0"

DEPTHS = (
    "background",
    "middle",
    "foreground",
)


def _point(obj):
    center = obj.get("center")

    if not isinstance(center, dict):
        return None

    x = center.get("x")
    y = center.get("y")

    for value in (x, y):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not 0 <= value <= 1
        ):
            raise ValueError(
                "Object centers must contain finite "
                "normalized x/y values"
            )

    return {
        "x": float(x),
        "y": float(y),
    }


def _validate(scenes):
    if not isinstance(scenes, list) or not scenes:
        raise ValueError(
            "scenes must be a nonempty list"
        )

    for index, scene in enumerate(scenes):
        if (
            not isinstance(scene, dict)
            or not isinstance(scene.get("objects"), list)
        ):
            raise ValueError(
                f"Scene {index} must contain an objects list"
            )

        ids = set()

        for obj in scene["objects"]:
            if (
                not isinstance(obj, dict)
                or not isinstance(obj.get("id"), str)
                or not obj["id"]
            ):
                raise ValueError(
                    "Each object needs a nonempty string id"
                )

            if obj["id"] in ids:
                raise ValueError(
                    f"Duplicate object id in scene "
                    f"{index}: {obj['id']}"
                )

            ids.add(obj["id"])

            _point(obj)

            if (
                obj.get("depth") is not None
                and obj["depth"] not in DEPTHS
            ):
                raise ValueError(
                    f"Unsupported depth: {obj['depth']}"
                )

            category = obj.get("category")

            if (
                category is not None
                and (
                    not isinstance(category, str)
                    or not category
                )
            ):
                raise ValueError(
                    "Object category must be a "
                    "nonempty string when supplied"
                )

            identity = obj.get("continuity_id")

            if (
                identity is not None
                and (
                    not isinstance(identity, str)
                    or not identity
                )
            ):
                raise ValueError(
                    "continuity_id must be a "
                    "nonempty string"
                )


def _distance(a, b):
    first = _point(a)
    second = _point(b)

    if first is None or second is None:
        return float("inf")

    return math.hypot(
        first["x"] - second["x"],
        first["y"] - second["y"],
    )


def _compatible(a, b):
    first = a.get("category")
    second = b.get("category")

    return (
        first == second
        or first is None
        or second is None
    )


def _new_identity(category, counters, used):
    name = category if category is not None else "object"

    counters[name] = counters.get(name, 0) + 1

    identity = f"{name}_{counters[name]}"

    while identity in used:
        counters[name] += 1
        identity = f"{name}_{counters[name]}"

    return identity


def _assign_identities(
    objects,
    previous,
    used,
    counters,
):
    """Assign stable identities without cross-category matching."""

    current = {}
    pending = []

    # Explicit continuity IDs have priority.
    for obj in objects:
        explicit = obj.get("continuity_id")

        if explicit is None:
            pending.append(obj)
            continue

        if explicit in current:
            raise ValueError(
                f"Duplicate continuity identity: {explicit}"
            )

        if (
            explicit in used
            and explicit not in previous
        ):
            raise ValueError(
                f"Previously used continuity identity "
                f"cannot be reused: {explicit}"
            )

        if (
            explicit in previous
            and not _compatible(
                previous[explicit], obj
            )
        ):
            raise ValueError(
                f"Continuity identity {explicit} "
                f"changes object category"
            )

        obj["continuity_id"] = explicit
        current[explicit] = obj
        used.add(explicit)

    # Match remaining objects to compatible previous objects.
    candidates = []

    for index, obj in enumerate(pending):
        for identity, previous_obj in previous.items():
            if identity in current:
                continue

            if not _compatible(previous_obj, obj):
                continue

            distance = _distance(previous_obj, obj)

            # Prefer exact category matches.
            category_penalty = (
                0
                if previous_obj.get("category")
                == obj.get("category")
                else 1
            )

            candidates.append((
                category_penalty,
                distance,
                identity,
                index,
            ))

    candidates.sort()

    matched_indices = set()

    for _, _, identity, index in candidates:
        if index in matched_indices:
            continue

        if identity in current:
            continue

        obj = pending[index]

        obj["continuity_id"] = identity
        current[identity] = obj
        matched_indices.add(index)

    # Allocate new identities for entering objects.
    for index, obj in enumerate(pending):
        if index in matched_indices:
            continue

        identity = _new_identity(
            obj.get("category"),
            counters,
            used,
        )

        obj["continuity_id"] = identity
        current[identity] = obj
        used.add(identity)

    return current


def plan_continuity(scenes, *, seed=1337):
    """Build deterministic category-aware object continuity."""

    _validate(scenes)

    if (
        isinstance(seed, bool)
        or not isinstance(seed, int)
    ):
        raise ValueError(
            "seed must be an integer"
        )

    tracks = {}
    transitions = []
    annotated = []

    previous = {}
    used = set()
    counters = {}

    for scene_index, scene in enumerate(scenes):
        copied = copy.deepcopy(scene)

        current = _assign_identities(
            copied["objects"],
            previous,
            used,
            counters,
        )

        for identity, obj in current.items():
            tracks.setdefault(identity, []).append({
                "scene_index": scene_index,
                "object_id": obj["id"],
                "category": obj.get("category"),
                "center": _point(obj),
                "depth": obj.get("depth"),
            })

        annotated.append(copied)

        if scene_index:
            previous_ids = set(previous)
            current_ids = set(current)

            shared = sorted(
                previous_ids & current_ids
            )

            entering = sorted(
                current_ids - previous_ids
            )

            exiting = sorted(
                previous_ids - current_ids
            )

            movements = []

            for identity in shared:
                before = previous[identity]
                after = current[identity]

                p = _point(before)
                q = _point(after)

                if p is None or q is None:
                    delta = None
                else:
                    delta = {
                        "dx": round(
                            q["x"] - p["x"], 6
                        ),
                        "dy": round(
                            q["y"] - p["y"], 6
                        ),
                    }

                movements.append({
                    "continuity_id": identity,
                    "position_change": delta,
                    "depth_from": before.get("depth"),
                    "depth_to": after.get("depth"),
                    "depth_changed": (
                        before.get("depth")
                        != after.get("depth")
                    ),
                    "category_changed": (
                        before.get("category")
                        != after.get("category")
                    ),
                })

            transitions.append({
                "from_scene": scene_index - 1,
                "to_scene": scene_index,
                "persistent": shared,
                "entering": entering,
                "exiting": exiting,
                "movements": movements,
                "suggested_transition": (
                    "crossfade"
                    if shared
                    else "fade_through_black"
                ),
            })

        previous = current

    return {
        "version": VERSION,
        "seed": seed,
        "scene_count": len(scenes),
        "scenes": annotated,
        "tracks": {
            key: tracks[key]
            for key in sorted(tracks)
        },
        "transitions": transitions,
    }


def main():
    parser = argparse.ArgumentParser(
        description="MELODIA AI scene continuity planner"
    )

    parser.add_argument(
        "--input",
        required=True,
        help=(
            "JSON file containing a scenes list "
            "or {'scenes': [...]} object"
        ),
    )

    parser.add_argument(
        "--output",
        required=True,
        help="Destination JSON file",
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=1337,
    )

    args = parser.parse_args()

    payload = json.loads(
        Path(args.input).read_text(
            encoding="utf-8"
        )
    )

    scenes = (
        payload.get("scenes")
        if isinstance(payload, dict)
        else payload
    )

    result = plan_continuity(
        scenes,
        seed=args.seed,
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
        f"MELODIA V{VERSION}: "
        f"{result['scene_count']} scenes, "
        f"{len(result['tracks'])} object tracks"
    )


if __name__ == "__main__":
    main()
