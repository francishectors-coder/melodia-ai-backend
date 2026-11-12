
"""MELODIA AI - Component Relationship Learner V1.3.

Learns component geometry, parent-relative offsets, and
example-based variations. Renders fitted SVG previews.

Standard library only. Experimental component.
Does not modify the production video generator.
"""

import argparse
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
import xml.etree.ElementTree as ET

from melodia_geometric_object_learner import EXAMPLES


def boxes_overlap(a, b):
    return (
        abs(a["x"] - b["x"]) * 2
        < a["width"] + b["width"]
        and abs(a["y"] - b["y"]) * 2
        < a["height"] + b["height"]
    )


def parse_sample(sample):
    return {
        role: {
            "role": role,
            "shape": shape,
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "color": color,
        }
        for role, shape, x, y, width, height, color in sample
    }


def choose_tree(sample):
    root = max(
        sample,
        key=lambda role: (
            sample[role]["width"]
            * sample[role]["height"],
            -len(role),
        ),
    )

    attached = {root}
    parents = {}

    while len(attached) < len(sample):
        candidates = []

        for child in sample:
            if child in attached:
                continue

            for parent in attached:
                a = sample[child]
                b = sample[parent]

                distance = math.hypot(
                    a["x"] - b["x"],
                    a["y"] - b["y"],
                )

                score = distance - (
                    0.5 if boxes_overlap(a, b) else 0
                )

                candidates.append(
                    (score, child, parent)
                )

        _, child, parent = min(candidates)
        parents[child] = parent
        attached.add(child)

    return root, parents


def train(examples):
    model = {}

    for category, samples in sorted(examples.items()):
        parsed = [
            parse_sample(sample)
            for sample in samples
        ]

        if not parsed:
            raise ValueError(
                f"No examples for {category}"
            )

        roles = set(parsed[0])

        if not roles or any(
            set(sample) != roles
            for sample in parsed
        ):
            raise ValueError(
                f"Inconsistent roles: {category}"
            )

        for sample in parsed:
            for part in sample.values():
                for key in (
                    "x", "y", "width", "height"
                ):
                    value = part[key]

                    if (
                        not math.isfinite(value)
                        or not 0 <= value <= 1
                    ):
                        raise ValueError(
                            f"Invalid geometry: {category}"
                        )

                if (
                    part["width"] <= 0
                    or part["height"] <= 0
                ):
                    raise ValueError(
                        "Zero-size component"
                    )

        root, parents = choose_tree(parsed[0])
        observations = defaultdict(list)

        for sample in parsed:
            for role, part in sample.items():
                parent = parents.get(role)

                reference = (
                    sample[parent]
                    if parent else None
                )

                observations[role].append({
                    "shape": part["shape"],
                    "color": part["color"],
                    "width": part["width"],
                    "height": part["height"],
                    "dx": (
                        part["x"] - reference["x"]
                        if reference else part["x"]
                    ),
                    "dy": (
                        part["y"] - reference["y"]
                        if reference else part["y"]
                    ),
                    "overlap": (
                        boxes_overlap(part, reference)
                        if reference else False
                    ),
                })

        parts = []

        for role in sorted(roles):
            obs = observations[role]

            def mean(key):
                return round(
                    sum(
                        item[key]
                        for item in obs
                    ) / len(obs),
                    6,
                )

            average = {
                key: mean(key)
                for key in (
                    "dx", "dy", "width", "height"
                )
            }

            deviations = []

            for item in obs:
                deviations.append({
                    key: round(
                        item[key] - average[key],
                        6
                    )
                    for key in average
                })

            parts.append({
                "role": role,
                "parent": parents.get(role),
                "shape": Counter(
                    item["shape"]
                    for item in obs
                ).most_common(1)[0][0],
                "color": Counter(
                    item["color"]
                    for item in obs
                ).most_common(1)[0][0],
                **average,
                "deviations": deviations,
                "overlap_frequency": mean(
                    "overlap"
                ),
            })

        model[category] = {
            "root": root,
            "training_examples": len(samples),
            "parts": parts,
        }

    return model


def reconstruct(
    category,
    model,
    scale=1.0,
    variation=0.0,
    seed=1337,
):
    """Generate geometry with coherent sampled deviations.

    variation=0 reproduces the averaged V1.2 layout.
    variation=1 selects a training example's geometric
    deviations, preserving its component relationships.
    """

    if not math.isfinite(scale) or scale <= 0:
        raise ValueError(
            "Scale must be positive and finite"
        )

    if (
        not math.isfinite(variation)
        or not 0 <= variation <= 1
    ):
        raise ValueError(
            "Variation must be between 0 and 1"
        )

    if category not in model:
        return {
            "status": "unknown",
            "requested_object": category,
            "reason": (
                "No training examples "
                "for requested object"
            ),
        }

    learned = model[category]
    rng = random.Random(seed)

    sample_index = rng.randrange(
        learned["training_examples"]
    )

    pending = {
        part["role"]: part
        for part in learned["parts"]
    }

    def geometry(part, key):
        deviation = part["deviations"][
            sample_index
        ][key]

        return (
            part[key]
            + variation * deviation
        )

    placed = {}
    components = []

    root_part = pending[learned["root"]]

    root_center = (
        geometry(root_part, "dx"),
        geometry(root_part, "dy"),
    )

    while pending:
        progress = False

        for role, part in list(pending.items()):
            parent = part["parent"]

            if (
                parent is not None
                and parent not in placed
            ):
                continue

            x = (
                placed[parent]["x"]
                + scale * geometry(part, "dx")
                if parent
                else root_center[0]
            )

            y = (
                placed[parent]["y"]
                + scale * geometry(part, "dy")
                if parent
                else root_center[1]
            )

            width = (
                geometry(part, "width") * scale
            )

            height = (
                geometry(part, "height") * scale
            )

            if width <= 0 or height <= 0:
                raise ValueError(
                    "Variation produced invalid size"
                )

            component = {
                "id": (
                    f"component_{len(components) + 1}"
                ),
                "role": role,
                "parent": parent,
                "shape": part["shape"],
                "color": part["color"],
                "x": round(x, 6),
                "y": round(y, 6),
                "width": round(width, 6),
                "height": round(height, 6),
            }

            placed[role] = component
            components.append(component)

            del pending[role]
            progress = True

        if not progress:
            raise ValueError(
                "Invalid parent relationships"
            )

    return {
        "status": "generated",
        "object": category,
        "scale": scale,
        "variation": variation,
        "seed": seed,
        "method": (
            "sampled_training_example_deviations"
        ),
        "components": components,
    }


def component_bounds(part, width, height):
    cx = part["x"] * width
    cy = part["y"] * height

    w = part["width"] * width
    h = part["height"] * height

    if part["shape"] == "circle":
        radius = h / 2

        return (
            cx - radius,
            cy - radius,
            cx + radius,
            cy + radius,
        )

    if part["shape"] in (
        "ellipse",
        "rectangle",
        "triangle",
        "polygon",
    ):
        return (
            cx - w / 2,
            cy - h / 2,
            cx + w / 2,
            cy + h / 2,
        )

    raise ValueError(
        f"Unsupported shape: {part['shape']}"
    )


def calculate_canvas_fit(
    components,
    width,
    height,
    padding=16,
):
    if not components:
        return 1.0, 0.0, 0.0

    bounds = [
        component_bounds(
            part, width, height
        )
        for part in components
    ]

    left = min(b[0] for b in bounds)
    top = min(b[1] for b in bounds)
    right = max(b[2] for b in bounds)
    bottom = max(b[3] for b in bounds)

    object_width = right - left
    object_height = bottom - top

    if (
        object_width <= 0
        or object_height <= 0
    ):
        raise ValueError(
            "Invalid object bounding box"
        )

    available_width = width - 2 * padding
    available_height = height - 2 * padding

    if (
        available_width <= 0
        or available_height <= 0
    ):
        raise ValueError(
            "Canvas padding is too large"
        )

    fit_scale = min(
        1.0,
        available_width / object_width,
        available_height / object_height,
    )

    object_center_x = (
        left + right
    ) / 2

    object_center_y = (
        top + bottom
    ) / 2

    translate_x = (
        width / 2
        - fit_scale * object_center_x
    )

    translate_y = (
        height / 2
        - fit_scale * object_center_y
    )

    return (
        fit_scale,
        translate_x,
        translate_y,
    )


def render_relationship_svg(
    representation,
    width=512,
    height=288,
):
    svg = ET.Element(
        "svg",
        xmlns="http://www.w3.org/2000/svg",
        width=str(width),
        height=str(height),
        viewBox=f"0 0 {width} {height}",
    )

    ET.SubElement(
        svg,
        "rect",
        width=str(width),
        height=str(height),
        fill="#ffffff",
    )

    components = representation.get(
        "components", []
    )

    fit_scale, tx, ty = calculate_canvas_fit(
        components,
        width,
        height,
    )

    group = ET.SubElement(
        svg,
        "g",
        transform=(
            f"translate({tx:.6f} {ty:.6f}) "
            f"scale({fit_scale:.6f})"
        ),
    )

    for part in components:
        cx = part["x"] * width
        cy = part["y"] * height

        w = part["width"] * width
        h = part["height"] * height

        color = part["color"]
        shape = part["shape"]

        if shape == "circle":
            ET.SubElement(
                group,
                "circle",
                cx=f"{cx:.6f}",
                cy=f"{cy:.6f}",
                r=f"{h / 2:.6f}",
                fill=color,
            )

        elif shape == "ellipse":
            ET.SubElement(
                group,
                "ellipse",
                cx=f"{cx:.6f}",
                cy=f"{cy:.6f}",
                rx=f"{w / 2:.6f}",
                ry=f"{h / 2:.6f}",
                fill=color,
            )

        elif shape == "rectangle":
            ET.SubElement(
                group,
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
                group,
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
                (cx + w / 4, cy + h / 2),
                (cx - w / 4, cy + h / 2),
            ]

            ET.SubElement(
                group,
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
        "--object",
        default="tree",
    )

    parser.add_argument(
        "--output",
        default="melodia_relationship_output",
    )

    parser.add_argument(
        "--scale",
        type=float,
        default=1.0,
    )

    parser.add_argument(
        "--variation",
        type=float,
        default=0.0,
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=1337,
    )

    args = parser.parse_args()

    output = Path(args.output)

    output.mkdir(
        parents=True,
        exist_ok=True,
    )

    learned = train(EXAMPLES)

    model = {
        "project": "MELODIA AI",
        "version": "1.3",
        "model_type": (
            "geometric_component_relationships"
        ),
        "categories": learned,
    }

    (output / "relationship_model.json").write_text(
        json.dumps(model, indent=2),
        encoding="utf-8",
    )

    representation = reconstruct(
        args.object,
        learned,
        args.scale,
        args.variation,
        args.seed,
    )

    (
        output / "relationship_representation.json"
    ).write_text(
        json.dumps(representation, indent=2),
        encoding="utf-8",
    )

    if representation["status"] == "generated":
        svg = render_relationship_svg(
            representation
        )

        (
            output / "relationship_preview.svg"
        ).write_text(
            svg,
            encoding="utf-8",
        )

    print(
        "MELODIA COMPONENT RELATIONSHIP LEARNER V1.3"
    )
    print("Categories:", len(learned))
    print("Requested:", args.object)
    print("Variation:", args.variation)
    print("Seed:", args.seed)
    print("Status:", representation["status"])
    print("Output:", output)


if __name__ == "__main__":
    main()
