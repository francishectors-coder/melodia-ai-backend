
"""MELODIA AI - Spatial Relationship Engine V1.7.

Corrected repeated-object reference resolution.

Supports:
- left of / right of
- above / below
- beside / next to
- near
- multiple spatial relationships
- repeated references to an existing object
- deterministic SVG scene generation

Uses existing V1.5 and V1.6 engines.

Standard library only.
Previously validated MELODIA engines remain unchanged.

Limitations:
- Rule-based English parsing
- Known geometric object categories only
- Simple relationships between adjacent object mentions
- Ambiguous references are not fully understood
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


def alias_lookup(categories):
    """Map supported object names to categories."""

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
    """Identify object mentions in reading order."""

    lookup = alias_lookup(categories)
    mentions = []

    text = prompt.lower()

    for match in re.finditer(
        r"\b[a-z]+\b",
        text,
    ):
        word = match.group()

        if word not in lookup:
            continue

        prefix = text[:match.start()]

        article_match = re.search(
            r"\b(a|an|the)\s+$",
            prefix,
        )

        article = (
            article_match.group(1)
            if article_match
            else None
        )

        mentions.append({
            "category": lookup[word],
            "word": word,
            "article": article,
            "start": match.start(),
            "end": match.end(),
        })

    return mentions


def resolve_references(mentions):
    """Resolve definite references to earlier objects.

    Example:
    'a house ... the house'
    refers to the same house.

    Indefinite references such as 'a house'
    introduce new objects.

    The resolver uses the most recent matching
    category for a definite reference.
    """

    objects = []
    mention_to_object = {}
    latest_by_category = {}

    for index, mention in enumerate(mentions):
        category = mention["category"]
        article = mention["article"]

        if (
            article == "the"
            and category in latest_by_category
        ):
            object_index = latest_by_category[
                category
            ]

        else:
            object_index = len(objects)

            objects.append({
                "category": category,
                "first_mention": index,
            })

        mention_to_object[index] = object_index

        latest_by_category[category] = (
            object_index
        )

    return objects, mention_to_object


def identify_relations(prompt, mentions):
    """Find relations between adjacent mentions."""

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


def resolve_relations(
    mention_relations,
    mention_to_object,
):
    """Convert mention relations into object relations."""

    resolved = []
    seen = set()

    for relation in mention_relations:
        subject = mention_to_object[
            relation["subject_index"]
        ]

        target = mention_to_object[
            relation["object_index"]
        ]

        if subject == target:
            continue

        key = (
            subject,
            target,
            relation["relation"],
        )

        if key in seen:
            continue

        seen.add(key)

        resolved.append({
            "subject_index": subject,
            "object_index": target,
            "relation": relation["relation"],
        })

    return resolved


def construct_layout(objects, relations):
    """Assign normalized coordinates to unique objects.

    Object relationships form a graph.
    Each relation adds a relative positioning
    constraint between its two objects.
    """

    count = len(objects)

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
                if neighbor in positions:
                    continue

                positions[neighbor] = (
                    x + dx,
                    y + dy,
                )

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

    center_x = (
        min_x + max_x
    ) / 2

    center_y = (
        min_y + max_y
    ) / 2

    return [
        (
            round(
                0.5
                + (
                    positions[index][0]
                    - center_x
                ) * scale,
                6,
            ),
            round(
                0.5
                + (
                    positions[index][1]
                    - center_y
                ) * scale,
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
    """Generate a scene with resolved object references."""

    if (
        not isinstance(prompt, str)
        or not prompt.strip()
    ):
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

    unique_objects, mention_map = (
        resolve_references(mentions)
    )

    mention_relations = identify_relations(
        prompt,
        mentions,
    )

    relations = resolve_relations(
        mention_relations,
        mention_map,
    )

    centers = construct_layout(
        unique_objects,
        relations,
    )

    base_scene = build_scene(
        " ".join(
            obj["category"]
            for obj in unique_objects
        ),
        learned,
        seed=seed,
        variation=variation,
    )

    if base_scene["status"] != "generated":
        raise ValueError(
            "Base scene generation failed"
        )

    if (
        len(base_scene["objects"])
        != len(unique_objects)
    ):
        raise ValueError(
            "Base object count mismatch"
        )

    object_size = min(
        0.55,
        0.8 / len(unique_objects),
    )

    objects = []

    for index, (obj, center) in enumerate(
        zip(
            base_scene["objects"],
            centers,
        )
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
            "and a flower to the right of the house"
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
