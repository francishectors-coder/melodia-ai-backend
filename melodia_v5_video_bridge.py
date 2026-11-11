
"""MELODIA AI V5 music bridge.

Supports both legacy settings.audio and web settings.music.
Preserves existing soundtracks and calls the existing local V5 engine.
"""
import json
import re
import wave
from pathlib import Path

from melodia_background_music import read_job_settings
from melodia_bg_engine_v1 import make_music

ROOT = Path(__file__).resolve().parent
MUSIC_DIR = ROOT / 'generated_music'


def music_requested(job):
    settings = job.get('settings') or {}
    music = str(settings.get('music', '')).strip().lower()
    if music:
        return music not in ('none', 'off', 'false', 'no', '0')
    return str(settings.get('audio', 'none')).strip().lower() == 'music'


def generate_job_soundtrack(job_id):
    """Generate or reuse local V5 music for a music-enabled video job."""
    if not re.fullmatch(r'[A-Za-z0-9_-]+', str(job_id)):
        raise ValueError('Invalid job ID')

    job_file = ROOT / 'jobs' / f'{job_id}.json'
    job = json.loads(job_file.read_text(encoding='utf-8'))
    if not music_requested(job):
        raise ValueError('Job does not request music')

    prompt, duration = read_job_settings(job_id)
    duration = float(duration)
    if not 5 <= duration <= 1800:
        raise ValueError('V5 engine supports 5 to 1800 seconds')

    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    dest = MUSIC_DIR / f'{job_id}_v5.wav'
    if dest.exists():
        with wave.open(str(dest), 'rb') as wav:
            actual = wav.getnframes() / wav.getframerate()
            if wav.getnchannels() != 2 or abs(actual - duration) > 0.1:
                raise RuntimeError(
                    'Existing V5 soundtrack mismatch; refusing overwrite'
                )
        return dest

    result = make_music(
        prompt,
        duration,
        output_dir=MUSIC_DIR / 'bg_engine'
    )
    generated = Path(result['wav_path'])
    if not generated.is_file() or generated.stat().st_size == 0:
        raise RuntimeError('V5 music engine did not produce a WAV file')
    if dest.exists():
        raise RuntimeError(
            'V5 soundtrack already exists; refusing overwrite'
        )
    generated.replace(dest)
    return dest


if __name__ == '__main__':
    print('MELODIA V5 VIDEO BRIDGE: IMPORT PASSED')
    print('No job processed and no existing files changed.')
