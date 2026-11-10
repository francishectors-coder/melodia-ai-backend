
# MELODIA AI - DYNAMIC BACKGROUND MUSIC
# Step 1113
#
# Generates original instrumental music
# based on video prompt, mood and duration.
#
# Uses Python standard library and FFmpeg.
# No GPU or external API required.
#
# Preserves existing videos and music files.

import array
import hashlib
import json
import math
import random
import re
import subprocess
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent

OUTPUTS = ROOT / "outputs"
MUSIC_DIR = ROOT / "generated_music"
JOBS = ROOT / "jobs"
PLANS = ROOT / "scene_plans"

OUTPUTS.mkdir(parents=True, exist_ok=True)
MUSIC_DIR.mkdir(parents=True, exist_ok=True)

TEST_JOB_ID = "melodia_worker_test_001"

SAMPLE_RATE = 16000

MOODS = {
    "peaceful": {
        "bpm": 72,
        "scale": [0, 2, 4, 7, 9],
        "root": 48,
        "wave": "soft",
        "volume": 0.28
    },
    "devotional": {
        "bpm": 66,
        "scale": [0, 2, 4, 5, 7, 9],
        "root": 48,
        "wave": "organ",
        "volume": 0.27
    },
    "adventure": {
        "bpm": 116,
        "scale": [0, 2, 3, 5, 7, 8, 10],
        "root": 45,
        "wave": "brass",
        "volume": 0.32
    },
    "playful": {
        "bpm": 112,
        "scale": [0, 2, 4, 5, 7, 9, 11],
        "root": 60,
        "wave": "bell",
        "volume": 0.25
    },
    "inspirational": {
        "bpm": 94,
        "scale": [0, 2, 4, 5, 7, 9, 11],
        "root": 48,
        "wave": "piano",
        "volume": 0.30
    },
    "educational": {
        "bpm": 84,
        "scale": [0, 2, 4, 7, 9],
        "root": 48,
        "wave": "soft",
        "volume": 0.23
    }
}


def detect_mood(prompt):
    text = prompt.casefold()

    rules = [
        (
            "devotional",
            [
                "prayer", "jesus", "god",
                "worship", "devotional",
                "church", "sacred", "rosary",
                "பிரார்த்தனை", "இயேசு",
                "ஜெபம்"
            ]
        ),
        (
            "adventure",
            [
                "adventure", "battle",
                "heroic", "dramatic",
                "action", "epic",
                "suspense"
            ]
        ),
        (
            "playful",
            [
                "children", "kids",
                "nursery", "funny",
                "cartoon", "playful"
            ]
        ),
        (
            "inspirational",
            [
                "inspirational", "hope",
                "success", "motivation",
                "uplifting", "triumph"
            ]
        ),
        (
            "educational",
            [
                "educational", "science",
                "documentary", "tutorial",
                "history", "explain"
            ]
        )
    ]

    for mood, keywords in rules:
        if any(
            keyword in text
            for keyword in keywords
        ):
            return mood

    return "peaceful"


def midi_frequency(note):
    return 440.0 * (
        2.0 ** ((note - 69) / 12.0)
    )


def oscillator(frequency, t, style):
    phase = 2 * math.pi * frequency * t

    if style == "organ":
        return (
            math.sin(phase)
            + 0.35 * math.sin(2 * phase)
            + 0.12 * math.sin(3 * phase)
        ) / 1.47

    if style == "brass":
        return (
            math.sin(phase)
            + 0.50 * math.sin(2 * phase)
            + 0.25 * math.sin(3 * phase)
        ) / 1.75

    if style == "bell":
        return (
            math.sin(phase)
            + 0.30 * math.sin(2.01 * phase)
            + 0.15 * math.sin(3.93 * phase)
        ) / 1.45

    if style == "piano":
        return (
            math.sin(phase)
            + 0.25 * math.sin(2 * phase)
            + 0.10 * math.sin(3 * phase)
        ) / 1.35

    return (
        math.sin(phase)
        + 0.12 * math.sin(2 * phase)
    ) / 1.12


def envelope(position, length, style):
    if length <= 0:
        return 0.0

    if style in ("piano", "bell"):
        attack = min(
            1.0,
            position / 0.025
        )
        decay = math.exp(
            -2.2 * position / length
        )
        return attack * decay

    fade = min(0.4, length / 5)

    attack = min(
        1.0,
        position / max(fade, 0.001)
    )

    release = min(
        1.0,
        (length - position)
        / max(fade, 0.001)
    )

    return max(
        0.0,
        min(attack, release)
    )


def read_job_settings(job_id):
    """Read the current nested job settings and verified scene duration."""
    job_file = JOBS / f"{job_id}.json"
    plan_file = PLANS / f"{job_id}_scenes.json"

    if not job_file.is_file():
        raise FileNotFoundError(f"Job settings missing: {job_file}")

    data = json.loads(job_file.read_text(encoding="utf-8"))
    settings = data.get("settings") or {}
    prompt = settings.get("prompt") or data.get("prompt") or data.get("user_prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("Job prompt is missing")

    duration_minutes = settings.get("duration")
    if duration_minutes is None:
        raise ValueError("Job duration is missing")
    duration = float(duration_minutes) * 60.0

    if plan_file.is_file():
        plan = json.loads(plan_file.read_text(encoding="utf-8"))
        planned_duration = float(plan["duration_seconds"])
        if abs(duration - planned_duration) > 0.05:
            raise ValueError("Job and scene-plan durations do not match")
        duration = planned_duration

    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Invalid soundtrack duration")
    return prompt.strip(), duration


def generate_job_soundtrack(job_id):
    """Create or reuse the instrumental WAV for one video job."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", str(job_id)):
        raise ValueError("Invalid job ID")

    job_file = JOBS / f"{job_id}.json"
    job = json.loads(job_file.read_text(encoding="utf-8"))
    settings = job.get("settings") or {}
    audio = settings.get("audio", "none")
    if audio != "music":
        raise ValueError(f"Job does not request instrumental music: {audio}")

    prompt, duration = read_job_settings(job_id)
    destination = MUSIC_DIR / f"{job_id}_dynamic.wav"
    if destination.is_file() and destination.stat().st_size > 44:
        with wave.open(str(destination), "rb") as existing:
            actual_duration = existing.getnframes() / existing.getframerate()
        if abs(actual_duration - duration) <= 0.05:
            print("Existing soundtrack preserved:", destination)
            return destination
        raise RuntimeError("Existing soundtrack has a different duration; refusing overwrite")

    composition = create_composition(prompt, duration)
    temporary = MUSIC_DIR / f"{job_id}_dynamic.tmp.wav"
    try:
        generate_music(composition, temporary)
        if not temporary.is_file() or temporary.stat().st_size <= 44:
            raise RuntimeError("Generated soundtrack is empty")
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return destination


def create_composition(prompt, duration):
    mood = detect_mood(prompt)
    settings = MOODS[mood]

    # Different prompts produce different
    # repeatable musical arrangements.
    seed_text = (
        prompt + "|" + str(duration)
    )

    seed = int(
        hashlib.sha256(
            seed_text.encode("utf-8")
        ).hexdigest()[:16],
        16
    )

    rng = random.Random(seed)

    bpm = settings["bpm"] + rng.randint(
        -5, 5
    )

    beat_seconds = 60.0 / bpm

    scale = settings["scale"]
    root = settings["root"]

    melody = [
        root + 12 + rng.choice(scale)
        for _ in range(16)
    ]

    chord_roots = [
        root + rng.choice([0, 5, 7, 9])
        for _ in range(8)
    ]

    return {
        "mood": mood,
        "bpm": bpm,
        "beat_seconds": beat_seconds,
        "style": settings["wave"],
        "volume": settings["volume"],
        "melody": melody,
        "chords": chord_roots,
        "duration": duration,
        "seed": seed
    }


def generate_music(composition, destination):
    duration = float(
        composition["duration"]
    )

    total_samples = int(
        SAMPLE_RATE * duration
    )

    beat = composition["beat_seconds"]
    style = composition["style"]
    volume = composition["volume"]

    melody = composition["melody"]
    chords = composition["chords"]

    melody_length = beat * 2
    chord_length = beat * 8

    print(
        "MELODIA AI - DYNAMIC MUSIC GENERATOR"
    )
    print("Mood:", composition["mood"])
    print("Tempo:", composition["bpm"], "BPM")
    print("Duration:", duration, "seconds")
    print("Instrument style:", style)

    # Stream audio in chunks to keep
    # memory usage low on older computers.
    chunk_size = 4096

    with wave.open(
        str(destination),
        "wb"
    ) as audio:

        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(SAMPLE_RATE)

        for chunk_start in range(
            0,
            total_samples,
            chunk_size
        ):
            chunk_end = min(
                chunk_start + chunk_size,
                total_samples
            )

            samples = array.array("h")

            for index in range(
                chunk_start,
                chunk_end
            ):
                t = index / SAMPLE_RATE

                chord_index = (
                    int(t / chord_length)
                    % len(chords)
                )

                chord_root = chords[
                    chord_index
                ]

                chord_position = (
                    t % chord_length
                )

                chord_env = envelope(
                    chord_position,
                    chord_length,
                    "soft"
                )

                pad = 0.0

                for interval in (0, 4, 7):
                    frequency = midi_frequency(
                        chord_root + interval
                    )

                    pad += oscillator(
                        frequency / 2,
                        t,
                        "soft"
                    )

                pad /= 3
                pad *= (
                    0.5 + 0.5 * chord_env
                )

                melody_index = (
                    int(t / melody_length)
                    % len(melody)
                )

                melody_note = melody[
                    melody_index
                ]

                melody_position = (
                    t % melody_length
                )

                melody_env = envelope(
                    melody_position,
                    melody_length,
                    style
                )

                lead = oscillator(
                    midi_frequency(
                        melody_note
                    ),
                    t,
                    style
                ) * melody_env

                # Gentle rhythmic pulse.
                pulse = (
                    math.sin(
                        2 * math.pi
                        * t / beat
                    )
                    * 0.05
                )

                signal = (
                    0.62 * pad
                    + 0.33 * lead
                    + 0.05 * pulse
                )

                # Smooth start and ending.
                fade_in = min(
                    1.0,
                    t / 2.5
                )

                fade_out = min(
                    1.0,
                    (duration - t) / 3.0
                )

                signal *= (
                    volume
                    * max(
                        0.0,
                        min(
                            fade_in,
                            fade_out
                        )
                    )
                )

                signal = max(
                    -1.0,
                    min(1.0, signal)
                )

                samples.append(
                    int(signal * 32767)
                )

            audio.writeframes(
                samples.tobytes()
            )

    print(
        "Dynamic soundtrack created:",
        destination
    )


def add_music_to_video(
    source,
    music,
    destination
):
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-nostdin",
        "-y",
        "-i", str(source),
        "-i", str(music),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        "-movflags", "+faststart",
        str(destination)
    ]

    subprocess.run(
        command,
        check=True
    )

    if (
        not destination.is_file()
        or destination.stat().st_size == 0
    ):
        raise RuntimeError(
            "Dynamic music MP4 not created"
        )

    print()
    print(
        "MELODIA AI - DYNAMIC VIDEO COMPLETE"
    )
    print("Output:", destination)
    print(
        "Size:",
        destination.stat().st_size,
        "bytes"
    )


def main():
    job_id = TEST_JOB_ID

    source = (
        OUTPUTS /
        f"{job_id}_bilingual_v3.mp4"
    )

    if not source.is_file():
        raise FileNotFoundError(
            "Bilingual video missing: "
            + str(source)
        )

    prompt, duration = read_job_settings(
        job_id
    )

    composition = create_composition(
        prompt,
        duration
    )

    music_file = (
        MUSIC_DIR /
        f"{job_id}_dynamic.wav"
    )

    output = (
        OUTPUTS /
        f"{job_id}_dynamic_music.mp4"
    )

    generate_music(
        composition,
        music_file
    )

    add_music_to_video(
        source,
        music_file,
        output
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(
            "DYNAMIC MUSIC FAILED"
        )
        print(
            type(error).__name__ + ":",
            error
        )
