
"""MELODIA AI V2.5 — MP4 production with English/bilingual captions and music.

Builds on the unchanged V2.4 geometric renderer. Requires FFmpeg/FFprobe,
CairoSVG, and existing MELODIA modules. No speech or singing is synthesized.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

from melodia_cinematic_video_renderer import render_video

VERSION = "2.5"
ASPECTS = {"16:9": (1280, 720), "9:16": (720, 1280)}


def _positive(value, label):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError(f"{label} must be a positive finite number")
    return float(value)


def _ass_time(seconds):
    centis = max(0, round(seconds * 100))
    hours, rem = divmod(centis, 360000)
    minutes, rem = divmod(rem, 6000)
    secs, cs = divmod(rem, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def _ass_text(value):
    if not isinstance(value, str):
        raise ValueError("Caption text must be a string")
    return (
        value.replace("\\", "\\\\")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("\r", "")
        .replace("\n", r"\N")
    )


def _caption_for_scene(scene, language):
    """Read explicit captions only; never invent translations or lyrics."""
    captions = scene.get("captions", {})
    if captions is None:
        captions = {}
    if not isinstance(captions, dict):
        raise ValueError("scene captions must be an object")

    if language == "en":
        value = captions.get(
            "en",
            scene.get("caption_en", scene.get("caption", ""))
        )
    else:
        value = captions.get(language, "")

    return _ass_text(value)


def _make_ass(plan, path, width, height, bilingual_language=None):
    scenes = plan["scenes"]
    timeline = plan["scene_timeline"]

    if len(scenes) != len(timeline):
        raise ValueError("Scene and timeline lengths differ")

    font_size = 32 if width > height else 27

    # Noto Sans Tamil supports Tamil text and Latin characters.
    # MarginV=110 raises captions above the bottom playback controls.
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        (
            "Format: Name, Fontname, Fontsize, PrimaryColour, "
            "SecondaryColour, OutlineColour, BackColour, Bold, "
            "Italic, Underline, StrikeOut, ScaleX, ScaleY, "
            "Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding"
        ),
        (
            f"Style: Default,Noto Sans Tamil,{font_size},"
            "&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,"
            "-1,0,0,0,100,100,0,0,1,2,1,2,35,35,110,1"
        ),
        "",
        "[Events]",
        (
            "Format: Layer, Start, End, Style, Name, "
            "MarginL, MarginR, MarginV, Effect, Text"
        ),
    ]

    count = 0

    for i, (scene, item) in enumerate(zip(scenes, timeline)):
        start = float(item["start_seconds"])
        end = float(item["end_seconds"])

        if not (
            math.isfinite(start)
            and math.isfinite(end)
            and 0 <= start < end
        ):
            raise ValueError(f"Invalid scene timeline {i}")

        # Avoid overlapping captions during cinematic crossfades.
        if i + 1 < len(timeline):
            end = min(
                end,
                float(timeline[i + 1]["start_seconds"])
            )

        if end <= start:
            continue

        english = _caption_for_scene(scene, "en")

        second = (
            _caption_for_scene(scene, bilingual_language)
            if bilingual_language
            else ""
        )

        text = english + (r"\N" + second if second else "")

        if not text:
            continue

        lines.append(
            f"Dialogue: 0,{_ass_time(start)},"
            f"{_ass_time(end)},Default,,0,0,0,,{text}"
        )
        count += 1

    path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8"
    )

    return count


def _filter_path(path):
    """Escape FFmpeg filtergraph paths, including Windows drive letters."""
    s = str(path.resolve()).replace("\\", "/")
    return (
        s.replace("'", r"'\\''")
        .replace(":", r"\:")
        .replace(",", r"\,")
        .replace("[", r"\[")
        .replace("]", r"\]")
    )


def produce_video(
    plan,
    output,
    *,
    aspect="16:9",
    fps=30,
    bilingual_language=None,
    music=None,
    music_volume=0.22,
    captions=True,
    ffmpeg="ffmpeg",
):
    """Render V2.3 plan through V2.4 and add captions and optional music."""

    if not isinstance(plan, dict) or plan.get("version") != "2.3":
        raise ValueError("Expected a V2.3 orchestration plan")

    if aspect not in ASPECTS:
        raise ValueError("aspect must be '16:9' or '9:16'")

    if isinstance(fps, bool) or not isinstance(fps, int) or fps <= 0:
        raise ValueError("fps must be a positive integer")

    if bilingual_language is not None and (
        not isinstance(bilingual_language, str)
        or not bilingual_language.strip()
        or bilingual_language == "en"
    ):
        raise ValueError(
            "bilingual_language must be a non-English language code"
        )

    if not isinstance(captions, bool):
        raise ValueError("captions must be boolean")

    volume = (
        _positive(music_volume, "music_volume")
        if music is not None
        else 0.0
    )

    if volume > 1:
        raise ValueError("music_volume cannot exceed 1")

    if not shutil.which(ffmpeg):
        raise RuntimeError("FFmpeg not found")

    music_path = (
        Path(music).resolve()
        if music is not None
        else None
    )

    if music_path is not None and not music_path.is_file():
        raise FileNotFoundError(
            f"Music file not found: {music_path}"
        )

    scenes = plan.get("scenes")

    if not isinstance(scenes, list) or not scenes:
        raise ValueError("Missing scenes")

    if captions:
        for i, scene in enumerate(scenes):
            if not _caption_for_scene(scene, "en").strip():
                raise ValueError(
                    f"English caption missing in scene {i}"
                )

    width, height = ASPECTS[aspect]

    destination = Path(output).resolve()
    destination.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with tempfile.TemporaryDirectory(
        prefix="melodia_v25_"
    ) as directory:

        tmp = Path(directory)
        silent = tmp / "silent.mp4"

        render_video(
            plan,
            silent,
            width=width,
            height=height,
            fps=fps,
            ffmpeg=ffmpeg,
        )

        ass = tmp / "captions.ass"

        caption_count = (
            _make_ass(
                plan,
                ass,
                width,
                height,
                bilingual_language
            )
            if captions
            else 0
        )

        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(silent),
        ]

        if music_path:
            command += [
                "-stream_loop",
                "-1",
                "-i",
                str(music_path),
            ]

        if captions:
            command += [
                "-vf",
                "ass=" + _filter_path(ass),
            ]

        command += ["-map", "0:v:0"]

        if music_path:
            command += [
                "-map",
                "1:a:0",
                "-af",
                f"volume={volume:.6f}",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-shortest",
            ]
        else:
            command += ["-an"]

        command += [
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "22",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(destination),
        ]

        subprocess.run(command, check=True)

    return {
        "version": VERSION,
        "output": str(destination),
        "aspect": aspect,
        "width": width,
        "height": height,
        "fps": fps,
        "caption_events": caption_count,
        "bilingual_language": bilingual_language,
        "music": bool(music_path),
        "expected_duration_seconds": plan[
            "total_output_duration_seconds"
        ],
    }


def main():
    parser = argparse.ArgumentParser(
        description="MELODIA AI V2.5 video production"
    )

    parser.add_argument(
        "--input",
        required=True,
        help="V2.3 orchestration JSON"
    )

    parser.add_argument(
        "--output",
        required=True,
        help="Destination MP4"
    )

    parser.add_argument(
        "--aspect",
        choices=ASPECTS,
        default="16:9"
    )

    parser.add_argument(
        "--fps",
        type=int,
        default=30
    )

    parser.add_argument(
        "--bilingual-language",
        default=None
    )

    parser.add_argument(
        "--music",
        default=None,
        help="Optional instrumental audio file"
    )

    parser.add_argument(
        "--music-volume",
        type=float,
        default=0.22
    )

    parser.add_argument(
        "--no-captions",
        action="store_true"
    )

    args = parser.parse_args()

    plan = json.loads(
        Path(args.input).read_text(
            encoding="utf-8"
        )
    )

    result = produce_video(
        plan,
        args.output,
        aspect=args.aspect,
        fps=args.fps,
        bilingual_language=args.bilingual_language,
        music=args.music,
        music_volume=args.music_volume,
        captions=not args.no_captions,
    )

    print(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()
