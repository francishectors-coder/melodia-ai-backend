
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


def _make_ass(plan, path, width, height, bilingual_language=None, captions=True,
              promo_seconds=0.0):
    scenes = plan["scenes"]
    timeline = plan["scene_timeline"]

    if len(scenes) != len(timeline):
        raise ValueError("Scene and timeline lengths differ")

    portrait = height > width
    font_size = 42 if portrait else 32
    margin_v = 285 if portrait else 110
    margin_h = 42 if portrait else 35

    watermark_size = 24 if portrait else 20
    watermark_margin = 30 if portrait else 24

    # Portrait captions sit above the green ground, with room for two lines.
    # Landscape caption styling remains unchanged.
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
            f"-1,0,0,0,100,100,0,0,1,2,1,2,{margin_h},{margin_h},{margin_v},1"
        ),
        (
            f"Style: Watermark,Noto Sans,{watermark_size},"
            "&H66FFFFFF,&H66FFFFFF,&H80000000,&HFF000000,"
            f"-1,0,0,0,100,100,0,0,1,1,0,9,{watermark_margin},{watermark_margin},{watermark_margin},1"
        ),
        "",
        "[Events]",
        (
            "Format: Layer, Start, End, Style, Name, "
            "MarginL, MarginR, MarginV, Effect, Text"
        ),
    ]

    # Watermark is independent of caption mode and stays on screen throughout.
    duration = _positive(plan.get("total_output_duration_seconds"), "planned video duration")
    lines.append(
        f"Dialogue: 1,{_ass_time(0)},{_ass_time(duration)},"
        "Watermark,,0,0,0,,MELODIA AI"
    )

    if promo_seconds:
        promo_start = duration
        promo_end = duration + promo_seconds
        center_x = width // 2
        center_y = height // 2
        promo_size = 64 if height > width else 56
        tagline_size = 32 if height > width else 28
        url_size = 25 if height > width else 23
        lines.extend([
            f"Dialogue: 2,{_ass_time(promo_start)},{_ass_time(promo_end)},"
            f"Default,,0,0,0,,{{\\an5\\pos({center_x},{center_y - int(height * .13)})"
            f"\\fs{promo_size}\\c&H0077C8E8&}}MELODIA AI",
            f"Dialogue: 2,{_ass_time(promo_start)},{_ass_time(promo_end)},"
            f"Default,,0,0,0,,{{\\an5\\pos({center_x},{center_y})"
            f"\\fs{tagline_size}}}Create. Inspire. Share.",
            f"Dialogue: 2,{_ass_time(promo_start)},{_ass_time(promo_end)},"
            f"Default,,0,0,0,,{{\\an5\\pos({center_x},{center_y + int(height * .14)})"
            f"\\fs{url_size}}}melodia-ai-backend.onrender.com",
        ])
        # Extend the watermark event to the full playback duration.
        lines[lines.index(next(x for x in lines if x.startswith("Dialogue: 1,")))] = (
            f"Dialogue: 1,{_ass_time(0)},{_ass_time(promo_end)},"
            "Watermark,,0,0,0,,MELODIA AI"
        )

    count = 0

    if captions:
        for i, (scene, item) in enumerate(zip(scenes, timeline)):
            start = float(item["start_seconds"])
            end = float(item["end_seconds"])

            if not (
                math.isfinite(start)
                and math.isfinite(end)
                and 0 <= start < end
            ):
                raise ValueError(f"Invalid scene timeline {i}")

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
    promo_seconds=0.0,
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

    if (isinstance(promo_seconds, bool) or
            not isinstance(promo_seconds, (int, float)) or
            not math.isfinite(promo_seconds) or
            promo_seconds < 0 or promo_seconds > 5):
        raise ValueError("promo_seconds must be between 0 and 5")

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

    # V2.6 duration synchronization correction:
    # Read the planned duration once and use it
    # to limit both audio and final MP4 output.
    target_duration = _positive(
        plan.get("total_output_duration_seconds"),
        "planned video duration"
    )

    total_duration = target_duration + float(promo_seconds)

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

        caption_count = _make_ass(
            plan,
            ass,
            width,
            height,
            bilingual_language,
            captions=captions,
            promo_seconds=promo_seconds,
        )

        command = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(silent),
        ]

        if promo_seconds:
            command += [
                "-f", "lavfi",
                "-i", (f"color=c=0x101B32:s={width}x{height}:"
                       f"r={fps}:d={promo_seconds:.6f}"),
            ]

        music_input_index = 2 if promo_seconds else 1
        if music_path:
            command += ["-stream_loop", "-1", "-i", str(music_path)]

        if promo_seconds:
            # Concatenate the existing main video with a static closing card.
            # Apply the same ASS overlay to both so the watermark persists.
            command += [
                "-filter_complex",
                ("[0:v]setpts=PTS-STARTPTS,format=yuv420p[main];"
                 "[1:v]setpts=PTS-STARTPTS,format=yuv420p[ending];"
                 "[main][ending]concat=n=2:v=1:a=0[joined];"
                 f"[joined]ass={_filter_path(ass)}[finalv]"),
                "-map", "[finalv]",
            ]
        else:
            command += ["-vf", "ass=" + _filter_path(ass),
                        "-map", "0:v:0"]

        if music_path:
            command += [
                "-map", f"{music_input_index}:a:0",
                "-af",
                (f"volume={volume:.6f},"
                 f"atrim=duration={total_duration:.6f},"
                 "asetpts=PTS-STARTPTS"),
                "-c:a", "aac", "-b:a", "128k",
            ]
        else:
            command += ["-an"]

        command += [
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
            "-pix_fmt", "yuv420p",
            "-t", f"{total_duration:.6f}",
            "-movflags", "+faststart", str(destination),
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
        "watermark": "MELODIA AI",
        "bilingual_language": bilingual_language,
        "music": bool(music_path),
        "expected_duration_seconds": total_duration,
        "main_duration_seconds": target_duration,
        "promotional_ending_seconds": float(promo_seconds),
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

    parser.add_argument(
        "--promo-seconds", type=float, default=0.0,
        help="Optional closing promo length, up to 5 seconds"
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
        promo_seconds=args.promo_seconds,
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
