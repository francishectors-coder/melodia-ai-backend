"""MELODIA AI V2.4 — render V2.3 geometric orchestration plans to MP4.

Requires FFmpeg and CairoSVG. V2.8 reading-focused mode:
backgrounds remain static throughout each scene; existing scene transitions,
timing, captions and audio integration remain unchanged.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

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



def _parse_legacy_svg(markup):
    """Parse legacy SVG, tolerating repeated identical root xmlns declarations.

    Some older SVG serializers emit xmlns twice on the opening <svg> tag.
    Remove only redundant identical namespace declarations; other malformed
    attributes still raise an XML ParseError.
    """
    try:
        return ET.fromstring(markup)
    except ET.ParseError as original_error:
        match = re.search(r"<svg\b[^>]*>", markup)
        if match is None:
            raise
        opening = match.group(0)
        declaration = re.compile(r"\s+(xmlns(?::[A-Za-z_][\w.-]*)?)\s*=\s*([\"'])(.*?)\2")
        seen = {}
        changed = [False]

        def deduplicate(found):
            key, value = found.group(1), found.group(3)
            if key in seen and seen[key] == value:
                changed[0] = True
                return ""
            seen.setdefault(key, value)
            return found.group(0)

        fixed_opening = declaration.sub(deduplicate, opening)
        if not changed[0]:
            raise original_error
        return ET.fromstring(markup[:match.start()] + fixed_opening + markup[match.end():])


def _bounds_intersect(a, b, padding=0.0):
    """Test pixel-space rectangles, including a small visual breathing gap."""
    return (a[0] < b[2] + padding and a[2] + padding > b[0]
            and a[1] < b[3] + padding and a[3] + padding > b[1])


def _clear_scenic_collisions(scenic_root, scene, width, height):
    """Remove only scenic decorative trees/flowers obscured by legacy objects.

    V2.9 scenic SVG emits each tree as a brown trunk followed by a green
    ellipse, and each flower as a green stem followed by six circles.
    Preserve all legacy objects and every nonconflicting scenic decoration.
    """
    from melodia_automatic_scene_composer import object_bounds

    obstacles = []
    for obj in scene.get("objects", []):
        if not isinstance(obj, dict) or not obj.get("components"):
            continue
        left, top, right, bottom = object_bounds(obj)
        obstacles.append((left * width, top * height,
                          right * width, bottom * height))
    if not obstacles:
        return

    children = list(scenic_root)
    namespace = "{http://www.w3.org/2000/svg}"
    padding = min(width, height) * 0.012
    remove = set()
    i = 0
    while i < len(children):
        node = children[i]
        # Trees: trunk rectangle immediately followed by green canopy ellipse.
        if (node.tag == namespace + "rect" and node.get("fill") == "#735139"
                and i + 1 < len(children)
                and children[i + 1].tag == namespace + "ellipse"
                and children[i + 1].get("fill") in {"#26784a", "#398958", "#4a9b59"}):
            canopy = children[i + 1]
            cx, cy = float(canopy.get("cx")), float(canopy.get("cy"))
            rx, ry = float(canopy.get("rx")), float(canopy.get("ry"))
            x, y = float(node.get("x")), float(node.get("y"))
            w, h = float(node.get("width")), float(node.get("height"))
            bounds = (min(x, cx-rx), min(y, cy-ry),
                      max(x+w, cx+rx), max(y+h, cy+ry))
            if any(_bounds_intersect(bounds, other, padding) for other in obstacles):
                remove.update((node, canopy))
            i += 2
            continue

        # Flowers: stem followed by five petals and one center circle.
        if (node.tag == namespace + "line" and node.get("stroke") == "#287344"
                and i + 6 < len(children)
                and all(item.tag == namespace + "circle"
                        for item in children[i+1:i+7])
                and children[i+6].get("fill") == "#f7e37c"):
            parts = children[i:i+7]
            xs = [float(node.get("x1")), float(node.get("x2"))]
            ys = [float(node.get("y1")), float(node.get("y2"))]
            for circle in parts[1:]:
                cx, cy, radius = (float(circle.get(key)) for key in ("cx", "cy", "r"))
                xs.extend((cx-radius, cx+radius))
                ys.extend((cy-radius, cy+radius))
            bounds = (min(xs), min(ys), max(xs), max(ys))
            if any(_bounds_intersect(bounds, other, padding) for other in obstacles):
                remove.update(parts)
            i += 7
            continue
        i += 1

    for node in remove:
        scenic_root.remove(node)


def _resolve_foreground_collisions(scene):
    """Resolve all non-intentional foreground overlaps, or fail explicitly.

    Uses full component bounds (including flower petals and tree canopies).
    Keeps objects in their original left-to-right order, preserves their
    identities, and does not change the caller's scene. Ground-based objects
    are laid out horizontally; intentionally stacked objects are exempted.
    """
    from melodia_automatic_scene_composer import object_bounds, shift_object

    adjusted = copy.deepcopy(scene)
    objects = adjusted.get("objects", [])
    if len(objects) < 2:
        return adjusted

    gap = 0.018
    margin = 0.025
    vertical = {"above", "below", "on_top_of"}
    relationships = adjusted.get("relationships", [])

    def intentionally_stacked(a, b):
        ids = {a.get("id"), b.get("id")}
        for rel in relationships:
            if not isinstance(rel, dict) or rel.get("relation") not in vertical:
                continue
            target = rel.get("target", rel.get("object"))
            if {rel.get("subject"), target} == ids:
                return True
        return False

    def collisions():
        result = []
        for i, first in enumerate(objects):
            if not first.get("components"):
                continue
            bounds_a = object_bounds(first)
            for j in range(i + 1, len(objects)):
                second = objects[j]
                if not second.get("components") or intentionally_stacked(first, second):
                    continue
                if _bounds_intersect(bounds_a, object_bounds(second), gap):
                    result.append((i, j))
        return result

    if not collisions():
        return adjusted

    # Arrange all movable ground objects using the actual component widths.
    # Do not reorder objects: the prompt's left/centre/right order is retained.
    ground_categories = {"tree", "house", "vehicle", "animal", "flower"}
    movable = [i for i, obj in enumerate(objects)
               if obj.get("components") and obj.get("category") in ground_categories
               and not any(isinstance(rel, dict) and rel.get("relation") in vertical
                           and obj.get("id") in {rel.get("subject"), rel.get("target", rel.get("object"))}
                           for rel in relationships)]
    movable.sort(key=lambda i: (objects[i]["center"]["x"], i))

    def shrink(indices, factor):
        # Ground-based geometry must scale around its bottom, not its centre.
        # Scaling around the centre was lifting trunks and stems into the air.
        for i in indices:
            obj = objects[i]
            cx = obj["center"]["x"]
            grounded = obj.get("category") in {"tree", "house", "vehicle", "animal", "flower"}
            anchor_y = object_bounds(obj)[3] if grounded else obj["center"]["y"]
            for part in obj["components"]:
                part["x"] = cx + (part["x"] - cx) * factor
                part["y"] = anchor_y + (part["y"] - anchor_y) * factor
                part["width"] *= factor
                part["height"] *= factor
            obj["center"]["y"] = anchor_y + (obj["center"]["y"] - anchor_y) * factor

    if len(movable) > 1:
        widths = [object_bounds(objects[i])[2] - object_bounds(objects[i])[0]
                  for i in movable]
        space = 1.0 - 2.0 * margin
        required = sum(widths) + gap * (len(movable) - 1)
        if required > space:
            usable = space - gap * (len(movable) - 1)
            if usable <= 0:
                raise ValueError("Too many foreground objects to separate on canvas")
            shrink(movable, min(1.0, usable / sum(widths) * 0.995))
            widths = [object_bounds(objects[i])[2] - object_bounds(objects[i])[0]
                      for i in movable]
            required = sum(widths) + gap * (len(movable) - 1)
        cursor = max(margin, (1.0 - required) / 2.0)
        for i, width_i in zip(movable, widths):
            left = object_bounds(objects[i])[0]
            objects[i] = shift_object(objects[i], cursor - left, 0.0)
            cursor += width_i + gap

    # Resolve exceptional collisions (including non-ground objects) by
    # shrinking the actual shapes, not by silently dropping requested items.
    # A final explicit check prevents falsely reporting success.
    for _ in range(64):
        pairs = collisions()
        if not pairs:
            break
        involved = sorted({i for pair in pairs for i in pair})
        shrink(involved, 0.92)
    # Re-anchor independent ground objects after all transformations.
    # Do not change explicitly stacked objects (above/below/on_top_of).
    for i in movable:
        obj = objects[i]
        dy = 0.82 - object_bounds(obj)[3]
        objects[i] = shift_object(obj, 0.0, dy)

    remaining = collisions()
    if remaining:
        labels = [f"{objects[i].get('id', i)} / {objects[j].get('id', j)}"
                  for i, j in remaining]
        raise ValueError("Unresolved foreground object overlap: " + ", ".join(labels))
    return adjusted


def _scenic_ground_y(features):
    """Match the exact visible ground boundary in the V2.9 SVG background."""
    return 0.63 if features["water"] else 0.70


def _align_foreground_to_scenic_ground(scene, ground_y):
    """Anchor each independent ground object to the scenic horizon.

    Work on component geometry before SVG conversion so depth rendering and
    decorative collision detection see the same final coordinates.
    """
    from melodia_automatic_scene_composer import object_bounds, shift_object

    result = copy.deepcopy(scene)
    relations = result.get("relationships", [])
    vertical = {"above", "below", "on_top_of"}
    protected = set()
    for relation in relations:
        if isinstance(relation, dict) and relation.get("relation") in vertical:
            protected.add(relation.get("subject"))
            protected.add(relation.get("target", relation.get("object")))
    categories = {"tree", "house", "vehicle", "animal", "flower"}
    for index, obj in enumerate(result.get("objects", [])):
        if (obj.get("category") not in categories or
                obj.get("id") in protected or not obj.get("components")):
            continue
        bottom = object_bounds(obj)[3]
        result["objects"][index] = shift_object(obj, 0.0, ground_y - bottom)
    return result


def _render_scene_svg(scene, render_depth_svg, width, height):
    """Merge scenic background and legacy artwork using one ground reference.

    Foreground collisions are resolved first. Then independent grounded
    objects are anchored to the actual scenic ground line, rather than the
    legacy composer's fixed 0.82 coordinate. Scenic decoration collision
    filtering runs only after final foreground positions are established.
    """
    scene = _resolve_foreground_collisions(scene)
    prompt = scene.get("scenic_prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return render_depth_svg(scene)

    from melodia_scenic_visual_engine import analyze_scenery, generate_scenic_svg
    features = analyze_scenery(prompt)
    if not any(features.values()):
        return render_depth_svg(scene)

    scene = _align_foreground_to_scenic_ground(scene, _scenic_ground_y(features))
    original = render_depth_svg(scene)
    scenic_root = ET.fromstring(generate_scenic_svg(
        prompt, width=width, height=height))
    _clear_scenic_collisions(scenic_root, scene, width, height)
    original_root = _parse_legacy_svg(original)
    namespace = "{http://www.w3.org/2000/svg}"
    original_viewbox = original_root.get("viewBox")
    if original_viewbox:
        parts = [float(v) for v in original_viewbox.replace(",", " ").split()]
        if len(parts) != 4 or parts[2] <= 0 or parts[3] <= 0:
            raise ValueError("Invalid legacy scene viewBox")
        x, y, source_w, source_h = parts
    else:
        x = y = 0.0
        source_w = float(original_root.get("width", width))
        source_h = float(original_root.get("height", height))
    scale_x, scale_y = width / source_w, height / source_h
    wrapper = ET.SubElement(scenic_root, namespace + "g", {
        "transform": f"scale({scale_x:.9g} {scale_y:.9g}) translate({-x:.9g} {-y:.9g})"
    })
    for child in original_root:
        if child.tag == namespace + "g" or child.tag == "g":
            wrapper.append(child)
    return ET.tostring(scenic_root, encoding="unicode")


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
            svg = _render_scene_svg(scene, render_depth_svg, width, height)
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
