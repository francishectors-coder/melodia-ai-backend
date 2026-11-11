
# MELODIA AI - CLASSICAL COMPOSITION ENGINE V5
# Standalone version. V1-V4 and video modules unchanged.

import os
import sys
import math
import wave
import hashlib
import ctypes.util
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
RATE = 22050
SOUNDFONT = ROOT / "soundfonts" / "FluidR3_GM.sf2"
OUTPUT = ROOT / "generated_music"

if sys.platform == "win32":
    folders = list(ROOT.glob(
        "fluidsynth-v2.6.2-win10-x64-cpp11/**/bin"
    ))
    if not folders:
        raise FileNotFoundError("FluidSynth DLL folder missing")

    dll_dir = folders[0].resolve()
    _dll_handle = os.add_dll_directory(str(dll_dir))
    _old_find = ctypes.util.find_library

    def _find_library(name):
        if name == "fluidsynth":
            return str(dll_dir / "libfluidsynth-3.dll")
        return _old_find(name)

    ctypes.util.find_library = _find_library

import fluidsynth

CHORDS = {
    "I": (48, (60, 64, 67)),
    "ii": (50, (62, 65, 69)),
    "IV": (53, (65, 69, 72)),
    "V": (55, (67, 71, 74)),
    "vi": (45, (57, 60, 64)),
}

SCALE = (
    60, 62, 64, 65, 67, 69, 71,
    72, 74, 76, 77, 79, 81, 83, 84
)

STYLES = {
    "prayer": (74, (0, 48, 73, 32), 72),
    "peaceful": (76, (0, 48, 11, 32), 66),
    "story": (92, (0, 48, 71, 32), 76),
    "news": (120, (0, 48, 61, 32), 82),
    "general": (90, (0, 48, 73, 32), 74),
}

WORDS = {
    "prayer": (
        "prayer", "devotional", "worship",
        "jesus", "church", "ஜெபம்", "பிரார்த்தனை"
    ),
    "peaceful": (
        "peaceful", "gentle", "calm",
        "relax", "அமைதி"
    ),
    "story": (
        "story", "narration", "cinematic", "கதை"
    ),
    "news": (
        "news", "headline", "breaking", "செய்தி"
    ),
}

PHRASES = (
    ("I", "vi", "IV", "V"),
    ("I", "IV", "V", "I"),
    ("vi", "ii", "IV", "V"),
    ("I", "IV", "V", "I"),
)

RHYTHMS = (
    (1, 1, 1, 1),
    (1, .5, .5, 2),
    (1, 1, 2),
    (2, 1, 1),
)


def detect_style(prompt):
    lower = str(prompt).lower()
    for name, terms in WORDS.items():
        if any(term in lower for term in terms):
            return name
    return "general"


def _seed(prompt):
    digest = hashlib.sha256(
        str(prompt).encode("utf-8")
    ).digest()
    return int.from_bytes(digest[:8], "big")


def _nearest(target, choices):
    return min(
        choices,
        key=lambda x: (abs(x - target), x)
    )


def _chord_note(target, chord):
    notes = [
        n + octave
        for n in chord
        for octave in (-12, 0, 12)
    ]
    return _nearest(target, notes)


def compose(prompt, duration, tempo):
    rng = np.random.default_rng(_seed(prompt))
    beat_s = 60.0 / tempo
    bar_s = 4.0 * beat_s

    main_bars = max(
        0, int((duration - 2 * bar_s) // bar_s)
    )

    events = []

    def note(ch, pitch, start, length, vel):
        if start >= duration or length <= 0:
            return
        events.append((
            ch,
            int(pitch),
            start,
            min(length, duration - start),
            int(vel)
        ))

    # Original melodic motif with stepwise motion.
    motif = [
        0, 1, 2, 1,
        0, -1, 0, 1,
        2, 1, -1, 0,
        1, 0, -1, 0
    ]

    shift = int(rng.choice((-1, 0, 1)))
    motif = [x + shift for x in motif]
    previous_pitch = 72

    def render_bar(bar, chord_name, cadence=False):
        nonlocal previous_pitch

        start = bar * bar_s
        if start >= duration:
            return

        bass, chord = CHORDS[chord_name]

        # Bach-inspired sustained harmony.
        for pitch in chord:
            note(
                1, pitch, start,
                bar_s * .91, 41
            )

        note(
            3, bass, start,
            bar_s * .88, 51
        )

        # Chopin-inspired arpeggiated accompaniment.
        arpeggio = (
            chord[0] + 12,
            chord[1] + 12,
            chord[2] + 12,
            chord[1] + 12
        )

        for k, pitch in enumerate(arpeggio):
            note(
                2, pitch,
                start + k * beat_s,
                beat_s * .77,
                31
            )

        # Mozart-inspired balanced rhythms.
        rhythm = RHYTHMS[bar % len(RHYTHMS)]
        beat = 0.0

        for k, beats in enumerate(rhythm):
            motif_i = (bar % 4) * 4 + k
            movement = motif[motif_i % len(motif)]

            # Beethoven-inspired motif development.
            phrase = (bar // 4) % 4

            if phrase == 2:
                movement = -movement
            elif phrase == 1 and k == 1:
                movement += 1

            target = 72 + movement * 2

            choices = [
                p for p in SCALE
                if 67 <= p <= 81
            ]

            pitch = _nearest(target, choices)

            if (
                k == 0
                or beat + beats >= 4
                or cadence
            ):
                pitch = _chord_note(pitch, chord)

            if abs(pitch - previous_pitch) > 7:
                nearby = [
                    p for p in choices
                    if abs(p - previous_pitch) <= 5
                ]
                pitch = _nearest(
                    previous_pitch, nearby
                )

            note(
                0, pitch,
                start + beat * beat_s,
                beats * beat_s * .89,
                74
            )

            previous_pitch = pitch
            beat += beats

    # Main composition.
    for bar in range(main_bars):
        phrase = PHRASES[
            (bar // 4) % len(PHRASES)
        ]
        render_bar(
            bar,
            phrase[bar % 4]
        )

    # Planned dominant-to-tonic ending.
    cadence_start = main_bars * bar_s
    remaining = duration - cadence_start

    if remaining > bar_s:
        render_bar(
            main_bars,
            "V",
            cadence=True
        )
        final_start = (main_bars + 1) * bar_s
    else:
        final_start = cadence_start

    if final_start < duration:
        bass, chord = CHORDS["I"]
        remaining = duration - final_start

        for pitch in chord:
            note(
                1, pitch,
                final_start,
                remaining,
                43
            )

        note(
            3, bass,
            final_start,
            remaining,
            48
        )

        note(
            0, 72,
            final_start,
            remaining,
            75
        )

    return events


def generate_music(
    prompt,
    duration=30,
    output_path=None
):
    duration = float(duration)

    if not math.isfinite(duration) or duration <= 0:
        raise ValueError(
            "Duration must be a positive finite number"
        )

    if not SOUNDFONT.is_file():
        raise FileNotFoundError(
            "SoundFont missing: " + str(SOUNDFONT)
        )

    style = detect_style(prompt)
    tempo, instruments, _ = STYLES[style]

    if output_path is None:
        output_path = OUTPUT / (
            "melodia_v5_" + style + ".wav"
        )

    output_path = Path(output_path)
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    timeline = []

    for ch, pitch, start, length, velocity in compose(
        prompt, duration, tempo
    ):
        begin = round(start * RATE)
        end = round(
            min(duration, start + length) * RATE
        )

        if end > begin:
            timeline.append((
                begin, 1, ch, pitch, velocity
            ))
            timeline.append((
                end, 0, ch, pitch, 0
            ))

    timeline.sort(
        key=lambda e: (e[0], e[1])
    )

    synth = fluidsynth.Synth(
        samplerate=RATE,
        gain=0.6
    )

    try:
        sfid = synth.sfload(str(SOUNDFONT))

        if sfid < 0:
            raise RuntimeError(
                "SoundFont could not be loaded"
            )

        for channel, instrument in enumerate(instruments):
            synth.program_select(
                channel,
                sfid,
                0,
                instrument
            )

        total = round(duration * RATE)

        # Smooth four-second fade-out.
        fade = max(
            1,
            round(min(4.0, duration / 4) * RATE)
        )

        current = 0
        index = 0

        with wave.open(str(output_path), "wb") as wav:
            wav.setnchannels(2)
            wav.setsampwidth(2)
            wav.setframerate(RATE)

            while current < total:
                while (
                    index < len(timeline)
                    and timeline[index][0] <= current
                ):
                    _, on, ch, pitch, velocity = (
                        timeline[index]
                    )

                    if on:
                        synth.noteon(
                            ch, pitch, velocity
                        )
                    else:
                        synth.noteoff(ch, pitch)

                    index += 1

                next_frame = (
                    timeline[index][0]
                    if index < len(timeline)
                    else total
                )

                frames = min(
                    4096,
                    total - current,
                    max(1, next_frame - current)
                )

                samples = np.asarray(
                    synth.get_samples(frames),
                    dtype=np.int16
                ).reshape(-1, 2)

                positions = np.arange(
                    current,
                    current + frames
                )

                envelope = np.minimum(
                    np.clip(
                        positions / max(
                            1, round(.35 * RATE)
                        ),
                        0, 1
                    ),
                    np.clip(
                        (total - positions) / fade,
                        0, 1
                    )
                )

                mixed = (
                    samples.astype(np.float32)
                    * envelope[:, None]
                )

                wav.writeframes(
                    np.clip(
                        mixed,
                        -32768,
                        32767
                    ).astype(np.int16).tobytes()
                )

                current += frames

    finally:
        synth.delete()

    print(
        "MELODIA AI V5 - CLASSICAL COMPOSITION ENGINE"
    )
    print("STYLE:", style)
    print("TEMPO:", tempo)
    print("DURATION:", duration)
    print("OUTPUT:", output_path)
    print("RESULT: PASSED")

    return str(output_path)


if __name__ == "__main__":
    generate_music(
        "Gentle devotional prayer instrumental",
        duration=30
    )
