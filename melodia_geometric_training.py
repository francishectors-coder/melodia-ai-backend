
"""
MELODIA AI - Geometric Training Data Generator
Version 1.1

Generates reproducible text-to-geometry training data
with validated spatial relationships.

Python standard library only.
"""

import argparse
import hashlib
import json
import random
from pathlib import Path


WIDTH = 512
HEIGHT = 288

COLORS = [
    "red", "blue", "green", "yellow",
    "orange", "purple", "brown", "white"
]

SHAPES = [
    "circle", "ellipse", "rectangle",
    "triangle", "polygon"
]

RELATIONS = [
    "above", "below", "beside",
    "inside", "overlapping"
]

ENVIRONMENTS = [
    "forest", "riverbank", "village",
    "desert", "mountain", "open field",
    "night sky", "seaside"
]


def make_object(rng, object_id, x, y, size, color):
    """Create a compound object around a fixed anchor."""

    components = []

    count = rng.randint(2, 5)

    for _ in range(count):
        shape = rng.choice(SHAPES)

        component_width = rng.randint(
            max(6, size // 6),
            max(8, size // 3)
        )

        component_height = rng.randint(
            max(6, size // 6),
            max(8, size // 3)
        )

        components.append({
            "shape": shape,
            "color": color,
            "x": rng.randint(
                x - size // 4,
                x + size // 4
            ),
            "y": rng.randint(
                y - size // 4,
                y + size // 4
            ),
            "width": component_width,
            "height": component_height,
            "rotation": rng.randint(-30, 30)
        })

    return {
        "object_id": object_id,
        "color": color,
        "x": x,
        "y": y,
        "size": size,
        "components": components
    }


def choose_positions(rng, relation):
    """Return anchors satisfying the requested relation."""

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

    raise ValueError("Unknown relationship")


def validate_relationship(scene):
    """Check the anchor geometry matches the relation."""

    first, second = scene["objects"]
    relation = scene["relationship"]["relation"]

    x1, y1 = first["x"], first["y"]
    x2, y2 = second["x"], second["y"]

    if relation == "above":
        return y1 < y2

    if relation == "below":
        return y1 > y2

    if relation == "beside":
        return abs(x1 - x2) > 80

    if relation == "inside":
        return (
            x1 == x2
            and y1 == y2
            and first["size"] < second["size"]
        )

    if relation == "overlapping":
        return (
            abs(x1 - x2)
            < (first["size"] + second["size"]) / 2
            and
            abs(y1 - y2)
            < (first["size"] + second["size"]) / 2
        )

    return False


def validate_bounds(scene):
    """Check object anchors and components remain on canvas."""

    for obj in scene["objects"]:
        if not (0 <= obj["x"] < WIDTH):
            return False

        if not (0 <= obj["y"] < HEIGHT):
            return False

        for component in obj["components"]:
            x = component["x"]
            y = component["y"]

            if not (0 <= x < WIDTH):
                return False

            if not (0 <= y < HEIGHT):
                return False

    return True


def create_example(rng, index):
    relation = rng.choice(RELATIONS)
    environment = rng.choice(ENVIRONMENTS)

    first_position, second_position = choose_positions(
        rng, relation
    )

    first_color = rng.choice(COLORS)
    second_color = rng.choice(COLORS)

    if relation == "inside":
        first_size = 35
        second_size = 120
    else:
        first_size = 65
        second_size = 65

    first = make_object(
        rng,
        "object_1",
        *first_position,
        first_size,
        first_color
    )

    second = make_object(
        rng,
        "object_2",
        *second_position,
        second_size,
        second_color
    )

    prompt = (
        f"In a {environment}, a {first_color} "
        f"geometric object is {relation} "
        f"a {second_color} geometric object."
    )

    scene = {
        "width": WIDTH,
        "height": HEIGHT,
        "environment": environment,
        "objects": [first, second],
        "relationship": {
            "subject": "object_1",
            "relation": relation,
            "target": "object_2"
        }
    }

    if not validate_relationship(scene):
        raise ValueError(
            "Invalid spatial relationship"
        )

    if not validate_bounds(scene):
        raise ValueError(
            "Geometry exceeds canvas"
        )

    return {
        "id": index,
        "prompt": prompt,
        "scene": scene
    }


def write_dataset(path, count, seed):
    rng = random.Random(seed)

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    digest = hashlib.sha256()

    with path.open("w", encoding="utf-8") as file:
        for index in range(1, count + 1):
            example = create_example(rng, index)

            line = json.dumps(
                example,
                ensure_ascii=False,
                separators=(",", ":")
            )

            file.write(line + "\n")

            digest.update(
                (line + "\n").encode("utf-8")
            )

    return {
        "path": str(path),
        "examples": count,
        "seed": seed,
        "sha256": digest.hexdigest()
    }


def validate_dataset(path, expected_count):
    count = 0

    with path.open("r", encoding="utf-8") as file:
        for line in file:
            record = json.loads(line)

            scene = record["scene"]

            assert validate_relationship(scene)
            assert validate_bounds(scene)

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
        parser.error(
            "Dataset counts must be positive."
        )

    output = Path(args.output)

    training = write_dataset(
        output / "train.jsonl",
        args.train_count,
        args.seed
    )

    evaluation = write_dataset(
        output / "evaluation.jsonl",
        args.eval_count,
        args.seed + 100000
    )

    validate_dataset(
        output / "train.jsonl",
        args.train_count
    )

    validate_dataset(
        output / "evaluation.jsonl",
        args.eval_count
    )

    manifest = {
        "project": "MELODIA Geometric Intelligence",
        "version": "1.1",
        "training": training,
        "evaluation": evaluation,
        "status": "validated"
    }

    (output / "dataset_manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8"
    )

    print("MELODIA GEOMETRIC TRAINING DATA V1.1")
    print("Training examples:", args.train_count)
    print("Evaluation examples:", args.eval_count)
    print("Spatial validation: PASSED")
    print("Output directory:", output)


if __name__ == "__main__":
    main()
