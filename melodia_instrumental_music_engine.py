"""MELODIA AI V2.8 — original procedural instrumental soundtrack generator.

CPU-only, Python standard library. Creates a WAV file suitable for the existing
V2.5 production engine's optional music input. No external music downloads,
pretrained models, or third-party audio packages are required.
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

# Original harmonic patterns; all tones are synthesized rather than sampled.
MOODS = {
    "peaceful": {"bpm": 72, "roots": [48, 45, 41, 43], "mode": "major", "brightness": 0.38},
    "uplifting": {"bpm": 104, "roots": [48, 43, 45, 41], "mode": "major", "brightness": 0.60},
    "reflective": {"bpm": 66, "roots": [45, 41, 48, 43], "mode": "minor", "brightness": 0.28},
    "gentle": {"bpm": 80, "roots": [48, 41, 45, 43], "mode": "major", "brightness": 0.40},
}


def detect_mood(prompt: str) -> str:
    """Select a soundtrack mood from a text prompt using stable keyword rules."""
    if not isinstance(prompt, str):
        raise TypeError("prompt must be a string")
    p = prompt.lower()
    if any(word in p for word in ("sad", "grief", "mourning", "reflect", "solemn", "meditat")):
        return "reflective"
    if any(word in p for word in ("celebrat", "joy", "happy", "victory", "uplift", "inspir")):
        return "uplifting"
    if any(word in p for word in ("gentle", "lullaby", "child", "sleep", "bedtime")):
        return "gentle"
    return "peaceful"


def _frequency(midi_note: float) -> float:
    return 440.0 * (2.0 ** ((midi_note - 69.0) / 12.0))


def _tone(phase: float, brightness: float) -> float:
    """Soft, organ-like original timbre with gentle harmonic overtones."""
    return (math.sin(phase) + brightness * 0.25 * math.sin(2 * phase)
            + brightness * 0.10 * math.sin(3 * phase)) / (1 + brightness * 0.35)


def generate_instrumental(prompt: str, output: str | Path, *, duration_seconds: float,
                          mood: str | None = None, volume: float = 0.42,
                          sample_rate: int = SAMPLE_RATE) -> dict:
    """Stream a soft instrumental WAV without holding the whole track in RAM.

    This is procedural instrumental accompaniment, not AI model-composed music.
    Duration supports up to ten minutes. Produces mono PCM16 WAV compatible
    with FFmpeg and the existing V2.5 music input.
    """
    if isinstance(duration_seconds, bool) or not isinstance(duration_seconds, (int, float)) or not math.isfinite(duration_seconds):
        raise ValueError("duration_seconds must be a finite number")
    duration_seconds = float(duration_seconds)
    if not 0 < duration_seconds <= MAX_DURATION_SECONDS:
        raise ValueError("duration_seconds must be between 0 and 600")
    if isinstance(volume, bool) or not isinstance(volume, (int, float)) or not math.isfinite(volume) or not 0 <= volume <= 1:
        raise ValueError("volume must be between 0 and 1")
    if isinstance(sample_rate, bool) or not isinstance(sample_rate, int) or not 8000 <= sample_rate <= 48000:
        raise ValueError("sample_rate must be an integer between 8000 and 48000")
    if mood is None:
        mood = detect_mood(prompt)
    if mood not in MOODS:
        raise ValueError(f"mood must be one of {', '.join(MOODS)}")

    config = MOODS[mood]
    beat = 60.0 / config["bpm"]
    bar = 4.0 * beat
    notes_in_chord = (0, 4, 7, 12) if config["mode"] == "major" else (0, 3, 7, 12)
    total_samples = round(duration_seconds * sample_rate)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fade_seconds = min(2.0, duration_seconds / 4)
    fade_samples = max(1, round(fade_seconds * sample_rate))
    chunk_samples = 4096

    with wave.open(str(output), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for start in range(0, total_samples, chunk_samples):
            buffer = bytearray()
            stop = min(total_samples, start + chunk_samples)
            for index in range(start, stop):
                t = index / sample_rate
                bar_index = int(t / bar)
                root = config["roots"][bar_index % len(config["roots"])]
                position = (t % bar) / bar
                # Gentle chord pad; fade at chord boundaries to avoid clicks.
                chord_envelope = min(1.0, position * 12.0, (1.0 - position) * 12.0)
                chord_envelope = max(0.0, chord_envelope)
                chord = 0.0
                for offset in notes_in_chord:
                    freq = _frequency(root + offset)
                    chord += _tone(2 * math.pi * freq * t, config["brightness"])
                chord /= len(notes_in_chord)
                # A restrained arpeggio adds musical shape without distracting narration/text.
                arp_step = int((t % bar) / beat) % 4
                arp_note = root + (0, 7, 12, 7)[arp_step] + 12
                arp_phase = 2 * math.pi * _frequency(arp_note) * t
                step_position = (t % beat) / beat
                arp_env = math.sin(math.pi * min(1.0, step_position)) ** 2
                arp = _tone(arp_phase, 0.2) * arp_env * 0.14
                signal = (chord * chord_envelope * 0.72 + arp) * float(volume)
                fade = min(1.0, (index + 1) / fade_samples, (total_samples - index) / fade_samples)
                signal *= max(0.0, fade)
                value = max(-32767, min(32767, round(signal * 32767)))
                buffer.extend(struct.pack("<h", value))
            wav.writeframesraw(buffer)

    return {"version": VERSION, "output": str(output), "mood": mood,
            "duration_seconds": total_samples / sample_rate,
            "sample_rate": sample_rate, "channels": 1,
            "format": "PCM16 WAV", "type": "original procedural instrumental"}


def main() -> None:
    parser = argparse.ArgumentParser(description="MELODIA AI original instrumental WAV generator")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--duration", type=float, required=True, help="Seconds, maximum 600")
    parser.add_argument("--mood", choices=tuple(MOODS))
    parser.add_argument("--volume", type=float, default=0.42)
    args = parser.parse_args()
    print(json.dumps(generate_instrumental(args.prompt, args.output,
        duration_seconds=args.duration, mood=args.mood, volume=args.volume), indent=2))


if __name__ == "__main__":
    main()
