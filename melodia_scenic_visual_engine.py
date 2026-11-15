"""MELODIA AI V2.9 — deterministic, lightweight SVG scenic backgrounds.

Creates illustrated backgrounds (not photorealistic AI images) from plain-English
prompts. Standard-library only. This standalone module does not alter V1.x/V2.8.
Integration with the existing scene composer is a separate development step.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
from pathlib import Path
from xml.etree import ElementTree as ET

VERSION = "2.9"
SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)


def _element(parent, tag, **attributes):
    return ET.SubElement(parent, f"{{{SVG_NS}}}{tag}", {k.replace("_", "-"): str(v) for k, v in attributes.items()})


def _matches(prompt: str, *words: str) -> bool:
    return any(re.search(r"(?<!\w)" + re.escape(word) + r"(?!\w)", prompt) for word in words)


def analyze_scenery(prompt: str) -> dict:
    """Extract simple scenery requests; does not claim semantic AI understanding."""
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("Prompt must be a nonempty string")
    p = prompt.casefold()
    sunrise = _matches(p, "sunrise", "dawn", "morning")
    sunset = _matches(p, "sunset", "dusk", "evening")
    night = _matches(p, "night", "moonlight", "starry") and not (sunrise or sunset)
    water = _matches(p, "lake", "river", "pond", "waterfall", "ocean", "sea", "water")
    mountain = _matches(p, "mountain", "mountains", "hill", "hills", "valley")
    forest = _matches(p, "forest", "woods", "woodland", "trees", "tree")
    garden = _matches(p, "garden", "flowers", "flower", "meadow", "park")
    clouds = _matches(p, "cloud", "clouds", "cloudy")
    return {"sunrise": sunrise, "sunset": sunset, "night": night,
            "water": water, "mountains": mountain, "forest": forest,
            "garden": garden, "clouds": clouds}


def generate_scenic_svg(prompt: str, *, width: int = 1280, height: int = 720,
                        seed: int | None = None) -> str:
    """Return a self-contained SVG background. No external images or fonts needed.

    A supplied seed yields reproducible variation. Without one, the prompt is
    hashed deterministically. No text is drawn; captions remain a later stage.
    """
    if isinstance(width, bool) or isinstance(height, bool) or not isinstance(width, int) or not isinstance(height, int):
        raise ValueError("Canvas dimensions must be integers")
    if not (128 <= width <= 4096 and 128 <= height <= 4096):
        raise ValueError("Canvas dimensions must be between 128 and 4096")
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
        raise ValueError("Seed must be an integer or None")
    features = analyze_scenery(prompt)
    if seed is None:
        seed = int.from_bytes(hashlib.sha256(prompt.casefold().encode("utf-8")).digest()[:8], "big")
    rng = random.Random(seed)
    svg = ET.Element(f"{{{SVG_NS}}}svg", {"width": str(width), "height": str(height),
                                               "viewBox": f"0 0 {width} {height}"})
    defs = _element(svg, "defs")
    gradient = _element(defs, "linearGradient", id="sky", x1="0", y1="0", x2="0", y2="1")
    if features["night"]:
        sky = [("0%", "#09142f"), ("100%", "#44557a")]
    elif features["sunrise"] or features["sunset"]:
        sky = [("0%", "#527bb7"), ("58%", "#f4a57c"), ("100%", "#ffe1a0")]
    else:
        sky = [("0%", "#77b8ed"), ("100%", "#d5effc")]
    for offset, color in sky:
        _element(gradient, "stop", offset=offset, stop_color=color)
    _element(svg, "rect", width=width, height=height, fill="url(#sky)")

    horizon = height * (0.63 if features["water"] else 0.70)
    if features["night"]:
        for _ in range(38):
            x, y = rng.uniform(0, width), rng.uniform(0, horizon * 0.76)
            _element(svg, "circle", cx=f"{x:.1f}", cy=f"{y:.1f}", r=rng.choice([1, 1.5, 2]), fill="#f9f4dd")
    else:
        sun_x = width * (0.77 if not features["sunset"] else 0.22)
        sun_y = horizon * (0.62 if features["sunrise"] or features["sunset"] else 0.32)
        _element(svg, "circle", cx=f"{sun_x:.1f}", cy=f"{sun_y:.1f}", r=f"{min(width, height)*0.067:.1f}", fill="#ffda72")

    if features["clouds"] or not features["night"]:
        for i in range(3 if features["clouds"] else 2):
            x = width * (0.12 + 0.31 * i) + rng.uniform(-35, 35)
            y = height * (0.14 + 0.06 * (i % 2))
            for dx, dy, radius in [(-30, 7, 26), (0, -8, 35), (34, 6, 25)]:
                _element(svg, "ellipse", cx=f"{x+dx:.1f}", cy=f"{y+dy:.1f}",
                         rx=radius * width / 1280, ry=radius * height / 720 * 0.66,
                         fill="#f6f7f4", opacity="0.8")

    if features["mountains"]:
        for i in range(5):
            left = width * (i - 0.55) / 3.8
            peak = left + width * 0.24
            right = left + width * 0.55
            peak_y = horizon - height * (0.18 + 0.12 * rng.random())
            _element(svg, "polygon", points=f"{left:.1f},{horizon:.1f} {peak:.1f},{peak_y:.1f} {right:.1f},{horizon:.1f}",
                     fill=["#809bb0", "#6989a0", "#93a7b5"][i % 3])
            _element(svg, "polygon", points=f"{peak-width*.055:.1f},{peak_y+height*.07:.1f} {peak:.1f},{peak_y:.1f} {peak+width*.06:.1f},{peak_y+height*.07:.1f}", fill="#e9f0f2")

    _element(svg, "rect", x="0", y=f"{horizon:.1f}", width=width,
             height=f"{height-horizon:.1f}", fill="#75a76a")
    if features["water"]:
        water_y = height * 0.72
        _element(svg, "path", d=f"M 0 {water_y:.1f} Q {width*.45:.1f} {water_y-height*.055:.1f} {width:.1f} {water_y:.1f} L {width} {height} L 0 {height} Z", fill="#4d9ebc")
        for i in range(12):
            x = width * (0.06 + 0.077 * i)
            y = height * (0.79 + 0.17 * rng.random())
            _element(svg, "line", x1=f"{x:.1f}", y1=f"{y:.1f}", x2=f"{x+width*.038:.1f}", y2=f"{y:.1f}",
                     stroke="#b6dce2", stroke_width=max(1, width / 850), opacity="0.65")

    if features["forest"] or features["garden"]:
        count = 7 if features["forest"] else 4
        for i in range(count):
            x = width * (0.06 + (i + 0.3) / (count + 0.5) * 0.88)
            ground_y = horizon + height * (0.03 + 0.025 * rng.random())
            tree_h = height * (0.13 + 0.08 * rng.random())
            _element(svg, "rect", x=f"{x-width*.006:.1f}", y=f"{ground_y-tree_h*.52:.1f}",
                     width=f"{width*.012:.1f}", height=f"{tree_h*.52:.1f}", fill="#735139")
            _element(svg, "ellipse", cx=f"{x:.1f}", cy=f"{ground_y-tree_h*.66:.1f}",
                     rx=f"{width*.038:.1f}", ry=f"{tree_h*.43:.1f}", fill=rng.choice(["#26784a", "#398958", "#4a9b59"]))

    if features["garden"]:
        for i in range(22):
            x = width * rng.uniform(0.03, 0.97)
            y = height * rng.uniform(0.70, 0.95)
            if features["water"] and y > height * 0.73:
                continue
            r = max(3, min(width, height) * rng.uniform(0.006, 0.012))
            _element(svg, "line", x1=f"{x:.1f}", y1=f"{y:.1f}", x2=f"{x:.1f}", y2=f"{y+r*3:.1f}", stroke="#287344", stroke_width=max(2, width/500))
            for angle in range(0, 360, 72):
                a = math.radians(angle)
                _element(svg, "circle", cx=f"{x+math.cos(a)*r:.1f}", cy=f"{y+math.sin(a)*r:.1f}", r=f"{r*.75:.1f}",
                         fill=rng.choice(["#ed8bb4", "#f7d06a", "#f7b1a6", "#d7b2f2"]))
            _element(svg, "circle", cx=f"{x:.1f}", cy=f"{y:.1f}", r=f"{r*.5:.1f}", fill="#f7e37c")
    return ET.tostring(svg, encoding="unicode")


def save_scenic_svg(prompt: str, output: str | Path, *, width: int = 1280,
                    height: int = 720, seed: int | None = None) -> Path:
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(generate_scenic_svg(prompt, width=width, height=height, seed=seed), encoding="utf-8")
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="MELODIA AI V2.9 illustrated scenic SVG engine")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()
    path = save_scenic_svg(args.prompt, args.output, width=args.width, height=args.height, seed=args.seed)
    print(json.dumps({"version": VERSION, "output": str(path), "features": analyze_scenery(args.prompt)}, indent=2))


if __name__ == "__main__":
    main()
