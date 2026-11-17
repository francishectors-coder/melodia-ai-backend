"""MELODIA AI V3.1 — lossless SVG scene asset adapter (independent stage).

Converts a validated unified scene plan into immutable SVG assets and a
traceable manifest. Does not invoke or modify the legacy V2.x renderer.
The MP4 renderer must explicitly consume each scene's svg_path; metadata alone
is not sufficient to activate V3.1 artwork.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET

from melodia_unified_scene_engine import plan_scenes, render_scene_svg, validate_plan

VERSION = "3.1.0-adapter"
ASPECTS = {"16:9": (1280, 720), "9:16": (720, 1280)}
SVG_NS = "http://www.w3.org/2000/svg"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def prepare_assets(prompt: str, output_dir: str | Path, *, duration_seconds: float = 30,
                   aspect: str = "16:9") -> dict:
    """Create exact SVG files plus manifest, without touching production code."""
    if aspect not in ASPECTS:
        raise ValueError("aspect must be 16:9 or 9:16")
    width, height = ASPECTS[aspect]
    plan = plan_scenes(prompt, duration_seconds)
    validate_plan(plan["scenes"])
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    records = []
    for index, scene in enumerate(plan["scenes"]):
        expected_id = f"scene_{index + 1:03d}"
        if scene["id"] != expected_id:
            raise ValueError(f"Scene order mismatch: {scene['id']}")
        caption = scene["caption_en"].strip()
        if not caption:
            raise ValueError(f"Missing caption for {expected_id}")
        svg_text = render_scene_svg(scene, width, height)
        svg_bytes = svg_text.encode("utf-8")
        root = ET.fromstring(svg_bytes)
        if root.tag != f"{{{SVG_NS}}}svg":
            raise ValueError(f"Invalid SVG root for {expected_id}")
        if root.attrib.get("viewBox") != f"0 0 {width} {height}":
            raise ValueError(f"Invalid SVG viewBox for {expected_id}")
        svg_file = destination / f"{expected_id}.svg"
        svg_file.write_bytes(svg_bytes)
        records.append({
            "scene_id": expected_id,
            "sequence": index + 1,
            "environment": scene["environment"],
            "lighting": scene["lighting"],
            "caption_en": caption,
            "duration_seconds": scene["duration_seconds"],
            "svg_path": str(svg_file.resolve()),
            "svg_sha256": _sha256(svg_bytes),
            "width": width,
            "height": height,
            "ground_y": scene["ground_y"],
        })
    manifest = {
        "version": VERSION,
        "source_engine_version": plan["version"],
        "source_prompt": prompt,
        "aspect": aspect,
        "duration_seconds": float(duration_seconds),
        "scenes": records,
        "integration_status": "assets_only_not_connected_to_mp4_renderer",
    }
    verify_assets(manifest)
    (destination / "v31_asset_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def verify_assets(manifest: dict) -> bool:
    """Fail closed if any scene is missing, reordered, modified or mismatched."""
    scenes = manifest.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("No V3.1 scene assets")
    if manifest.get("aspect") not in ASPECTS:
        raise ValueError("Invalid aspect")
    width, height = ASPECTS[manifest["aspect"]]
    duration_sum = 0.0
    for index, scene in enumerate(scenes):
        if scene.get("scene_id") != f"scene_{index + 1:03d}" or scene.get("sequence") != index + 1:
            raise ValueError("Scene sequence mismatch")
        if not isinstance(scene.get("caption_en"), str) or not scene["caption_en"].strip():
            raise ValueError("Empty caption")
        path = Path(scene["svg_path"])
        data = path.read_bytes()
        if _sha256(data) != scene.get("svg_sha256"):
            raise ValueError(f"Scene artwork modified: {path.name}")
        root = ET.fromstring(data)
        if root.tag != f"{{{SVG_NS}}}svg" or root.get("viewBox") != f"0 0 {width} {height}":
            raise ValueError("Scene SVG dimensions invalid")
        if scene.get("width") != width or scene.get("height") != height:
            raise ValueError("Scene dimensions mismatch")
        duration = float(scene["duration_seconds"])
        if duration <= 0:
            raise ValueError("Invalid scene duration")
        duration_sum += duration
    if abs(duration_sum - float(manifest["duration_seconds"])) > 0.0001:
        raise ValueError("Scene durations do not sum to requested duration")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="MELODIA V3.1 independent SVG asset adapter")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--duration", type=float, default=30)
    parser.add_argument("--aspect", choices=tuple(ASPECTS), default="16:9")
    args = parser.parse_args()
    manifest = prepare_assets(args.prompt, args.output, duration_seconds=args.duration, aspect=args.aspect)
    print(json.dumps({"status": "PASS", "scene_count": len(manifest["scenes"]),
                      "aspect": manifest["aspect"], "integration_status": manifest["integration_status"]}, indent=2))


if __name__ == "__main__":
    main()
