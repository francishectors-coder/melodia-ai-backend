"""Optional V5 music bridge for MELODIA video worker. No existing files modified."""
import re
import wave
from pathlib import Path

from melodia_background_music import read_job_settings, add_music_to_video
from melodia_bg_engine_v1 import make_music

ROOT = Path(__file__).resolve().parent
MUSIC_DIR = ROOT / 'generated_music'


def generate_job_soundtrack(job_id):
    """Generate or reuse V5 audio for an existing music-enabled video job."""
    if not re.fullmatch(r'[A-Za-z0-9_-]+', str(job_id)):
        raise ValueError('Invalid job ID')
    import json
    job_file = ROOT / 'jobs' / f'{job_id}.json'
    job = json.loads(job_file.read_text(encoding='utf-8'))
    if (job.get('settings') or {}).get('audio', 'none') != 'music':
        raise ValueError('Job does not request music')
    prompt, duration = read_job_settings(job_id)
    if not 5 <= duration <= 1800:
        raise ValueError('V5 engine supports 5 to 1800 seconds')
    dest = MUSIC_DIR / f'{job_id}_v5.wav'
    if dest.exists():
        with wave.open(str(dest), 'rb') as wav:
            actual = wav.getnframes() / wav.getframerate()
            if wav.getnchannels() != 2 or abs(actual-duration) > .1:
                raise RuntimeError('Existing V5 soundtrack mismatch; refusing overwrite')
        return dest
    result = make_music(prompt, duration, output_dir=MUSIC_DIR / 'bg_engine')
    generated = Path(result['wav_path'])
    # Atomic publish; never overwrite a previously existing job soundtrack.
    if dest.exists():
        raise RuntimeError('V5 soundtrack already exists; refusing overwrite')
    generated.replace(dest)
    return dest


if __name__ == '__main__':
    print('MELODIA V5 VIDEO BRIDGE: IMPORT PASSED')
    print('No job processed and no existing files changed.')
