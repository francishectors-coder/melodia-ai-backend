"""MELODIA AI V3.1 — verified SVG-to-MP4 bridge (standalone).

Uses V2.4.3 single-pass encoder without invoking its legacy scene compositor.
Does not alter production modules or add music/captions; those remain a later
integration stage. The caller must supply an adapter manifest.
"""
from __future__ import annotations

import argparse
import json
import sys
import types
from contextlib import contextmanager
from pathlib import Path

from melodia_v31_production_adapter import verify_assets

VERSION = '3.1.0-bridge'


def _make_plan(manifest, transition_seconds):
    records = manifest['scenes']
    durations = [float(item['duration_seconds']) for item in records]
    overlaps = [min(float(transition_seconds), durations[i] * .2, durations[i + 1] * .2)
                for i in range(len(records) - 1)]
    scenes = [{'status': 'generated', 'objects': [], 'relationships': [],
               'v31_svg_path': item['svg_path'], 'v31_scene_id': item['scene_id'],
               'caption_en': item['caption_en']} for item in records]
    cameras = [{'keyframes': [{'x': .5, 'y': .5, 'zoom': 1.0},
                              {'x': .5, 'y': .5, 'zoom': 1.0}]} for _ in records]
    transitions = [{'from_scene': i, 'to_scene': i + 1,
                    'duration_seconds': overlaps[i],
                    'transition': 'crossfade' if overlaps[i] else 'cut'}
                   for i in range(len(overlaps))]
    return {'version': '2.3', 'scenes': scenes, 'camera_plans': cameras,
            'scene_timeline': [{'duration_seconds': d} for d in durations],
            'cinematic_transitions': transitions,
            'total_output_duration_seconds': sum(durations) - sum(overlaps)}


@contextmanager
def _direct_svg_mode(renderer, verified_records):
    """Patch only during this synchronous call; restore module state afterwards."""
    original = renderer._render_scene_svg
    previous = sys.modules.get('melodia_scene_depth_engine')
    temporary = types.ModuleType('melodia_scene_depth_engine')
    def unused_depth_renderer(*args, **kwargs):
        raise RuntimeError('Legacy geometry renderer must not run in V3.1')
    temporary.render_depth_svg = unused_depth_renderer
    sys.modules['melodia_scene_depth_engine'] = temporary
    by_id = {r['scene_id']: r for r in verified_records}
    def exact_svg(scene, _unused, width, height):
        item = by_id[scene['v31_scene_id']]
        if (width, height) != (item['width'], item['height']):
            raise ValueError('Renderer size must equal verified SVG size')
        if Path(scene['v31_svg_path']).resolve() != Path(item['svg_path']).resolve():
            raise ValueError('SVG path mismatch')
        # Read only verified assets. No scenery regeneration or object layout.
        import hashlib
        data = Path(item['svg_path']).read_bytes()
        if hashlib.sha256(data).hexdigest() != item['svg_sha256']:
            raise ValueError('SVG changed after manifest verification')
        return data.decode('utf-8')
    renderer._render_scene_svg = exact_svg
    try:
        yield
    finally:
        renderer._render_scene_svg = original
        if previous is None:
            sys.modules.pop('melodia_scene_depth_engine', None)
        else:
            sys.modules['melodia_scene_depth_engine'] = previous


def render_verified_manifest(manifest: dict, output: str | Path, *, fps: int = 10,
                             transition_seconds: float = .5, ffmpeg: str = 'ffmpeg') -> dict:
    """Encode verified V3.1 artwork using the existing single-pass renderer.

    Silent MP4 only; captions and music are intentionally not yet integrated.
    """
    verify_assets(manifest)
    if isinstance(fps, bool) or not isinstance(fps, int) or fps <= 0:
        raise ValueError('fps must be a positive integer')
    if not 0 <= transition_seconds < 10:
        raise ValueError('Invalid transition duration')
    import melodia_cinematic_video_renderer as renderer
    width, height = (manifest['scenes'][0]['width'], manifest['scenes'][0]['height'])
    plan = _make_plan(manifest, transition_seconds)
    with _direct_svg_mode(renderer, manifest['scenes']):
        result = renderer.render_video(plan, output, width=width, height=height,
                                       fps=fps, ffmpeg=ffmpeg)
    return {'version': VERSION, 'scene_ids': [r['scene_id'] for r in manifest['scenes']],
            'captions_en': [r['caption_en'] for r in manifest['scenes']],
            'renderer_result': result, 'audio': False, 'burned_captions': False}


def main():
    parser = argparse.ArgumentParser(description='MELODIA V3.1 independent rendering bridge')
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--fps', type=int, default=10)
    parser.add_argument('--transition', type=float, default=.5)
    args = parser.parse_args()
    manifest = json.loads(Path(args.manifest).read_text(encoding='utf-8'))
    print(json.dumps(render_verified_manifest(manifest, args.output, fps=args.fps,
                    transition_seconds=args.transition), indent=2))


if __name__ == '__main__':
    main()
