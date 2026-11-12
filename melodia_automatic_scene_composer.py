
"""MELODIA AI - Automatic Scene Composer V1.8.

Creates composed SVG scenes from the V1.7 spatial engine.

Features:
- Natural-language object selection through V1.7
- Automatic sky and ground backgrounds
- Ground alignment for supported objects
- Preservation of left/right and above/below relationships
- Automatic scene fitting
- Reproducible SVG and JSON exports
- Optional landscape, sunset and night themes

Standard library only.

Existing MELODIA engines remain unchanged.

Limitations:
- Geometric illustrations, not photorealistic images
- Rule-based English prompt interpretation
- Five previously learned object categories
- Basic layout and environmental styling
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
from melodia_spatial_relationship_engine import (
    generate_spatial_scene,
)
from melodia_prompt_scene_generator import (
    CANVAS_WIDTH,
    CANVAS_HEIGHT,
    render_scene_svg,
)

VERSION = "1.8"

GROUND_Y = 0.82

THEMES = {
    "day": {
        "sky": "#BFE7FF",
        "ground": "#85C76D",
        "sun": "#FFD65A",
    },
    "sunset": {
        "sky": "#F6A46B",
        "ground": "#658B58",
        "sun": "#FFDB83",
    },
    "night": {
        "sky": "#14294F",
        "ground": "#294D42",
        "sun": "#F3F1D2",
    },
}

GROUND_CATEGORIES = {
    "tree",
    "house",
    "vehicle",
    "animal",
    "flower",
}

VERTICAL_RELATIONS = {
    "above",
    "below",
}


def detect_theme(prompt):
    """Select a background theme from prompt words."""

    tokens = set(
        re.findall(
            r"[a-z]+",
            prompt.lower(),
        )
    )

    if tokens & {
        "night",
        "moonlight",
        "midnight",
    }:
        return "night"

    if tokens & {
        "sunset",
        "evening",
        "dusk",
    }:
        return "sunset"

    return "day"


def object_bounds(obj):
    """Calculate object bounds in normalized coordinates."""

    components = obj["components"]

    if not components:
        raise ValueError(
            "Object has no components"
        )

    bounds = []

    for part in components:
        x = part["x"]
        y = part["y"]
        width = part["width"]
        height = part["height"]

        if not all(
            math.isfinite(value)
            for value in (
                x, y, width, height
            )
        ):
            raise ValueError(
                "Non-finite component geometry"
            )

        if width <= 0 or height <= 0:
            raise ValueError(
                "Invalid component dimensions"
            )

        bounds.append((
            x - width / 2,
            y - height / 2,
            x + width / 2,
            y + height / 2,
        ))

    return (
        min(b[0] for b in bounds),
        min(b[1] for b in bounds),
        max(b[2] for b in bounds),
        max(b[3] for b in bounds),
    )


def shift_object(obj, dx, dy):
    """Translate an object without changing its geometry."""

    shifted = copy.deepcopy(obj)

    for part in shifted["components"]:
        part["x"] = round(
            part["x"] + dx,
            6,
        )

        part["y"] = round(
            part["y"] + dy,
            6,
        )

    shifted["center"]["x"] = round(
        shifted["center"]["x"] + dx,
        6,
    )

    shifted["center"]["y"] = round(
        shifted["center"]["y"] + dy,
        6,
    )

    return shifted


def vertical_object_ids(scene):
    """Find objects involved in explicit vertical relations."""

    ids = set()

    for relation in scene["relationships"]:
        if relation["relation"] in VERTICAL_RELATIONS:
            ids.add(relation["subject"])
            ids.add(relation["target"])

    return ids


def align_objects_to_ground(scene):
    """Align ordinary objects to the ground line.

    Objects involved in explicit above/below relations
    retain their relative vertical positioning.
    """

    result = copy.deepcopy(scene)

    protected = vertical_object_ids(result)

    aligned = []

    for obj in result["objects"]:
        if (
            obj["category"] not in GROUND_CATEGORIES
            or obj["id"] in protected
        ):
            aligned.append(obj)
            continue

        bounds = object_bounds(obj)

        bottom = bounds[3]

        dy = GROUND_Y - bottom

        aligned.append(
            shift_object(
                obj,
                0.0,
                dy,
            )
        )

    result["objects"] = aligned

    return result


def fit_composition(scene):
    """Fit the composed objects inside the visible canvas."""

    result = copy.deepcopy(scene)

    if not result["objects"]:
        return result

    bounds = [
        object_bounds(obj)
        for obj in result["objects"]
    ]

    left = min(b[0] for b in bounds)
    top = min(b[1] for b in bounds)
    right = max(b[2] for b in bounds)
    bottom = max(b[3] for b in bounds)

    margin = 0.045

    available_width = 1 - 2 * margin
    available_height = 1 - 2 * margin

    width = right - left
    height = bottom - top

    if width <= 0 or height <= 0:
        raise ValueError(
            "Invalid scene bounds"
        )

    factor = min(
        1.0,
        available_width / width,
        available_height / height,
    )

    center_x = (left + right) / 2
    center_y = (top + bottom) / 2

    target_x = 0.5
    target_y = 0.5

    transformed = []

    for obj in result["objects"]:
        updated = copy.deepcopy(obj)

        for part in updated["components"]:
            part["x"] = round(
                target_x
                + (part["x"] - center_x) * factor,
                6,
            )

            part["y"] = round(
                target_y
                + (part["y"] - center_y) * factor,
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

        updated["center"]["x"] = round(
            target_x
            + (
                obj["center"]["x"]
                - center_x
            ) * factor,
            6,
        )

        updated["center"]["y"] = round(
            target_y
            + (
                obj["center"]["y"]
                - center_y
            ) * factor,
            6,
        )

        transformed.append(updated)

    result["objects"] = transformed

    return result


def compose_scene(
    prompt,
    learned,
    seed=1337,
    variation=0.5,
):
    """Build and visually compose a V1.7 scene."""

    base = generate_spatial_scene(
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

    theme = detect_theme(prompt)

    composed = align_objects_to_ground(
        base
    )

    composed = fit_composition(
        composed
    )

    composed["version"] = VERSION
    composed["base_version"] = "1.7"
    composed["theme"] = theme
    composed["environment"] = {
        "sky_color": THEMES[theme]["sky"],
        "ground_color": THEMES[theme]["ground"],
        "ground_y": GROUND_Y,
    }

    return composed


def render_composed_svg(scene):
    """Render environment and geometric objects."""

    if scene["status"] != "generated":
        raise ValueError(
            "Cannot render unsupported scene"
        )

    theme = THEMES[scene["theme"]]

    root = ET.Element(
        "svg",
        xmlns="http://www.w3.org/2000/svg",
        width=str(CANVAS_WIDTH),
        height=str(CANVAS_HEIGHT),
        viewBox=(
            f"0 0 {CANVAS_WIDTH} {CANVAS_HEIGHT}"
        ),
    )

    ET.SubElement(
        root,
        "rect",
        width=str(CANVAS_WIDTH),
        height=str(CANVAS_HEIGHT),
        fill=theme["sky"],
    )

    if scene["theme"] == "night":
        ET.SubElement(
            root,
            "circle",
            cx="875",
            cy="105",
            r="38",
            fill=theme["sun"],
        )

    else:
        ET.SubElement(
            root,
            "circle",
            cx="875",
            cy="105",
            r="48",
            fill=theme["sun"],
        )

    ground_pixel = (
        GROUND_Y * CANVAS_HEIGHT
    )

    ET.SubElement(
        root,
        "rect",
        x="0",
        y=f"{ground_pixel:.6f}",
        width=str(CANVAS_WIDTH),
        height=f"{CANVAS_HEIGHT - ground_pixel:.6f}",
        fill=theme["ground"],
    )

    # Reuse the validated V1.6 SVG renderer for objects.
    object_svg = ET.fromstring(
        render_scene_svg(scene)
    )

    ns = "{http://www.w3.org/2000/svg}"

    for child in object_svg:
        if child.tag == ns + "g":
            root.append(child)

    return ET.tostring(
        root,
        encoding="unicode",
    )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--prompt",
        default=(
            "A tree to the left of a house "
            "and a flower to the right of the house "
            "at sunset"
        ),
    )

    parser.add_argument(
        "--output",
        default="melodia_composed_scene_output",
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

    scene = compose_scene(
        args.prompt,
        learned,
        seed=args.seed,
        variation=args.variation,
    )

    (
        output / "composed_scene.json"
    ).write_text(
        json.dumps(
            scene,
            indent=2,
        ),
        encoding="utf-8",
    )

    if scene["status"] == "generated":
        svg = render_composed_svg(
            scene
        )

        (
            output / "composed_scene.svg"
        ).write_text(
            svg,
            encoding="utf-8",
        )

    print(
        "MELODIA AUTOMATIC SCENE COMPOSER V1.8"
    )

    print("Prompt:", args.prompt)
    print("Status:", scene["status"])

    if scene["status"] == "generated":
        print(
            "Objects:",
            len(scene["objects"]),
        )

        print(
            "Theme:",
            scene["theme"],
        )

    print("Output:", output)


if __name__ == "__main__":
    main()
