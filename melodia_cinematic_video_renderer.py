"""MELODIA AI V2.4 — render V2.3 geometric orchestration plans to MP4.

Requires FFmpeg and CairoSVG. V2.8 reading-focused mode:
backgrounds remain static throughout each scene; existing scene transitions,
timing, captions and audio integration remain unchanged.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

VERSION = "2.4"


def _positive(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive finite number")
    return float(value)


def _identities(scene):
    return {obj.get("continuity_id", obj.get("id")) for obj in scene.get("objects", []) if isinstance(obj, dict)}


def _camera_endpoints(scenes, cameras):
    """Use a common endpoint/startpoint when adjacent scenes share objects.

    For unchanged composition, carry the entire camera transform across the
    boundary. This avoids restarting the zoom/pan during a crossfade. A changed
    composition retains its planned independent camera transform.
    """
    endpoints = []
    for i, camera in enumerate(cameras):
        keyframes = camera.get("keyframes")
        if not isinstance(keyframes, list) or len(keyframes) < 2:
            raise ValueError(f"Missing camera keyframes for scene {i}")
        start, end = dict(keyframes[0]), dict(keyframes[-1])
        for frame in (start, end):
            for name in ("x", "y", "zoom"):
                value = frame.get(name)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError(f"Invalid camera {name}")
            if not (0 <= frame["x"] <= 1 and 0 <= frame["y"] <= 1 and frame["zoom"] >= 1):
                raise ValueError("Camera keyframes out of bounds")
        if i and _identities(scenes[i - 1]) & _identities(scenes[i]):
            start = dict(endpoints[-1][1])
            # A new independent movement could zoom out below the previous
            # crop, but zoompan handles the smooth interpolation safely.
        endpoints.append((start, end))
    return endpoints


def render_video(plan, output, *, width=1280, height=720, fps=30, ffmpeg="ffmpeg"):
    """Render a V2.3 plan to silent H.264 MP4 with static scene backgrounds."""
    if not isinstance(plan, dict) or plan.get("version") != "2.3":
        raise ValueError("Expected a V2.3 orchestration plan")
    scenes = plan.get("scenes")
    cameras = plan.get("camera_plans")
    transitions = plan.get("cinematic_transitions")
    timeline = plan.get("scene_timeline")
    if not isinstance(scenes, list) or not scenes or not all(isinstance(v, list) for v in (cameras, transitions, timeline)):
        raise ValueError("Missing V2.3 scene, camera or timeline arrays")
    n = len(scenes)
    if len(cameras) != n or len(timeline) != n or len(transitions) != n - 1:
        raise ValueError("Inconsistent plan lengths")
    if not all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in (width, height, fps)):
        raise ValueError("width, height and fps must be positive integers")
    if width % 2 or height % 2:
        raise ValueError("H.264 dimensions must be even")
    if not shutil.which(ffmpeg):
        raise RuntimeError("FFmpeg executable not found")
    try:
        import cairosvg
        from melodia_scene_depth_engine import render_depth_svg
    except ImportError as exc:
        raise RuntimeError("Install CairoSVG and ensure V1.9 modules are available") from exc

    durations = [_positive(item["duration_seconds"], f"scene {i} duration") for i, item in enumerate(timeline)]
    overlaps = []
    for i, transition in enumerate(transitions):
        if transition.get("from_scene") != i or transition.get("to_scene") != i + 1:
            raise ValueError("Transition order mismatch")
        amount = transition.get("duration_seconds")
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount) or amount < 0:
            raise ValueError("Invalid overlap")
        if amount >= min(durations[i], durations[i + 1]):
            raise ValueError("Overlap must be shorter than adjacent scenes")
        overlaps.append(float(amount))
    expected = sum(durations) - sum(overlaps)
    if abs(expected - float(plan["total_output_duration_seconds"])) > 0.0001:
        raise ValueError("Plan output duration mismatch")

    # Preserve camera-plan validation, but do not animate camera keyframes.
    _camera_endpoints(scenes, cameras)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    # Frame-based allocation prevents cumulative timestamp drift. Each scene
    # contributes a static core; adjacent overlaps are rendered separately.
    scene_frames = [round(d * fps) for d in durations]
    overlap_frames = [round(d * fps) for d in overlaps]
    if any(f <= 0 for f in scene_frames):
        raise ValueError("Scene duration is shorter than one frame")
    if any(f >= min(scene_frames[i], scene_frames[i + 1])
           for i, f in enumerate(overlap_frames)):
        raise ValueError("Transition is too long after frame rounding")
    core_frames = []
    for i, total in enumerate(scene_frames):
        incoming = overlap_frames[i - 1] if i else 0
        outgoing = overlap_frames[i] if i < n - 1 else 0
        count = total - incoming - outgoing
        if count <= 0:
            raise ValueError(f"Scene {i} has no remaining static frames")
        core_frames.append(count)

    def run_ffmpeg(args):
        subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                        "-threads", "1", "-filter_threads", "1", *args], check=True)

    def encode_args(destination):
        return ["-an", "-c:v", "libx264", "-threads", "1", "-preset", "veryfast",
                "-crf", "22", "-pix_fmt", "yuv420p", "-r", str(fps),
                "-video_track_timescale", str(fps * 1000), str(destination)]

    with tempfile.TemporaryDirectory(prefix="melodia_v24_stream_") as directory:
        tmp = Path(directory)
        images = []
        for i, scene in enumerate(scenes):
            if scene.get("status") != "generated":
                raise ValueError(f"Scene {i} is not a generated V1.9 geometric scene")
            svg = render_depth_svg(scene)
            png = tmp / f"scene_{i:04d}.png"
            cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=str(png),
                             output_width=width, output_height=height)
            images.append(png)

        segments = []
        for i in range(n):
            core = tmp / f"segment_{len(segments):04d}.mp4"
            run_ffmpeg(["-loop", "1", "-framerate", str(fps), "-i", str(images[i]),
                        "-frames:v", str(core_frames[i]), *encode_args(core)])
            segments.append(core)
            if i == n - 1 or overlap_frames[i] == 0:
                continue
            kind = transitions[i].get("transition")
            if kind == "cut":
                # A cut has no overlap; a nonzero cut overlap is invalid.
                raise ValueError("Cut transition must have zero duration")
            effect = {"crossfade": "fade", "dissolve": "dissolve",
                      "fade_through_black": "fadeblack"}.get(kind)
            if effect is None:
                raise ValueError(f"Unsupported transition {kind}")
            count = overlap_frames[i]
            transition_file = tmp / f"segment_{len(segments):04d}.mp4"
            # Decode only two stills for each transition. xfade begins after
            # one overlap interval; trim extracts exactly the blended interval.
            length = (count * 2 + 2) / fps
            graph = (f"[0:v]format=yuv420p,trim=duration={length:.9f},"
                     f"setpts=PTS-STARTPTS,fps={fps}[a];"
                     f"[1:v]format=yuv420p,trim=duration={length:.9f},"
                     f"setpts=PTS-STARTPTS,fps={fps}[b];"
                     f"[a][b]xfade=transition={effect}:duration={count/fps:.9f}:"
                     f"offset={count/fps:.9f},trim=start={count/fps:.9f}:"
                     f"duration={count/fps:.9f},setpts=PTS-STARTPTS[out]")
            run_ffmpeg(["-loop", "1", "-framerate", str(fps), "-i", str(images[i]),
                        "-loop", "1", "-framerate", str(fps), "-i", str(images[i + 1]),
                        "-filter_complex", graph, "-map", "[out]",
                        "-frames:v", str(count), *encode_args(transition_file)])
            segments.append(transition_file)

        # All segments share codec, dimensions, frame rate, and encoder settings.
        # Stream-copy concatenation avoids decoding all scenes simultaneously.
        concat_file = tmp / "segments.txt"
        concat_file.write_text("".join(
            "file '" + str(segment).replace("'", "'\\''") + "'\n"
            for segment in segments), encoding="utf-8")
        run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(concat_file),
                    "-c", "copy", "-movflags", "+faststart", str(output)])

    return {"version": VERSION, "output": str(output),
            "expected_duration_seconds": round(sum(core_frames + overlap_frames) / fps, 6),
            "scene_count": n, "width": width, "height": height, "fps": fps}


def main():
    parser = argparse.ArgumentParser(description="MELODIA AI V2.4 geometric MP4 renderer")
    parser.add_argument("--input", required=True, help="V2.3 orchestration JSON")
    parser.add_argument("--output", required=True, help="Output MP4 path")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=int, default=30)
    args = parser.parse_args()
    plan = json.loads(Path(args.input).read_text(encoding="utf-8"))
    print(json.dumps(render_video(plan, args.output, width=args.width, height=args.height, fps=args.fps), indent=2))


if __name__ == "__main__":
    main()
