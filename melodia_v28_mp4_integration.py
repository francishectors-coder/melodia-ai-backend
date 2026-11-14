
"""
MELODIA AI V2.8
Prompt-to-MP4 Production Integration

Connects:
    V2.8 Prompt Scene Engine
    V2.8 Cinematic Integration
    V2.5 Video Production Engine

Features:
    - One-prompt cinematic MP4 production
    - English captions
    - Optional user-supplied bilingual captions
    - Optional instrumental background music
    - Landscape 16:9 and portrait 9:16
    - Exact-duration cinematic planning
    - Existing engines remain unchanged

Requirements:
    Python 3.11+
    FFmpeg and FFprobe
    CairoSVG
    Existing MELODIA AI engine modules
"""

from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path

from melodia_prompt_cinematic_integration import (
    generate_cinematic_plan,
)

from melodia_video_production_engine import (
    produce_video,
)

VERSION = "2.8"

ASPECTS = {
    "16:9": (1280, 720),
    "9:16": (720, 1280),
}


def _positive_number(value, label):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError(
            f"{label} must be a positive finite number"
        )

    return float(value)


def _validate_language(language):
    if language is None:
        return None

    if (
        not isinstance(language, str)
        or not language.strip()
        or language.strip().lower() == "en"
    ):
        raise ValueError(
            "Second language must be a non-English code"
        )

    return language.strip().lower()


def _load_bilingual_captions(source):
    """
    Load optional user-provided translations.

    Accepted JSON format:

    {
        "scene_001": "Translated text",
        "scene_002": "Translated text"
    }

    No automatic translation is performed.
    """

    if source is None:
        return {}

    if isinstance(source, dict):
        data = source
    else:
        data = json.loads(
            Path(source).read_text(encoding="utf-8")
        )

    if not isinstance(data, dict):
        raise ValueError(
            "Bilingual captions must be a JSON object"
        )

    for key, value in data.items():
        if (
            not isinstance(key, str)
            or not isinstance(value, str)
        ):
            raise ValueError(
                "Bilingual caption keys and values "
                "must be strings"
            )

    return data


def prepare_production_plan(
    integration_result,
    *,
    bilingual_language=None,
    bilingual_captions=None,
):
    """
    Convert a V2.8 integration result into a V2.3
    plan suitable for the V2.5 production engine.

    The original integration result is not modified.
    """

    if not isinstance(integration_result, dict):
        raise ValueError(
            "Integration result must be a dictionary"
        )

    if integration_result.get("version") != VERSION:
        raise ValueError(
            "Expected a V2.8 integration result"
        )

    language = _validate_language(
        bilingual_language
    )

    translations = _load_bilingual_captions(
        bilingual_captions
    )

    if translations and language is None:
        raise ValueError(
            "A second language must be selected "
            "when bilingual captions are provided"
        )

    cinematic = integration_result.get(
        "cinematic_plan"
    )

    if not isinstance(cinematic, dict):
        raise ValueError(
            "Missing cinematic plan"
        )

    if cinematic.get("version") != "2.3":
        raise ValueError(
            "Expected a V2.3 cinematic plan"
        )

    plan = copy.deepcopy(cinematic)

    scenes = plan.get("scenes")

    if not isinstance(scenes, list) or not scenes:
        raise ValueError(
            "Cinematic plan contains no scenes"
        )

    for index, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            raise ValueError(
                f"Invalid scene {index + 1}"
            )

        scene_id = scene.get(
            "scene_id",
            f"scene_{index + 1:03d}",
        )

        description = scene.get("description", "")

        if (
            not isinstance(description, str)
            or not description.strip()
        ):
            raise ValueError(
                f"Scene {index + 1} has no "
                "English description"
            )

        english = description.strip()

        captions = scene.get("captions", {})

        if captions is None:
            captions = {}

        if not isinstance(captions, dict):
            raise ValueError(
                f"Invalid captions in scene {index + 1}"
            )

        captions = dict(captions)

        existing_english = captions.get(
            "en",
            scene.get("caption_en", ""),
        )

        if (
            isinstance(existing_english, str)
            and existing_english.strip()
        ):
            english = existing_english.strip()

        captions["en"] = english

        if language is not None:
            translated = translations.get(scene_id)

            if translated is not None:
                captions[language] = translated

        scene["captions"] = captions

    return plan


def produce_v28_video(
    *,
    prompt=None,
    integration_result=None,
    output,
    duration_seconds=60,
    aspect_ratio="16:9",
    scene_seconds=10,
    camera_intensity=0.35,
    transition_duration=1.0,
    seed=None,
    fps=30,
    bilingual_language=None,
    bilingual_captions=None,
    music=None,
    music_volume=0.22,
    captions=True,
    ffmpeg="ffmpeg",
):
    """
    Generate a cinematic MP4 from a prompt or
    a previously generated V2.8 integration plan.

    Exactly one input source must be supplied.
    """

    if (prompt is None) == (
        integration_result is None
    ):
        raise ValueError(
            "Provide either a prompt or "
            "an integration result, not both"
        )

    if aspect_ratio not in ASPECTS:
        raise ValueError(
            "Unsupported aspect ratio"
        )

    if not isinstance(captions, bool):
        raise ValueError(
            "captions must be boolean"
        )

    if prompt is not None:
        integration_result = generate_cinematic_plan(
            prompt=prompt,
            duration_seconds=duration_seconds,
            aspect_ratio=aspect_ratio,
            scene_seconds=scene_seconds,
            camera_intensity=camera_intensity,
            transition_duration=transition_duration,
            seed=seed,
        )
    else:
        plan_aspect = integration_result.get(
            "aspect_ratio"
        )

        if plan_aspect != aspect_ratio:
            raise ValueError(
                "Requested aspect ratio differs "
                "from the existing cinematic plan"
            )

    production_plan = prepare_production_plan(
        integration_result,
        bilingual_language=bilingual_language,
        bilingual_captions=bilingual_captions,
    )

    requested_duration = _positive_number(
        integration_result.get(
            "requested_duration_seconds"
        ),
        "Requested duration",
    )

    planned_duration = _positive_number(
        production_plan.get(
            "total_output_duration_seconds"
        ),
        "Planned duration",
    )

    if abs(
        requested_duration - planned_duration
    ) > 0.001:
        raise ValueError(
            "Cinematic duration does not match "
            "the requested duration"
        )

    result = produce_video(
        production_plan,
        output,
        aspect=aspect_ratio,
        fps=fps,
        bilingual_language=bilingual_language,
        music=music,
        music_volume=music_volume,
        captions=captions,
        ffmpeg=ffmpeg,
    )

    return {
        "project": "MELODIA AI",
        "version": VERSION,
        "engine": "prompt_mp4_integration",
        "requested_duration_seconds": (
            requested_duration
        ),
        "planned_duration_seconds": (
            planned_duration
        ),
        "scene_count": len(
            production_plan["scenes"]
        ),
        "production": result,
    }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "MELODIA AI V2.8 Prompt-to-MP4 "
            "Production Integration"
        )
    )

    source = parser.add_mutually_exclusive_group(
        required=True
    )

    source.add_argument(
        "--prompt",
        help="Natural-language video prompt",
    )

    source.add_argument(
        "--input",
        help="Existing V2.8 cinematic JSON plan",
    )

    parser.add_argument(
        "--output",
        required=True,
        help="Destination MP4 file",
    )

    parser.add_argument(
        "--duration",
        type=float,
        default=60,
    )

    parser.add_argument(
        "--aspect",
        choices=ASPECTS,
        default="16:9",
    )

    parser.add_argument(
        "--scene-seconds",
        type=float,
        default=10,
    )

    parser.add_argument(
        "--camera-intensity",
        type=float,
        default=0.35,
    )

    parser.add_argument(
        "--transition-duration",
        type=float,
        default=1.0,
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=None,
    )

    parser.add_argument(
        "--fps",
        type=int,
        default=30,
    )

    parser.add_argument(
        "--bilingual-language",
        default=None,
    )

    parser.add_argument(
        "--bilingual-captions",
        default=None,
        help="Optional JSON translation file",
    )

    parser.add_argument(
        "--music",
        default=None,
        help="Optional instrumental audio file",
    )

    parser.add_argument(
        "--music-volume",
        type=float,
        default=0.22,
    )

    parser.add_argument(
        "--no-captions",
        action="store_true",
    )

    parser.add_argument(
        "--ffmpeg",
        default="ffmpeg",
    )

    args = parser.parse_args()

    existing_plan = None

    if args.input:
        existing_plan = json.loads(
            Path(args.input).read_text(
                encoding="utf-8"
            )
        )

    result = produce_v28_video(
        prompt=args.prompt,
        integration_result=existing_plan,
        output=args.output,
        duration_seconds=args.duration,
        aspect_ratio=args.aspect,
        scene_seconds=args.scene_seconds,
        camera_intensity=args.camera_intensity,
        transition_duration=args.transition_duration,
        seed=args.seed,
        fps=args.fps,
        bilingual_language=args.bilingual_language,
        bilingual_captions=args.bilingual_captions,
        music=args.music,
        music_volume=args.music_volume,
        captions=not args.no_captions,
        ffmpeg=args.ffmpeg,
    )

    print(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
