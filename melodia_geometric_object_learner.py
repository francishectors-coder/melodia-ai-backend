
"""
MELODIA AI - Geometric Object Learner
Version 1.0

Learns reusable geometric object representations
from structured examples.

Uses a lightweight statistical prototype learner.
No external AI models or Python dependencies.

This is an independent experimental component.
It does not modify the production video generator.
"""

import argparse
import json
import math
import random
from collections import defaultdict
from pathlib import Path


SHAPE_TYPES = [
    "circle",
    "ellipse",
    "rectangle",
    "triangle",
    "polygon"
]

FEATURES = [
    "roundness",
    "elongation",
    "angularity",
    "verticality",
    "symmetry",
    "component_count"
]

# These examples provide initial geometric concepts.
# They are training examples, not object-specific
# rendering functions.
#
# Feature values are normalized to 0..1.

TRAINING_EXAMPLES = [
    {
        "name": "tree",
        "features": [0.25, 0.75, 0.60, 0.95, 0.85, 0.50],
        "components": ["rectangle", "triangle", "triangle"]
    },
    {
        "name": "tree",
        "features": [0.45, 0.65, 0.35, 0.90, 0.90, 0.60],
        "components": ["rectangle", "ellipse", "ellipse"]
    },
    {
        "name": "house",
        "features": [0.10, 0.35, 0.95, 0.65, 0.95, 0.65],
        "components": ["rectangle", "triangle", "rectangle"]
    },
    {
        "name": "house",
        "features": [0.15, 0.40, 0.90, 0.70, 0.90, 0.75],
        "components": ["rectangle", "polygon", "rectangle"]
    },
    {
        "name": "vehicle",
        "features": [0.35, 0.90, 0.65, 0.20, 0.80, 0.75],
        "components": ["rectangle", "circle", "circle"]
    },
    {
        "name": "vehicle",
        "features": [0.40, 0.85, 0.60, 0.25, 0.85, 0.80],
        "components": ["polygon", "circle", "circle"]
    },
    {
        "name": "animal",
        "features": [0.65, 0.70, 0.35, 0.45, 0.55, 0.85],
        "components": ["ellipse", "circle", "rectangle"]
    },
    {
        "name": "animal",
        "features": [0.70, 0.65, 0.30, 0.50, 0.60, 0.90],
        "components": ["ellipse", "ellipse", "rectangle"]
    },
    {
        "name": "flower",
        "features": [0.90, 0.40, 0.15, 0.75, 0.95, 0.95],
        "components": ["circle", "ellipse", "ellipse"]
    },
    {
        "name": "flower",
        "features": [0.85, 0.45, 0.20, 0.80, 0.90, 0.90],
        "components": ["circle", "circle", "ellipse"]
    }
]


def validate_example(example):
    if not example["name"]:
        raise ValueError("Missing object name")

    features = example["features"]

    if len(features) != len(FEATURES):
        raise ValueError("Incorrect feature count")

    for value in features:
        if not isinstance(value, (int, float)):
            raise ValueError("Non-numeric feature")

        if not math.isfinite(value):
            raise ValueError("Non-finite feature")

        if not 0.0 <= value <= 1.0:
            raise ValueError("Feature outside 0..1")

    for component in example["components"]:
        if component not in SHAPE_TYPES:
            raise ValueError(
                f"Unsupported component: {component}"
            )


def train_prototypes(examples):
    grouped = defaultdict(list)

    for example in examples:
        validate_example(example)
        grouped[example["name"]].append(example)

    prototypes = {}

    for name, samples in grouped.items():
        count = len(samples)

        average_features = [
            sum(
                sample["features"][index]
                for sample in samples
            ) / count
            for index in range(len(FEATURES))
        ]

        component_counts = defaultdict(int)

        for sample in samples:
            for component in sample["components"]:
                component_counts[component] += 1

        total_components = sum(
            component_counts.values()
        )

        distribution = {
            shape: (
                component_counts[shape] / total_components
            )
            for shape in SHAPE_TYPES
        }

        prototypes[name] = {
            "features": average_features,
            "component_distribution": distribution,
            "training_examples": count
        }

    return prototypes


def distance(first, second):
    return math.sqrt(
        sum(
            (a - b) ** 2
            for a, b in zip(first, second)
        )
    )


def classify(features, prototypes):
    if not prototypes:
        raise ValueError("No trained prototypes")

    scores = []

    for name, prototype in prototypes.items():
        score = distance(
            features,
            prototype["features"]
        )

        scores.append((score, name))

    scores.sort()

    return {
        "predicted_object": scores[0][1],
        "distance": round(scores[0][0], 6)
    }


def generate_representation(name, prototypes, seed=1337):
    if name not in prototypes:
        return {
            "status": "unknown",
            "requested_object": name,
            "reason": "Object has no learned prototype"
        }

    prototype = prototypes[name]

    rng = random.Random(seed)

    distribution = prototype[
        "component_distribution"
    ]

    shapes = list(distribution)
    weights = [
        distribution[shape]
        for shape in shapes
    ]

    count = max(
        2,
        round(
            prototype["features"][
                FEATURES.index("component_count")
            ] * 5
        )
    )

    components = rng.choices(
        shapes,
        weights=weights,
        k=count
    )

    return {
        "status": "generated",
        "object": name,
        "features": prototype["features"],
        "components": [
            {
                "id": f"component_{index}",
                "shape": shape
            }
            for index, shape in enumerate(
                components, start=1
            )
        ],
        "method": "learned_statistical_prototype"
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--output",
        default="melodia_object_learning_output"
    )

    parser.add_argument(
        "--object",
        default="tree"
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=1337
    )

    args = parser.parse_args()

    prototypes = train_prototypes(
        TRAINING_EXAMPLES
    )

    output = Path(args.output)
    output.mkdir(
        parents=True,
        exist_ok=True
    )

    model = {
        "project": "MELODIA AI",
        "version": "1.0",
        "model_type": "geometric_object_prototypes",
        "features": FEATURES,
        "shapes": SHAPE_TYPES,
        "prototypes": prototypes
    }

    model_path = output / "object_model.json"

    model_path.write_text(
        json.dumps(model, indent=2),
        encoding="utf-8"
    )

    representation = generate_representation(
        args.object,
        prototypes,
        args.seed
    )

    representation_path = (
        output / "object_representation.json"
    )

    representation_path.write_text(
        json.dumps(representation, indent=2),
        encoding="utf-8"
    )

    print("MELODIA GEOMETRIC OBJECT LEARNER V1.0")
    print("Learned object categories:", len(prototypes))
    print("Requested object:", args.object)
    print("Generation status:", representation["status"])
    print("Model:", model_path)
    print("Representation:", representation_path)


if __name__ == "__main__":
    main()
