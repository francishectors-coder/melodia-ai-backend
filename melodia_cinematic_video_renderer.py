
"""MELODIA AI V2.4 - Geometric cinematic MP4 renderer.

V2.8 reading-focused compatibility:
- Static backgrounds throughout each scene
- Cinematic transitions between scenes
- Native landscape and portrait SVG composition
- Original object proportions and continuity preserved
- Existing timing, caption and audio pipelines unchanged

Requires FFmpeg and CairoSVG.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

VERSION = "2.4"

SVG_NS = "http://www.w3.org/2000/svg"


def _positive(value, name):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError(
            f"{name} must be a positive finite number"
        )
    return float(value)


def _identities(scene):
    return {
        obj.get("continuity_id", obj.get("id"))
        for obj in scene.get("objects", [])
        if isinstance(obj, dict)
    }


def _camera_endpoints(scenes, cameras):
    """Validate camera plans and preserve continuity information."""
    endpoints = []

    for i, camera in enumerate(cameras):
        keyframes = camera.get("keyframes")

        if not isinstance(keyframes, list) or len(keyframes) < 2:
            raise ValueError(
                f"Missing camera keyframes for scene {i}"
            )

        start = dict(keyframes[0])
        end = dict(keyframes[-1])

        for frame in (start, end):
            for name in ("x", "y", "zoom"):
                value = frame.get(name)

                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                ):
                    raise ValueError(
                        f"Invalid camera {name}"
                    )

            if not (
                0 <= frame["x"] <= 1
                and 0 <= frame["y"] <= 1
                and frame["zoom"] >= 1
            ):
                raise ValueError(
                    "Camera keyframes out of bounds"
                )

        if i and (
            _identities(scenes[i - 1])
            & _identities(scenes[i])
        ):
            start = dict(endpoints[-1][1])

        endpoints.append((start, end))

    return endpoints


def _portrait_svg(svg_text):
    """Recompose a landscape geometric SVG into a portrait canvas.

    The background fills the entire 9:16 canvas.
    Drawable objects retain their proportions and relative positions.
    No cropping, stretching or camera animation is introduced.
    """
    source = ET.fromstring(svg_text)

    viewbox = source.get("viewBox")

    if not viewbox:
        raise ValueError(
            "Source SVG is missing viewBox"
        )

    values = [float(v) for v in viewbox.replace(",", " ").split()]

    if len(values) != 4:
        raise ValueError(
            "Invalid source SVG viewBox"
        )

    _, _, source_width, source_height = values

    if source_width <= 0 or source_height <= 0:
        raise ValueError(
            "Invalid source SVG dimensions"
        )

    portrait_width = 576.0
    portrait_height = 1024.0

    # Preserve object proportions while fitting the complete
    # horizontal composition inside the portrait frame.
    scale = portrait_width / source_width

    # Keep the original ground reference near the lower part
    # of the portrait canvas.
    original_ground = source_height * 0.82
    portrait_ground = portrait_height * 0.82

    offset_x = 0.0
    offset_y = portrait_ground - original_ground * scale

    root = ET.Element(
        f"{{{SVG_NS}}}svg",
        {
            "width": str(int(portrait_width)),
            "height": str(int(portrait_height)),
            "viewBox": (
                f"0 0 {portrait_width:g} "
                f"{portrait_height:g}"
            ),
        },
    )

    children = list(source)

    sky_color = "#BFE7FF"
    ground_color = "#85C76D"
    sun_color = "#FFD65A"

    rectangles = [
        element
        for element in children
        if element.tag == f"{{{SVG_NS}}}rect"
    ]

    circles = [
        element
        for element in children
        if element.tag == f"{{{SVG_NS}}}circle"
    ]

    if rectangles:
        sky_color = rectangles[0].get(
            "fill", sky_color
        )

    if len(rectangles) > 1:
        ground_color = rectangles[1].get(
            "fill", ground_color
        )

    if circles:
        sun_color = circles[0].get(
            "fill", sun_color
        )

    ET.SubElement(
        root,
        f"{{{SVG_NS}}}rect",
        {
            "x": "0",
            "y": "0",
            "width": str(int(portrait_width)),
            "height": str(int(portrait_height)),
            "fill": sky_color,
        },
    )

    # Position the sun naturally in the portrait sky.
    ET.SubElement(
        root,
        f"{{{SVG_NS}}}circle",
        {
            "cx": str(portrait_width * 0.83),
            "cy": str(portrait_height * 0.16),
            "r": "28",
            "fill": sun_color,
        },
    )

    ET.SubElement(
        root,
        f"{{{SVG_NS}}}rect",
        {
            "x": "0",
            "y": f"{portrait_ground:.6f}",
            "width": str(int(portrait_width)),
            "height": (
                f"{portrait_height - portrait_ground:.6f}"
            ),
            "fill": ground_color,
        },
    )

    # Preserve the original object groups and their
    # spatial relationships with one uniform transform.
    group = ET.SubElement(
        root,
        f"{{{SVG_NS}}}g",
        {
            "transform": (
                f"translate({offset_x:.6f},"
                f"{offset_y:.6f}) "
                f"scale({scale:.9f})"
            )
        },
    )

    for element in children:
        if element.tag == f"{{{SVG_NS}}}g":
            group.append(element)

    return ET.tostring(
        root,
        encoding="unicode",
    )


def render_video(
    plan,
    output,
    *,
    width=1280,
    height=720,
    fps=30,
    ffmpeg="ffmpeg",
):
    """Render static geometric scenes into a silent H.264 MP4."""
    if (
        not isinstance(plan, dict)
        or plan.get("version") != "2.3"
    ):
        raise ValueError(
            "Expected a V2.3 orchestration plan"
        )

    scenes = plan.get("scenes")
    cameras = plan.get("camera_plans")
    transitions = plan.get("cinematic_transitions")
    timeline = plan.get("scene_timeline")

    if (
        not isinstance(scenes, list)
        or not scenes
        or not all(
            isinstance(v, list)
            for v in (cameras, transitions, timeline)
        )
    ):
        raise ValueError(
            "Missing V2.3 scene, camera or timeline arrays"
        )

    n = len(scenes)

    if (
        len(cameras) != n
        or len(timeline) != n
        or len(transitions) != n - 1
    ):
        raise ValueError(
            "Inconsistent plan lengths"
        )

    if not all(
        isinstance(v, int)
        and not isinstance(v, bool)
        and v > 0
        for v in (width, height, fps)
    ):
        raise ValueError(
            "width, height and fps must be positive integers"
        )

    if width % 2 or height % 2:
        raise ValueError(
            "H.264 dimensions must be even"
        )

    if not shutil.which(ffmpeg):
        raise RuntimeError(
            "FFmpeg executable not found"
        )

    try:
        import cairosvg
        from melodia_scene_depth_engine import render_depth_svg
    except ImportError as exc:
        raise RuntimeError(
            "Install CairoSVG and ensure V1.9 modules are available"
        ) from exc

    durations = [
        _positive(
            item["duration_seconds"],
            f"scene {i} duration",
        )
        for i, item in enumerate(timeline)
    ]

    overlaps = []

    for i, transition in enumerate(transitions):
        if (
            transition.get("from_scene") != i
            or transition.get("to_scene") != i + 1
        ):
            raise ValueError(
                "Transition order mismatch"
            )

        amount = transition.get("duration_seconds")

        if (
            isinstance(amount, bool)
            or not isinstance(amount, (int, float))
            or not math.isfinite(amount)
            or amount < 0
        ):
            raise ValueError(
                "Invalid overlap"
            )

        if amount >= min(
            durations[i], durations[i + 1]
        ):
            raise ValueError(
                "Overlap must be shorter than adjacent scenes"
            )

        overlaps.append(float(amount))

    expected = sum(durations) - sum(overlaps)

    if abs(
        expected - float(
            plan["total_output_duration_seconds"]
        )
    ) > 0.0001:
        raise ValueError(
            "Plan output duration mismatch"
        )

    # Validate camera plans without applying movement.
    _camera_endpoints(scenes, cameras)

    output = Path(output)
    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with tempfile.TemporaryDirectory(
        prefix="melodia_v24_"
    ) as directory:
        tmp = Path(directory)
        inputs = []

        portrait = height > width

        for i, scene in enumerate(scenes):
            if scene.get("status") != "generated":
                raise ValueError(
                    f"Scene {i} is not a generated V1.9 geometric scene"
                )

            svg = render_depth_svg(scene)

            if portrait:
                svg = _portrait_svg(svg)

            png = tmp / f"scene_{i:04d}.png"

            cairosvg.svg2png(
                bytestring=svg.encode("utf-8"),
                write_to=str(png),
                output_width=width,
                output_height=height,
            )

            inputs += [
                "-loop", "1",
                "-framerate", str(fps),
                "-t", str(durations[i]),
                "-i", str(png),
            ]

        filters = []

        # Static frames throughout each scene.
        for i in range(n):
            filters.append(
                f"[{i}:v]"
                f"trim=duration={durations[i]:.6f},"
                f"setpts=PTS-STARTPTS,"
                f"format=yuv420p[v{i}]"
            )

        previous = "v0"
        elapsed = durations[0]

        for i, transition in enumerate(transitions):
            overlap = overlaps[i]
            kind = transition.get("transition")
            label = f"m{i + 1}"

            if overlap == 0 or kind == "cut":
                filters.append(
                    f"[{previous}][v{i + 1}]"
                    f"concat=n=2:v=1:a=0[{label}]"
                )
                elapsed += durations[i + 1]
            else:
                effect = {
                    "crossfade": "fade",
                    "dissolve": "dissolve",
                    "fade_through_black": "fadeblack",
                }.get(kind)

                if effect is None:
                    raise ValueError(
                        f"Unsupported transition {kind}"
                    )

                offset = elapsed - overlap

                filters.append(
                    f"[{previous}][v{i + 1}]"
                    f"xfade=transition={effect}:"
                    f"duration={overlap:.6f}:"
                    f"offset={offset:.6f}[{label}]"
                )

                elapsed += durations[i + 1] - overlap

            previous = label

        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel", "error",
            "-y",
            *inputs,
            "-filter_complex", ";".join(filters),
            "-map", f"[{previous}]",
            "-an",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "22",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(output),
        ]

        subprocess.run(
            command,
            check=True,
        )

    return {
        "version": VERSION,
        "output": str(output),
        "expected_duration_seconds": round(expected, 6),
        "scene_count": n,
        "width": width,
        "height": height,
        "fps": fps,
    }


def main():
    parser = argparse.ArgumentParser(
        description="MELODIA AI V2.4 geometric MP4 renderer"
    )

    parser.add_argument(
        "--input",
        required=True,
        help="V2.3 orchestration JSON",
    )

    parser.add_argument(
        "--output",
        required=True,
        help="Output MP4 path",
    )

    parser.add_argument(
        "--width",
        type=int,
        default=1280,
    )

    parser.add_argument(
        "--height",
        type=int,
        default=720,
    )

    parser.add_argument(
        "--fps",
        type=int,
        default=30,
    )

    args = parser.parse_args()

    plan = json.loads(
        Path(args.input).read_text(
            encoding="utf-8"
        )
    )

    result = render_video(
        plan,
        args.output,
        width=args.width,
        height=args.height,
        fps=args.fps,
    )

    print(
        json.dumps(
            result,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
