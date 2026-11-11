
# MELODIA AI - AUTOMATIC VIDEO WORKER
# Step 1337.34 - Full-height scenery and three distinct scenes
# Production workflow and V5 soundtrack preserved.

import json
import math
import os
import random
import re
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
JOBS = ROOT / "jobs"
PLANS = ROOT / "scene_plans"
OUTPUTS = ROOT / "outputs"
CONTENT = ROOT / "generated_content"
VISUALS = ROOT / "generated_visuals"

for folder in (JOBS, PLANS, OUTPUTS, CONTENT, VISUALS):
    folder.mkdir(parents=True, exist_ok=True)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def save_job(job_file, job):
    job["updated_at"] = utc_now()
    temporary = job_file.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as f:
        json.dump(job, f, ensure_ascii=False, indent=2)
    temporary.replace(job_file)


def find_pending_jobs():
    statuses = (
        "queued", "preparing", "scenes_ready",
        "generating_captions", "captions_ready",
        "rendering", "generating_music", "adding_music"
    )
    pending = []
    for job_file in sorted(JOBS.glob("*.json")):
        try:
            with job_file.open(encoding="utf-8") as f:
                job = json.load(f)
            if job.get("status") in statuses:
                pending.append((job_file, job))
        except (OSError, ValueError) as error:
            print("Skipping invalid job:", error, flush=True)
    return pending


def images_ready(plan):
    scenes = plan.get("scenes", [])
    return bool(scenes) and all(
        scene.get("image_path")
        and Path(scene["image_path"]).is_file()
        and Path(scene["image_path"]).stat().st_size > 0
        for scene in scenes
    )


def is_quota_error(error):
    message = str(error).lower()
    return any(term in message for term in (
        "zerogpu", "quota", "rate limit",
        "too many requests", "exceeded your",
        "429", "402", "resource_exhausted",
        "prepayment credits", "credits are depleted"
    ))


def preserve_image_progress(job, plan_path):
    if not plan_path.is_file():
        return
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        scenes = plan.get("scenes", [])
        completed = sum(
            1 for scene in scenes
            if scene.get("image_path")
            and Path(scene["image_path"]).is_file()
            and Path(scene["image_path"]).stat().st_size > 0
        )
        if scenes:
            job["progress"] = min(
                39, int(40 * completed / len(scenes))
            )
        job["completed_images"] = completed
        job["total_images"] = len(scenes)
    except (OSError, ValueError, KeyError, TypeError):
        pass


def finish_job(job_file, job, output):
    output = Path(output)
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError("Final MP4 missing or empty")
    job["status"] = "completed"
    job["progress"] = 100
    job["video_path"] = str(output)
    job.pop("error", None)
    save_job(job_file, job)
    print("VIDEO GENERATION COMPLETE:", output, flush=True)


def is_free_test(job):
    settings = job.get("settings") or {}
    prompt = str(job.get("prompt") or settings.get("prompt") or "")
    return "[FREE TEST]" in prompt.upper()


def free_test_theme(prompt):
    words = set(re.findall(
        r"[a-z]+",
        prompt.lower().replace("[free test]", "")
    ))
    themes = (
        ("space", {
            "space", "universe", "planet", "planets",
            "galaxy", "galaxies", "moon", "saturn",
            "stars", "astronomy", "cosmos", "nebula"
        }),
        ("ocean", {
            "ocean", "sea", "beach", "underwater",
            "coral", "marine", "fish", "island"
        }),
        ("city", {
            "city", "architecture", "buildings",
            "urban", "skyscraper", "street"
        }),
        ("prayer", {
            "prayer", "church", "jesus",
            "mary", "christian", "candle", "faith"
        }),
        ("nature", {
            "nature", "forest", "waterfall",
            "mountain", "mountains", "river",
            "landscape", "sunrise", "sunset",
            "wildlife", "trees"
        }),
    )
    scores = [
        (len(words & keywords), name)
        for name, keywords in themes
    ]
    score, name = max(scores, key=lambda item: item[0])
    return name if score else "inspiration"


def free_test_people_request(prompt):
    text = prompt.lower()
    if "last supper" in text or (
        "jesus" in text and "apostles" in text
    ):
        return "last_supper"
    if any(term in text for term in (
        "people", "person", "human", "family",
        "children", "crowd", "walking", "praying",
        "apostles", "jesus", "mary",
        "teacher", "students"
    )):
        return "people"
    return None


def draw_geometric_person(
    draw, x, y, scale=1.0,
    robe=(100, 117, 157),
    skin=(218, 172, 130),
    halo=False, seated=False
):
    x, y = int(x), int(y)
    r = max(3, int(13 * scale))

    if halo:
        hr = int(20 * scale)
        draw.ellipse(
            (x-hr, y-hr, x+hr, y+hr),
            outline=(249, 210, 121),
            width=max(2, int(3 * scale))
        )

    draw.ellipse(
        (x-r, y-r, x+r, y+r),
        fill=skin
    )

    shoulder = int(22 * scale)
    top = y + r + int(4 * scale)
    bottom = top + int(
        (43 if seated else 64) * scale
    )

    draw.polygon((
        (x-shoulder, top+int(9*scale)),
        (x+shoulder, top+int(9*scale)),
        (x+int(27*scale), bottom),
        (x-int(27*scale), bottom)
    ), fill=robe)

    for direction in (-1, 1):
        draw.line((
            (x+direction*shoulder,
             top+int(14*scale)),
            (x+direction*int(30*scale),
             bottom-int(11*scale))
        ), fill=skin, width=max(3, int(5*scale)))

    if not seated:
        for direction in (-1, 1):
            leg_x = x + direction * int(11*scale)
            draw.line((
                (leg_x, bottom),
                (leg_x, bottom+int(28*scale))
            ), fill=(57, 56, 71),
               width=max(4, int(9*scale)))


PALETTE = (
    (72, 99, 139),
    (142, 83, 82),
    (112, 121, 87),
    (118, 93, 142),
    (142, 113, 75),
    (79, 116, 114),
)


def draw_last_supper(draw, index):
    """
    Three different Last Supper compositions.
    All geometry is drawn on the full 854x480 canvas.
    No reserved 104-pixel header.
    """

    if index == 1:
        # Scene 1: Wide view, Jesus and twelve apostles.
        draw.rectangle(
            (0, 0, 853, 479),
            fill=(104, 86, 83)
        )
        draw.rectangle(
            (35, 30, 819, 423),
            fill=(155, 127, 109),
            outline=(226, 193, 151),
            width=5
        )

        for x in (95, 707):
            draw.rectangle(
                (x, 65, x+50, 220),
                fill=(65, 83, 103),
                outline=(228, 198, 150),
                width=6
            )

        draw.polygon((
            (342, 55), (427, 22), (512, 55)
        ), fill=(116, 97, 95))

        for i in range(13):
            x = 75 + i * 58
            jesus = i == 6
            draw_geometric_person(
                draw, x,
                153 if jesus else 170,
                scale=1.05,
                robe=(185, 67, 71)
                if jesus else PALETTE[i % 6],
                halo=jesus,
                seated=True
            )

        draw.polygon((
            (56, 290), (798, 290),
            (815, 375), (40, 375)
        ), fill=(226, 197, 155))

        draw.rectangle(
            (56, 375, 798, 398),
            fill=(112, 71, 57)
        )

        for x in (84, 749):
            draw.rectangle(
                (x, 398, x+19, 447),
                fill=(112, 71, 57)
            )

        for x in (213, 325, 531, 643):
            draw.ellipse(
                (x-16, 320, x+16, 334),
                fill=(245, 215, 152)
            )

        for x in (280, 427, 574):
            draw.polygon((
                (x-9, 312), (x+9, 312),
                (x+5, 343), (x-5, 343)
            ), fill=(229, 192, 95))

        draw.rectangle(
            (0, 448, 853, 479),
            fill=(89, 74, 71)
        )

    elif index == 2:
        # Scene 2: Medium view of blessing bread and wine.
        draw.rectangle(
            (0, 0, 853, 479),
            fill=(88, 72, 74)
        )
        draw.rectangle(
            (44, 22, 810, 431),
            fill=(174, 139, 111),
            outline=(225, 189, 139),
            width=7
        )

        draw.polygon((
            (305, 25), (427, 80), (549, 25)
        ), fill=(109, 82, 76))

        draw.rectangle(
            (345, 85, 509, 265),
            fill=(71, 87, 106),
            outline=(226, 195, 143),
            width=8
        )

        for i, x in enumerate(
            (105, 202, 299, 555, 652, 749)
        ):
            draw_geometric_person(
                draw, x,
                187 + (i % 2) * 9,
                scale=1.25,
                robe=PALETTE[(i+2) % 6],
                seated=True
            )

        draw_geometric_person(
            draw, 427, 130,
            scale=1.85,
            robe=(180, 58, 68),
            halo=True,
            seated=True
        )

        draw.polygon((
            (54, 345), (800, 345),
            (822, 418), (32, 418)
        ), fill=(234, 199, 150))

        draw.rectangle(
            (50, 418, 804, 442),
            fill=(104, 64, 52)
        )

        draw.line(
            ((372, 263), (411, 345)),
            fill=(220, 172, 129),
            width=12
        )
        draw.line(
            ((482, 263), (443, 345)),
            fill=(220, 172, 129),
            width=12
        )

        draw.ellipse(
            (396, 354, 458, 377),
            fill=(247, 216, 153),
            outline=(184, 131, 74),
            width=3
        )

        draw.polygon((
            (496, 348), (525, 348),
            (520, 384), (502, 384)
        ), fill=(227, 190, 88))

        draw.line(
            ((511, 384), (511, 401)),
            fill=(227, 190, 88),
            width=4
        )

        draw.rectangle(
            (0, 444, 853, 479),
            fill=(88, 72, 74)
        )

    else:
        # Scene 3: Closer view of Jesus addressing apostles.
        draw.rectangle(
            (0, 0, 853, 479),
            fill=(63, 78, 94)
        )

        draw.rectangle(
            (35, 20, 819, 439),
            fill=(126, 106, 100),
            outline=(213, 183, 138),
            width=7
        )

        draw.ellipse(
            (326, 25, 528, 260),
            fill=(232, 184, 122)
        )
        draw.rectangle(
            (326, 140, 528, 260),
            fill=(232, 184, 122)
        )
        draw.rectangle(
            (350, 50, 504, 257),
            fill=(91, 109, 132)
        )
        draw.line(
            ((427, 50), (427, 257)),
            fill=(224, 193, 149),
            width=7
        )

        listeners = (
            (115, 200), (245, 220),
            (609, 220), (739, 200)
        )

        for i, (x, y) in enumerate(listeners):
            draw_geometric_person(
                draw, x, y,
                scale=1.5,
                robe=PALETTE[(i+3) % 6],
                seated=True
            )

        draw_geometric_person(
            draw, 427, 110,
            scale=2.35,
            robe=(186, 65, 75),
            halo=True,
            seated=True
        )

        draw.line(
            ((490, 245), (560, 200)),
            fill=(220, 172, 129),
            width=14
        )
        draw.ellipse(
            (548, 187, 570, 210),
            fill=(220, 172, 129)
        )

        draw.polygon((
            (65, 382), (789, 382),
            (809, 432), (45, 432)
        ), fill=(222, 187, 145))

        draw.ellipse(
            (392, 390, 461, 418),
            fill=(246, 215, 150)
        )

        draw.rectangle(
            (0, 443, 853, 479),
            fill=(75, 65, 68)
        )


def draw_people_scene(draw, theme, index):
    colors = (
        (179, 91, 85),
        (84, 124, 156),
        (150, 124, 81),
        (114, 100, 147)
    )
    for i, x in enumerate((250, 370, 490, 610)):
        draw_geometric_person(
            draw, x, 265 + (i % 2)*7,
            scale=1.1,
            robe=colors[(i+index-1) % 4]
        )


def draw_other_scene(draw, theme, index, rng):
    """Full-frame backgrounds for other free-test themes."""

    if theme == "space":
        for _ in range(80):
            x = rng.randrange(30, 824)
            y = rng.randrange(30, 445)
            r = rng.choice((1, 1, 2, 3))
            draw.ellipse(
                (x-r, y-r, x+r, y+r),
                fill=(213, 223, 246)
            )

        cx = 500 + index*40
        cy = 220
        radius = 105
        draw.ellipse(
            (cx-radius, cy-radius,
             cx+radius, cy+radius),
            fill=(93+index*23, 120, 174)
        )

    elif theme == "ocean":
        for band in range(10):
            y = band*48
            draw.rectangle(
                (0, y, 853, min(479, y+48)),
                fill=(10, 70+band*5, 115+band*4)
            )

        for n in range(11):
            x = 65+n*65
            y = 180+rng.randrange(190)
            draw.polygon((
                (x, y), (x+23, y-12),
                (x+23, y+12)
            ), fill=(236, 174, 104))
            draw.ellipse(
                (x+21, y-9, x+48, y+9),
                fill=(236, 174, 104)
            )

    elif theme == "city":
        draw.rectangle(
            (0, 430, 853, 479),
            fill=(43, 49, 74)
        )

        for n in range(10):
            x = 55+n*75
            h = rng.randrange(150, 350)
            top = 430-h
            draw.rectangle(
                (x, top, x+52, 430),
                fill=(25, 37, 67)
            )

            for wx in range(x+9, x+47, 15):
                for wy in range(top+14, 415, 24):
                    draw.rectangle(
                        (wx, wy, wx+7, wy+10),
                        fill=(232, 193, 110)
                    )

        draw.ellipse(
            (660, 50, 760, 150),
            fill=(249, 211, 150)
        )

    elif theme == "prayer":
        draw.ellipse(
            (645, 45, 785, 185),
            fill=(245, 197, 120)
        )

        draw.polygon((
            (242, 230), (427, 55), (612, 230)
        ), fill=(49, 49, 77))

        draw.rectangle(
            (276, 230, 578, 438),
            fill=(42, 43, 69)
        )

        draw.rectangle(
            (406, 95, 424, 205),
            fill=(247, 224, 170)
        )
        draw.rectangle(
            (381, 123, 449, 141),
            fill=(247, 224, 170)
        )

        draw.rectangle(
            (408, 350, 449, 438),
            fill=(102, 88, 91)
        )

        for x in (319, 505):
            draw.rectangle(
                (x, 280, x+32, 320),
                fill=(245, 197, 120)
            )

        draw.line(
            ((250, 440), (605, 440)),
            fill=(210, 197, 172),
            width=3
        )

    else:
        draw.ellipse(
            (655, 40, 775, 160),
            fill=(246, 202, 118)
        )

        draw.polygon((
            (0, 400), (180, 110), (390, 400)
        ), fill=(24, 64, 77))

        draw.polygon((
            (230, 412), (510, 90), (853, 412)
        ), fill=(29, 73, 79))

        draw.rectangle(
            (0, 417, 853, 479),
            fill=(22, 65, 72)
        )

        if theme == "nature":
            for n in range(9):
                x = 62+n*87
                draw.rectangle(
                    (x, 345, x+12, 441),
                    fill=(55, 52, 43)
                )
                draw.polygon((
                    (x-29, 370),
                    (x+6, 240),
                    (x+41, 370)
                ), fill=(23, 90, 65))


def prepare_free_test(job_id, job=None):
    from PIL import Image, ImageDraw

    job = job or {}
    settings = job.get("settings") or {}
    prompt = str(
        job.get("prompt")
        or settings.get("prompt")
        or ""
    )

    people_mode = free_test_people_request(prompt)
    theme = (
        "prayer"
        if people_mode == "last_supper"
        else free_test_theme(prompt)
    )

    image_dir = VISUALS / job_id
    image_dir.mkdir(parents=True, exist_ok=True)

    plan_path = PLANS / f"{job_id}_scenes.json"
    caption_path = CONTENT / f"{job_id}_captions.json"

    content = {
        "space": (
            ("BEYOND OUR WORLD",
             "THE RINGS OF SATURN",
             "DISTANT GALAXIES"),
            ("Our universe is full of wonders.",
             "Planets travel among the stars.",
             "Every galaxy holds new mysteries."),
            ((11, 16, 47), (22, 14, 67), (12, 31, 73))
        ),
        "ocean": (
            ("THE BLUE OCEAN",
             "BENEATH THE WAVES",
             "A LIVING REEF"),
            ("The ocean connects our world.",
             "Marine life thrives below the surface.",
             "Coral reefs shelter countless creatures."),
            ((13, 79, 119), (8, 62, 98), (7, 89, 113))
        ),
        "city": (
            ("CITY LIGHTS",
             "URBAN HORIZONS",
             "THE CITY AWAKENS"),
            ("Cities bring people together.",
             "Architecture shapes our skylines.",
             "Every street tells a story."),
            ((41, 52, 87), (74, 61, 96), (39, 76, 103))
        ),
        "prayer": (
            ("A MOMENT OF PEACE",
             "LIGHT OF HOPE",
             "FAITH AND GRATITUDE"),
            ("May peace fill every heart.",
             "A quiet light can inspire hope.",
             "Let gratitude guide our day."),
            ((65, 71, 112), (83, 66, 99), (85, 91, 120))
        ),
        "nature": (
            ("THE GREAT OUTDOORS",
             "MOUNTAINS AND VALLEYS",
             "A NEW DAWN"),
            ("Nature surrounds us with beauty.",
             "Every landscape has a story.",
             "The earth welcomes a new day."),
            ((34, 101, 125), (47, 97, 108), (87, 117, 126))
        ),
        "inspiration": (
            ("A NEW BEGINNING",
             "FIND YOUR PEACE",
             "EVERY MOMENT MATTERS"),
            ("Every new day brings possibility.",
             "Small steps lead to change.",
             "Make this moment count."),
            ((32, 75, 125), (28, 105, 91), (112, 66, 118))
        )
    }

    titles, messages, backgrounds = content[theme]

    if people_mode == "last_supper":
        titles = (
            "THE LAST SUPPER",
            "BREAD AND WINE",
            "A SACRED MOMENT"
        )
        messages = (
            "Jesus gathers with his twelve apostles.",
            "They share bread and wine at the table.",
            "A moment of faith and remembrance."
        )

    scenes = []
    records = []

    for index, (title, message, color) in enumerate(
        zip(titles, messages, backgrounds), 1
    ):
        image_path = image_dir / f"scene_{index:03d}.png"

        if (
            not image_path.is_file()
            or image_path.stat().st_size == 0
        ):
            rng = random.Random(
                f"{job_id}:{index}:{theme}"
            )

            image = Image.new(
                "RGB", (854, 480), color
            )
            draw = ImageDraw.Draw(image)

            # Full-height scenery, with no top header.
            if people_mode == "last_supper":
                draw_last_supper(draw, index)
            else:
                draw_other_scene(
                    draw, theme, index, rng
                )

            if people_mode == "people":
                draw_people_scene(
                    draw, theme, index
                )

            # Small watermark, not a large header.
            draw.rounded_rectangle(
                (13, 12, 146, 35),
                radius=5,
                fill=(24, 35, 52)
            )
            draw.text(
                (20, 18),
                "MELODIA AI",
                fill=(232, 237, 245)
            )

            image.save(
                image_path, format="PNG"
            )

        start = float((index-1)*10)
        end = float(index*10)

        scenes.append({
            "scene_number": index,
            "start_seconds": start,
            "end_seconds": end,
            "duration_seconds": 10.0,
            "image_path": str(image_path.resolve()),
            "caption_mode": "single",
            "primary_language": "English",
            "second_language": None
        })

        records.append({
            "scene_number": index,
            "start_seconds": start,
            "end_seconds": end,
            "primary": message,
            "translated": ""
        })

    plan = {
        "job_id": job_id,
        "aspect_ratio": "16:9",
        "duration_seconds": 30.0,
        "generation_status": "complete",
        "scenes": scenes
    }

    captions = {
        "job_id": job_id,
        "caption_mode": "single",
        "primary_language": "English",
        "second_language": None,
        "records": records
    }

    if not plan_path.exists():
        plan_path.write_text(
            json.dumps(plan, indent=2),
            encoding="utf-8"
        )

    if not caption_path.exists():
        caption_path.write_text(
            json.dumps(
                captions,
                ensure_ascii=False,
                indent=2
            ),
            encoding="utf-8"
        )

    print(
        "FREE TEST SCENERY THEME:",
        theme, flush=True
    )

    return plan_path, caption_path


def free_test_music_enabled(job):
    settings = job.get("settings") or {}
    mode = str(
        settings.get("music", "none")
    ).strip().lower()
    return mode not in (
        "none", "off", "false", "no", ""
    )


def create_free_test_soundtrack(destination, seconds=30):
    sample_rate = 22050
    samples = array("h")
    chords = (
        (261.63, 329.63, 392.00),
        (220.00, 261.63, 329.63),
        (196.00, 246.94, 392.00)
    )

    for i in range(int(seconds*sample_rate)):
        t = i/sample_rate
        chord = chords[
            min(int(t//10), len(chords)-1)
        ]
        fade = max(
            0.0,
            min(1.0, t/2.0, (seconds-t)/3.0)
        )
        pulse = (
            0.82
            + 0.18*math.sin(2*math.pi*0.22*t)
        )
        tone = sum(
            math.sin(2*math.pi*hz*t)
            + 0.13*math.sin(2*math.pi*hz*2*t)
            for hz in chord
        )/(len(chord)*1.13)

        samples.append(
            int(10500*fade*pulse*tone)
        )

    with wave.open(str(destination), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(samples.tobytes())

    if (
        not destination.is_file()
        or destination.stat().st_size < 1000
    ):
        raise RuntimeError(
            "Local instrumental soundtrack was not created"
        )


def mux_free_test_music(silent_video, destination):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required")

    with tempfile.TemporaryDirectory(
        prefix="melodia_free_audio_",
        dir=OUTPUTS
    ) as folder:
        folder = Path(folder)
        soundtrack = folder/"instrumental.wav"
        combined = folder/"with_music.mp4"

        create_free_test_soundtrack(soundtrack)

        command = [
            ffmpeg, "-hide_banner",
            "-loglevel", "error",
            "-nostdin", "-y",
            "-i", str(silent_video),
            "-i", str(soundtrack),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "128k",
            "-t", "30",
            "-movflags", "+faststart",
            str(combined)
        ]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            raise RuntimeError(
                "FFmpeg audio mux failed: "
                + result.stderr[-3000:]
            )

        if (
            not combined.is_file()
            or combined.stat().st_size == 0
        ):
            raise RuntimeError(
                "Music-enabled MP4 is missing"
            )

        os.replace(combined, destination)


def process_free_test(job_file, job):
    job_id = job["job_id"]
    final_video = OUTPUTS/f"{job_id}.mp4"
    silent_master = OUTPUTS/f"{job_id}_silent_master.mp4"
    wants_music = free_test_music_enabled(job)

    try:
        job["status"] = "preparing"
        job["progress"] = 10
        job.pop("error", None)
        save_job(job_file, job)

        prepare_free_test(job_id, job)

        if wants_music and final_video.is_file():
            probe = shutil.which("ffprobe")
            has_audio = False

            if probe:
                result = subprocess.run([
                    probe, "-v", "error",
                    "-select_streams", "a:0",
                    "-show_entries", "stream=codec_name",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(final_video)
                ], capture_output=True, text=True)

                has_audio = (
                    result.returncode == 0
                    and bool(result.stdout.strip())
                )

            if has_audio:
                finish_job(
                    job_file, job, final_video
                )
                return

            if not silent_master.exists():
                os.replace(
                    final_video, silent_master
                )
            else:
                raise RuntimeError(
                    "Silent output and silent master both exist"
                )

        if (
            not silent_master.is_file()
            and not final_video.is_file()
        ):
            job["status"] = "rendering"
            job["progress"] = 50
            save_job(job_file, job)

            rendered = Path(
                assemble_video(job_id)
            )

            if (
                not rendered.is_file()
                or rendered.stat().st_size == 0
            ):
                raise RuntimeError(
                    "Free-test video was not rendered"
                )

            if wants_music:
                if silent_master.exists():
                    raise RuntimeError(
                        "Silent master already exists"
                    )
                os.replace(
                    rendered, silent_master
                )
            elif rendered != final_video:
                os.replace(
                    rendered, final_video
                )

        if wants_music:
            job["status"] = "generating_music"
            job["progress"] = 85
            save_job(job_file, job)

            print(
                "FREE TEST: calling V5 soundtrack",
                flush=True
            )

            music_file = Path(
                generate_job_soundtrack(job_id)
            )

            if (
                not music_file.is_file()
                or music_file.stat().st_size <= 44
            ):
                raise RuntimeError(
                    "V5 music engine returned no soundtrack"
                )

            job["status"] = "adding_music"
            job["progress"] = 95
            save_job(job_file, job)

            with tempfile.TemporaryDirectory(
                prefix="melodia_v5_",
                dir=OUTPUTS
            ) as tmp:
                combined = Path(tmp)/"combined.mp4"

                add_music_to_video(
                    silent_master,
                    music_file,
                    combined
                )

                if (
                    not combined.is_file()
                    or combined.stat().st_size == 0
                ):
                    raise RuntimeError(
                        "Music muxing produced no MP4"
                    )

                probe = shutil.which("ffprobe")
                if not probe:
                    raise RuntimeError(
                        "ffprobe required"
                    )

                checked = subprocess.run([
                    probe, "-v", "error",
                    "-select_streams", "a:0",
                    "-show_entries", "stream=codec_name",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(combined)
                ], capture_output=True, text=True)

                if (
                    checked.returncode != 0
                    or "aac" not in checked.stdout.lower()
                ):
                    raise RuntimeError(
                        "Muxed video has no AAC audio"
                    )

                os.replace(
                    combined, final_video
                )

            print(
                "FREE TEST: V5 soundtrack verified",
                flush=True
            )

        finish_job(
            job_file, job, final_video
        )

    except Exception as error:
        job["status"] = "failed"
        job["error"] = (
            "Free video/music integration failed: "
            + str(error)
        )
        save_job(job_file, job)
        print(
            "FREE TEST FAILED:",
            error, flush=True
        )


def process_job(job_file, job):
    job_id = job["job_id"]

    if is_free_test(job):
        print(
            "FREE TEST MODE: no Gemini API calls",
            flush=True
        )
        process_free_test(job_file, job)
        return

    settings = job.get("settings") or {}
    audio_mode = (
        "music"
        if free_test_music_enabled(job)
        else settings.get("audio", "none")
    )

    if audio_mode not in ("none", "music"):
        job["status"] = "failed"
        job["error"] = (
            "Audio mode not yet supported: "
            + str(audio_mode)
        )
        save_job(job_file, job)
        return

    plan_path = PLANS/f"{job_id}_scenes.json"
    video_path = OUTPUTS/f"{job_id}.mp4"
    silent_master = OUTPUTS/f"{job_id}_silent_master.mp4"

    if (
        video_path.is_file()
        and video_path.stat().st_size > 0
    ):
        finish_job(
            job_file, job, video_path
        )
        return

    if (
        audio_mode == "music"
        and silent_master.is_file()
        and silent_master.stat().st_size > 0
    ):
        print(
            "Existing silent master preserved:",
            silent_master
        )
    else:
        job["status"] = "preparing"
        job["progress"] = 5
        job.pop("error", None)
        save_job(job_file, job)

        try:
            plan, plan_output = create_scene_plan(job)

            if not images_ready(plan):
                raise RuntimeError(
                    "Scene generation is incomplete"
                )

            job["status"] = "scenes_ready"
            job["progress"] = 40
            job.pop("error", None)
            save_job(job_file, job)

            print(
                "All scene images verified:",
                plan_output
            )

        except Exception as error:
            if is_quota_error(error):
                job["status"] = "paused_quota"
                job["progress"] = 5
                preserve_image_progress(
                    job, plan_path
                )
                job["error"] = (
                    "Image-generation provider quota reached. "
                    "Generated images preserved; job can resume."
                )
            else:
                job["status"] = "failed"
                job["error"] = str(error)

            save_job(job_file, job)
            print(
                "SCENE GENERATION INTERRUPTED:",
                error
            )
            return

        caption_mode = (
            plan.get("scenes", [{}])[0]
            .get("caption_mode", "single")
        )

        if caption_mode != "none":
            job["status"] = "generating_captions"
            job["progress"] = 42
            save_job(job_file, job)

            try:
                caption_file = (
                    generate_multilingual_captions(job_id)
                )

                if (
                    not caption_file.is_file()
                    or caption_file.stat().st_size == 0
                ):
                    raise RuntimeError(
                        "Caption file missing or empty"
                    )

                job["caption_path"] = str(caption_file)
                job["status"] = "captions_ready"
                job["progress"] = 48
                job.pop("error", None)
                save_job(job_file, job)

            except Exception as error:
                if is_quota_error(error):
                    job["status"] = "paused_quota"
                    job["error"] = (
                        "Gemini caption quota reached. "
                        "Existing scene images preserved."
                    )
                else:
                    job["status"] = "failed"
                    job["error"] = (
                        "Caption generation failed: "
                        + str(error)
                    )

                save_job(job_file, job)
                return

        job["status"] = "rendering"
        job["progress"] = 50
        save_job(job_file, job)

        try:
            rendered = Path(
                assemble_video(job_id)
            )

            if (
                not rendered.is_file()
                or rendered.stat().st_size == 0
            ):
                raise RuntimeError(
                    "MP4 output missing or empty"
                )

            if audio_mode == "none":
                finish_job(
                    job_file, job, rendered
                )
                return

            if silent_master.exists():
                raise RuntimeError(
                    "Silent master already exists"
                )

            os.replace(
                rendered, silent_master
            )

        except Exception as error:
            job["status"] = "failed"
            job["error"] = (
                "MP4 assembly failed: "
                + str(error)
            )
            save_job(job_file, job)
            return

    if audio_mode == "none":
        job["status"] = "failed"
        job["error"] = (
            "Silent video was not finalized"
        )
        save_job(job_file, job)
        return

    job["status"] = "generating_music"
    job["progress"] = 85
    save_job(job_file, job)

    try:
        music_file = generate_job_soundtrack(job_id)
        job["music_path"] = str(music_file)
        job["status"] = "adding_music"
        job["progress"] = 95
        save_job(job_file, job)

        with tempfile.TemporaryDirectory(
            prefix="melodia_music_",
            dir=OUTPUTS
        ) as temp_dir:
            temp_output = (
                Path(temp_dir)/"final.mp4"
            )

            add_music_to_video(
                silent_master,
                music_file,
                temp_output
            )

            if (
                not temp_output.is_file()
                or temp_output.stat().st_size == 0
            ):
                raise RuntimeError(
                    "Soundtrack muxing produced no MP4"
                )

            if video_path.exists():
                raise RuntimeError(
                    "Final MP4 already exists"
                )

            os.replace(
                temp_output, video_path
            )

        finish_job(
            job_file, job, video_path
        )

    except Exception as error:
        job["status"] = "failed"
        job["error"] = (
            "Background music integration failed: "
            + str(error)
        )
        save_job(job_file, job)
        print(
            "BACKGROUND MUSIC FAILED:",
            error
        )
        print(
            "Silent master preserved:",
            silent_master
        )


def main():
    print("MELODIA AI - AUTOMATIC VIDEO WORKER")

    pending = find_pending_jobs()
    print("Pending jobs found:", len(pending))

    if not pending:
        print("NO PENDING JOBS")
        return

    job_file, job = pending[0]
    process_job(job_file, job)
    print("WORKER FINISHED")



# STEP 1337.35.3
# Universal geometric scene engine integration.
# Preserves the original Last Supper renderer,
# existing MP4 assembler, captions and V5 music.

_original_prepare_free_test = prepare_free_test


def prepare_free_test(job_id, job=None):
    from melodia_universal_scene_engine import generate_video_scenes

    job = job or {}
    settings = job.get("settings") or {}
    prompt = str(
        job.get("prompt")
        or settings.get("prompt")
        or ""
    )

    # Preserve the working Last Supper scenes.
    if free_test_people_request(prompt) == "last_supper":
        return _original_prepare_free_test(job_id, job)

    # All other free-test subjects use the universal engine.
    clean_prompt = re.sub(
        r"\[FREE TEST\]",
        "",
        prompt,
        flags=re.IGNORECASE
    ).strip()

    if not clean_prompt:
        clean_prompt = "A peaceful landscape"

    image_dir = VISUALS / job_id
    image_dir.mkdir(parents=True, exist_ok=True)

    plan_path = PLANS / f"{job_id}_scenes.json"
    caption_path = CONTENT / f"{job_id}_captions.json"

    generated = generate_video_scenes(
        clean_prompt,
        image_dir,
        count=3
    )

    if len(generated) != 3:
        raise RuntimeError(
            "Universal engine must produce three scenes"
        )

    scenes = []
    records = []

    captions = (
        clean_prompt,
        f"A closer look: {clean_prompt}",
        f"The final scene: {clean_prompt}"
    )

    for index, item in enumerate(generated, 1):
        image_path = Path(item["image_path"])

        if (
            not image_path.is_file()
            or image_path.stat().st_size == 0
        ):
            raise RuntimeError(
                f"Missing scene image: {image_path}"
            )

        start = float((index - 1) * 10)
        end = float(index * 10)

        scenes.append({
            "scene_number": index,
            "start_seconds": start,
            "end_seconds": end,
            "duration_seconds": 10.0,
            "image_path": str(image_path.resolve()),
            "caption_mode": "single",
            "primary_language": "English",
            "second_language": None
        })

        records.append({
            "scene_number": index,
            "start_seconds": start,
            "end_seconds": end,
            "primary": captions[index - 1][:240],
            "translated": ""
        })

    plan = {
        "job_id": job_id,
        "aspect_ratio": "16:9",
        "duration_seconds": 30.0,
        "generation_status": "complete",
        "scenes": scenes
    }

    caption_data = {
        "job_id": job_id,
        "caption_mode": "single",
        "primary_language": "English",
        "second_language": None,
        "records": records
    }

    plan_path.write_text(
        json.dumps(plan, indent=2),
        encoding="utf-8"
    )

    caption_path.write_text(
        json.dumps(
            caption_data,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print(
        "UNIVERSAL GEOMETRIC ENGINE ACTIVE:",
        clean_prompt,
        flush=True
    )

    return plan_path, caption_path

if __name__ == "__main__":
    main()
