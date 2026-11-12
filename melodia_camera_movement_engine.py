"""MELODIA AI V2.1: deterministic cinematic camera movement planner.

This module plans normalized camera keyframes; it does not render video.
"""

import argparse
import json
import math
from pathlib import Path

VERSION = "2.1"
MOVEMENTS = ("static", "pan_left", "pan_right", "zoom_in", "zoom_out", "track_subject")


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def _center(obj):
    point = obj.get("center")
    if not isinstance(point, dict):
        raise ValueError("object center must be an object")
    x = _number(point.get("x"), "center.x")
    y = _number(point.get("y"), "center.y")
    if not (0 <= x <= 1 and 0 <= y <= 1):
        raise ValueError("object center must be normalized to [0, 1]")
    return {"x": x, "y": y}


def _scene_objects(scene):
    if not isinstance(scene, dict) or not isinstance(scene.get("objects"), list):
        raise ValueError("each scene must contain an objects list")
    objects = scene["objects"]
    seen = set()
    for obj in objects:
        if not isinstance(obj, dict) or not isinstance(obj.get("id"), str) or not obj["id"].strip():
            raise ValueError("each object requires a nonempty string id")
        identity = obj.get("continuity_id", obj["id"])
        if not isinstance(identity, str) or not identity.strip() or identity in seen:
            raise ValueError("object continuity identities must be unique within a scene")
        seen.add(identity)
        _center(obj)
    return objects


def _clamp(value, low, high):
    return max(low, min(high, value))


def _keyframe(t, x, y, zoom):
    return {"t": round(t, 6), "x": round(x, 6), "y": round(y, 6), "zoom": round(zoom, 6)}


def plan_camera_movements(scenes, seed=0, default_duration=10.0, intensity=0.35):
    """Return a deterministic camera plan for a list of scene dictionaries.

    Optional per-scene keys: duration (seconds), camera_movement (one of
    MOVEMENTS), and focus_id (id or continuity_id of an object).
    """
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("scenes must be a nonempty list")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    default_duration = _number(default_duration, "default_duration")
    intensity = _number(intensity, "intensity")
    if default_duration <= 0 or not 0 <= intensity <= 1:
        raise ValueError("default_duration must be positive and intensity must be in [0, 1]")

    plans = []
    elapsed = 0.0
    for index, scene in enumerate(scenes):
        objects = _scene_objects(scene)
        duration = _number(scene.get("duration", default_duration), "duration")
        if duration <= 0:
            raise ValueError("scene duration must be positive")
        movement = scene.get("camera_movement")
        if movement is None:
            movement = ("zoom_in", "pan_right", "zoom_out", "pan_left")[((index + seed) % 4)] if objects else "static"
        if movement not in MOVEMENTS:
            raise ValueError(f"unsupported camera movement: {movement}")
        focus_id = scene.get("focus_id")
        focus = None
        if focus_id is not None:
            if not isinstance(focus_id, str):
                raise ValueError("focus_id must be a string")
            focus = next((o for o in objects if focus_id in (o["id"], o.get("continuity_id"))), None)
            if focus is None:
                raise ValueError(f"focus_id not found: {focus_id}")
        elif objects:
            focus = objects[0]
        if movement == "track_subject" and focus is None:
            raise ValueError("track_subject requires a scene object")

        center = _center(focus) if focus else {"x": 0.5, "y": 0.5}
        x, y = center["x"], center["y"]
        displacement = 0.12 * intensity
        zoom_delta = 0.35 * intensity
        start = _keyframe(0, x, y, 1.0)
        end = _keyframe(1, x, y, 1.0)
        if movement == "pan_left":
            start = _keyframe(0, _clamp(x + displacement, 0, 1), y, 1.0)
            end = _keyframe(1, _clamp(x - displacement, 0, 1), y, 1.0)
        elif movement == "pan_right":
            start = _keyframe(0, _clamp(x - displacement, 0, 1), y, 1.0)
            end = _keyframe(1, _clamp(x + displacement, 0, 1), y, 1.0)
        elif movement == "zoom_in":
            end = _keyframe(1, x, y, 1.0 + zoom_delta)
        elif movement == "zoom_out":
            start = _keyframe(0, x, y, 1.0 + zoom_delta)
        elif movement == "track_subject":
            # A single scene snapshot has no motion trajectory; keep the subject
            # centered. Later integration may supply timed subject positions.
            start = _keyframe(0, x, y, 1.0 + zoom_delta / 2)
            end = _keyframe(1, x, y, 1.0 + zoom_delta / 2)

        plans.append({
            "scene_index": index,
            "start_seconds": round(elapsed, 6),
            "duration_seconds": duration,
            "movement": movement,
            "focus_id": focus.get("continuity_id", focus["id"]) if focus else None,
            "keyframes": [start, end],
            "easing": "ease_in_out",
        })
        elapsed += duration
    return {"version": VERSION, "seed": seed, "scene_count": len(plans),
            "total_duration_seconds": round(elapsed, 6), "camera_plans": plans}


def main():
    parser = argparse.ArgumentParser(description="MELODIA AI camera movement planner")
    parser.add_argument("--input", required=True, help="JSON file with a scenes list")
    parser.add_argument("--output", required=True, help="Output JSON plan path")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or "scenes" not in payload:
        parser.error("input JSON must contain a scenes list")
    result = plan_camera_movements(payload["scenes"], seed=args.seed)
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Saved {len(result['camera_plans'])} camera plans to {destination}")


if __name__ == "__main__":
    main()
