"""MELODIA AI V2.7 — render supplied AI images using V2.3 camera plans.

This independent renderer produces silent MP4 video. It does not call Gemini,
change V2.4–V2.6, or add captions/music. Image generation is a separate step.
Requires FFmpeg and Pillow.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageOps

VERSION = "2.7"


def _positive(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a positive finite number")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{label} must be a positive finite number")
    return float(value)


def _camera_filter(index, camera, duration, width, height, fps):
    keyframes = camera.get("keyframes") if isinstance(camera, dict) else None
    if not isinstance(keyframes, list) or len(keyframes) < 2:
        raise ValueError(f"Missing camera keyframes for scene {index}")
    a, b = keyframes[0], keyframes[-1]
    for frame in (a, b):
        if not isinstance(frame, dict):
            raise ValueError(f"Invalid camera keyframe for scene {index}")
        for name in ("x", "y", "zoom"):
            value = frame.get(name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"Invalid camera {name} for scene {index}")
        if not (0 <= frame["x"] <= 1 and 0 <= frame["y"] <= 1 and frame["zoom"] >= 1):
            raise ValueError(f"Camera keyframe out of bounds for scene {index}")
    frames = max(1, round(duration * fps))
    progress = f"min(1,max(0,on/{max(1, frames - 1)}))"
    def interp(name):
        start, end = float(a[name]), float(b[name])
        return f"({start:.8f}+({end - start:.8f})*{progress})"
    z, x, y = interp("zoom"), interp("x"), interp("y")
    return (
        f"[{index}:v]zoompan=z='{z}':"
        f"x='max(0,min(iw-iw/zoom,iw*{x}-iw/(2*zoom)))':"
        f"y='max(0,min(ih-ih/zoom,ih*{y}-ih/(2*zoom)))':"
        f"d=1:s={width}x{height}:fps={fps},"
        f"trim=duration={duration:.6f},setpts=PTS-STARTPTS,format=yuv420p[v{index}]"
    )


def render_ai_image_video(plan, image_paths, output, *, width=1280, height=720,
                          fps=30, ffmpeg="ffmpeg"):
    """Render one image per scene to a silent MP4 using V2.3 timing/cameras.

    image_paths: ordered list of PNG/JPEG file paths, one for each scene.
    Images are center-cropped to the requested aspect ratio before animation.
    """
    if not isinstance(plan, dict) or plan.get("version") != "2.3":
        raise ValueError("Expected a V2.3 orchestration plan")
    scenes = plan.get("scenes")
    cameras = plan.get("camera_plans")
    transitions = plan.get("cinematic_transitions")
    timeline = plan.get("scene_timeline")
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("Missing scenes")
    n = len(scenes)
    if not all(isinstance(v, list) for v in (cameras, transitions, timeline)):
        raise ValueError("Missing camera, transition or timeline arrays")
    if len(cameras) != n or len(timeline) != n or len(transitions) != n - 1:
        raise ValueError("Inconsistent V2.3 plan lengths")
    if not isinstance(image_paths, (list, tuple)) or len(image_paths) != n:
        raise ValueError("image_paths must contain exactly one path per scene")
    if not all(isinstance(v, int) and not isinstance(v, bool) and v > 0
               for v in (width, height, fps)) or width % 2 or height % 2:
        raise ValueError("width, height and fps must be positive integers; dimensions must be even")
    if not shutil.which(ffmpeg):
        raise RuntimeError("FFmpeg executable not found")

    durations = [_positive(item["duration_seconds"], f"scene {i} duration")
                 for i, item in enumerate(timeline)]
    overlaps = []
    for i, transition in enumerate(transitions):
        if not isinstance(transition, dict) or transition.get("from_scene") != i or transition.get("to_scene") != i + 1:
            raise ValueError(f"Transition order mismatch at scene {i}")
        overlap = transition.get("duration_seconds")
        if isinstance(overlap, bool) or not isinstance(overlap, (int, float)) or not math.isfinite(overlap) or overlap < 0:
            raise ValueError("Invalid transition duration")
        if overlap >= min(durations[i], durations[i + 1]):
            raise ValueError("Overlap must be shorter than adjacent scenes")
        overlaps.append(float(overlap))
    expected = sum(durations) - sum(overlaps)
    planned = _positive(plan.get("total_output_duration_seconds"), "planned duration")
    if abs(expected - planned) > 0.0001:
        raise ValueError("Plan output duration mismatch")
    if expected > 600.000001:
        raise ValueError("Video exceeds the 600-second limit")

    source_paths = [Path(p).expanduser().resolve() for p in image_paths]
    for i, path in enumerate(source_paths):
        if not path.is_file():
            raise FileNotFoundError(f"Scene {i} image not found: {path}")

    destination = Path(output).expanduser().resolve()
    if destination.suffix.lower() != ".mp4":
        raise ValueError("Output must have an .mp4 extension")
    destination.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="melodia_v27_") as directory:
        tmp = Path(directory)
        inputs = []
        for i, path in enumerate(source_paths):
            normalized = tmp / f"scene_{i:04d}.png"
            with Image.open(path) as original:
                original.load()
                rgb = ImageOps.exif_transpose(original).convert("RGB")
                fitted = ImageOps.fit(rgb, (width, height), method=Image.Resampling.LANCZOS)
                fitted.save(normalized, format="PNG")
            inputs.extend(["-loop", "1", "-framerate", str(fps), "-t",
                           f"{durations[i]:.6f}", "-i", str(normalized)])

        filters = [_camera_filter(i, camera, durations[i], width, height, fps)
                   for i, camera in enumerate(cameras)]
        previous = "v0"
        elapsed = durations[0]
        for i, transition in enumerate(transitions):
            overlap = overlaps[i]
            kind = transition.get("transition")
            label = f"m{i + 1}"
            if overlap == 0 or kind == "cut":
                filters.append(f"[{previous}][v{i + 1}]concat=n=2:v=1:a=0[{label}]")
                elapsed += durations[i + 1]
            else:
                effect = {"crossfade": "fade", "dissolve": "dissolve",
                          "fade_through_black": "fadeblack"}.get(kind)
                if effect is None:
                    raise ValueError(f"Unsupported transition: {kind}")
                filters.append(
                    f"[{previous}][v{i + 1}]xfade=transition={effect}:"
                    f"duration={overlap:.6f}:offset={elapsed - overlap:.6f}[{label}]"
                )
                elapsed += durations[i + 1] - overlap
            previous = label

        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *inputs,
                   "-filter_complex", ";".join(filters), "-map", f"[{previous}]",
                   "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                   "-pix_fmt", "yuv420p", "-t", f"{expected:.6f}",
                   "-movflags", "+faststart", str(destination)]
        subprocess.run(command, check=True)

    return {"version": VERSION, "output": str(destination), "scene_count": n,
            "width": width, "height": height, "fps": fps,
            "expected_duration_seconds": round(expected, 6)}


def main():
    parser = argparse.ArgumentParser(description="MELODIA V2.7 AI-image MP4 renderer")
    parser.add_argument("--plan", required=True, help="V2.3 orchestration JSON")
    parser.add_argument("--images-json", required=True, help="JSON list of image paths")
    parser.add_argument("--output", required=True, help="Destination silent MP4")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=int, default=30)
    args = parser.parse_args()
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    images = json.loads(Path(args.images_json).read_text(encoding="utf-8"))
    result = render_ai_image_video(plan, images, args.output,
                                   width=args.width, height=args.height, fps=args.fps)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
