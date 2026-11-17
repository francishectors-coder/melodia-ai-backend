"""MELODIA AI V3.2 — independent duration-aware scene planner.

Expands V3.1's validated, prompt-ordered environments into approximately
10-second scenes for videos of 30–600 seconds. Does not alter V3.1 modules,
production routing, artwork or caption translation.

This is a scene-planning stage only. V3.2 production integration, music,
multilingual captions and long-video rendering require separate validation.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path

from melodia_unified_scene_engine import (
    plan_scenes as plan_v31_scenes,
    render_scene_svg,
    validate_plan,
)

VERSION = "3.2.0-scene-planner"
MIN_DURATION_SECONDS = 30.0
MAX_DURATION_SECONDS = 600.0
TARGET_SCENE_SECONDS = 10.0
MAX_SCENES = 60


def _duration(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Duration must be a number of seconds")
    value = float(value)
    if not math.isfinite(value) or not MIN_DURATION_SECONDS <= value <= MAX_DURATION_SECONDS:
        raise ValueError("Duration must be between 30 and 600 seconds")
    return value


def plan_scenes(prompt: str, duration_seconds: float = 30) -> dict:
    """Return V3.1-compatible validated scenes, scaled to requested duration.

    Environments repeat in the same order as the user's prompt. This avoids
    inventing new environments or captions beyond V3.1's supported vocabulary.
    Each scene has its own deep-copied objects and sequential scene ID.
    """
    seconds = _duration(duration_seconds)
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("A nonempty prompt is required")

    # V3.1 remains the source of truth for supported prompt interpretation,
    # scene artwork, captions, geometry and ground alignment.
    baseline = plan_v31_scenes(prompt, 30)
    source_scenes = baseline.get("scenes")
    validate_plan(source_scenes)
    if not source_scenes:
        raise ValueError("No supported scenes in prompt")

    scene_count = max(1, min(MAX_SCENES, int(math.floor(seconds / TARGET_SCENE_SECONDS + 0.5))))
    # Set the last duration as a residual to preserve the exact requested sum.
    per_scene = seconds / scene_count
    scenes = []
    elapsed = 0.0
    for index in range(scene_count):
        scene = copy.deepcopy(source_scenes[index % len(source_scenes)])
        scene["id"] = f"scene_{index + 1:03d}"
        scene_duration = per_scene if index < scene_count - 1 else seconds - elapsed
        scene["duration_seconds"] = scene_duration
        scenes.append(scene)
        elapsed += scene_duration

    validate_plan(scenes)
    if abs(math.fsum(s["duration_seconds"] for s in scenes) - seconds) > 1e-6:
        raise ValueError("Scene durations do not match requested duration")

    return {
        "version": VERSION,
        "source_engine_version": baseline.get("version"),
        "source_prompt": prompt,
        "duration_seconds": seconds,
        "target_scene_seconds": TARGET_SCENE_SECONDS,
        "scenes": scenes,
    }


def export_preview(plan: dict, output_dir: str | Path, *, width: int = 1280,
                   height: int = 720) -> Path:
    """Export each V3.2 scene through the unchanged V3.1 SVG renderer."""
    validate_plan(plan["scenes"])
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    for scene in plan["scenes"]:
        (directory / f"{scene['id']}.svg").write_text(
            render_scene_svg(scene, width, height), encoding="utf-8"
        )
    (directory / "v32_scene_plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return directory


def main() -> None:
    parser = argparse.ArgumentParser(description="MELODIA V3.2 independent scene planner")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--duration", type=float, default=30, help="Video seconds (30–600)")
    parser.add_argument("--output", help="Optional directory for SVG preview and plan JSON")
    parser.add_argument("--aspect", choices=("16:9", "9:16"), default="16:9")
    args = parser.parse_args()
    plan = plan_scenes(args.prompt, args.duration)
    if args.output:
        dimensions = (1280, 720) if args.aspect == "16:9" else (720, 1280)
        export_preview(plan, args.output, width=dimensions[0], height=dimensions[1])
    print(json.dumps({
        "status": "PASS", "version": VERSION,
        "scene_count": len(plan["scenes"]),
        "duration_seconds": plan["duration_seconds"],
        "scene_duration_seconds": plan["scenes"][0]["duration_seconds"],
        "environments_first_cycle": [s["environment"] for s in plan["scenes"][:3]],
        "integration_status": "planner_only_not_connected_to_website",
    }, indent=2))


if __name__ == "__main__":
    main()
