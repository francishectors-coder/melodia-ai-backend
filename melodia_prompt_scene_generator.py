
"""MELODIA AI - Prompt-to-Scene Generator V1.6.

Converts simple English prompts into SVG scenes using
the automatically learned V1.5 geometric object models.

Supports:
- Known object recognition using word matching
- Multiple objects in one scene
- Simple spatial relationships
- Reproducible geometric variation
- Automatic canvas fitting
- JSON and SVG outputs

Standard library only.
Does not modify existing MELODIA modules.

Limitations:
This is a rule-based prompt parser, not a trained
natural-language or text-to-image model.
"""

import argparse
import json
import math
import random
import re
from pathlib import Path
import xml.etree.ElementTree as ET

from melodia_geometric_object_learner import EXAMPLES
from melodia_automatic_structure_learner import learn_all
from melodia_component_relationship_learner import (
    reconstruct,
    component_bounds,
)


VERSION = "1.6"

CANVAS_WIDTH = 1024
CANVAS_HEIGHT = 576
PADDING = 24

OBJECT_ALIASES = {
    "tree": {"tree", "trees"},
    "house": {"house", "houses", "home", "homes"},
    "vehicle": {
        "vehicle", "vehicles",
        "car", "cars",
        "truck", "trucks",
    },
    "animal": {
        "animal", "animals",
    },
    "flower": {
        "flower", "flowers",
    },
}

SPATIAL_WORDS = {
    "left": {"left"},
    "right": {"right"},
    "center": {"center", "middle"},
    "top": {"top", "above"},
    "bottom": {"bottom", "below"},
}


def tokenize(prompt):
    return re.findall(
        r"[a-z]+",
        prompt.lower(),
    )


def detect_objects(prompt, known_categories):
    """Recognize supported objects from prompt words."""

    tokens = tokenize(prompt)
    detected = []

    for token in tokens:
        for category in sorted(known_categories):
            aliases = OBJECT_ALIASES.get(
                category,
                {category, category + "s"},
            )

            if token in aliases:
                detected.append(category)
                break

    return detected


def detect_position(prompt):
    """Detect a simple global placement instruction."""

    tokens = set(tokenize(prompt))

    for position in (
        "left",
        "right",
        "top",
        "bottom",
        "center",
    ):
        if tokens & SPATIAL_WORDS[position]:
            return position

    return "center"


def scene_centers(count, position):
    """Generate evenly spaced object centers."""

    if count <= 0:
        return []

    if count == 1:
        locations = [(0.5, 0.5)]
    else:
        locations = [
            (
                0.15 + 0.7 * index / (count - 1),
                0.5,
            )
            for index in range(count)
        ]

    dx = {
        "left": -0.1,
        "right": 0.1,
        "center": 0.0,
        "top": 0.0,
        "bottom": 0.0,
    }[position]

    dy = {
        "left": 0.0,
        "right": 0.0,
        "center": 0.0,
        "top": -0.12,
        "bottom": 0.12,
    }[position]

    return [
        (x + dx, y + dy)
        for x, y in locations
    ]


def calculate_object_bounds(components):
    """Calculate normalized bounds, accounting for circles."""

    bounds = [
        component_bounds(
            part,
            CANVAS_WIDTH,
            CANVAS_HEIGHT,
        )
        for part in components
    ]

    left = min(b[0] for b in bounds)
    top = min(b[1] for b in bounds)
    right = max(b[2] for b in bounds)
    bottom = max(b[3] for b in bounds)

    return (
        left / CANVAS_WIDTH,
        top / CANVAS_HEIGHT,
        right / CANVAS_WIDTH,
        bottom / CANVAS_HEIGHT,
    )


def place_object(components, center, size):
    """Move and uniformly resize an object in pixel space."""

    left, top, right, bottom = (
        calculate_object_bounds(components)
    )

    original_width = (
        right - left
    ) * CANVAS_WIDTH

    original_height = (
        bottom - top
    ) * CANVAS_HEIGHT

    if original_width <= 0 or original_height <= 0:
        raise ValueError(
            "Invalid object bounds"
        )

    target_width = (
        size * CANVAS_WIDTH
    )

    target_height = (
        size * CANVAS_HEIGHT
    )

    factor = min(
        target_width / original_width,
        target_height / original_height,
    )

    old_center_x = (
        left + right
    ) * CANVAS_WIDTH / 2

    old_center_y = (
        top + bottom
    ) * CANVAS_HEIGHT / 2

    new_center_x = (
        center[0] * CANVAS_WIDTH
    )

    new_center_y = (
        center[1] * CANVAS_HEIGHT
    )

    placed = []

    for part in components:
        item = dict(part)

        px = part["x"] * CANVAS_WIDTH
        py = part["y"] * CANVAS_HEIGHT

        new_x = (
            new_center_x
            + factor * (px - old_center_x)
        )

        new_y = (
            new_center_y
            + factor * (py - old_center_y)
        )

        item["x"] = round(
            new_x / CANVAS_WIDTH,
            6,
        )

        item["y"] = round(
            new_y / CANVAS_HEIGHT,
            6,
        )

        item["width"] = round(
            part["width"] * factor,
            6,
        )

        item["height"] = round(
            part["height"] * factor,
            6,
        )

        placed.append(item)

    return placed


def build_scene(
    prompt,
    learned,
    seed=1337,
    variation=0.5,
):
    """Construct a scene from recognized object categories."""

    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError(
            "Prompt must not be empty"
        )

    if (
        not math.isfinite(variation)
        or not 0 <= variation <= 1
    ):
        raise ValueError(
            "Variation must be between 0 and 1"
        )

    detected = detect_objects(
        prompt,
        learned.keys(),
    )

    if not detected:
        return {
            "status": "unsupported",
            "prompt": prompt,
            "reason": (
                "No recognized object categories "
                "in prompt"
            ),
            "supported_categories": sorted(
                learned.keys()
            ),
        }

    position = detect_position(prompt)

    centers = scene_centers(
        len(detected),
        position,
    )

    rng = random.Random(seed)

    objects = []

    for index, (category, center) in enumerate(
        zip(detected, centers)
    ):
        object_seed = rng.randrange(
            0, 2**31
        )

        representation = reconstruct(
            category,
            learned,
            scale=1.0,
            variation=variation,
            seed=object_seed,
        )

        if representation["status"] != "generated":
            raise ValueError(
                f"Failed to construct {category}"
            )

        object_size = min(
            0.55,
            0.8 / len(detected),
        )

        components = place_object(
            representation["components"],
            center,
            object_size,
        )

        objects.append({
            "id": f"object_{index + 1}",
            "category": category,
            "center": {
                "x": center[0],
                "y": center[1],
            },
            "seed": object_seed,
            "components": components,
        })

    return {
        "project": "MELODIA AI",
        "version": VERSION,
        "status": "generated",
        "prompt": prompt,
        "seed": seed,
        "variation": variation,
        "position": position,
        "canvas": {
            "width": CANVAS_WIDTH,
            "height": CANVAS_HEIGHT,
        },
        "objects": objects,
    }


def render_scene_svg(scene):
    """Render multiple geometric objects into one fitted SVG."""

    svg = ET.Element(
        "svg",
        xmlns="http://www.w3.org/2000/svg",
        width=str(CANVAS_WIDTH),
        height=str(CANVAS_HEIGHT),
        viewBox=(
            f"0 0 {CANVAS_WIDTH} {CANVAS_HEIGHT}"
        ),
    )

    ET.SubElement(
        svg,
        "rect",
        width=str(CANVAS_WIDTH),
        height=str(CANVAS_HEIGHT),
        fill="#eaf4ff",
    )

    all_components = []

    for obj in scene["objects"]:
        for component in obj["components"]:
            all_components.append(component)

    from melodia_component_relationship_learner import (
        calculate_canvas_fit,
    )

    factor, tx, ty = calculate_canvas_fit(
        all_components,
        CANVAS_WIDTH,
        CANVAS_HEIGHT,
        padding=PADDING,
    )

    group = ET.SubElement(
        svg,
        "g",
        transform=(
            f"translate({tx:.6f} {ty:.6f}) "
            f"scale({factor:.6f})"
        ),
    )

    for obj in scene["objects"]:
        object_group = ET.SubElement(
            group,
            "g",
            id=obj["id"],
        )

        for part in obj["components"]:
            cx = part["x"] * CANVAS_WIDTH
            cy = part["y"] * CANVAS_HEIGHT

            w = part["width"] * CANVAS_WIDTH
            h = part["height"] * CANVAS_HEIGHT

            color = part["color"]
            shape = part["shape"]

            if shape == "circle":
                ET.SubElement(
                    object_group,
                    "circle",
                    cx=f"{cx:.6f}",
                    cy=f"{cy:.6f}",
                    r=f"{h / 2:.6f}",
                    fill=color,
                )

            elif shape == "ellipse":
                ET.SubElement(
                    object_group,
                    "ellipse",
                    cx=f"{cx:.6f}",
                    cy=f"{cy:.6f}",
                    rx=f"{w / 2:.6f}",
                    ry=f"{h / 2:.6f}",
                    fill=color,
                )

            elif shape == "rectangle":
                ET.SubElement(
                    object_group,
                    "rect",
                    x=f"{cx - w / 2:.6f}",
                    y=f"{cy - h / 2:.6f}",
                    width=f"{w:.6f}",
                    height=f"{h:.6f}",
                    fill=color,
                )

            elif shape == "triangle":
                points = [
                    (cx, cy - h / 2),
                    (cx - w / 2, cy + h / 2),
                    (cx + w / 2, cy + h / 2),
                ]

                ET.SubElement(
                    object_group,
                    "polygon",
                    points=" ".join(
                        f"{x:.6f},{y:.6f}"
                        for x, y in points
                    ),
                    fill=color,
                )

            elif shape == "polygon":
                points = [
                    (cx - w / 2, cy),
                    (cx - w / 4, cy - h / 2),
                    (cx + w / 4, cy - h / 2),
                    (cx + w / 2, cy),
                    (cx + w / 2, cy),
                    (cx + w / 4, cy + h / 2),
                    (cx - w / 4, cy + h / 2),
                ]

                ET.SubElement(
                    object_group,
                    "polygon",
                    points=" ".join(
                        f"{x:.6f},{y:.6f}"
                        for x, y in points
                    ),
                    fill=color,
                )

            else:
                raise ValueError(
                    f"Unsupported shape: {shape}"
                )

    return ET.tostring(
        svg,
        encoding="unicode",
    )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--prompt",
        default=(
            "A tree beside a house "
            "with flowers"
        ),
    )

    parser.add_argument(
        "--output",
        default="melodia_prompt_scene_output",
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

    scene = build_scene(
        args.prompt,
        learned,
        seed=args.seed,
        variation=args.variation,
    )

    scene_path = (
        output / "scene_representation.json"
    )

    scene_path.write_text(
        json.dumps(
            scene,
            indent=2,
        ),
        encoding="utf-8",
    )

    if scene["status"] == "generated":
        svg = render_scene_svg(scene)

        (
            output / "scene_preview.svg"
        ).write_text(
            svg,
            encoding="utf-8",
        )

    print(
        "MELODIA PROMPT-TO-SCENE GENERATOR V1.6"
    )
    print("Prompt:", args.prompt)
    print("Status:", scene["status"])

    if scene["status"] == "generated":
        print(
            "Objects:",
            len(scene["objects"]),
        )

    print("Output:", output)


if __name__ == "__main__":
    main()
