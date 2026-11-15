"""
MELODIA AI V2.8
Automatic Prompt-to-Scene Generation Engine

Deterministic natural-language geometric scene planner.

Supports:
- Object recognition and spatial relationships
- Stable category-based continuity identities
- Multiple scenes
- Landscape and portrait aspect ratios
- Video durations up to 600 seconds
- JSON output for V2.3 orchestration

Python 3.11+
Standard library only.

Previous MELODIA AI versions remain unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

VERSION = "2.8"

SUPPORTED_ASPECTS = {
    "16:9": (1280, 720),
    "9:16": (720, 1280),
}

OBJECT_ALIASES = {
    "tree": ("tree", "trees"),
    "house": ("house", "houses", "home", "homes"),
    "flower": ("flower", "flowers", "rose", "roses"),
    "person": (
        "person", "people", "man", "woman",
        "boy", "girl", "child", "children",
    ),
    "animal": (
        "animal", "animals", "dog", "cat",
        "horse", "bird", "cow", "deer",
    ),
    "vehicle": (
        "vehicle", "vehicles", "car", "cars",
        "truck", "bus", "bicycle",
    ),
    "mountain": (
        "mountain", "mountains", "hill", "hills",
    ),
    "sun": ("sun", "sunrise", "sunset"),
    "moon": ("moon", "moonlight"),
    "cloud": ("cloud", "clouds"),
    "river": ("river", "stream"),
    "lake": ("lake", "pond"),
    "church": ("church", "chapel"),
    "building": ("building", "buildings", "tower"),
    "boat": ("boat", "ship", "sailboat"),
    "road": ("road", "street", "path"),
    "star": ("star", "stars"),
}

POSITION_X = {
    "left": 0.22,
    "center": 0.50,
    "right": 0.78,
}

DEPTH_Y = {
    "background": 0.28,
    "middle": 0.55,
    "foreground": 0.78,
}

POSITION_RE = re.compile(
    r"\b(?:on|to|at|in)\s+the\s+"
    r"(left|right|center|centre|middle)\b"
    r"|\b(left|right)\s+side\b",
    re.IGNORECASE,
)

DEPTH_RE = re.compile(
    r"\b(background|middle|foreground)\b",
    re.IGNORECASE,
)

SCENE_SPLIT = re.compile(
    r"\s*(?:\n+|(?<=[.!?])\s+|;)\s*"
)

WORD_RE = re.compile(r"[a-z]+")

MAX_SCENES = 120

# Categories drawable by the current V2.8 geometric renderer.
DRAWABLE_CATEGORIES = frozenset(("tree", "house", "flower", "animal", "vehicle"))


def _positive_number(value, name, maximum=None):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError(
            f"{name} must be a positive finite number"
        )

    result = float(value)

    if maximum is not None and result > maximum:
        raise ValueError(
            f"{name} cannot exceed {maximum}"
        )

    return result


def _normalize(text):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Prompt must be nonempty text")

    return " ".join(text.lower().split())


def _stable_seed(text):
    digest = hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()

    return int(digest[:12], 16)


def _find_mentions(text):
    mentions = []

    for match in WORD_RE.finditer(text):
        token = match.group()

        for category, aliases in OBJECT_ALIASES.items():
            if token in aliases:
                mentions.append({
                    "category": category,
                    "start": match.start(),
                    "end": match.end(),
                })
                break

    return mentions


def _normalize_position(value):
    if value in ("middle", "centre"):
        return "center"

    return value


def _object_phrase(text, mentions, index):
    """
    Isolate the phrase associated with one object.

    Example:
    'house in the middle, tree on the left'

    Each object's position is interpreted separately.
    """

    mention = mentions[index]
    start = mention["end"]

    if index + 1 < len(mentions):
        end = mentions[index + 1]["start"]
    else:
        end = len(text)

    phrase = text[start:end]

    # Avoid borrowing instructions from the next clause.
    phrase = re.split(
        r",|\band\b|\bwhile\b",
        phrase,
        maxsplit=1,
    )[0]

    return phrase.strip()


def _position_for_object(
    text,
    mentions,
    index,
):
    phrase = _object_phrase(
        text,
        mentions,
        index,
    )

    match = POSITION_RE.search(phrase)

    if match:
        value = match.group(1) or match.group(2)
        return _normalize_position(
            value.lower()
        )

    # Support "left tree" and "right flower".
    start = mentions[index]["start"]
    prefix = text[max(0, start - 25):start]

    prefix = re.split(
        r",|\band\b",
        prefix,
    )[-1]

    match = re.search(
        r"\b(left|right|center|centre|middle)\s+$",
        prefix,
    )

    if match:
        return _normalize_position(
            match.group(1)
        )

    return None


def _depth_for_object(
    text,
    mentions,
    index,
):
    phrase = _object_phrase(
        text,
        mentions,
        index,
    )

    match = DEPTH_RE.search(phrase)

    if match:
        return match.group(1).lower()

    return "middle"


def _extract_objects(text):
    mentions = _find_mentions(text)

    if not mentions:
        return [{
            "category": "abstract",
            "position": "center",
            "depth": "middle",
            "occurrence": 1,
        }]

    objects = []
    counts = {}

    for index, mention in enumerate(mentions):
        category = mention["category"]

        counts[category] = (
            counts.get(category, 0) + 1
        )

        position = _position_for_object(
            text,
            mentions,
            index,
        )

        if position is None:
            position = (
                "left", "center", "right"
            )[index % 3]

        depth = _depth_for_object(
            text,
            mentions,
            index,
        )

        objects.append({
            "category": category,
            "position": position,
            "depth": depth,
            "occurrence": counts[category],
        })

    return objects


def _scene_segments(prompt):
    segments = [
        part.strip()
        for part in SCENE_SPLIT.split(prompt)
        if part.strip()
    ]

    return segments or [prompt.strip()]



def _caption_for_scene(description, objects, scene_index, scene_count):
    """Produce a short factual caption from drawable objects, never prompt text.

    This geometric version describes what it can draw. Creative lyrics,
    narration and arbitrary prompt-to-caption generation are separate features.
    """
    unique = []
    for obj in objects:
        category = obj["category"]
        if category in DRAWABLE_CATEGORIES and category not in [o["category"] for o in unique]:
            unique.append(obj)
    if not unique:
        raise ValueError("Cannot caption a scene without drawable objects")

    focus = unique[scene_index % len(unique)]
    location = {
        "left": "on the left",
        "right": "on the right",
        "center": "in the center",
    }[focus["position"]]
    article = "An" if focus["category"][0] in "aeiou" else "A"
    return f"{article} {focus['category']} {location}"


def _build_scene(
    description,
    scene_index,
    duration,
    scene_count=1,
    unique_description=False,
    fallback_objects=None,
):
    text = _normalize(description)

    extracted = [
        item for item in _extract_objects(text)
        if item["category"] in DRAWABLE_CATEGORIES
    ]
    # Instruction-only sentences are not separate abstract visual objects.
    # Carry the recognized composition from the full prompt instead.
    if not extracted and fallback_objects:
        extracted = [dict(item) for item in fallback_objects]
    if not extracted:
        raise ValueError(
            "Prompt has no drawable objects. Current geometric renderer supports: "
            + ", ".join(sorted(DRAWABLE_CATEGORIES))
        )

    objects = []

    for item in extracted:
        category = item["category"]
        occurrence = item["occurrence"]

        identity = f"{category}_{occurrence}"

        objects.append({
            "id": identity,
            "category": category,
            "continuity_id": identity,
            "center": {
                "x": POSITION_X[
                    item["position"]
                ],
                "y": DEPTH_Y[
                    item["depth"]
                ],
            },
            "depth": item["depth"],
        })

    # Always derive display text from visible objects, not generation commands.
    caption = _caption_for_scene(
        description, extracted, scene_index, scene_count
    )

    return {
        "scene_id": f"scene_{scene_index + 1:03d}",
        "description": description,
        "duration": duration,
        "objects": objects,
        "caption_en": caption,
        "captions": {"en": caption},
    }


def generate_prompt_scenes(
    prompt,
    duration_seconds=60,
    aspect_ratio="16:9",
    scene_seconds=10,
):
    normalized = _normalize(prompt)

    total_duration = _positive_number(
        duration_seconds,
        "duration_seconds",
        maximum=600,
    )

    target_duration = _positive_number(
        scene_seconds,
        "scene_seconds",
    )

    if aspect_ratio not in SUPPORTED_ASPECTS:
        raise ValueError(
            "Aspect ratio must be 16:9 or 9:16"
        )

    width, height = SUPPORTED_ASPECTS[
        aspect_ratio
    ]

    segments = _scene_segments(prompt)

    # Extract supported visual objects from the full prompt before splitting
    # it into scene descriptions. This prevents text-only directions from
    # producing abstract-only scenes and preserves explicit object positions.
    fallback_objects = [
        item for item in _extract_objects(normalized)
        if item["category"] in DRAWABLE_CATEGORIES
    ]
    if not fallback_objects:
        raise ValueError(
            "Prompt has no drawable objects. Current geometric renderer supports: "
            + ", ".join(sorted(DRAWABLE_CATEGORIES))
        )

    requested_count = max(
        len(segments),
        math.ceil(
            total_duration / target_duration
        ),
    )

    scene_count = min(
        MAX_SCENES,
        requested_count,
    )

    # Avoid zero-length or negative scene durations.
    scene_count = min(
        scene_count,
        max(
            1,
            int(total_duration / 0.001),
        ),
    )

    if scene_count < 1:
        scene_count = 1

    scenes = []

    # Distribute scene descriptions deterministically.
    # When the duration requires additional scenes,
    # descriptions repeat in their original order.
    for index in range(scene_count):
        description = segments[
            index % len(segments)
        ]

        start = (
            total_duration * index / scene_count
        )

        end = (
            total_duration * (index + 1) / scene_count
        )

        duration = round(
            end - start,
            6,
        )

        scenes.append(
            _build_scene(
                description,
                index,
                duration,
                scene_count,
                index < len(segments),
                fallback_objects=fallback_objects,
            )
        )

    # Ensure the sum of durations matches the target.
    if len(scenes) > 1:
        previous = sum(
            scene["duration"]
            for scene in scenes[:-1]
        )

        scenes[-1]["duration"] = round(
            total_duration - previous,
            6,
        )

    identities = sorted({
        obj["continuity_id"]
        for scene in scenes
        for obj in scene["objects"]
    })

    return {
        "project": "MELODIA AI",
        "version": VERSION,
        "prompt": prompt.strip(),
        "seed": _stable_seed(normalized),
        "aspect_ratio": aspect_ratio,
        "width": width,
        "height": height,
        "duration_seconds": total_duration,
        "scene_count": len(scenes),
        "object_identities": identities,
        "scenes": scenes,
    }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "MELODIA AI V2.8 Prompt-to-Scene Engine"
        )
    )

    parser.add_argument(
        "--prompt",
        required=True,
    )

    parser.add_argument(
        "--output",
        required=True,
    )

    parser.add_argument(
        "--duration",
        type=float,
        default=60,
    )

    parser.add_argument(
        "--aspect",
        choices=tuple(SUPPORTED_ASPECTS),
        default="16:9",
    )

    parser.add_argument(
        "--scene-seconds",
        type=float,
        default=10,
    )

    args = parser.parse_args()

    result = generate_prompt_scenes(
        prompt=args.prompt,
        duration_seconds=args.duration,
        aspect_ratio=args.aspect,
        scene_seconds=args.scene_seconds,
    )

    destination = Path(args.output)

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination.write_text(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print("MELODIA AI V2.8 scene plan generated")
    print("Scenes:", result["scene_count"])
    print("Duration:", result["duration_seconds"])
    print("Aspect:", result["aspect_ratio"])
    print("Output:", destination)


if __name__ == "__main__":
    main()
