
"""MELODIA AI - Automatic Structure Learner V1.5.

Infers component relationships from geometric training examples,
without requiring manually supplied parent-child connections.

Exports learned structures to the V1.4 universal object schema.

Standard library only.
Existing MELODIA engines remain unchanged.

Limitations:
- Training examples must contain named geometric components.
- Inference uses geometric proximity, overlap and consistency.
- This is not yet visual recognition or arbitrary prompt learning.
"""

import argparse
import json
import math
from collections import Counter
from pathlib import Path

from melodia_geometric_object_learner import EXAMPLES
from melodia_universal_object_schema import (
    build_universal_library,
    validate_object,
)


VERSION = "1.5"

GEOMETRY_KEYS = (
    "dx",
    "dy",
    "width",
    "height",
)


def parse_example(sample):
    """Convert component tuples to dictionaries."""

    result = {}

    for (
        role,
        shape,
        x,
        y,
        width,
        height,
        color,
    ) in sample:

        if role in result:
            raise ValueError(
                f"Duplicate role: {role}"
            )

        values = (x, y, width, height)

        if not all(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            for value in values
        ):
            raise ValueError(
                f"Invalid geometry: {role}"
            )

        if width <= 0 or height <= 0:
            raise ValueError(
                f"Invalid component size: {role}"
            )

        result[role] = {
            "role": role,
            "shape": shape,
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "color": color,
        }

    return result


def overlap_ratio(a, b):
    """Calculate intersection divided by smaller box area."""

    left = max(
        a["x"] - a["width"] / 2,
        b["x"] - b["width"] / 2,
    )

    right = min(
        a["x"] + a["width"] / 2,
        b["x"] + b["width"] / 2,
    )

    top = max(
        a["y"] - a["height"] / 2,
        b["y"] - b["height"] / 2,
    )

    bottom = min(
        a["y"] + a["height"] / 2,
        b["y"] + b["height"] / 2,
    )

    intersection = (
        max(0.0, right - left)
        * max(0.0, bottom - top)
    )

    smaller = min(
        a["width"] * a["height"],
        b["width"] * b["height"],
    )

    return (
        intersection / smaller
        if smaller > 0 else 0.0
    )


def mean(values):
    return sum(values) / len(values)


def select_root(samples, roles):
    """Select a consistently large central component."""

    scores = {}

    for role in roles:
        areas = []
        centrality = []

        for sample in samples:
            part = sample[role]

            areas.append(
                part["width"] * part["height"]
            )

            centrality.append(
                math.hypot(
                    part["x"] - 0.5,
                    part["y"] - 0.5,
                )
            )

        scores[role] = (
            mean(areas)
            - 0.1 * mean(centrality)
        )

    return max(
        sorted(roles),
        key=lambda role: scores[role],
    )


def relationship_score(samples, child, parent):
    """Score a candidate geometric attachment."""

    distances = []
    overlaps = []

    for sample in samples:
        a = sample[child]
        b = sample[parent]

        distance = math.hypot(
            a["x"] - b["x"],
            a["y"] - b["y"],
        )

        distances.append(distance)

        overlaps.append(
            overlap_ratio(a, b)
        )

    average_distance = mean(distances)
    average_overlap = mean(overlaps)

    distance_variance = mean([
        (distance - average_distance) ** 2
        for distance in distances
    ])

    return (
        average_distance
        + 0.5 * math.sqrt(distance_variance)
        - 0.25 * average_overlap
    )


def infer_hierarchy(samples, roles):
    """Infer a rooted, cycle-free component hierarchy."""

    root = select_root(samples, roles)

    attached = {root}
    parents = {}

    while len(attached) < len(roles):
        candidates = []

        for child in roles:
            if child in attached:
                continue

            for parent in attached:
                score = relationship_score(
                    samples,
                    child,
                    parent,
                )

                candidates.append(
                    (score, child, parent)
                )

        if not candidates:
            raise ValueError(
                "Cannot construct hierarchy"
            )

        _, child, parent = min(candidates)

        parents[child] = parent
        attached.add(child)

    return root, parents


def learn_category(category, examples):
    """Learn one object structure from repeated examples."""

    samples = [
        parse_example(example)
        for example in examples
    ]

    if not samples:
        raise ValueError(
            f"No training examples: {category}"
        )

    roles = sorted(samples[0])

    if not roles:
        raise ValueError(
            f"No components: {category}"
        )

    for sample in samples:
        if sorted(sample) != roles:
            raise ValueError(
                f"Inconsistent component roles: {category}"
            )

    root, parents = infer_hierarchy(
        samples,
        roles,
    )

    learned_parts = []

    for role in roles:
        parent = parents.get(role)

        observations = []

        for sample in samples:
            part = sample[role]

            reference = (
                sample[parent]
                if parent is not None
                else None
            )

            observations.append({
                "shape": part["shape"],
                "color": part["color"],
                "dx": (
                    part["x"] - reference["x"]
                    if reference
                    else part["x"]
                ),
                "dy": (
                    part["y"] - reference["y"]
                    if reference
                    else part["y"]
                ),
                "width": part["width"],
                "height": part["height"],
                "overlap": (
                    overlap_ratio(
                        part,
                        reference,
                    )
                    if reference else 0.0
                ),
            })

        averages = {
            key: round(
                mean([
                    item[key]
                    for item in observations
                ]),
                6,
            )
            for key in GEOMETRY_KEYS
        }

        deviations = []

        for observation in observations:
            deviations.append({
                key: round(
                    observation[key]
                    - averages[key],
                    6,
                )
                for key in GEOMETRY_KEYS
            })

        shape = Counter(
            item["shape"]
            for item in observations
        ).most_common(1)[0][0]

        color = Counter(
            item["color"]
            for item in observations
        ).most_common(1)[0][0]

        learned_parts.append({
            "role": role,
            "parent": parent,
            "shape": shape,
            "color": color,
            **averages,
            "deviations": deviations,
            "overlap_frequency": round(
                mean([
                    1.0 if item["overlap"] > 0 else 0.0
                    for item in observations
                ]),
                6,
            ),
        })

    return {
        "root": root,
        "training_examples": len(samples),
        "parts": learned_parts,
    }


def learn_all(examples):
    """Learn structures for every supplied category."""

    return {
        category: learn_category(
            category,
            samples,
        )
        for category, samples in sorted(
            examples.items()
        )
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--output",
        default="melodia_structure_learning_output",
    )

    args = parser.parse_args()

    output = Path(args.output)

    output.mkdir(
        parents=True,
        exist_ok=True,
    )

    learned = learn_all(EXAMPLES)

    library = build_universal_library(
        learned
    )

    for obj in library["objects"].values():
        validate_object(obj)

    model = {
        "project": "MELODIA AI",
        "version": VERSION,
        "model_type": (
            "automatically_inferred_component_hierarchy"
        ),
        "categories": learned,
    }

    model_path = (
        output / "automatic_structure_model.json"
    )

    model_path.write_text(
        json.dumps(
            model,
            indent=2,
        ),
        encoding="utf-8",
    )

    library_path = (
        output / "universal_object_library.json"
    )

    library_path.write_text(
        json.dumps(
            library,
            indent=2,
        ),
        encoding="utf-8",
    )

    summary = {
        "project": "MELODIA AI",
        "version": VERSION,
        "categories": len(learned),
        "components": sum(
            len(item["parts"])
            for item in learned.values()
        ),
        "validation": "passed",
        "method": (
            "geometric_relationship_inference"
        ),
    }

    summary_path = (
        output / "structure_learning_summary.json"
    )

    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        "MELODIA AUTOMATIC STRUCTURE LEARNER V1.5"
    )
    print("Categories:", summary["categories"])
    print("Components:", summary["components"])
    print("Validation:", summary["validation"])
    print("Output:", output)


if __name__ == "__main__":
    main()
