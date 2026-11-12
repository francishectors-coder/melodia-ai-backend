
"""
MELODIA AI - Geometric Scene Reasoner
Version 1.0

Converts simple text descriptions into structured
geometric scenes and SVG illustrations.

Independent prototype; does not modify the
production video generator.

Python standard library only.
"""

import argparse
import html
import json
import re
from pathlib import Path


WIDTH = 512
HEIGHT = 288

COLORS = {
    "red", "blue", "green", "yellow",
    "orange", "purple", "brown", "white",
    "black", "pink", "gray", "gold"
}

SHAPES = {
    "circle", "ellipse", "rectangle",
    "square", "triangle", "polygon"
}

RELATION_PATTERNS = {
    "above": [
        r"\babove\b",
        r"\bover\b",
        r"\bhigher than\b",
        r"\boverhead\b"
    ],
    "below": [
        r"\bbelow\b",
        r"\bunder\b",
        r"\bbeneath\b",
        r"\blower than\b"
    ],
    "beside": [
        r"\bbeside\b",
        r"\bnext to\b",
        r"\balongside\b",
        r"\badjacent to\b"
    ],
    "inside": [
        r"\binside\b",
        r"\bwithin\b",
        r"\bcontained in\b"
    ],
    "overlapping": [
        r"\boverlapping\b",
        r"\boverlaps?\b",
        r"\bintersecting\b",
        r"\bintersects?\b"
    ]
}


def detect_relation(prompt):
    text = prompt.lower()

    for relation, patterns in RELATION_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text):
                return relation

    return None


def extract_objects(prompt):
    """
    Identify explicitly named geometric shapes.
    This version does not infer arbitrary objects.
    """

    text = prompt.lower()

    pattern = (
        r"\b(?:(red|blue|green|yellow|orange|purple|"
        r"brown|white|black|pink|gray|gold)\s+)?"
        r"(circle|ellipse|rectangle|square|triangle|polygon)\b"
    )

    matches = list(re.finditer(pattern, text))

    objects = []

    for index, match in enumerate(matches[:2], start=1):
        objects.append({
            "id": f"object_{index}",
            "shape": match.group(2),
            "color": match.group(1) or "blue"
        })

    return objects


def choose_positions(relation):
    if relation == "above":
        return (256, 85), (256, 205)

    if relation == "below":
        return (256, 205), (256, 85)

    if relation == "beside":
        return (155, 145), (355, 145)

    if relation == "inside":
        return (256, 145), (256, 145)

    if relation == "overlapping":
        return (235, 145), (275, 145)

    return (155, 145), (355, 145)


def build_scene(prompt):
    objects = extract_objects(prompt)
    relation = detect_relation(prompt)

    if len(objects) != 2:
        return {
            "status": "unsupported",
            "reason": (
                "V1.0 requires two explicitly named "
                "geometric shapes."
            ),
            "prompt": prompt
        }

    if relation is None:
        return {
            "status": "unsupported",
            "reason": (
                "No supported spatial relationship "
                "was identified."
            ),
            "prompt": prompt
        }

    first_position, second_position = choose_positions(
        relation
    )

    for index, obj in enumerate(objects):
        obj["x"], obj["y"] = (
            first_position
            if index == 0
            else second_position
        )

        obj["size"] = 35 if (
            relation == "inside" and index == 0
        ) else 120 if (
            relation == "inside" and index == 1
        ) else 65

    return {
        "status": "supported",
        "prompt": prompt,
        "width": WIDTH,
        "height": HEIGHT,
        "objects": objects,
        "relationship": {
            "subject": "object_1",
            "relation": relation,
            "target": "object_2"
        }
    }


def render_shape(obj):
    x = obj["x"]
    y = obj["y"]
    size = obj["size"]

    color = html.escape(obj["color"])
    shape = obj["shape"]

    if shape == "circle":
        return (
            f'<circle cx="{x}" cy="{y}" '
            f'r="{size // 2}" fill="{color}" '
            f'stroke="#202020" stroke-width="2"/>'
        )

    if shape == "ellipse":
        return (
            f'<ellipse cx="{x}" cy="{y}" '
            f'rx="{size // 2}" ry="{size // 3}" '
            f'fill="{color}" stroke="#202020" '
            f'stroke-width="2"/>'
        )

    if shape in ("rectangle", "square"):
        width = size
        height = (
            size
            if shape == "square"
            else int(size * 0.65)
        )

        return (
            f'<rect x="{x - width // 2}" '
            f'y="{y - height // 2}" '
            f'width="{width}" height="{height}" '
            f'fill="{color}" stroke="#202020" '
            f'stroke-width="2"/>'
        )

    if shape == "triangle":
        points = (
            f"{x},{y - size // 2} "
            f"{x - size // 2},{y + size // 2} "
            f"{x + size // 2},{y + size // 2}"
        )

        return (
            f'<polygon points="{points}" '
            f'fill="{color}" stroke="#202020" '
            f'stroke-width="2"/>'
        )

    if shape == "polygon":
        points = [
            (x, y - size // 2),
            (x + size // 2, y - size // 5),
            (x + size // 3, y + size // 2),
            (x - size // 3, y + size // 2),
            (x - size // 2, y - size // 5)
        ]

        coordinates = " ".join(
            f"{px},{py}" for px, py in points
        )

        return (
            f'<polygon points="{coordinates}" '
            f'fill="{color}" stroke="#202020" '
            f'stroke-width="2"/>'
        )

    raise ValueError(f"Unsupported shape: {shape}")


def render_svg(scene):
    if scene["status"] != "supported":
        raise ValueError(
            "Cannot render unsupported scene"
        )

    first, second = scene["objects"]
    relation = scene["relationship"]["relation"]

    # Draw the containing object first so the
    # smaller object remains visible inside it.
    draw_order = (
        [second, first]
        if relation == "inside"
        else [first, second]
    )

    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}">',
        '<rect width="100%" height="100%" '
        'fill="#eef5fb"/>'
    ]

    for obj in draw_order:
        elements.append(render_shape(obj))

    elements.append("</svg>")

    return "\n".join(elements)


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--prompt",
        default=(
            "A red circle above a blue square"
        )
    )

    parser.add_argument(
        "--output",
        default="melodia_scene_reasoner_output"
    )

    args = parser.parse_args()

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    scene = build_scene(args.prompt)

    scene_path = output / "scene.json"

    scene_path.write_text(
        json.dumps(scene, indent=2),
        encoding="utf-8"
    )

    print("MELODIA GEOMETRIC SCENE REASONER V1.0")
    print("Prompt:", args.prompt)
    print("Status:", scene["status"])

    if scene["status"] == "supported":
        svg = render_svg(scene)

        svg_path = output / "scene.svg"

        svg_path.write_text(
            svg,
            encoding="utf-8"
        )

        print("SVG generated:", svg_path)
    else:
        print("Reason:", scene["reason"])

    print("Scene JSON:", scene_path)


if __name__ == "__main__":
    main()
