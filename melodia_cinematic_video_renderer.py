"""MELODIA AI V2.4 — render V2.3 geometric orchestration plans to MP4.

Requires FFmpeg on PATH and CairoSVG (pip install cairosvg).
Uses V1.9 geometric SVG renderer. Does not modify earlier engines.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

VERSION = '2.4'


def _positive(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f'{name} must be a positive finite number')
    return float(value)


def render_video(plan, output, *, width=1280, height=720, fps=30, ffmpeg='ffmpeg'):
    """Render a V2.3 plan to silent H.264 MP4; return output metadata.

    Camera keyframes drive a gentle crop-based pan/zoom; scene transition
    overlaps follow the V2.3 timeline. This is a geometric rendering backend,
    not photorealistic image generation.
    """
    if not isinstance(plan, dict) or plan.get('version') != '2.3':
        raise ValueError('Expected a V2.3 orchestration plan')
    scenes = plan.get('scenes')
    cameras = plan.get('camera_plans')
    transitions = plan.get('cinematic_transitions')
    timeline = plan.get('scene_timeline')
    if not isinstance(scenes, list) or not scenes or not all(isinstance(v, list) for v in (cameras, transitions, timeline)):
        raise ValueError('Missing V2.3 scene, camera or timeline arrays')
    n = len(scenes)
    if len(cameras) != n or len(timeline) != n or len(transitions) != n - 1:
        raise ValueError('Inconsistent plan lengths')
    if not all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in (width, height, fps)):
        raise ValueError('width, height and fps must be positive integers')
    if width % 2 or height % 2:
        raise ValueError('H.264 dimensions must be even')
    if not shutil.which(ffmpeg):
        raise RuntimeError('FFmpeg executable not found')
    try:
        import cairosvg
        from melodia_scene_depth_engine import render_depth_svg
    except ImportError as exc:
        raise RuntimeError('Install CairoSVG and ensure V1.9 modules are available') from exc

    durations = [_positive(item['duration_seconds'], f'scene {i} duration') for i, item in enumerate(timeline)]
    overlaps = []
    for i, transition in enumerate(transitions):
        if transition.get('from_scene') != i or transition.get('to_scene') != i + 1:
            raise ValueError('Transition order mismatch')
        amount = transition.get('duration_seconds')
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount) or amount < 0:
            raise ValueError('Invalid overlap')
        if amount >= min(durations[i], durations[i + 1]):
            raise ValueError('Overlap must be shorter than adjacent scenes')
        overlaps.append(float(amount))
    expected = sum(durations) - sum(overlaps)
    if abs(expected - float(plan['total_output_duration_seconds'])) > 0.0001:
        raise ValueError('Plan output duration mismatch')

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='melodia_v24_') as directory:
        tmp = Path(directory)
        inputs = []
        for i, (scene, camera) in enumerate(zip(scenes, cameras)):
            if scene.get('status') != 'generated':
                raise ValueError(f'Scene {i} is not a generated V1.9 geometric scene')
            svg = render_depth_svg(scene)
            png = tmp / f'scene_{i:04d}.png'
            cairosvg.svg2png(bytestring=svg.encode('utf-8'), write_to=str(png),
                             output_width=width, output_height=height)
            inputs += ['-loop', '1', '-framerate', str(fps), '-t', str(durations[i]), '-i', str(png)]

        filters = []
        # Scale to a slightly oversized canvas. Camera x/y positions and zoom
        # are interpolated by FFmpeg zoompan in normalized scene coordinates.
        for i, camera in enumerate(cameras):
            frames = max(1, round(durations[i] * fps))
            keyframes = camera.get('keyframes')
            if not isinstance(keyframes, list) or len(keyframes) < 2:
                raise ValueError(f'Missing camera keyframes for scene {i}')
            a, b = keyframes[0], keyframes[-1]
            for k in (a, b):
                for name in ('x', 'y', 'zoom'):
                    val = k.get(name)
                    if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val):
                        raise ValueError(f'Invalid camera {name}')
                if not (0 <= k['x'] <= 1 and 0 <= k['y'] <= 1 and k['zoom'] >= 1):
                    raise ValueError('Camera keyframes out of bounds')
            # Interpolation uses the output frame index; the crop follows the
            # subject while staying within source image bounds.
            progress = f'min(1,max(0,on/{max(1, frames - 1)}))'
            z = f'({float(a["zoom"]):.8f}+({float(b["zoom"])-float(a["zoom"]):.8f})*{progress})'
            x = f'({float(a["x"]):.8f}+({float(b["x"])-float(a["x"]):.8f})*{progress})'
            y = f'({float(a["y"]):.8f}+({float(b["y"])-float(a["y"]):.8f})*{progress})'
            filters.append(f'[{i}:v]zoompan=z=\'{z}\':x=\'max(0,min(iw-iw/zoom,iw*{x}-iw/(2*zoom)))\':y=\'max(0,min(ih-ih/zoom,ih*{y}-ih/(2*zoom)))\':d=1:s={width}x{height}:fps={fps},trim=duration={durations[i]:.6f},setpts=PTS-STARTPTS,format=yuv420p[v{i}]')
        previous = 'v0'
        elapsed = durations[0]
        for i, transition in enumerate(transitions):
            overlap = overlaps[i]
            kind = transition.get('transition')
            label = f'm{i + 1}'
            if overlap == 0 or kind == 'cut':
                filters.append(f'[{previous}][v{i + 1}]concat=n=2:v=1:a=0[{label}]')
                elapsed += durations[i + 1]
            else:
                effect = {'crossfade': 'fade', 'dissolve': 'dissolve',
                          'fade_through_black': 'fadeblack'}.get(kind)
                if effect is None:
                    raise ValueError(f'Unsupported transition {kind}')
                offset = elapsed - overlap
                filters.append(f'[{previous}][v{i + 1}]xfade=transition={effect}:duration={overlap:.6f}:offset={offset:.6f}[{label}]')
                elapsed += durations[i + 1] - overlap
            previous = label
        command = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', *inputs,
                   '-filter_complex', ';'.join(filters), '-map', f'[{previous}]',
                   '-an', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '22',
                   '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(output)]
        if n == 1:
            command = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', *inputs,
                       '-filter_complex', ';'.join(filters), '-map', '[v0]',
                       '-an', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '22',
                       '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(output)]
        subprocess.run(command, check=True)
    return {'version': VERSION, 'output': str(output), 'expected_duration_seconds': round(expected, 6),
            'scene_count': n, 'width': width, 'height': height, 'fps': fps}


def main():
    parser = argparse.ArgumentParser(description='MELODIA AI V2.4 geometric MP4 renderer')
    parser.add_argument('--input', required=True, help='V2.3 orchestration JSON')
    parser.add_argument('--output', required=True, help='Output MP4 path')
    parser.add_argument('--width', type=int, default=1280)
    parser.add_argument('--height', type=int, default=720)
    parser.add_argument('--fps', type=int, default=30)
    args = parser.parse_args()
    plan = json.loads(Path(args.input).read_text(encoding='utf-8'))
    print(json.dumps(render_video(plan, args.output, width=args.width,
                                  height=args.height, fps=args.fps), indent=2))


if __name__ == '__main__':
    main()
