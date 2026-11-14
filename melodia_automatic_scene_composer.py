
"""MELODIA AI - Automatic Scene Composer V1.8.

Automatic geometric scene composition with:
- Day, sunset and night backgrounds
- Ground alignment
- Spatial relationship preservation
- Canvas fitting
- Deterministic SVG and JSON output

Ground alignment correction:
Final composition fitting preserves the ground position
instead of vertically centering ground-based objects.

Existing MELODIA engines remain unchanged.
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

MARGIN = 0.045

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
    """Detect a supported environmental theme."""

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
    """Return normalized bounds of an object."""

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
                x,
                y,
                width,
                height,
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
    """Translate an object without modifying its source."""

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
    """Find objects protected by vertical relationships."""

    ids = set()

    for relation in scene["relationships"]:
        if relation["relation"] in VERTICAL_RELATIONS:
            ids.add(relation["subject"])
            ids.add(relation["target"])

    return ids


def align_objects_to_ground(scene):
    """Ground-align objects without breaking vertical relations."""

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

        bottom = object_bounds(obj)[3]

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
    """Fit objects while preserving ground alignment.

    Ground-based objects remain on GROUND_Y.

    Objects involved in explicit vertical relationships
    are transformed together so their relative ordering
    is preserved.

    When a scene contains ground-based objects, the
    composition is anchored to the ground rather than
    vertically centered.
    """

    result = copy.deepcopy(scene)

    objects = result["objects"]

    if not objects:
        return result

    bounds = [
        object_bounds(obj)
        for obj in objects
    ]

    left = min(b[0] for b in bounds)
    top = min(b[1] for b in bounds)
    right = max(b[2] for b in bounds)
    bottom = max(b[3] for b in bounds)

    width = right - left
    height = bottom - top

    if width <= 0 or height <= 0:
        raise ValueError(
            "Invalid scene bounds"
        )

    protected = vertical_object_ids(result)

    grounded = [
        obj
        for obj in objects
        if (
            obj["category"] in GROUND_CATEGORIES
            and obj["id"] not in protected
        )
    ]

    available_width = 1.0 - 2.0 * MARGIN

    # Preserve the existing ground line.
    # Grounded objects must fit between the top margin
    # and the ground, with any protected objects also
    # remaining inside the visible canvas.

    scale_x = available_width / width

    if grounded:
        ground_bottoms = [
            object_bounds(obj)[3]
            for obj in grounded
        ]

        ground_reference = max(
            ground_bottoms
        )

        space_above = ground_reference - top
        space_below = bottom - ground_reference

        scale_y = 1.0

        if space_above > 0:
            scale_y = min(
                scale_y,
                (GROUND_Y - MARGIN)
                / space_above,
            )

        if space_below > 0:
            scale_y = min(
                scale_y,
                (1.0 - MARGIN - GROUND_Y)
                / space_below,
            )

        scale = min(
            1.0,
            scale_x,
            scale_y,
        )

        anchor_y = ground_reference
        target_y = GROUND_Y

    else:
        available_height = (
            1.0 - 2.0 * MARGIN
        )

        scale = min(
            1.0,
            scale_x,
            available_height / height,
        )

        anchor_y = (top + bottom) / 2
        target_y = 0.5

    center_x = (left + right) / 2

    transformed = []

    for obj in objects:
        updated = copy.deepcopy(obj)

        for part in updated["components"]:
            part["x"] = round(
                0.5
                + (
                    part["x"] - center_x
                ) * scale,
                6,
            )

            part["y"] = round(
                target_y
                + (
                    part["y"] - anchor_y
                ) * scale,
                6,
            )

            part["width"] = round(
                part["width"] * scale,
                6,
            )

            part["height"] = round(
                part["height"] * scale,
                6,
            )

        updated["center"]["x"] = round(
            0.5
            + (
                obj["center"]["x"] - center_x
            ) * scale,
            6,
        )

        updated["center"]["y"] = round(
            target_y
            + (
                obj["center"]["y"] - anchor_y
            ) * scale,
            6,
        )

        transformed.append(updated)

    result["objects"] = transformed

    return result




def separate_horizontal_overlaps(scene, gap=0.025):
    """Separate ground-based objects using their actual component bounds.

    Only adjusts horizontally arranged ground objects. Objects participating
    in above/below relationships are excluded so vertical arrangements stay
    intact. Every translated component and its object center move together.
    """
    result = copy.deepcopy(scene)
    protected = vertical_object_ids(result)
    candidates = [
        (index, obj)
        for index, obj in enumerate(result["objects"])
        if obj.get("category") in GROUND_CATEGORIES
        and obj.get("id") not in protected
    ]
    if len(candidates) < 2:
        return result

    candidates.sort(key=lambda entry: (object_bounds(entry[1])[0], entry[0]))
    widths = [object_bounds(obj)[2] - object_bounds(obj)[0] for _, obj in candidates]
    available = 1.0 - 2.0 * MARGIN
    required = sum(widths) + gap * (len(widths) - 1)

    # When objects cannot all fit at their current size, shrink their
    # geometry uniformly around the ground line, then recompute bounds.
    if required > available:
        factor = available / required
        scaled = []
        for index, obj in candidates:
            updated = copy.deepcopy(obj)
            cx = updated["center"]["x"]
            for part in updated["components"]:
                part["x"] = round(cx + (part["x"] - cx) * factor, 6)
                part["y"] = round(GROUND_Y + (part["y"] - GROUND_Y) * factor, 6)
                part["width"] = round(part["width"] * factor, 6)
                part["height"] = round(part["height"] * factor, 6)
            updated["center"]["y"] = round(
                GROUND_Y + (updated["center"]["y"] - GROUND_Y) * factor, 6
            )
            result["objects"][index] = updated
            scaled.append((index, updated))
        candidates = scaled
        widths = [object_bounds(obj)[2] - object_bounds(obj)[0] for _, obj in candidates]
        gap = min(gap, max(0.0, (available - sum(widths)) / (len(widths) - 1)))

    # Keep the scene centered and distribute any necessary separation.
    required = sum(widths) + gap * (len(widths) - 1)
    left_edge = max(MARGIN, (1.0 - required) / 2.0)
    for index, obj in candidates:
        left = object_bounds(obj)[0]
        shifted = shift_object(obj, left_edge - left, 0.0)
        result["objects"][index] = shifted
        left_edge += object_bounds(shifted)[2] - object_bounds(shifted)[0] + gap

    return result


def compose_scene(
    prompt,
    learned,
    seed=1337,
    variation=0.5,
):
    """Generate and compose a geometric scene."""

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

    composed = separate_horizontal_overlaps(composed)

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
    """Render the composed SVG scene."""

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
        sun_radius = "38"
    else:
        sun_radius = "48"

    ET.SubElement(
        root,
        "circle",
        cx="875",
        cy="105",
        r=sun_radius,
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
        height=(
            f"{CANVAS_HEIGHT - ground_pixel:.6f}"
        ),
        fill=theme["ground"],
    )

    # Preserve the validated object renderer.
    object_svg = ET.fromstring(
        render_scene_svg(scene)
    )

    namespace = (
        "{http://www.w3.org/2000/svg}"
    )

    for child in object_svg:
        if child.tag == namespace + "g":
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
        default=(
            "melodia_composed_scene_output"
        ),
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
