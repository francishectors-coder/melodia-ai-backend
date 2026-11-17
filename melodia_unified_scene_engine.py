"""MELODIA AI V3.1 — independent, validated scene-first SVG prototype.

No changes to the live V2.x pipeline. This module plans and draws complete
scenes, then validates the same geometry and captions used for drawing.
Illustrated SVG only; not a photorealistic image-generation model.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from xml.etree import ElementTree as ET

VERSION = "3.1.0-prototype"
NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)


def element(parent, name, **attrs):
    return ET.SubElement(parent, f"{{{NS}}}{name}",
                         {key.replace("_", "-"): str(value) for key, value in attrs.items()})


def _features(text):
    p = text.casefold()
    return {
        "mountain": bool(re.search(r"\b(mountains?|valleys?|hills?)\b", p)),
        "garden": bool(re.search(r"\b(gardens?|flowers?|meadows?)\b", p)),
        "lake": bool(re.search(r"\b(lakes?|lakesides?|ponds?|rivers?|waters?)\b", p)),
        "sunrise": bool(re.search(r"\b(sunrise|dawn|morning)\b", p)),
        "sunset": bool(re.search(r"\b(sunset|dusk|evening)\b", p)),
    }


def _ordered_environments(prompt):
    """Recognize ordered environments in the original request, not object nouns.

    This deliberately limited deterministic prototype refuses unsupported
    prompts rather than silently generating a generic flower scene.
    """
    text = prompt.strip()
    if not text:
        raise ValueError("Prompt must not be empty")
    patterns = {
        "mountain_valley": r"\b(mountain(?:s)?|valley|valleys|hills?)\b",
        "flower_garden": r"\b(garden|gardens|flower|flowers|meadow|meadows)\b",
        "lakeside": r"\b(lake|lakeside|pond|river)\b",
    }
    hits = []
    for kind, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            hits.append((match.start(), kind))
    hits.sort()
    if not hits:
        raise ValueError("V3.1 prototype supports mountain valleys, flower gardens and lakesides; unsupported prompt")
    return hits


def plan_scenes(prompt, duration_seconds=30):
    if isinstance(duration_seconds, bool) or not isinstance(duration_seconds, (int, float)) or not math.isfinite(duration_seconds) or duration_seconds <= 0:
        raise ValueError("duration_seconds must be positive")
    ordered = _ordered_environments(prompt)
    settings = {
        "mountain_valley": ("Mountain valley at sunrise", "Morning sunlight illuminates the mountain valley.", "sunrise"),
        "flower_garden": ("Flower garden", "Colorful flowers bloom in a peaceful garden.", "daylight"),
        "lakeside": ("Quiet lakeside at sunset", "The setting sun reflects across the quiet lake.", "sunset"),
    }
    # Respect local time-of-day wording when explicitly present near an environment.
    scenes = []
    for i, (start, kind) in enumerate(ordered):
        end = ordered[i + 1][0] if i + 1 < len(ordered) else len(prompt)
        context = prompt[start:end].casefold()
        name, caption, default_light = settings[kind]
        light = "sunset" if re.search(r"\b(sunset|dusk)\b", context) else "sunrise" if re.search(r"\b(sunrise|dawn)\b", context) else default_light
        scenes.append({"id": f"scene_{i+1:03d}", "environment": kind,
                       "title": name, "lighting": light, "caption_en": caption,
                       "duration_seconds": float(duration_seconds) / len(ordered),
                       "ground_y": 0.79 if kind != "lakeside" else 0.68,
                       "objects": _objects_for(kind)})
    validate_plan(scenes)
    return {"version": VERSION, "source_prompt": prompt, "duration_seconds": float(duration_seconds), "scenes": scenes}


def _objects_for(kind):
    # x, bottom, width, height are normalized; all bases equal scene ground.
    if kind == "mountain_valley":
        return [{"kind": "tree", "x": 0.16, "width": 0.075, "height": 0.25},
                {"kind": "tree", "x": 0.85, "width": 0.07, "height": 0.22}]
    if kind == "flower_garden":
        return [{"kind": "flower", "x": x, "width": 0.055, "height": 0.17 + (i % 3) * 0.025}
                for i, x in enumerate((0.12, 0.25, 0.38, 0.52, 0.66, 0.79, 0.90))]
    return [{"kind": "tree", "x": 0.13, "width": 0.075, "height": 0.22},
            {"kind": "tree", "x": 0.89, "width": 0.065, "height": 0.18}]


def validate_plan(scenes):
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("No scenes")
    allowed = {"mountain_valley": "mountain", "flower_garden": "flower", "lakeside": "lake"}
    for scene in scenes:
        kind = scene["environment"]
        if kind not in allowed or allowed[kind] not in (scene["title"] + " " + scene["caption_en"]).lower():
            raise ValueError(f"Scene/caption mismatch: {scene['id']}")
        ground = scene["ground_y"]
        if not 0.55 <= ground <= 0.9:
            raise ValueError("Ground outside visible landscape")
        if kind == "flower_garden" and sum(o["kind"] == "flower" for o in scene["objects"]) < 5:
            raise ValueError("Garden has insufficient flowers")
        bounds = []
        for obj in scene["objects"]:
            x, w, h = (obj[k] for k in ("x", "width", "height"))
            if not (0 < w < 1 and 0 < h < ground and w/2 <= x <= 1-w/2):
                raise ValueError("Invalid foreground geometry")
            rect = (x-w/2, ground-h, x+w/2, ground)
            for other in bounds:
                if rect[0] < other[2] and rect[2] > other[0] and rect[1] < other[3] and rect[3] > other[1]:
                    raise ValueError("Foreground overlap")
            bounds.append(rect)
    return True


def render_scene_svg(scene, width=1280, height=720):
    validate_plan([scene])
    if isinstance(width, bool) or isinstance(height, bool) or not isinstance(width, int) or not isinstance(height, int) or min(width, height) < 128:
        raise ValueError("Invalid canvas dimensions")
    kind = scene["environment"]
    light = scene["lighting"]
    ground = scene["ground_y"] * height
    root = ET.Element(f"{{{NS}}}svg", {"width": str(width), "height": str(height), "viewBox": f"0 0 {width} {height}"})
    sky = "#f6b68f" if light == "sunset" else "#b7dff6" if light == "sunrise" else "#8ad1f2"
    element(root, "rect", width=width, height=height, fill=sky)
    element(root, "circle", cx=width * (0.75 if light != "sunset" else 0.23), cy=height * 0.23,
            r=min(width, height)*0.07, fill="#ffe18a")
    if kind == "mountain_valley":
        for i, color in enumerate(("#829bb3", "#6e8da8", "#92a9ba")):
            x = (i - 0.25) * width * 0.40
            element(root, "polygon", points=f"{x:.1f},{ground:.1f} {x+width*.27:.1f},{height*.31:.1f} {x+width*.62:.1f},{ground:.1f}", fill=color)
        element(root, "path", d=f"M0 {ground:.1f} Q{width*.5:.1f} {ground-height*.11:.1f} {width} {ground:.1f} L{width} {height} H0 Z", fill="#70a46e")
    elif kind == "flower_garden":
        element(root, "path", d=f"M0 {ground:.1f} Q{width*.45:.1f} {ground-height*.04:.1f} {width} {ground:.1f} L{width} {height} H0 Z", fill="#79b66b")
    else:
        element(root, "rect", y=ground, width=width, height=height-ground, fill="#74a76e")
        # Shore is at ground level; water is BEHIND the shore and cannot swallow trunks.
        element(root, "path", d=f"M{width*.20:.1f} {height*.77:.1f} Q{width*.55:.1f} {height*.71:.1f} {width*.84:.1f} {height*.78:.1f} L{width*.96:.1f} {height} H{width*.05:.1f} Z", fill="#4b9fc2")
    for i, obj in enumerate(scene["objects"]):
        cx = obj["x"]*width
        w = obj["width"]*width
        h = obj["height"]*height
        y = ground
        if obj["kind"] == "tree":
            trunk_w = w*.19
            element(root, "rect", x=cx-trunk_w/2, y=y-h*.52, width=trunk_w, height=h*.52, fill="#70503a")
            element(root, "ellipse", cx=cx, cy=y-h*.65, rx=w*.5, ry=h*.36, fill="#318252")
        else:
            stem_w = max(3, width*.004)
            element(root, "rect", x=cx-stem_w/2, y=y-h*.68, width=stem_w, height=h*.68, fill="#267c40")
            for j in range(5):
                a = j*math.tau/5
                element(root, "circle", cx=cx+math.cos(a)*w*.26,
                        cy=y-h*.78+math.sin(a)*w*.26, r=w*.22,
                        fill=("#f17b9b", "#ffb84f", "#e9a0e6")[i % 3])
            element(root, "circle", cx=cx, cy=y-h*.78, r=w*.13, fill="#ffe27b")
    return ET.tostring(root, encoding="unicode")


def export_preview(plan, folder, width=1280, height=720):
    directory = Path(folder)
    directory.mkdir(parents=True, exist_ok=True)
    for scene in plan["scenes"]:
        (directory / f"{scene['id']}.svg").write_text(render_scene_svg(scene, width, height), encoding="utf-8")
    (directory / "scene_plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    return directory


def main():
    parser = argparse.ArgumentParser(description="MELODIA V3.1 independent scene preview")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--duration", type=float, default=30)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    args = parser.parse_args()
    plan = plan_scenes(args.prompt, args.duration)
    print(json.dumps({"version": VERSION, "scenes": len(plan["scenes"]), "output": str(export_preview(plan, args.output, args.width, args.height))}, indent=2))


if __name__ == "__main__":
    main()
