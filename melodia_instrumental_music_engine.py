
"""MELODIA AI V2.8 - original procedural instrumental music engine.

CPU-only and Python-standard-library-only. Creates softly arranged instrumental
PCM16 WAV for the V2.5 production engine. This is algorithmic composition and
synthesis, not a pretrained music-generation model or sampled instruments.
"""
from __future__ import annotations

import argparse
import json
import math
import struct
import wave
from pathlib import Path

VERSION = "2.8"
SAMPLE_RATE = 22050
MAX_DURATION_SECONDS = 600.0

# Chord roots and diatonic melodic patterns are original procedural arrangements.
MOODS = {
    "peaceful": {"bpm": 72, "roots": (48, 45, 41, 43), "mode": "major", "lead": "flute"},
    "uplifting": {"bpm": 104, "roots": (48, 43, 45, 41), "mode": "major", "lead": "piano"},
    "reflective": {"bpm": 66, "roots": (45, 41, 48, 43), "mode": "minor", "lead": "strings"},
    "gentle": {"bpm": 80, "roots": (48, 41, 45, 43), "mode": "major", "lead": "bells"},
}

# Each phrase is two bars; (beat position, chord-relative scale step, length).
# Four phrases rotate across the piece.
PHRASES = (
    ((0, 0, 1.5), (1.5, 2, .5), (2, 4, 1), (3, 2, 1),
     (4, 1, 1), (5, 0, 1), (6, 2, 1.5)),
    ((0, 4, 1), (1, 5, 1), (2, 4, 1.5), (3.5, 2, .5),
     (4, 1, 1), (5, 2, 1), (6, 0, 2)),
    ((0, 2, 1), (1, 4, 1), (2, 5, 1), (3, 4, 1),
     (4, 2, 1.5), (5.5, 1, .5), (6, 0, 2)),
    ((0, 4, 1.5), (1.5, 2, .5), (2, 1, 1), (3, 0, 1),
     (4, 2, 1), (5, 1, 1), (6, 0, 2)),
)


def detect_mood(prompt: str) -> str:
    """Choose a deterministic mood using words in the user's prompt."""
    if not isinstance(prompt, str):
        raise TypeError("prompt must be a string")
    p = prompt.lower()
    if any(w in p for w in ("sad", "grief", "mourning", "reflect", "solemn", "meditat")):
        return "reflective"
    if any(w in p for w in ("celebrat", "joy", "happy", "victory", "uplift", "inspir")):
        return "uplifting"
    if any(w in p for w in ("gentle", "lullaby", "child", "sleep", "bedtime")):
        return "gentle"
    return "peaceful"


def _frequency(note: int) -> float:
    return 440.0 * 2.0 ** ((note - 69) / 12.0)


def _instrument(phase: float, kind: str) -> float:
    """Soft additive tones without downloaded instrument samples."""
    if kind == "flute":
        return .88 * math.sin(phase) + .10 * math.sin(2 * phase)
    if kind == "strings":
        return (.68 * math.sin(phase) + .21 * math.sin(2 * phase)
                + .08 * math.sin(3 * phase))
    if kind == "bells":
        return (.74 * math.sin(phase) + .17 * math.sin(2 * phase)
                + .07 * math.sin(3 * phase))
    return (.79 * math.sin(phase) + .15 * math.sin(2 * phase)
            + .04 * math.sin(3 * phase))


def _envelope(age: float, length: float, kind: str) -> float:
    if age < 0 or age >= length:
        return 0.0
    attack = .035 if kind in ("piano", "bells") else .18
    release = min(.28, length * .35)
    a = min(1.0, age / attack)
    r = min(1.0, (length - age) / max(.01, release))
    decay = math.exp(
        -age * (
            1.5 if kind == "bells"
            else .65 if kind == "piano"
            else .12
        )
    )
    return a * r * decay


def _melody_note(root: int, step: int, minor: bool) -> int:
    scale = (
        (0, 2, 3, 5, 7, 8, 10)
        if minor else
        (0, 2, 4, 5, 7, 9, 11)
    )
    return (
        root + 12
        + scale[step % len(scale)]
        + 12 * (step // len(scale))
    )


def _build_events(duration: float, config: dict) -> list[tuple]:
    """Precompose note events without storing the full audio in memory."""
    beat = 60.0 / config["bpm"]
    bar = 4 * beat
    events = []
    minor = config["mode"] == "minor"
    chord = (0, 3, 7) if minor else (0, 4, 7)
    bar_count = math.ceil(duration / bar)

    for b in range(bar_count):
        start = b * bar
        root = config["roots"][b % len(config["roots"])]
        remaining = max(0.0, duration - start)

        if remaining <= 0:
            break

        chord_length = min(bar + .10, remaining)

        for offset in chord:
            events.append(
                (start, chord_length, root + offset, "strings", .115)
            )

        events.append(
            (
                start,
                min(2 * beat, remaining),
                root - 12,
                "piano",
                .18,
            )
        )

        if remaining > 2 * beat:
            events.append(
                (
                    start + 2 * beat,
                    min(2 * beat, remaining - 2 * beat),
                    root - 5,
                    "piano",
                    .12,
                )
            )

        # Sparse arpeggios, rather than a constant electronic pulse.
        for j, offset in enumerate(
            (0, 7, 4 if not minor else 3, 7)
        ):
            t = start + j * beat

            if t < duration:
                events.append(
                    (
                        t,
                        min(.78 * beat, duration - t),
                        root + offset + 12,
                        "piano",
                        .10,
                    )
                )

        # One melodic phrase spans two bars.
        if b % 2 == 0:
            phrase = PHRASES[
                (b // 2) % len(PHRASES)
            ]

            for pos, step, beats_long in phrase:
                t = start + pos * beat

                if t >= duration:
                    continue

                active_bar = int(t / bar)
                active_root = config["roots"][
                    active_bar % len(config["roots"])
                ]

                note = _melody_note(
                    active_root,
                    step,
                    minor,
                )

                length = min(
                    beats_long * beat * .92,
                    duration - t,
                )

                events.append(
                    (
                        t,
                        length,
                        note,
                        config["lead"],
                        .24,
                    )
                )

    return sorted(
        events,
        key=lambda event: event[0],
    )


def generate_instrumental(
    prompt: str,
    output: str | Path,
    *,
    duration_seconds: float,
    mood: str | None = None,
    volume: float = .42,
    sample_rate: int = SAMPLE_RATE,
) -> dict:
    """Generate original procedural PCM16 WAV, up to 600 seconds."""
    if (
        isinstance(duration_seconds, bool)
        or not isinstance(duration_seconds, (int, float))
        or not math.isfinite(duration_seconds)
        or not 0 < duration_seconds <= MAX_DURATION_SECONDS
    ):
        raise ValueError(
            "duration_seconds must be a finite number between 0 and 600"
        )

    if (
        isinstance(volume, bool)
        or not isinstance(volume, (int, float))
        or not math.isfinite(volume)
        or not 0 <= volume <= 1
    ):
        raise ValueError(
            "volume must be between 0 and 1"
        )

    if (
        isinstance(sample_rate, bool)
        or not isinstance(sample_rate, int)
        or not 8000 <= sample_rate <= 48000
    ):
        raise ValueError(
            "sample_rate must be an integer between 8000 and 48000"
        )

    if mood is None:
        mood = detect_mood(prompt)

    if mood not in MOODS:
        raise ValueError(
            f"mood must be one of {', '.join(MOODS)}"
        )

    duration_seconds = float(duration_seconds)
    config = MOODS[mood]
    events = _build_events(
        duration_seconds,
        config,
    )

    # Calculate note frequencies once, before audio synthesis.
    notes = [
        (
            round(start * sample_rate),
            round((start + length) * sample_rate),
            _frequency(pitch),
            kind,
            strength,
        )
        for start, length, pitch, kind, strength in events
    ]

    total = round(
        duration_seconds * sample_rate
    )

    fade = max(
        1,
        round(
            min(2.0, duration_seconds / 4)
            * sample_rate
        ),
    )

    output = Path(output)
    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    next_event = 0
    active = []
    chunk_size = 4096
    two_pi = 2.0 * math.pi

    with wave.open(str(output), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)

        for first in range(
            0, total, chunk_size
        ):
            buf = bytearray()

            for i in range(
                first,
                min(first + chunk_size, total),
            ):
                while (
                    next_event < len(notes)
                    and notes[next_event][0] <= i
                ):
                    active.append(
                        notes[next_event]
                    )
                    next_event += 1

                active = [
                    event
                    for event in active
                    if event[1] > i
                ]

                signal = 0.0

                for (
                    begin,
                    end,
                    frequency,
                    kind,
                    strength,
                ) in active:
                    age = (
                        i - begin
                    ) / sample_rate

                    length = (
                        end - begin
                    ) / sample_rate

                    env = _envelope(
                        age,
                        length,
                        kind,
                    )

                    phase = (
                        two_pi * frequency * age
                    )

                    signal += (
                        _instrument(
                            phase,
                            kind,
                        )
                        * env
                        * strength
                    )

                fade_gain = min(
                    1.0,
                    (i + 1) / fade,
                    (total - i) / fade,
                )

                # Soft saturation avoids clipping.
                signal = (
                    math.tanh(
                        signal
                        * float(volume)
                        * 1.6
                    )
                    * max(
                        0.0,
                        fade_gain,
                    )
                )

                value = max(
                    -32767,
                    min(
                        32767,
                        round(
                            signal * 32767
                        ),
                    ),
                )

                buf.extend(
                    struct.pack(
                        "<h",
                        value,
                    )
                )

            wav.writeframesraw(buf)

    return {
        "version": VERSION,
        "output": str(output),
        "mood": mood,
        "duration_seconds": total / sample_rate,
        "sample_rate": sample_rate,
        "channels": 1,
        "format": "PCM16 WAV",
        "type": "original procedural instrumental",
        "instrument": config["lead"],
        "note_events": len(notes),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="MELODIA AI procedural instrumental music"
    )

    parser.add_argument(
        "--prompt",
        required=True,
    )

    parser.add_argument(
        "--output",
        required=True,
    )

    parser.add_argument(
        "--duration",
        type=float,
        required=True,
        help="Seconds, maximum 600",
    )

    parser.add_argument(
        "--mood",
        choices=tuple(MOODS),
    )

    parser.add_argument(
        "--volume",
        type=float,
        default=.42,
    )

    args = parser.parse_args()

    result = generate_instrumental(
        args.prompt,
        args.output,
        duration_seconds=args.duration,
        mood=args.mood,
        volume=args.volume,
    )

    print(
        json.dumps(
            result,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
