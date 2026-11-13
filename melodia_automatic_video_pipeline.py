"""MELODIA AI V2.6 — supported-prompt to MP4 pipeline.

Connects V2.3 scene orchestration with V2.5 video production, preserving
all earlier engines. Geometric scene prompts must be supported by V1.9.
No automatic translation, narration, or music synthesis is performed.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path

from melodia_cinematic_orchestration_engine import orchestrate_prompts
from melodia_video_production_engine import produce_video

VERSION = "2.6"
MAX_DURATION = 600.0


def _duration(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite positive number")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{label} must be a finite positive number")
    return float(value)


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty text")
    return value.strip()


def generate_video(
    prompt,
    output,
    *,
    scene_prompts=None,
    english_captions=None,
    bilingual_language=None,
    translated_captions=None,
    scene_duration=10.0,
    transition_duration=1.0,
    aspect="16:9",
    fps=30,
    music=None,
    music_volume=0.22,
    seed=1337,
    variation=0.5,
    camera_intensity=0.35,
    preferred_transition=None,
):
    """Generate MP4 from supported V1.9 prompts and supplied caption text.

    The single ``prompt`` is used as a geometric scene prompt by default.
    For multiple scenes, supply ``scene_prompts`` explicitly. English
    captions default to the scene prompt text; this is not AI-written copy.
    Translations must be provided by the caller, one per scene.
    """
    prompt = _text(prompt, "prompt")
    if scene_prompts is None:
        prompts = [prompt]
    else:
        if not isinstance(scene_prompts, list) or not scene_prompts:
            raise ValueError("scene_prompts must be a nonempty list")
        prompts = [_text(item, f"scene_prompts[{i}]") for i, item in enumerate(scene_prompts)]

    duration = _duration(scene_duration, "scene_duration")
    overlap = _duration(transition_duration, "transition_duration")
    if len(prompts) > 1 and overlap >= duration:
        raise ValueError("transition_duration must be shorter than scene_duration")
    expected = len(prompts) * duration - (len(prompts) - 1) * overlap
    if expected > MAX_DURATION + 1e-6:
        raise ValueError("Video duration cannot exceed 600 seconds")

    if english_captions is None:
        english = prompts[:]
    else:
        if not isinstance(english_captions, list) or len(english_captions) != len(prompts):
            raise ValueError("english_captions must contain one entry per scene")
        english = [_text(item, f"english_captions[{i}]") for i, item in enumerate(english_captions)]

    if bilingual_language is None:
        if translated_captions is not None:
            raise ValueError("translated_captions requires bilingual_language")
    else:
        if not isinstance(bilingual_language, str) or not bilingual_language.strip() or bilingual_language.strip().lower() == "en":
            raise ValueError("bilingual_language must be a non-English language code")
        if not isinstance(translated_captions, list) or len(translated_captions) != len(prompts):
            raise ValueError("translated_captions must contain one entry per scene")
        translated_captions = [
            _text(item, f"translated_captions[{i}]") for i, item in enumerate(translated_captions)
        ]

    # V2.3 orchestrates supported geometric scene prompts only.
    plan = orchestrate_prompts(
        prompts,
        seed=seed,
        variation=variation,
        default_duration=duration,
        camera_intensity=camera_intensity,
        transition_duration=overlap,
        preferred_transition=preferred_transition,
    )
    if len(plan.get("scenes", [])) != len(prompts):
        raise RuntimeError("Orchestration returned an unexpected scene count")

    # Avoid modifying the V2.3 result or any earlier engine state.
    plan = copy.deepcopy(plan)
    for i, scene in enumerate(plan["scenes"]):
        captions = scene.get("captions")
        if captions is None:
            captions = {}
        if not isinstance(captions, dict):
            raise ValueError(f"scene {i} captions must be an object")
        captions = dict(captions)
        captions["en"] = english[i]
        if bilingual_language is not None:
            captions[bilingual_language] = translated_captions[i]
        scene["captions"] = captions

    output_path = Path(output)
    if output_path.suffix.lower() != ".mp4":
        raise ValueError("output must have an .mp4 extension")
    result = produce_video(
        plan,
        output_path,
        aspect=aspect,
        fps=fps,
        bilingual_language=bilingual_language,
        music=music,
        music_volume=music_volume,
        captions=True,
    )
    return {
        "version": VERSION,
        "prompt": prompt,
        "scene_count": len(prompts),
        "video": result,
        "engine_versions": plan.get("engine_versions", {}),
        "note": "Geometric rendering; translations and music are not generated automatically.",
    }


def main():
    parser = argparse.ArgumentParser(description="MELODIA AI V2.6 geometric video pipeline")
    parser.add_argument("--prompt", required=True, help="Supported V1.9 geometric scene prompt")
    parser.add_argument("--output", required=True, help="Destination MP4")
    parser.add_argument("--scenes-json", help="Optional JSON list of geometric scene prompts")
    parser.add_argument("--captions-en-json", help="Optional JSON list of English captions")
    parser.add_argument("--bilingual-language", help="Optional second-language code")
    parser.add_argument("--captions-second-json", help="JSON list of supplied translations")
    parser.add_argument("--scene-duration", type=float, default=10.0)
    parser.add_argument("--transition-duration", type=float, default=1.0)
    parser.add_argument("--aspect", choices=("16:9", "9:16"), default="16:9")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--music", help="Optional existing instrumental audio file")
    parser.add_argument("--music-volume", type=float, default=0.22)
    parser.add_argument("--seed", type=int, default=1337)
    args = parser.parse_args()

    def load_list(path):
        if path is None:
            return None
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, list):
            parser.error(f"{path} must contain a JSON list")
        return data

    result = generate_video(
        args.prompt,
        args.output,
        scene_prompts=load_list(args.scenes_json),
        english_captions=load_list(args.captions_en_json),
        bilingual_language=args.bilingual_language,
        translated_captions=load_list(args.captions_second_json),
        scene_duration=args.scene_duration,
        transition_duration=args.transition_duration,
        aspect=args.aspect,
        fps=args.fps,
        music=args.music,
        music_volume=args.music_volume,
        seed=args.seed,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
