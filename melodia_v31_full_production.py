"""MELODIA AI V3.1 — isolated SVG full-production pipeline.

Requires melodia_v31_production_adapter.py, melodia_v31_render_bridge.py,
melodia_video_production_engine.py, and the existing renderer in the same
Python environment. Runs the legacy-renderer bridge in a separate process,
so its temporary scene hook cannot affect concurrent web workers.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from melodia_v31_production_adapter import ASPECTS, verify_assets
from melodia_v31_render_bridge import _make_plan
from melodia_video_production_engine import _filter_path, _make_ass

VERSION = "3.1.0-full-production"
BRIDGE = Path(__file__).resolve().with_name("melodia_v31_render_bridge.py")


def _valid_number(value, name, *, minimum=0, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    value = float(value)
    if value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _caption_plan(manifest, transition_seconds, fps):
    """Create caption timing from the same frame-quantized transition schedule."""
    plan = _make_plan(manifest, transition_seconds)
    records = manifest["scenes"]
    durations = [round(float(s["duration_seconds"]) * fps) for s in records]
    overlaps = [round(float(t["duration_seconds"]) * fps)
                for t in plan["cinematic_transitions"]]
    if any(v <= 0 for v in durations):
        raise ValueError("Each scene must contain at least one frame")
    if any(overlaps[i] >= min(durations[i], durations[i+1]) for i in range(len(overlaps))):
        raise ValueError("Transition exceeds adjacent scene duration")
    timeline = []
    start_frames = 0
    for i, (scene, frames) in enumerate(zip(records, durations)):
        # Caption switches at the start of the crossfade to the next scene.
        display_frames = frames - (overlaps[i] if i < len(overlaps) else 0)
        if display_frames <= 0:
            raise ValueError("No display frames for scene")
        timeline.append({"duration_seconds": frames / fps,
                         "start_seconds": start_frames / fps,
                         "end_seconds": (start_frames + display_frames) / fps})
        start_frames += display_frames
    plan["scene_timeline"] = timeline
    plan["total_output_duration_seconds"] = start_frames / fps
    for item, record in zip(plan["scenes"], records):
        item["captions"] = {"en": record["caption_en"], **record.get("captions", {})}
        item["caption_en"] = record["caption_en"]
    return plan


def produce_v31_video(manifest: dict, output: str | Path, *, fps: int = 10,
                      transition_seconds: float = 0.5, bilingual_language=None,
                      music=None, music_volume: float = 0.22, captions: bool = True,
                      promo_seconds: float = 0.0, ffmpeg: str = "ffmpeg") -> dict:
    """Render approved SVGs to a captioned, optionally musical MP4.

    The live V2.x renderer and production functions are never patched in this
    process. Only the isolated bridge subprocess temporarily hooks the renderer.
    """
    verify_assets(manifest)
    if isinstance(fps, bool) or not isinstance(fps, int) or fps <= 0:
        raise ValueError("fps must be a positive integer")
    transition_seconds = _valid_number(transition_seconds, "transition_seconds", maximum=9.999)
    promo_seconds = _valid_number(promo_seconds, "promo_seconds", maximum=5)
    music_volume = _valid_number(music_volume, "music_volume", maximum=1)
    if not isinstance(captions, bool):
        raise ValueError("captions must be boolean")
    if bilingual_language is not None and (not isinstance(bilingual_language, str)
                                           or not bilingual_language.strip()
                                           or bilingual_language == "en"):
        raise ValueError("Invalid bilingual language")
    if not shutil.which(ffmpeg):
        raise RuntimeError("FFmpeg not found")
    if not BRIDGE.is_file():
        raise FileNotFoundError(f"Missing bridge: {BRIDGE}")
    music_path = Path(music).resolve() if music is not None else None
    if music_path is not None and not music_path.is_file():
        raise FileNotFoundError(f"Music not found: {music_path}")
    aspect = manifest["aspect"]
    width, height = ASPECTS[aspect]
    plan = _caption_plan(manifest, transition_seconds, fps)
    main_duration = plan["total_output_duration_seconds"]
    full_duration = main_duration + promo_seconds
    destination = Path(output).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="melodia_v31_full_") as tmpname:
        tmp = Path(tmpname)
        silent = tmp / "silent.mp4"
        ass = tmp / "captions.ass"
        manifest_file = tmp / "manifest.json"
        manifest_file.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        # Separate interpreter process: no global renderer monkey-patch leaks.
        subprocess.run([sys.executable, str(BRIDGE), "--manifest", str(manifest_file),
                        "--output", str(silent), "--fps", str(fps),
                        "--transition", str(transition_seconds)], check=True)
        caption_count = _make_ass(plan, ass, width, height,
                                  bilingual_language=bilingual_language,
                                  captions=captions, promo_seconds=promo_seconds)
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(silent)]
        if promo_seconds:
            command += ["-f", "lavfi", "-i",
                        f"color=c=0x101B32:s={width}x{height}:r={fps}:d={promo_seconds:.6f}"]
        music_index = 2 if promo_seconds else 1
        if music_path:
            command += ["-stream_loop", "-1", "-i", str(music_path)]
        if promo_seconds:
            graph = ("[0:v]setpts=PTS-STARTPTS,format=yuv420p[main];"
                     "[1:v]setpts=PTS-STARTPTS,format=yuv420p[ending];"
                     "[main][ending]concat=n=2:v=1:a=0[joined];"
                     f"[joined]ass={_filter_path(ass)}[finalv]")
            command += ["-filter_complex", graph, "-map", "[finalv]"]
        else:
            command += ["-vf", "ass=" + _filter_path(ass), "-map", "0:v:0"]
        if music_path:
            command += ["-map", f"{music_index}:a:0", "-af",
                        f"volume={music_volume:.6f},atrim=duration={full_duration:.6f},asetpts=PTS-STARTPTS",
                        "-c:a", "aac", "-b:a", "128k"]
        else:
            command += ["-an"]
        command += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                    "-pix_fmt", "yuv420p", "-t", f"{full_duration:.6f}",
                    "-movflags", "+faststart", str(destination)]
        subprocess.run(command, check=True)
    return {"version": VERSION, "output": str(destination), "aspect": aspect,
            "width": width, "height": height, "fps": fps,
            "scene_ids": [r["scene_id"] for r in manifest["scenes"]],
            "captions": caption_count, "music": bool(music_path),
            "watermark": "MELODIA AI", "main_duration_seconds": main_duration,
            "promo_seconds": promo_seconds, "expected_duration_seconds": full_duration}


def main():
    parser = argparse.ArgumentParser(description="MELODIA V3.1 full production")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--fps", type=int, default=10)
    parser.add_argument("--transition", type=float, default=0.5)
    parser.add_argument("--music")
    parser.add_argument("--music-volume", type=float, default=0.22)
    parser.add_argument("--bilingual-language")
    parser.add_argument("--no-captions", action="store_true")
    parser.add_argument("--promo-seconds", type=float, default=0)
    args = parser.parse_args()
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    result = produce_v31_video(manifest, args.output, fps=args.fps,
                               transition_seconds=args.transition, music=args.music,
                               music_volume=args.music_volume,
                               bilingual_language=args.bilingual_language,
                               captions=not args.no_captions,
                               promo_seconds=args.promo_seconds)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
