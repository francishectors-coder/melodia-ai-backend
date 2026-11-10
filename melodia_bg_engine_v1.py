"""MELODIA background-music engine adapter for the existing V5 composer.

Usage:
 py -3.13 melodia_bg_engine_v1.py --prompt "Gentle prayer" --duration 45
 py -3.13 melodia_bg_engine_v1.py --job request.json
"""
import argparse
import hashlib
import json
import math
import sys
import wave
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def make_music(prompt: str, duration: float = 30, output_dir=None):
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError('prompt must be nonempty text')
    if len(prompt) > 4000:
        raise ValueError('prompt is too long (maximum 4000 characters)')
    duration = float(duration)
    if not math.isfinite(duration) or not 5 <= duration <= 1800:
        raise ValueError('duration must be between 5 and 1800 seconds')
    # Import only when generating, so --help works without audio dependencies.
    from melodia_soundfont_composer_v5 import generate_music, detect_style, STYLES
    folder = Path(output_dir) if output_dir else ROOT / 'generated_music' / 'bg_engine'
    folder.mkdir(parents=True, exist_ok=True)
    # Distinct output names prevent overwriting prior jobs.
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    digest = hashlib.sha256(f'{prompt}\n{duration}\n{stamp}'.encode('utf-8')).hexdigest()[:10]
    filename = f'melodia_bg_{stamp}_{digest}.wav'
    path = folder / filename
    generated = Path(generate_music(prompt, duration=duration, output_path=path))
    with wave.open(str(generated), 'rb') as audio:
        channels = audio.getnchannels()
        rate = audio.getframerate()
        frames = audio.getnframes()
        if channels != 2 or rate <= 0 or frames <= 0:
            raise RuntimeError('Output WAV failed basic format validation')
        actual_duration = frames / rate
    if abs(actual_duration - duration) > 0.1:
        raise RuntimeError(f'Unexpected WAV duration: {actual_duration}')
    style = detect_style(prompt)
    result = {
        'status': 'completed',
        'engine': 'MELODIA_BG_V1_V5',
        'style': style,
        'tempo_bpm': STYLES[style][0],
        'prompt': prompt,
        'duration_seconds': actual_duration,
        'sample_rate': rate,
        'channels': channels,
        'wav_path': str(generated.resolve()),
        'created_utc': datetime.now(timezone.utc).isoformat(),
    }
    manifest = generated.with_suffix('.json')
    manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    result['manifest_path'] = str(manifest.resolve())
    return result


def main():
    parser = argparse.ArgumentParser(description='MELODIA V5 background music engine')
    parser.add_argument('--prompt', default='Gentle devotional prayer instrumental')
    parser.add_argument('--duration', type=float, default=30)
    parser.add_argument('--output-dir', default=None)
    parser.add_argument('--job', help='Optional JSON request file with prompt and duration')
    args = parser.parse_args()
    try:
        if args.job:
            data = json.loads(Path(args.job).read_text(encoding='utf-8'))
            if not isinstance(data, dict):
                raise ValueError('job must be a JSON object')
            prompt = data.get('prompt', args.prompt)
            duration = data.get('duration', args.duration)
        else:
            prompt, duration = args.prompt, args.duration
        result = make_music(prompt, duration, args.output_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print('RESULT: PASSED')
    except Exception as exc:
        print(f'RESULT: FAILED - {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
