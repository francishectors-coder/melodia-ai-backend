
"""
MELODIA AI - Geometric Training Data Generator
Version 1.0

Creates reproducible synthetic text-to-geometry examples.
Uses only Python standard-library modules.

This is a training-data foundation, not a trained
universal text-to-image model.
"""

import argparse
import hashlib
import json
import random
from pathlib import Path


COLORS = [
    "red", "blue", "green", "yellow",
    "orange", "purple", "brown", "white"
]

SHAPES = [
    "circle", "ellipse", "rectangle",
    "triangle", "polygon"
]

POSITIONS = [
    "left", "right", "center",
    "top", "bottom"
]

RELATIONS = [
    "above", "below", "beside",
    "overlapping", "inside"
]

ACTIONS = [
    "moving", "rising", "falling",
    "turning", "approaching", "resting"
]

ENVIRONMENTS = [
    "forest", "riverbank", "village",
    "desert", "mountain", "open field",
    "night sky", "seaside"
]


def make_shape(rng, width=512, height=288):
    kind = rng.choice(SHAPES)
    color = rng.choice(COLORS)

    return {
        "shape": kind,
        "color": color,
        "x": rng.randint(40, width - 40),
        "y": rng.randint(35, height - 35),
        "width": rng.randint(18, 90),
        "height": rng.randint(18, 90),
        "rotation": rng.randint(-45, 45),
    }


def create_object(rng):
    count = rng.randint(2, 5)
    components = [
        make_shape(rng)
        for _ in range(count)
    ]

    return {
        "object_id": "object_1",
        "components": components,
        "action": rng.choice(ACTIONS),
        "position": rng.choice(POSITIONS),
    }


def create_example(rng, index):
    environment = rng.choice(ENVIRONMENTS)
    relation = rng.choice(RELATIONS)

    primary = create_object(rng)

    secondary = {
        "object_id": "object_2",
        "components": [
            make_shape(rng)
            for _ in range(rng.randint(1, 3))
        ],
        "action": rng.choice(ACTIONS),
        "position": rng.choice(POSITIONS),
    }

    primary_color = primary["components"][0]["color"]
    secondary_color = secondary["components"][0]["color"]

    prompt = (
        f"In a {environment}, a {primary_color} "
        f"geometric object is {primary['action']} "
        f"{relation} a {secondary_color} "
        f"geometric object."
    )

    return {
        "id": index,
        "prompt": prompt,
        "scene": {
            "width": 512,
            "height": 288,
            "environment": environment,
            "objects": [primary, secondary],
            "relationship": {
                "subject": "object_1",
                "relation": relation,
                "target": "object_2",
            },
        },
    }


def write_dataset(path, count, seed):
    rng = random.Random(seed)
    path.parent.mkdir(parents=True, exist_ok=True)

    digest = hashlib.sha256()

    with path.open("w", encoding="utf-8") as file:
        for index in range(1, count + 1):
            example = create_example(rng, index)

            line = json.dumps(
                example,
                ensure_ascii=False,
                separators=(",", ":"),
            )

            file.write(line + "\n")
            digest.update((line + "\n").encode("utf-8"))

    return {
        "path": str(path),
        "examples": count,
        "seed": seed,
        "sha256": digest.hexdigest(),
    }


def validate_dataset(path, expected_count):
    count = 0

    with path.open("r", encoding="utf-8") as file:
        for line in file:
            record = json.loads(line)

            assert record["prompt"]
            assert len(record["scene"]["objects"]) == 2
            assert record["scene"]["relationship"]

            count += 1

    assert count == expected_count
    return count


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--output",
        default="melodia_training_output"
    )

    parser.add_argument(
        "--train-count",
        type=int,
        default=2000
    )

    parser.add_argument(
        "--eval-count",
        type=int,
        default=200
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=1337
    )

    args = parser.parse_args()

    if args.train_count < 1 or args.eval_count < 1:
        parser.error("Dataset counts must be positive.")

    output = Path(args.output)

    training = write_dataset(
        output / "train.jsonl",
        args.train_count,
        args.seed,
    )

    evaluation = write_dataset(
        output / "evaluation.jsonl",
        args.eval_count,
        args.seed + 100000,
    )

    validate_dataset(
        output / "train.jsonl",
        args.train_count,
    )

    validate_dataset(
        output / "evaluation.jsonl",
        args.eval_count,
    )

    manifest = {
        "project": "MELODIA Geometric Intelligence",
        "version": "1.0",
        "training": training,
        "evaluation": evaluation,
        "status": "dataset_generated",
    }

    output.mkdir(parents=True, exist_ok=True)

    (output / "dataset_manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    print("MELODIA GEOMETRIC TRAINING DATA")
    print("Training examples:", args.train_count)
    print("Evaluation examples:", args.eval_count)
    print("Output directory:", output)
    print("Dataset validation: PASSED")


if __name__ == "__main__":
    main()
