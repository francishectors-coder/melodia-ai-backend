
"""MELODIA AI - Spatial Relationship Engine V1.7.

Interprets simple English relationships between objects:
- left of / right of
- above / below
- beside / next to
- near

Uses V1.6 for object reconstruction and SVG rendering.

Produces JSON and SVG scenes.

Standard library only.
Does not modify existing MELODIA engines.

Limitations:
- Supports known V1.5 object categories only.
- Uses rule-based English parsing.
- Supports singular object references and repeated
  references to an already introduced object.
- Does not understand unrestricted natural language.
"""

import argparse
import json
import re
from pathlib import Path

from melodia_geometric_object_learner import EXAMPLES
from melodia_automatic_structure_learner import learn_all
from melodia_prompt_scene_generator import (
    VERSION as BASE_VERSION,
    OBJECT_ALIASES,
    CANVAS_WIDTH,
    CANVAS_HEIGHT,
    build_scene,
    place_object,
    render_scene_svg,
)

VERSION = "1.7"

RELATION_PATTERNS = [
    (
        "left_of",
        r"(?:to\s+the\s+)?left\s+of",
    ),
    (
        "right_of",
        r"(?:to\s+the\s+)?right\s+of",
    ),
    (
        "above",
        r"(?:above|over)",
    ),
    (
        "below",
        r"(?:below|under|beneath)",
    ),
    (
        "beside",
        r"(?:beside|next\s+to)",
    ),
    (
        "near",
        r"(?:near|close\s+to)",
    ),
]

OFFSETS = {
    "left_of": (-0.24, 0.0),
    "right_of": (0.24, 0.0),
    "above": (0.0, -0.22),
    "below": (0.0, 0.22),
    "beside": (0.24, 0.0),
    "near": (0.16, 0.04),
}

INVERSE = {
    "left_of": "right_of",
    "right_of": "left_of",
    "above": "below",
    "below": "above",
    "beside": "beside",
    "near": "near",
}


def alias_lookup(categories):
    lookup = {}

    for category in sorted(categories):
        aliases = OBJECT_ALIASES.get(
            category,
            {category, category + "s"},
        )

        for alias in aliases:
            lookup[alias] = category

    return lookup


def identify_mentions(prompt, categories):
    """Identify ordered object mentions in a prompt."""

    lookup = alias_lookup(categories)

    mentions = []

    for match in re.finditer(
        r"\b[a-z]+\b",
        prompt.lower(),
    ):
        word = match.group()

        if word in lookup:
            mentions.append({
                "category": lookup[word],
                "word": word,
                "start": match.start(),
                "end": match.end(),
            })

    return mentions


def identify_relations(prompt, mentions):
    """Find relationships between adjacent mentions."""

    text = prompt.lower()
    relations = []

    for index in range(len(mentions) - 1):
        first = mentions[index]
        second = mentions[index + 1]

        between = text[
            first["end"]:second["start"]
        ]

        matched = None

        for relation, pattern in RELATION_PATTERNS:
            if re.search(pattern, between):
                matched = relation
                break

        if matched is not None:
            relations.append({
                "subject_index": index,
                "object_index": index + 1,
                "relation": matched,
            })

    return relations


def construct_layout(mentions, relations):
    """Assign relative coordinates to object mentions."""

    count = len(mentions)

    if count == 0:
        return []

    adjacency = {
        index: []
        for index in range(count)
    }

    for relation in relations:
        subject = relation["subject_index"]
        target = relation["object_index"]
        kind = relation["relation"]

        dx, dy = OFFSETS[kind]

        # Subject position relative to target.
        adjacency[target].append(
            (subject, dx, dy)
        )

        adjacency[subject].append(
            (target, -dx, -dy)
        )

    positions = {}
    component_index = 0

    for start in range(count):
        if start in positions:
            continue

        positions[start] = (
            component_index * 0.5,
            0.0,
        )

        queue = [start]

        while queue:
            current = queue.pop(0)
            x, y = positions[current]

            for neighbor, dx, dy in adjacency[current]:
                proposed = (
                    x + dx,
                    y + dy,
                )

                if neighbor not in positions:
                    positions[neighbor] = proposed
                    queue.append(neighbor)

        component_index += 1

    xs = [
        position[0]
        for position in positions.values()
    ]

    ys = [
        position[1]
        for position in positions.values()
    ]

    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)

    span_x = max_x - min_x
    span_y = max_y - min_y

    scale = min(
        1.0,
        0.7 / span_x if span_x else 1.0,
        0.7 / span_y if span_y else 1.0,
    )

    center_x = (min_x + max_x) / 2
    center_y = (min_y + max_y) / 2

    return [
        (
            round(
                0.5
                + (positions[index][0] - center_x)
                * scale,
                6,
            ),
            round(
                0.5
                + (positions[index][1] - center_y)
                * scale,
                6,
            ),
        )
        for index in range(count)
    ]


def generate_spatial_scene(
    prompt,
    learned,
    seed=1337,
    variation=0.5,
):
    """Generate a scene with inferred spatial placement."""

    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError(
            "Prompt must be a non-empty string"
        )

    mentions = identify_mentions(
        prompt,
        learned.keys(),
    )

    if not mentions:
        return {
            "project": "MELODIA AI",
            "version": VERSION,
            "status": "unsupported",
            "prompt": prompt,
            "reason": "No supported objects found",
            "supported_categories": sorted(
                learned.keys()
            ),
        }

    relations = identify_relations(
        prompt,
        mentions,
    )

    centers = construct_layout(
        mentions,
        relations,
    )

    # V1.6 reconstructs each object and supplies
    # consistent geometric variation.
    base_scene = build_scene(
        " ".join(
            mention["category"]
            for mention in mentions
        ),
        learned,
        seed=seed,
        variation=variation,
    )

    if base_scene["status"] != "generated":
        raise ValueError(
            "Base scene generation failed"
        )

    if len(base_scene["objects"]) != len(mentions):
        raise ValueError(
            "Base object count mismatch"
        )

    objects = []

    object_size = min(
        0.55,
        0.8 / len(mentions),
    )

    for index, (obj, center) in enumerate(
        zip(base_scene["objects"], centers)
    ):
        components = place_object(
            obj["components"],
            center,
            object_size,
        )

        objects.append({
            **obj,
            "id": f"object_{index + 1}",
            "center": {
                "x": center[0],
                "y": center[1],
            },
            "components": components,
        })

    return {
        "project": "MELODIA AI",
        "version": VERSION,
        "base_version": BASE_VERSION,
        "status": "generated",
        "prompt": prompt,
        "seed": seed,
        "variation": variation,
        "canvas": {
            "width": CANVAS_WIDTH,
            "height": CANVAS_HEIGHT,
        },
        "objects": objects,
        "relationships": [
            {
                "subject": (
                    f"object_{relation['subject_index'] + 1}"
                ),
                "relation": relation["relation"],
                "target": (
                    f"object_{relation['object_index'] + 1}"
                ),
            }
            for relation in relations
        ],
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--prompt",
        default=(
            "A tree to the left of a house "
            "and a flower to the right of a house"
        ),
    )

    parser.add_argument(
        "--output",
        default="melodia_spatial_scene_output",
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

    scene = generate_spatial_scene(
        args.prompt,
        learned,
        seed=args.seed,
        variation=args.variation,
    )

    (
        output / "spatial_scene.json"
    ).write_text(
        json.dumps(
            scene,
            indent=2,
        ),
        encoding="utf-8",
    )

    if scene["status"] == "generated":
        svg = render_scene_svg(scene)

        (
            output / "spatial_scene.svg"
        ).write_text(
            svg,
            encoding="utf-8",
        )

    print(
        "MELODIA SPATIAL RELATIONSHIP ENGINE V1.7"
    )

    print("Prompt:", args.prompt)
    print("Status:", scene["status"])

    if scene["status"] == "generated":
        print(
            "Objects:",
            len(scene["objects"]),
        )

        print(
            "Relationships:",
            len(scene["relationships"]),
        )

    print("Output:", output)


if __name__ == "__main__":
    main()
