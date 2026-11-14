
"""
MELODIA AI V2.8 - Prompt-to-MP4 Integration

Converts V2.8 cinematic scene plans into V1.9-compatible
geometric scenes before invoking the existing V2.5
production engine.

Earlier MELODIA engines remain unchanged.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import tempfile
from pathlib import Path

from melodia_prompt_cinematic_integration import (
    generate_cinematic_plan,
)
from melodia_video_production_engine import produce_video
from melodia_instrumental_music_engine import generate_instrumental

from melodia_geometric_object_learner import EXAMPLES
from melodia_automatic_structure_learner import learn_all
from melodia_component_relationship_learner import reconstruct
from melodia_prompt_scene_generator import place_object
from melodia_automatic_scene_composer import (
    detect_theme,
    THEMES,
    GROUND_Y,
    object_bounds,
)
from melodia_scene_depth_engine import (
    DEPTH_LAYERS,
    validate_depth_geometry,
)

VERSION = "2.8"

ASPECTS = {
    "16:9": (1280, 720),
    "9:16": (720, 1280),
}

GEOMETRIC_CATEGORIES = {
    "tree",
    "house",
    "flower",
    "animal",
    "vehicle",
}

DEPTH_SIZES = {
    "background": 0.16,
    "middle": 0.23,
    "foreground": 0.29,
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

    if not isinstance(language, str):
        raise ValueError("Invalid second language")

    language = language.strip().lower()

    if not language or language == "en":
        raise ValueError(
            "Second language must be non-English"
        )

    return language


def _load_bilingual_captions(source):
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
        if not isinstance(key, str):
            raise ValueError("Invalid translation key")
        if not isinstance(value, str):
            raise ValueError("Invalid translation text")

    return data


def _convert_object(obj, learned, seed):
    """
    Construct drawable components while preserving
    V2.8 object identity and planned center.
    """

    if not isinstance(obj, dict):
        raise ValueError("Invalid V2.8 object")

    category = obj.get("category")

    if category not in GEOMETRIC_CATEGORIES:
        raise ValueError(
            f"Geometric renderer does not yet support "
            f"category: {category}"
        )

    if category not in learned:
        raise ValueError(
            f"No learned geometry for {category}"
        )

    identity = obj.get("id")
    continuity_id = obj.get("continuity_id")

    if not isinstance(identity, str) or not identity:
        raise ValueError("Missing object identity")

    if (
        not isinstance(continuity_id, str)
        or not continuity_id
    ):
        raise ValueError("Missing continuity identity")

    center = obj.get("center")

    if not isinstance(center, dict):
        raise ValueError("Missing object center")

    x = center.get("x")
    y = center.get("y")

    for name, value in (("x", x), ("y", y)):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not 0 <= value <= 1
        ):
            raise ValueError(
                f"Invalid object center {name}"
            )

    depth = obj.get("depth", "middle")

    if depth not in DEPTH_LAYERS:
        raise ValueError(
            f"Unsupported depth layer: {depth}"
        )

    representation = reconstruct(
        category,
        learned,
        scale=1.0,
        variation=0.0,
        seed=seed,
    )

    if representation.get("status") != "generated":
        raise ValueError(
            f"Could not reconstruct {category}"
        )

    components = place_object(
        representation["components"],
        (float(x), float(y)),
        DEPTH_SIZES[depth],
    )

    result = {
        "id": identity,
        "category": category,
        "continuity_id": continuity_id,
        "center": {
            "x": float(x),
            "y": float(y),
        },
        "depth": depth,
        "depth_order": DEPTH_LAYERS[depth]["order"],
        "depth_scale": DEPTH_LAYERS[depth]["scale"],
        "depth_ground_y": (
            DEPTH_LAYERS[depth]["ground_y"]
        ),
        "seed": seed,
        "components": components,
    }

    # Confirm the generated object remains drawable.
    left, top, right, bottom = object_bounds(result)

    if (
        left < -0.00001
        or top < -0.00001
        or right > 1.00001
        or bottom > 1.00001
    ):
        raise ValueError(
            f"Object geometry outside canvas: {identity}"
        )

    return result


def _convert_scene(scene, learned, seed):
    """
    Convert one V2.8 scene into a V1.9-compatible
    geometric scene without replanning positions.
    """

    if not isinstance(scene, dict):
        raise ValueError("Invalid cinematic scene")

    description = scene.get("description", "")

    if (
        not isinstance(description, str)
        or not description.strip()
    ):
        raise ValueError(
            "Cinematic scene description missing"
        )

    source_objects = scene.get("objects")

    if (
        not isinstance(source_objects, list)
        or not source_objects
    ):
        raise ValueError(
            "Cinematic scene contains no objects"
        )

    objects = []

    for obj in source_objects:
        objects.append(
            _convert_object(
                obj,
                learned,
                seed,
            )
        )

    objects.sort(
        key=lambda item: (
            item["depth_order"],
            item["id"],
        )
    )

    theme = detect_theme(description)

    result = copy.deepcopy(scene)

    result["status"] = "generated"
    result["version"] = "1.9"
    result["base_version"] = "2.8"
    result["prompt"] = description
    result["theme"] = theme
    result["objects"] = objects

    result["canvas"] = {
        "width": 1024,
        "height": 576,
    }

    result["depth_layers"] = copy.deepcopy(
        DEPTH_LAYERS
    )

    result["environment"] = {
        "sky_color": THEMES[theme]["sky"],
        "ground_color": THEMES[theme]["ground"],
        "ground_y": GROUND_Y,
    }

    validate_depth_geometry(result)

    return result


def prepare_production_plan(
    integration_result,
    *,
    bilingual_language=None,
    bilingual_captions=None,
):
    """
    Prepare a V2.3 orchestration plan for the
    existing V2.4/V2.5 rendering pipeline.
    """

    if not isinstance(integration_result, dict):
        raise ValueError(
            "Integration result must be a dictionary"
        )

    if integration_result.get("version") != VERSION:
        raise ValueError(
            "Expected V2.8 integration result"
        )

    language = _validate_language(
        bilingual_language
    )

    translations = _load_bilingual_captions(
        bilingual_captions
    )

    if translations and language is None:
        raise ValueError(
            "Select a second language for translations"
        )

    cinematic = integration_result.get(
        "cinematic_plan"
    )

    if not isinstance(cinematic, dict):
        raise ValueError("Missing cinematic plan")

    if cinematic.get("version") != "2.3":
        raise ValueError(
            "Expected V2.3 orchestration plan"
        )

    plan = copy.deepcopy(cinematic)

    scenes = plan.get("scenes")

    if not isinstance(scenes, list) or not scenes:
        raise ValueError("Missing cinematic scenes")

    learned = learn_all(EXAMPLES)

    converted = []

    for index, scene in enumerate(scenes):
        converted_scene = _convert_scene(
            scene,
            learned,
            seed=1337,
        )

        scene_id = converted_scene.get(
            "scene_id",
            f"scene_{index + 1:03d}",
        )

        description = converted_scene["description"]

        captions = converted_scene.get(
            "captions", {}
        )

        if captions is None:
            captions = {}

        if not isinstance(captions, dict):
            raise ValueError(
                f"Invalid captions in scene {index + 1}"
            )

        captions = dict(captions)

        english = captions.get(
            "en",
            converted_scene.get("caption_en", ""),
        )

        if (
            not isinstance(english, str)
            or not english.strip()
        ):
            english = description

        captions["en"] = english.strip()

        if language is not None:
            translated = translations.get(scene_id)

            if translated is not None:
                captions[language] = translated

        converted_scene["captions"] = captions

        converted.append(converted_scene)

    plan["scenes"] = converted

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
    auto_music=True,
    music_volume=0.22,
    captions=True,
    ffmpeg="ffmpeg",
):
    """
    Render an MP4 from a prompt or an existing
    V2.8 cinematic integration result.
    """

    if (prompt is None) == (
        integration_result is None
    ):
        raise ValueError(
            "Provide exactly one input source"
        )

    if aspect_ratio not in ASPECTS:
        raise ValueError("Unsupported aspect ratio")

    if not isinstance(captions, bool):
        raise ValueError("captions must be boolean")

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
        if not isinstance(integration_result, dict):
            raise ValueError(
                "Invalid integration result"
            )

        if (
            integration_result.get("aspect_ratio")
            != aspect_ratio
        ):
            raise ValueError(
                "Existing plan aspect ratio mismatch"
            )

    production_plan = prepare_production_plan(
        integration_result,
        bilingual_language=bilingual_language,
        bilingual_captions=bilingual_captions,
    )

    requested = _positive_number(
        integration_result.get(
            "requested_duration_seconds"
        ),
        "Requested duration",
    )

    planned = _positive_number(
        production_plan.get(
            "total_output_duration_seconds"
        ),
        "Planned duration",
    )

    if abs(requested - planned) > 0.001:
        raise ValueError(
            "Planned duration differs from request"
        )

    if not isinstance(auto_music, bool):
        raise ValueError("auto_music must be boolean")
    if music is not None and not isinstance(music, (str, Path)):
        raise ValueError("music must be a file path or None")
    if music is not None and not Path(music).is_file():
        raise FileNotFoundError(f"Music file not found: {music}")

    # The V2.5 engine already supports music files. Generate a temporary
    # soundtrack only when automatic music is enabled and no file was given.
    # Its lifetime covers the entire MP4 production call.
    with tempfile.TemporaryDirectory(prefix="melodia_v28_music_") as music_dir:
        selected_music = music
        music_metadata = None
        if selected_music is None and auto_music:
            soundtrack_prompt = prompt
            if soundtrack_prompt is None:
                soundtrack_prompt = integration_result.get("prompt")
            if not isinstance(soundtrack_prompt, str) or not soundtrack_prompt.strip():
                soundtrack_prompt = " ".join(
                    str(scene.get("description", ""))
                    for scene in production_plan["scenes"]
                )
            selected_music = str(Path(music_dir) / "instrumental.wav")
            music_metadata = generate_instrumental(
                soundtrack_prompt,
                selected_music,
                duration_seconds=requested,
            )

        result = produce_video(
            production_plan,
            output,
            aspect=aspect_ratio,
            fps=fps,
            bilingual_language=bilingual_language,
            music=selected_music,
            music_volume=music_volume,
            captions=captions,
            ffmpeg=ffmpeg,
        )

    music_mode = "provided" if music is not None else (
        "automatic" if auto_music else "disabled"
    )

    return {
        "project": "MELODIA AI",
        "version": VERSION,
        "engine": "prompt_mp4_integration",
        "requested_duration_seconds": requested,
        "planned_duration_seconds": planned,
        "scene_count": len(
            production_plan["scenes"]
        ),
        "music_mode": music_mode,
        "generated_music": (
            {key: value for key, value in music_metadata.items() if key != "output"}
            if music_metadata is not None else None
        ),
        "production": result,
    }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "MELODIA AI V2.8 Prompt-to-MP4 Integration"
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
        help="Existing V2.8 integration JSON",
    )

    parser.add_argument(
        "--output",
        required=True,
        help="Destination MP4",
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
    )

    parser.add_argument(
        "--music",
        default=None,
    )

    parser.add_argument(
        "--no-music",
        action="store_true",
        help="Disable automatic music (unless --music supplies a file)",
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
        auto_music=not args.no_music,
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
