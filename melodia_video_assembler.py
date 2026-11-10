
# MELODIA AI - MULTILINGUAL VIDEO ASSEMBLER
# Step 1160
# FFmpeg 9.x compatible
# Primary-language and bilingual captions
# Preserves existing completed MP4 files
# Supports landscape and portrait output

import json
import math
import os
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent

PLANS = ROOT / "scene_plans"
CONTENT = ROOT / "generated_content"
OUTPUTS = ROOT / "outputs"

OUTPUTS.mkdir(parents=True, exist_ok=True)

FPS = 15
TRANSITION_SECONDS = 1.0

TEST_JOB_ID = "melodia_worker_test_001"

LANGUAGE_FONTS = {
    "English": "Arial",
    "Tamil": "Nirmala UI",
    "Hindi": "Nirmala UI",
    "Malayalam": "Nirmala UI",
    "Telugu": "Nirmala UI"
}


def get_video_resolution(aspect_ratio):
    if aspect_ratio == "16:9":
        return 854, 480

    if aspect_ratio == "9:16":
        return 480, 854

    raise ValueError(
        "Unsupported aspect ratio: "
        + str(aspect_ratio)
    )


def run_ffmpeg(arguments):
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-nostdin",
        "-y",
        "-threads", "1",
        "-filter_complex_threads", "1"
    ] + arguments

    subprocess.run(
        command,
        check=True
    )


def ass_time(seconds):
    seconds = max(0.0, float(seconds))

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    remaining = seconds % 60

    return (
        f"{hours}:{minutes:02d}:"
        f"{remaining:05.2f}"
    )


def escape_subtitle(value):
    text = str(value or "")

    text = text.replace("\\", " ")
    text = text.replace("{", "(")
    text = text.replace("}", ")")
    text = text.replace("\r", " ")
    text = text.replace("\n", " ")

    return re.sub(
        r"\s+", " ", text
    ).strip()


def create_subtitles(
    records,
    primary_language,
    second_language,
    caption_mode,
    width,
    height,
    destination
):
    portrait = height > width

    primary_font = LANGUAGE_FONTS.get(
        primary_language,
        "Arial"
    )

    second_font = LANGUAGE_FONTS.get(
        second_language,
        "Nirmala UI"
    )

    if portrait:
        primary_size = 22
        second_size = 23
        bottom_margin = 165
        side_margin = 35
    else:
        primary_size = 24
        second_size = 25
        bottom_margin = 105
        side_margin = 45

    header = f"""[Script Info]
Title: MELODIA AI Multilingual Captions
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Arial,{primary_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,2,1,2,{side_margin},{side_margin},{bottom_margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events = []

    for record in records:
        start = float(
            record["start_seconds"]
        )

        end = float(
            record["end_seconds"]
        )

        if end <= start:
            raise ValueError(
                "Invalid subtitle timing"
            )

        primary = escape_subtitle(
            record.get("primary", "")
        )

        translated = escape_subtitle(
            record.get("translated", "")
        )

        if not primary:
            raise ValueError(
                "Primary caption is missing"
            )

        primary_line = (
            r"{\fn"
            + primary_font
            + r"\c&HFFFFFF&\fs"
            + str(primary_size)
            + r"}"
            + primary
        )

        if caption_mode == "bilingual":
            if not translated:
                raise ValueError(
                    "Bilingual translation is missing"
                )

            second_line = (
                r"{\fn"
                + second_font
                + r"\c&H00FFFF&\fs"
                + str(second_size)
                + r"}"
                + translated
            )

            caption = (
                primary_line
                + r"\N"
                + second_line
            )

        else:
            caption = primary_line

        events.append(
            f"Dialogue: 0,{ass_time(start)},"
            f"{ass_time(end)},Caption,,0,0,0,,"
            f"{caption}"
        )

    destination.write_text(
        header + "\n".join(events) + "\n",
        encoding="utf-8-sig"
    )

    return len(events)


def load_captions(job_id, scenes):
    caption_file = (
        CONTENT /
        f"{job_id}_captions.json"
    )

    if not caption_file.is_file():
        raise FileNotFoundError(
            "Caption JSON missing: "
            + str(caption_file)
        )

    data = json.loads(
        caption_file.read_text(
            encoding="utf-8"
        )
    )

    if data.get("job_id") != job_id:
        raise ValueError(
            "Caption job ID mismatch"
        )

    records = data.get("records", [])

    if len(records) != len(scenes):
        raise ValueError(
            "Caption count does not match scenes"
        )

    expected_mode = scenes[0].get(
        "caption_mode", "single"
    )

    expected_primary = scenes[0].get(
        "primary_language", "English"
    )

    expected_second = (
        scenes[0].get("second_language")
        if expected_mode == "bilingual"
        else None
    )

    if data.get("caption_mode") != expected_mode:
        raise ValueError(
            "Caption mode mismatch"
        )

    if (
        data.get("primary_language")
        != expected_primary
    ):
        raise ValueError(
            "Primary language mismatch"
        )

    if (
        data.get("second_language")
        != expected_second
    ):
        raise ValueError(
            "Secondary language mismatch"
        )

    for index, (record, scene) in enumerate(
        zip(records, scenes),
        start=1
    ):
        if record.get("scene_number") != index:
            raise ValueError(
                "Caption scene order mismatch"
            )

        for field in (
            "start_seconds",
            "end_seconds"
        ):
            actual = float(record[field])
            expected = float(scene[field])

            if abs(actual - expected) > 0.01:
                raise ValueError(
                    "Caption timing mismatch"
                )

    return data


def get_scene_images(scenes):
    images = []

    for index, scene in enumerate(
        scenes,
        start=1
    ):
        image = Path(
            scene["image_path"]
        )

        if not image.is_file():
            raise FileNotFoundError(
                f"Scene {index} image missing: "
                + str(image)
            )

        if image.stat().st_size == 0:
            raise ValueError(
                f"Scene {index} image is empty"
            )

        images.append(image)

    return images


def render_video(
    images,
    lengths,
    width,
    height,
    destination,
    subtitle_file=None
):
    count = len(images)

    if count != len(lengths):
        raise ValueError(
            "Scene/image count mismatch"
        )

    if not count:
        raise ValueError(
            "No scenes to render"
        )

    arguments = []

    for image in images:
        arguments.extend([
            "-loop", "1",
            "-framerate", str(FPS),
            "-i", str(image)
        ])

    filters = []
    transitions = []

    for index in range(1, count):
        transition = min(
            TRANSITION_SECONDS,
            lengths[index - 1] / 2,
            lengths[index] / 2
        )

        transitions.append(transition)

    for index in range(count):
        incoming = (
            transitions[index - 1]
            if index > 0 else 0
        )

        duration = lengths[index] + incoming

        filters.append(
            f"[{index}:v]"
            f"trim=duration={duration:.6f},"
            "setpts=PTS-STARTPTS,"
            f"scale={width}:{height}:"
            "force_original_aspect_ratio=increase,"
            f"crop={width}:{height},"
            "setsar=1,"
            f"fps={FPS},"
            "format=yuv420p"
            f"[v{index}]"
        )

    current = "v0"
    elapsed = lengths[0]

    for index in range(1, count):
        transition = transitions[index - 1]
        offset = elapsed - transition

        output_label = f"xf{index}"

        filters.append(
            f"[{current}][v{index}]"
            "xfade=transition=fade:"
            f"duration={transition:.6f}:"
            f"offset={offset:.6f},"
            "format=yuv420p"
            f"[{output_label}]"
        )

        current = output_label
        elapsed += lengths[index]

    if subtitle_file is not None:
        subtitle_path = (
            subtitle_file.resolve()
            .as_posix()
            .replace("\\", "/")
            .replace(":", "\\:")
            .replace("'", "\\'")
        )

        filters.append(
            f"[{current}]"
            f"ass=filename='{subtitle_path}'"
            "[final]"
        )

        current = "final"

    filter_graph = ";".join(filters)

    with tempfile.TemporaryDirectory(
        prefix="melodia_filters_",
        dir=OUTPUTS
    ) as temp_dir:
        filter_file = (
            Path(temp_dir) /
            "filters.txt"
        )

        filter_file.write_text(
            filter_graph,
            encoding="utf-8"
        )

        run_ffmpeg(
            arguments + [
                "-/filter_complex",
                str(filter_file),
                "-map", f"[{current}]",
                "-an",
                "-t", str(sum(lengths)),
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-crf", "28",
                "-r", str(FPS),
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                str(destination)
            ]
        )


def assemble_video(job_id):
    if not re.fullmatch(
        r"[A-Za-z0-9_-]+",
        str(job_id)
    ):
        raise ValueError(
            "Invalid job ID"
        )

    manifest = (
        PLANS /
        f"{job_id}_scenes.json"
    )

    if not manifest.is_file():
        raise FileNotFoundError(
            "Scene plan missing: "
            + str(manifest)
        )

    plan = json.loads(
        manifest.read_text(
            encoding="utf-8"
        )
    )

    if plan.get("job_id") != job_id:
        raise ValueError(
            "Scene plan job ID mismatch"
        )

    scenes = plan.get("scenes", [])

    if not scenes:
        raise ValueError(
            "Scene plan contains no scenes"
        )

    if plan.get("generation_status") not in (
        None,
        "complete"
    ):
        raise RuntimeError(
            "Scene generation is not complete"
        )

    width, height = get_video_resolution(
        plan["aspect_ratio"]
    )

    lengths = [
        float(scene["duration_seconds"])
        for scene in scenes
    ]

    if any(
        not math.isfinite(length)
        or length <= 0
        for length in lengths
    ):
        raise ValueError(
            "Invalid scene duration"
        )

    total_duration = sum(lengths)

    if abs(
        total_duration
        - float(plan["duration_seconds"])
    ) > 0.01:
        raise ValueError(
            "Scene durations do not match"
        )

    images = get_scene_images(scenes)

    output = (
        OUTPUTS /
        f"{job_id}.mp4"
    )

    # Preserve any existing completed video.
    if (
        output.is_file()
        and output.stat().st_size > 0
    ):
        print(
            "Existing MP4 preserved:",
            output
        )
        return output

    caption_mode = scenes[0].get(
        "caption_mode", "single"
    )

    if caption_mode not in (
        "single",
        "bilingual",
        "none"
    ):
        raise ValueError(
            "Unsupported caption mode"
        )

    print(
        "MELODIA AI - MULTILINGUAL ASSEMBLER"
    )
    print("Job ID:", job_id)
    print("Scenes:", len(scenes))
    print("Resolution:", width, "x", height)
    print("Duration:", total_duration)
    print("Caption mode:", caption_mode)

    caption_data = None

    if caption_mode != "none":
        caption_data = load_captions(
            job_id,
            scenes
        )

    with tempfile.TemporaryDirectory(
        prefix="melodia_assembly_",
        dir=OUTPUTS
    ) as temp_dir:
        temp = Path(temp_dir)

        temporary_video = (
            temp /
            "video.mp4"
        )

        subtitle_file = (
            temp /
            "captions.ass"
        )

        caption_count = 0

        if caption_data is not None:
            caption_count = create_subtitles(
                caption_data["records"],
                caption_data["primary_language"],
                caption_data.get(
                    "second_language"
                ),
                caption_mode,
                width,
                height,
                subtitle_file
            )

            if caption_count != len(scenes):
                raise RuntimeError(
                    "Incomplete subtitle events"
                )

        render_video(
            images,
            lengths,
            width,
            height,
            temporary_video,
            (
                subtitle_file
                if caption_count
                else None
            )
        )

        if (
            not temporary_video.is_file()
            or temporary_video.stat().st_size == 0
        ):
            raise RuntimeError(
                "FFmpeg did not create MP4"
            )

        os.replace(
            temporary_video,
            output
        )

    print()
    print(
        "MELODIA AI - VIDEO COMPLETE"
    )
    print("Output:", output)
    print("Duration:", total_duration)
    print("Caption events:", caption_count)
    print(
        "Size:",
        output.stat().st_size,
        "bytes"
    )

    return output


def main():
    print(
        "MELODIA AI - MULTILINGUAL ASSEMBLER"
    )
    print(
        "Use assemble_video(job_id) "
        "from the automatic video worker."
    )
    print(
        "No rendering was started."
    )


if __name__ == "__main__":
    main()
