"""MELODIA AI V2.0 — deterministic continuity planning for sequential scenes.

Consumes scene dictionaries with an ``objects`` list. Each object must have a
unique ``id`` within its scene; optional ``category``, ``center`` (normalized
x/y), and ``depth`` fields are used to match and track objects across scenes.
This module does not alter V1.9 rendering or scene-generation modules.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path

VERSION = "2.0"
DEPTHS = ("background", "middle", "foreground")


def _point(obj):
    center = obj.get("center")
    if not isinstance(center, dict):
        return None
    x, y = center.get("x"), center.get("y")
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool)
               and math.isfinite(v) and 0 <= v <= 1 for v in (x, y)):
        raise ValueError("Object centers must contain finite normalized x/y values")
    return {"x": float(x), "y": float(y)}


def _validate(scenes):
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("scenes must be a nonempty list")
    for index, scene in enumerate(scenes):
        if not isinstance(scene, dict) or not isinstance(scene.get("objects"), list):
            raise ValueError(f"Scene {index} must contain an objects list")
        ids = set()
        for obj in scene["objects"]:
            if not isinstance(obj, dict) or not isinstance(obj.get("id"), str) or not obj["id"]:
                raise ValueError("Each object needs a nonempty string id")
            if obj["id"] in ids:
                raise ValueError(f"Duplicate object id in scene {index}: {obj['id']}")
            ids.add(obj["id"])
            _point(obj)
            if obj.get("depth") is not None and obj["depth"] not in DEPTHS:
                raise ValueError(f"Unsupported depth: {obj['depth']}")


def plan_continuity(scenes, *, seed=1337):
    """Return a non-mutating continuity plan for an ordered scene sequence.

    Matching policy: explicit ``continuity_id`` first; otherwise an object's
    ``id``. IDs are stable across scenes only when the producer reuses them.
    No speculative matching of different IDs is attempted.
    """
    _validate(scenes)
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("seed must be an integer")
    tracks = {}
    transitions = []
    annotated = []
    previous = {}

    for scene_index, scene in enumerate(scenes):
        current = {}
        copied = copy.deepcopy(scene)
        for obj in copied["objects"]:
            identity = obj.get("continuity_id", obj["id"])
            if not isinstance(identity, str) or not identity:
                raise ValueError("continuity_id must be a nonempty string")
            if identity in current:
                raise ValueError(f"Duplicate continuity identity in scene {scene_index}: {identity}")
            obj["continuity_id"] = identity
            current[identity] = obj
            tracks.setdefault(identity, []).append({
                "scene_index": scene_index,
                "object_id": obj["id"],
                "category": obj.get("category"),
                "center": _point(obj),
                "depth": obj.get("depth"),
            })
        annotated.append(copied)
        if scene_index:
            shared = sorted(previous.keys() & current.keys())
            entering = sorted(current.keys() - previous.keys())
            exiting = sorted(previous.keys() - current.keys())
            movements = []
            for identity in shared:
                before, after = previous[identity], current[identity]
                p, q = _point(before), _point(after)
                delta = None if p is None or q is None else {
                    "dx": round(q["x"] - p["x"], 6),
                    "dy": round(q["y"] - p["y"], 6),
                }
                movements.append({
                    "continuity_id": identity,
                    "position_change": delta,
                    "depth_from": before.get("depth"),
                    "depth_to": after.get("depth"),
                    "depth_changed": before.get("depth") != after.get("depth"),
                    "category_changed": before.get("category") != after.get("category"),
                })
            transitions.append({
                "from_scene": scene_index - 1,
                "to_scene": scene_index,
                "persistent": shared,
                "entering": entering,
                "exiting": exiting,
                "movements": movements,
                "suggested_transition": "crossfade" if shared else "fade_through_black",
            })
        previous = current

    return {
        "version": VERSION,
        "seed": seed,
        "scene_count": len(scenes),
        "scenes": annotated,
        "tracks": {key: tracks[key] for key in sorted(tracks)},
        "transitions": transitions,
    }


def main():
    parser = argparse.ArgumentParser(description="MELODIA AI scene continuity planner")
    parser.add_argument("--input", required=True, help="JSON file containing a scenes list or {'scenes': [...]} object")
    parser.add_argument("--output", required=True, help="Destination JSON file")
    parser.add_argument("--seed", type=int, default=1337)
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    scenes = payload.get("scenes") if isinstance(payload, dict) else payload
    result = plan_continuity(scenes, seed=args.seed)
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"MELODIA V{VERSION}: {result['scene_count']} scenes, {len(result['tracks'])} object tracks")


if __name__ == "__main__":
    main()
