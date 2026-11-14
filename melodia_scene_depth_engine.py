
"""MELODIA AI - Scene Depth and Layering Engine V1.9.

Adds three depth layers to V1.8 geometric scenes:
- Background
- Middle ground
- Foreground

Features:
- Explicit depth instructions from prompts
- Automatic default depth assignment
- Perspective scaling
- Depth-aware ground placement
- Back-to-front SVG rendering
- Deterministic JSON and SVG exports

Existing V1.3-V1.8 engines remain unchanged.

Limitations:
- Geometric illustration only
- Rule-based English depth interpretation
- Five learned object categories
- Basic perspective rather than 3D geometry
"""

import argparse
import copy
import json
import math
import re
from pathlib import Path
import xml.etree.ElementTree as ET

from melodia_geometric_object_learner import EXAMPLES
from melodia_automatic_structure_learner import learn_all
from melodia_automatic_scene_composer import (
    compose_scene,
    render_composed_svg,
    object_bounds,
    GROUND_Y,
    THEMES,
)
from melodia_prompt_scene_generator import (
    CANVAS_WIDTH,
    CANVAS_HEIGHT,
    render_scene_svg,
)

VERSION = "1.9"

DEPTH_LAYERS = {
    "background": {
        "order": 0,
        "scale": 0.65,
        "ground_y": 0.68,
    },
    "middle": {
        "order": 1,
        "scale": 0.85,
        "ground_y": 0.76,
    },
    "foreground": {
        "order": 2,
        "scale": 1.0,
        "ground_y": GROUND_Y,
    },
}

DEFAULT_DEPTH = {
    "tree": "middle",
    "house": "middle",
    "vehicle": "foreground",
    "animal": "foreground",
    "flower": "foreground",
}

DEPTH_PHRASES = {
    "background": (
        "in the background",
        "far away",
        "in the distance",
        "distant",
        "far behind",
    ),
    "middle": (
        "in the middle ground",
        "in the middleground",
        "in the midground",
    ),
    "foreground": (
        "in the foreground",
        "in front",
        "close to the viewer",
        "near the viewer",
    ),
}

CATEGORY_ALIASES = {
    "tree": ("tree", "trees"),
    "house": ("house", "houses", "home", "homes"),
    "vehicle": (
        "vehicle", "vehicles",
        "car", "cars",
        "truck", "trucks",
    ),
    "animal": (
        "animal", "animals",
        "dog", "dogs",
        "cat", "cats",
    ),
    "flower": ("flower", "flowers"),
}


def detect_depth_assignments(prompt, objects):
    """Assign depth layers using explicit phrases or defaults.

    Explicit depth phrases are associated with the nearest
    preceding recognized object mention in the same clause.

    If no suitable preceding mention exists, the nearest
    following mention is used.

    Repeated objects with identical categories remain a
    limitation of this rule-based interpreter.
    """

    lower = prompt.lower()

    mentions = []

    for category, aliases in CATEGORY_ALIASES.items():
        for alias in aliases:
            pattern = (
                r"\b" + re.escape(alias) + r"\b"
            )

            for match in re.finditer(pattern, lower):
                mentions.append({
                    "category": category,
                    "start": match.start(),
                    "end": match.end(),
                })

    mentions.sort(key=lambda item: item["start"])

    assignments = {
        obj["id"]: DEFAULT_DEPTH.get(
            obj["category"], "middle"
        )
        for obj in objects
    }

    # Associate each distinct recognized mention with an
    # object in scene order, without reusing assigned IDs.
    available = list(objects)
    matched_mentions = []

    for mention in mentions:
        for index, obj in enumerate(available):
            if obj["category"] == mention["category"]:
                matched_mentions.append({
                    **mention,
                    "object_id": obj["id"],
                })
                available.pop(index)
                break

    depth_matches = []

    for depth, phrases in DEPTH_PHRASES.items():
        for phrase in phrases:
            pattern = (
                r"\b" + re.escape(phrase) + r"\b"
            )

            for match in re.finditer(pattern, lower):
                depth_matches.append({
                    "depth": depth,
                    "start": match.start(),
                    "end": match.end(),
                })

    depth_matches.sort(key=lambda item: item["start"])

    for depth_match in depth_matches:
        preceding = [
            mention
            for mention in matched_mentions
            if mention["end"] <= depth_match["start"]
        ]

        following = [
            mention
            for mention in matched_mentions
            if mention["start"] >= depth_match["end"]
        ]

        if preceding:
            selected = min(
                preceding,
                key=lambda item:
                    depth_match["start"] - item["end"],
            )
        elif following:
            selected = min(
                following,
                key=lambda item:
                    item["start"] - depth_match["end"],
            )
        else:
            continue

        assignments[selected["object_id"]] = (
            depth_match["depth"]
        )

    return assignments


def transform_object_depth(obj, depth):
    """Scale an object and move its bottom to the depth plane."""

    if depth not in DEPTH_LAYERS:
        raise ValueError(
            f"Unsupported depth layer: {depth}"
        )

    result = copy.deepcopy(obj)

    settings = DEPTH_LAYERS[depth]

    factor = settings["scale"]
    target_ground = settings["ground_y"]

    bounds = object_bounds(obj)

    anchor_x = (
        bounds[0] + bounds[2]
    ) / 2

    anchor_y = bounds[3]

    for part in result["components"]:
        part["x"] = round(
            anchor_x
            + (part["x"] - anchor_x) * factor,
            6,
        )

        part["y"] = round(
            target_ground
            + (part["y"] - anchor_y) * factor,
            6,
        )

        part["width"] = round(
            part["width"] * factor,
            6,
        )

        part["height"] = round(
            part["height"] * factor,
            6,
        )

    result["center"]["x"] = round(
        anchor_x
        + (
            obj["center"]["x"] - anchor_x
        ) * factor,
        6,
    )

    result["center"]["y"] = round(
        target_ground
        + (
            obj["center"]["y"] - anchor_y
        ) * factor,
        6,
    )

    result["depth"] = depth
    result["depth_order"] = settings["order"]
    result["depth_scale"] = factor
    result["depth_ground_y"] = target_ground

    return result


def validate_depth_geometry(scene):
    """Ensure transformed objects remain inside the canvas."""

    for obj in scene["objects"]:
        left, top, right, bottom = object_bounds(obj)

        values = (left, top, right, bottom)

        if not all(math.isfinite(v) for v in values):
            raise ValueError(
                "Non-finite depth geometry"
            )

        if (
            left < -0.00001
            or top < -0.00001
            or right > 1.00001
            or bottom > 1.00001
        ):
            raise ValueError(
                f"Depth object outside canvas: {obj['id']}"
            )


def generate_depth_scene(
    prompt,
    learned,
    seed=1337,
    variation=0.5,
):
    """Generate a V1.9 depth-aware scene."""

    base = compose_scene(
        prompt,
        learned,
        seed=seed,
        variation=variation,
    )

    if base["status"] != "generated":
        return {
            **base,
            "version": VERSION,
        }

    assignments = detect_depth_assignments(
        prompt,
        base["objects"],
    )

    result = copy.deepcopy(base)

    transformed = []

    for obj in result["objects"]:
        depth = assignments[obj["id"]]

        transformed.append(
            transform_object_depth(
                obj,
                depth,
            )
        )

    transformed.sort(
        key=lambda obj: (
            obj["depth_order"],
            obj["id"],
        )
    )

    result["objects"] = transformed
    result["version"] = VERSION
    result["base_version"] = "1.8"

    result["depth_layers"] = copy.deepcopy(
        DEPTH_LAYERS
    )

    validate_depth_geometry(result)

    return result


def render_depth_svg(scene):
    """Render all depth-sorted objects in one shared SVG coordinate system.

    Rendering objects separately invokes V1.6 canvas fitting for each object,
    which recenters each one and causes apparent overlap. The V1.8 renderer
    handles the complete scene in one pass and retains the depth-sorted order.
    """
    if scene["status"] != "generated":
        raise ValueError("Cannot render unsupported scene")

    return render_composed_svg(scene)


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--prompt",
        default=(
            "A tree in the background, "
            "a house in the middle ground, "
            "and a flower in the foreground "
            "at sunset"
        ),
    )

    parser.add_argument(
        "--output",
        default="melodia_depth_scene_output",
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=1337,
    )

    parser.add_argument(
        "--variation",
        type=float,
        default=0.5,
    )

    args = parser.parse_args()

    output = Path(args.output)

    output.mkdir(
        parents=True,
        exist_ok=True,
    )

    learned = learn_all(EXAMPLES)

    scene = generate_depth_scene(
        args.prompt,
        learned,
        seed=args.seed,
        variation=args.variation,
    )

    (
        output / "depth_scene.json"
    ).write_text(
        json.dumps(scene, indent=2),
        encoding="utf-8",
    )

    if scene["status"] == "generated":
        svg = render_depth_svg(scene)

        (
            output / "depth_scene.svg"
        ).write_text(
            svg,
            encoding="utf-8",
        )

    print(
        "MELODIA SCENE DEPTH ENGINE V1.9"
    )

    print("Prompt:", args.prompt)
    print("Status:", scene["status"])

    if scene["status"] == "generated":
        print(
            "Objects:",
            len(scene["objects"]),
        )

        for obj in scene["objects"]:
            print(
                obj["category"],
                "->",
                obj["depth"],
            )

    print("Output:", output)


if __name__ == "__main__":
    main()
