# MELODIA AI - AUTOMATIC VIDEO WORKER
# Step 1337.28 - Full-frame composition with complete foreground objects; V5 music preserved
# Existing production flow retained; test activated by [FREE TEST] in prompt.

import json
import math
import os
import shutil
import subprocess
import tempfile
import wave
from array import array
from pathlib import Path
from datetime import datetime, timezone

from melodia_scene_planner import create_scene_plan
from melodia_video_assembler import assemble_video
from melodia_gemini_generator import generate_multilingual_captions
from melodia_v5_video_bridge import generate_job_soundtrack
from melodia_background_music import add_music_to_video

ROOT = Path(__file__).resolve().parent
JOBS = ROOT / 'jobs'
PLANS = ROOT / 'scene_plans'
OUTPUTS = ROOT / 'outputs'
CONTENT = ROOT / 'generated_content'
VISUALS = ROOT / 'generated_visuals'
for folder in (JOBS, PLANS, OUTPUTS, CONTENT, VISUALS):
    folder.mkdir(parents=True, exist_ok=True)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def save_job(job_file, job):
    job['updated_at'] = utc_now()
    temporary = job_file.with_suffix('.tmp')
    with temporary.open('w', encoding='utf-8') as file:
        json.dump(job, file, ensure_ascii=False, indent=2)
    temporary.replace(job_file)


def find_pending_jobs():
    pending = []
    allowed_statuses = (
        'queued', 'preparing', 'scenes_ready', 'generating_captions',
        'captions_ready', 'rendering', 'generating_music', 'adding_music'
    )
    for job_file in sorted(JOBS.glob('*.json')):
        try:
            with job_file.open('r', encoding='utf-8') as file:
                job = json.load(file)
            if job.get('status') in allowed_statuses:
                pending.append((job_file, job))
        except (OSError, ValueError) as error:
            print('Skipping invalid job:', error, flush=True)
    return pending


def images_ready(plan):
    scenes = plan.get('scenes', [])
    if not scenes:
        return False
    for scene in scenes:
        image_path = scene.get('image_path')
        if not image_path:
            return False
        image = Path(image_path)
        if not image.is_file() or image.stat().st_size == 0:
            return False
    return True


def is_quota_error(error):
    message = str(error).lower()
    return any(term in message for term in (
        'zerogpu', 'quota', 'rate limit', 'too many requests',
        'exceeded your', '429', '402', 'resource_exhausted',
        'prepayment credits', 'credits are depleted'
    ))


def preserve_image_progress(job, plan_path):
    if not plan_path.is_file():
        return
    try:
        with plan_path.open('r', encoding='utf-8') as file:
            saved_plan = json.load(file)
        scenes = saved_plan.get('scenes', [])
        total = len(scenes)
        completed = sum(
            1 for scene in scenes
            if scene.get('image_path')
            and Path(scene['image_path']).is_file()
            and Path(scene['image_path']).stat().st_size > 0
        )
        if total:
            job['progress'] = min(39, int(40 * completed / total))
        job['completed_images'] = completed
        job['total_images'] = total
    except (OSError, ValueError, KeyError, TypeError):
        pass


def finish_job(job_file, job, output):
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError('Final MP4 missing or empty')
    job['status'] = 'completed'
    job['progress'] = 100
    job['video_path'] = str(output)
    job.pop('error', None)
    save_job(job_file, job)
    print('VIDEO GENERATION COMPLETE:', output, flush=True)


def is_free_test(job):
    # Explicit marker only. Ordinary customer prompts remain production jobs.
    settings = job.get('settings') or {}
    prompt = str(job.get('prompt') or settings.get('prompt') or '')
    return '[FREE TEST]' in prompt.upper()


def free_test_theme(prompt):
    """Choose a deterministic, offline geometric scenery theme from prompt words."""
    import re
    words = set(re.findall(r"[a-z]+", prompt.lower().replace('[free test]', '')))
    themes = (
        ('space', {'space', 'universe', 'planet', 'planets', 'galaxy', 'galaxies',
                   'moon', 'saturn', 'stars', 'astronomy', 'cosmos', 'nebula'}),
        ('ocean', {'ocean', 'sea', 'beach', 'underwater', 'coral', 'marine', 'fish', 'island'}),
        ('city', {'city', 'architecture', 'buildings', 'urban', 'skyscraper', 'street'}),
        ('prayer', {'prayer', 'church', 'jesus', 'mary', 'christian', 'candle', 'faith'}),
        ('nature', {'nature', 'forest', 'waterfall', 'mountain', 'mountains', 'river',
                    'landscape', 'sunrise', 'sunset', 'wildlife', 'trees'}),
    )
    scores = [(len(words & keywords), name) for name, keywords in themes]
    score, name = max(scores, key=lambda entry: entry[0])
    return name if score else 'inspiration'


def prepare_free_test(job_id, job=None):
    """Create three prompt-sensitive geometric scenes offline; no paid API."""
    from PIL import Image, ImageDraw
    import random

    job = job or {}
    settings = job.get('settings') or {}
    prompt = str(job.get('prompt') or settings.get('prompt') or '')
    theme = free_test_theme(prompt)
    image_dir = VISUALS / job_id
    image_dir.mkdir(parents=True, exist_ok=True)
    plan_path = PLANS / f'{job_id}_scenes.json'
    caption_path = CONTENT / f'{job_id}_captions.json'

    content = {
        'space': (
            ('BEYOND OUR WORLD', 'THE RINGS OF SATURN', 'DISTANT GALAXIES'),
            ('Our universe is full of wonders.', 'Planets travel among the stars.',
             'Every galaxy holds new mysteries.'),
            ((11, 16, 47), (22, 14, 67), (12, 31, 73))),
        'ocean': (
            ('THE BLUE OCEAN', 'BENEATH THE WAVES', 'A LIVING REEF'),
            ('The ocean connects our world.', 'Marine life thrives below the surface.',
             'Coral reefs shelter countless creatures.'),
            ((13, 79, 119), (8, 62, 98), (7, 89, 113))),
        'city': (
            ('CITY LIGHTS', 'URBAN HORIZONS', 'THE CITY AWAKENS'),
            ('Cities bring people together.', 'Architecture shapes our skylines.',
             'Every street tells a story.'),
            ((41, 52, 87), (74, 61, 96), (39, 76, 103))),
        'prayer': (
            ('A MOMENT OF PEACE', 'LIGHT OF HOPE', 'FAITH AND GRATITUDE'),
            ('May peace fill every heart.', 'A quiet light can inspire hope.',
             'Let gratitude guide our day.'),
            ((65, 71, 112), (83, 66, 99), (85, 91, 120))),
        'nature': (
            ('THE GREAT OUTDOORS', 'MOUNTAINS AND VALLEYS', 'A NEW DAWN'),
            ('Nature surrounds us with beauty.', 'Every landscape has a story.',
             'The earth welcomes a new day.'),
            ((34, 101, 125), (47, 97, 108), (87, 117, 126))),
        'inspiration': (
            ('A NEW BEGINNING', 'FIND YOUR PEACE', 'EVERY MOMENT MATTERS'),
            ('Every new day brings possibility.', 'Small steps lead to change.',
             'Make this moment count.'),
            ((32, 75, 125), (28, 105, 91), (112, 66, 118))),
    }
    titles, messages, backgrounds = content[theme]
    scenes, records = [], []
    for index, (title, message, color) in enumerate(zip(titles, messages, backgrounds), 1):
        image_path = image_dir / f'scene_{index:03d}.png'
        if not image_path.is_file() or image_path.stat().st_size == 0:
            rng = random.Random(f'{job_id}:{index}:{theme}')
            image = Image.new('RGB', (854, 480), color)
            draw = ImageDraw.Draw(image)
            # Full-bleed 16:9 composition. Background may fill the edges;
            # complete foreground objects stay within a 5% safe margin.
            if theme == 'space':
                for _ in range(65):
                    x, y = rng.randrange(30, 824), rng.randrange(115, 445)
                    r = rng.choice((1, 1, 2, 3))
                    draw.ellipse((x-r, y-r, x+r, y+r), fill=(213, 223, 246))
                cx, cy, radius = 540 + index*35, 280, 95
                draw.ellipse((cx-radius, cy-radius, cx+radius, cy+radius),
                             fill=(93+index*23, 120, 174))
                draw.ellipse((cx-48, cy-40, cx-12, cy-4), fill=(114, 148, 197))
                draw.ellipse((cx+12, cy+26, cx+43, cy+57), fill=(68, 98, 148))
            elif theme == 'ocean':
                # Water is a full-frame background; fish remain entirely visible.
                for band in range(7):
                    y = 160 + band*45
                    draw.rectangle((0, y, 853, min(479, y+25)),
                                   fill=(10, 76+band*5, 122+band*4))
                for n in range(11):
                    x = 65 + n*65
                    y = 280 + rng.randrange(105)
                    draw.polygon(((x,y),(x+23,y-12),(x+23,y+12)),
                                 fill=(236, 174, 104))
                    draw.ellipse((x+21,y-9,x+48,y+9), fill=(236, 174, 104))
                for _ in range(14):
                    x = rng.randrange(45, 801)
                    y = rng.randrange(155, 420)
                    draw.ellipse((x,y,x+8,y+8), outline=(167, 219, 238), width=2)
            elif theme == 'city':
                # Buildings have visible bases, not bottoms clipped at y=480.
                draw.rectangle((0, 430, 853, 479), fill=(43, 49, 74))
                for n in range(10):
                    x = 55 + n*75
                    h = rng.randrange(120, 260)
                    top, bottom = 430-h, 430
                    draw.rectangle((x, top, x+52, bottom), fill=(25, 37, 67))
                    for wx in range(x+9, x+47, 15):
                        for wy in range(top+14, bottom-14, 24):
                            draw.rectangle((wx, wy, wx+7, wy+10),
                                           fill=(232, 193, 110))
                draw.ellipse((660, 115, 760, 215), fill=(249, 211, 150))
            elif theme == 'prayer':
                # Complete church silhouette: roof, walls and base all visible.
                draw.ellipse((645, 118, 785, 258), fill=(245, 197, 120))
                draw.polygon(((242, 296), (427, 139), (612, 296)),
                             fill=(49, 49, 77))
                draw.rectangle((276, 296, 578, 440), fill=(42, 43, 69))
                draw.rectangle((406, 182, 424, 271), fill=(247, 224, 170))
                draw.rectangle((381, 208, 449, 226), fill=(247, 224, 170))
                # Door and windows make the building visibly complete.
                draw.rectangle((408, 371, 449, 440), fill=(102, 88, 91))
                draw.rectangle((319, 329, 351, 364), fill=(245, 197, 120))
                draw.rectangle((505, 329, 537, 364), fill=(245, 197, 120))
                draw.line(((250, 441), (605, 441)), fill=(210, 197, 172), width=3)
            else:
                # Hills are background silhouettes; trees are complete objects.
                draw.ellipse((655, 122, 775, 242), fill=(246, 202, 118))
                draw.polygon(((0, 400), (180, 200), (390, 400)), fill=(24, 64, 77))
                draw.polygon(((230, 412), (510, 175), (853, 412)), fill=(29, 73, 79))
                draw.rectangle((0, 417, 853, 479), fill=(22, 65, 72))
                if theme == 'nature':
                    for n in range(9):
                        x = 62 + n*87
                        draw.rectangle((x, 345, x+12, 441), fill=(55, 52, 43))
                        draw.polygon(((x-29, 370), (x+6, 258), (x+41, 370)),
                                     fill=(23, 90, 65))
            # Header is overlaid directly on the full-size illustration.
            # The video assembler handles subtitles separately.
            draw.rectangle((0, 0, 853, 103), fill=(18, 28, 49))
            draw.text((35, 25), 'MELODIA AI - FREE TEST', fill=(220, 230, 241))
            draw.text((35, 62), title, fill='white')
            image.save(image_path, format='PNG')

        start, end = float((index - 1) * 10), float(index * 10)
        scenes.append({
            'scene_number': index, 'start_seconds': start, 'end_seconds': end,
            'duration_seconds': 10.0, 'image_path': str(image_path.resolve()),
            'caption_mode': 'single', 'primary_language': 'English',
            'second_language': None
        })
        records.append({
            'scene_number': index, 'start_seconds': start, 'end_seconds': end,
            'primary': message, 'translated': ''
        })

    plan = {
        'job_id': job_id, 'aspect_ratio': '16:9', 'duration_seconds': 30.0,
        'generation_status': 'complete', 'scenes': scenes
    }
    captions = {
        'job_id': job_id, 'caption_mode': 'single',
        'primary_language': 'English', 'second_language': None, 'records': records
    }
    if not plan_path.exists():
        plan_path.write_text(json.dumps(plan, indent=2), encoding='utf-8')
    if not caption_path.exists():
        caption_path.write_text(json.dumps(captions, ensure_ascii=False, indent=2), encoding='utf-8')
    print('FREE TEST SCENERY THEME:', theme, flush=True)
    return plan_path, caption_path


def free_test_music_enabled(job):
    """Respect the frontend's explicit music selector in free-test mode."""
    settings = job.get('settings') or {}
    mode = str(settings.get('music', 'none')).strip().lower()
    return mode not in ('none', 'off', 'false', 'no', '')


def create_free_test_soundtrack(destination, seconds=30):
    """Generate an original soft instrumental pad locally; no paid APIs."""
    sample_rate = 22050
    total_samples = int(seconds * sample_rate)
    samples = array('h')
    # Three gently changing major chords, one per ten-second scene.
    chords = (
        (261.63, 329.63, 392.00),
        (220.00, 261.63, 329.63),
        (196.00, 246.94, 392.00),
    )
    for index in range(total_samples):
        t = index / sample_rate
        chord = chords[min(int(t // 10), len(chords) - 1)]
        # A slow envelope avoids clicks and provides fade-in/out.
        fade = min(1.0, t / 2.0, (seconds - t) / 3.0)
        fade = max(0.0, fade)
        # Gentle modulation makes this a sustained instrumental texture.
        pulse = 0.82 + 0.18 * math.sin(2 * math.pi * 0.22 * t)
        tone = sum(
            math.sin(2 * math.pi * hz * t) +
            0.13 * math.sin(2 * math.pi * hz * 2 * t)
            for hz in chord
        ) / (len(chord) * 1.13)
        samples.append(int(10500 * fade * pulse * tone))
    with wave.open(str(destination), 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(samples.tobytes())
    if not destination.is_file() or destination.stat().st_size < 1000:
        raise RuntimeError('Local instrumental soundtrack was not created')


def mux_free_test_music(silent_video, destination):
    """Copy rendered video and attach locally generated AAC audio."""
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise RuntimeError('FFmpeg is required to add free-test music')
    with tempfile.TemporaryDirectory(prefix='melodia_free_audio_', dir=OUTPUTS) as folder:
        folder = Path(folder)
        soundtrack = folder / 'instrumental.wav'
        combined = folder / 'with_music.mp4'
        create_free_test_soundtrack(soundtrack)
        command = [
            ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
            '-i', str(silent_video), '-i', str(soundtrack),
            '-map', '0:v:0', '-map', '1:a:0',
            '-c:v', 'copy', '-c:a', 'aac', '-b:a', '128k',
            '-t', '30', '-movflags', '+faststart', str(combined),
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError('FFmpeg audio mux failed: ' + result.stderr[-3000:])
        if not combined.is_file() or combined.stat().st_size == 0:
            raise RuntimeError('Music-enabled MP4 is missing')
        # Fail rather than mark a silent video complete.
        probe = shutil.which('ffprobe')
        if probe:
            check = subprocess.run([
                probe, '-v', 'error', '-select_streams', 'a:0',
                '-show_entries', 'stream=codec_name',
                '-of', 'default=noprint_wrappers=1:nokey=1', str(combined),
            ], capture_output=True, text=True)
            if check.returncode != 0 or 'aac' not in check.stdout.lower():
                raise RuntimeError('Audio verification failed: no AAC stream')
        os.replace(combined, destination)


def process_free_test(job_file, job):
    """Render the free video, then call the existing V5 music engine."""
    job_id = job['job_id']
    final_video = OUTPUTS / f'{job_id}.mp4'
    silent_master = OUTPUTS / f'{job_id}_silent_master.mp4'
    wants_music = free_test_music_enabled(job)
    try:
        job['status'] = 'preparing'
        job['progress'] = 10
        job.pop('error', None)
        save_job(job_file, job)
        prepare_free_test(job_id, job)

        # An old silent file must not be mistaken for a music-enabled result.
        if wants_music and final_video.is_file():
            probe = shutil.which('ffprobe')
            has_audio = False
            if probe:
                result = subprocess.run([
                    probe, '-v', 'error', '-select_streams', 'a:0',
                    '-show_entries', 'stream=codec_name',
                    '-of', 'default=noprint_wrappers=1:nokey=1',
                    str(final_video)
                ], capture_output=True, text=True)
                has_audio = result.returncode == 0 and bool(result.stdout.strip())
            if has_audio:
                finish_job(job_file, job, final_video)
                return
            if not silent_master.exists():
                os.replace(final_video, silent_master)
            else:
                raise RuntimeError('Silent output and silent master both exist; refusing overwrite')

        if not silent_master.is_file() and not final_video.is_file():
            job['status'] = 'rendering'
            job['progress'] = 50
            save_job(job_file, job)
            rendered = Path(assemble_video(job_id))
            if not rendered.is_file() or rendered.stat().st_size == 0:
                raise RuntimeError('Free-test video was not rendered')
            if wants_music:
                if silent_master.exists():
                    raise RuntimeError('Silent master exists; refusing overwrite')
                os.replace(rendered, silent_master)
            elif rendered != final_video:
                os.replace(rendered, final_video)

        if wants_music:
            job['status'] = 'generating_music'
            job['progress'] = 85
            save_job(job_file, job)
            print('FREE TEST: calling V5 generate_job_soundtrack', flush=True)
            music_file = Path(generate_job_soundtrack(job_id))
            if not music_file.is_file() or music_file.stat().st_size <= 44:
                raise RuntimeError('V5 music engine returned no usable soundtrack')
            job['status'] = 'adding_music'
            job['progress'] = 95
            save_job(job_file, job)
            with tempfile.TemporaryDirectory(prefix='melodia_v5_', dir=OUTPUTS) as tmp:
                combined = Path(tmp) / 'combined.mp4'
                add_music_to_video(silent_master, music_file, combined)
                if not combined.is_file() or combined.stat().st_size == 0:
                    raise RuntimeError('Music muxing produced no MP4')
                probe = shutil.which('ffprobe')
                if not probe:
                    raise RuntimeError('ffprobe required to verify soundtrack')
                checked = subprocess.run([
                    probe, '-v', 'error', '-select_streams', 'a:0',
                    '-show_entries', 'stream=codec_name',
                    '-of', 'default=noprint_wrappers=1:nokey=1',
                    str(combined)
                ], capture_output=True, text=True)
                if checked.returncode != 0 or 'aac' not in checked.stdout.lower():
                    raise RuntimeError('Muxed video has no AAC audio stream')
                os.replace(combined, final_video)
            print('FREE TEST: V5 soundtrack verified in MP4', flush=True)
        finish_job(job_file, job, final_video)
    except Exception as error:
        job['status'] = 'failed'
        job['error'] = 'Free video/music integration failed: ' + str(error)
        save_job(job_file, job)
        print('FREE TEST FAILED:', error, flush=True)


def process_job(job_file, job):
    job_id = job['job_id']
    if is_free_test(job):
        print('FREE TEST MODE: no Gemini or paid music API calls', flush=True)
        process_free_test(job_file, job)
        return

    settings = job.get('settings') or {}
    audio_mode = 'music' if free_test_music_enabled(job) else settings.get('audio', 'none')
    if audio_mode not in ('none', 'music'):
        job['status'] = 'failed'
        job['error'] = 'Audio mode not yet supported: ' + str(audio_mode)
        save_job(job_file, job)
        return

    print('Job ID:', job_id)
    print('Current status:', job['status'])
    plan_path = PLANS / f'{job_id}_scenes.json'
    video_path = OUTPUTS / f'{job_id}.mp4'
    silent_master = OUTPUTS / f'{job_id}_silent_master.mp4'

    if video_path.is_file() and video_path.stat().st_size > 0:
        finish_job(job_file, job, video_path)
        print('Existing MP4 preserved:', video_path)
        return

    if audio_mode == 'music' and silent_master.is_file() and silent_master.stat().st_size > 0:
        print('Existing silent master preserved:', silent_master)
    else:
        job['status'] = 'preparing'
        job['progress'] = 5
        job.pop('error', None)
        save_job(job_file, job)
        try:
            plan, plan_output = create_scene_plan(job)
            if not images_ready(plan):
                raise RuntimeError('Scene generation is incomplete')
            job['status'] = 'scenes_ready'
            job['progress'] = 40
            job.pop('error', None)
            save_job(job_file, job)
            print('All scene images verified:', plan_output)
        except Exception as error:
            if is_quota_error(error):
                job['status'] = 'paused_quota'
                job['progress'] = 5
                preserve_image_progress(job, plan_path)
                job['error'] = (
                    'Image-generation provider quota reached. '
                    'Generated images preserved; job can resume.'
                )
            else:
                job['status'] = 'failed'
                job['error'] = str(error)
            save_job(job_file, job)
            print('SCENE GENERATION INTERRUPTED:', error)
            return

        caption_mode = plan.get('scenes', [{}])[0].get('caption_mode', 'single')
        if caption_mode != 'none':
            job['status'] = 'generating_captions'
            job['progress'] = 42
            save_job(job_file, job)
            try:
                caption_file = generate_multilingual_captions(job_id)
                if not caption_file.is_file() or caption_file.stat().st_size == 0:
                    raise RuntimeError('Caption file missing or empty')
                job['caption_path'] = str(caption_file)
                job['status'] = 'captions_ready'
                job['progress'] = 48
                job.pop('error', None)
                save_job(job_file, job)
                print('Captions generated:', caption_file)
            except Exception as error:
                if is_quota_error(error):
                    job['status'] = 'paused_quota'
                    job['error'] = (
                        'Gemini caption quota reached. '
                        'Existing scene images preserved; job can resume.'
                    )
                else:
                    job['status'] = 'failed'
                    job['error'] = 'Caption generation failed: ' + str(error)
                save_job(job_file, job)
                print('CAPTION GENERATION INTERRUPTED:', error)
                return
        else:
            print('Caption generation skipped: no captions requested')

        job['status'] = 'rendering'
        job['progress'] = 50
        save_job(job_file, job)
        try:
            rendered = assemble_video(job_id)
            if not rendered.is_file() or rendered.stat().st_size == 0:
                raise RuntimeError('MP4 output is missing or empty')
            if audio_mode == 'none':
                finish_job(job_file, job, rendered)
                return
            if silent_master.exists():
                raise RuntimeError('Silent master already exists; refusing overwrite')
            os.replace(rendered, silent_master)
            print('Silent master preserved:', silent_master)
        except Exception as error:
            job['status'] = 'failed'
            job['error'] = 'MP4 assembly failed: ' + str(error)
            save_job(job_file, job)
            print('MP4 ASSEMBLY FAILED:', error)
            return

    if audio_mode == 'none':
        job['status'] = 'failed'
        job['error'] = 'Silent video was not finalized'
        save_job(job_file, job)
        return

    job['status'] = 'generating_music'
    job['progress'] = 85
    save_job(job_file, job)
    try:
        music_file = generate_job_soundtrack(job_id)
        job['music_path'] = str(music_file)
        job['status'] = 'adding_music'
        job['progress'] = 95
        save_job(job_file, job)
        with tempfile.TemporaryDirectory(prefix='melodia_music_', dir=OUTPUTS) as temp_dir:
            temp_output = Path(temp_dir) / 'final.mp4'
            add_music_to_video(silent_master, music_file, temp_output)
            if not temp_output.is_file() or temp_output.stat().st_size == 0:
                raise RuntimeError('Soundtrack muxing produced no MP4')
            if video_path.exists():
                raise RuntimeError('Final MP4 already exists; refusing overwrite')
            os.replace(temp_output, video_path)
        finish_job(job_file, job, video_path)
    except Exception as error:
        job['status'] = 'failed'
        job['error'] = 'Background music integration failed: ' + str(error)
        save_job(job_file, job)
        print('BACKGROUND MUSIC FAILED:', error)
        print('Silent master preserved:', silent_master)


def main():
    print('MELODIA AI - AUTOMATIC VIDEO WORKER')
    pending = find_pending_jobs()
    print('Pending jobs found:', len(pending))
    if not pending:
        print('NO PENDING JOBS')
        return
    job_file, job = pending[0]
    process_job(job_file, job)
    print('WORKER FINISHED')


if __name__ == '__main__':
    main()
