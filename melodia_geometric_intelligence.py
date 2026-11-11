"""MELODIA Geometric Intelligence V1: dependency-free learning prototype.

Trains a small multi-label text classifier on synthetic scene descriptions,
then produces three distinct SVG scene drafts and caption records.
No external APIs, model downloads, or production pipeline modifications.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import re
from pathlib import Path

LABELS = ('water', 'trees', 'buildings', 'mountains', 'night', 'sunset', 'movement', 'group')
VOCAB = ('river', 'lake', 'sea', 'ocean', 'water', 'forest', 'tree', 'jungle',
         'village', 'city', 'house', 'building', 'mountain', 'hill', 'night',
         'stars', 'moon', 'sunset', 'evening', 'dusk', 'walk', 'run', 'fly',
         'travel', 'move', 'herd', 'group', 'family', 'together')
TRAINING = {
    'water': ('river', 'lake', 'sea', 'ocean', 'water'),
    'trees': ('forest', 'tree', 'jungle'),
    'buildings': ('village', 'city', 'house', 'building'),
    'mountains': ('mountain', 'hill'),
    'night': ('night', 'stars', 'moon'),
    'sunset': ('sunset', 'evening', 'dusk'),
    'movement': ('walk', 'run', 'fly', 'travel', 'move'),
    'group': ('herd', 'group', 'family', 'together'),
}


def words(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", text.lower()))


def features(text: str) -> list[float]:
    found = words(text)
    return [float(word in found) for word in VOCAB] + [1.0]


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, x))))


class GeometricLearner:
    """Tiny trainable multi-label classifier, not a pretrained image model."""

    def __init__(self) -> None:
        self.weights = [[0.0] * (len(VOCAB) + 1) for _ in LABELS]

    def train(self, epochs: int = 90) -> None:
        rng = random.Random(1337)
        examples = []
        for _ in range(450):
            selected = [label for label in LABELS if rng.random() < 0.32]
            tokens = [rng.choice(TRAINING[label]) for label in selected]
            examples.append((' '.join(tokens), set(selected)))
        for _ in range(epochs):
            rng.shuffle(examples)
            for phrase, targets in examples:
                x = features(phrase)
                for index, label in enumerate(LABELS):
                    weights = self.weights[index]
                    probability = sigmoid(sum(a * b for a, b in zip(weights, x)))
                    error = float(label in targets) - probability
                    for j, value in enumerate(x):
                        weights[j] += 0.13 * error * value

    def predict(self, prompt: str) -> dict[str, float]:
        x = features(prompt)
        return {label: round(sigmoid(sum(a * b for a, b in zip(row, x))), 3)
                for label, row in zip(LABELS, self.weights)}


def _scene_svg(scores: dict[str, float], scene_index: int, prompt: str) -> str:
    active = lambda key: scores[key] >= 0.5
    evening = active('sunset') or (scene_index == 2 and active('movement'))
    night = active('night')
    sky = '#101d43' if night else ('#e99b73' if evening else '#9bd7f3')
    ground = '#395c49' if night else '#6da65b'
    seed = int(hashlib.sha256((prompt + str(scene_index)).encode()).hexdigest()[:12], 16)
    rng = random.Random(seed)
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="854" height="480" viewBox="0 0 854 480">',
           f'<rect width="854" height="480" fill="{sky}"/>',
           f'<rect y="280" width="854" height="200" fill="{ground}"/>']
    if not night:
        x = 115 + scene_index * 250
        y = 92 if not evening else 225
        svg.append(f'<circle cx="{x}" cy="{y}" r="39" fill="#ffdf8b"/>')
    if active('mountains'):
        for x in (0, 290, 570):
            svg.append(f'<polygon points="{x},285 {x+170},90 {x+355},285" fill="#637e89"/>')
    if active('water'):
        svg.append('<path d="M0 370 Q210 320 430 373 T854 360 L854 480 L0 480Z" fill="#3e9cc2"/>')
        for i in range(6):
            x = 40 + i * 135
            svg.append(f'<path d="M{x} 410 q35 -12 70 0" stroke="#c7eafa" stroke-width="3" fill="none"/>')
    if active('trees'):
        for i in range(5):
            x = 50 + i * 180 + rng.randrange(-35, 35)
            y = 270 + rng.randrange(-15, 22)
            svg.append(f'<rect x="{x}" y="{y-75}" width="15" height="95" fill="#70513a"/>')
            svg.append(f'<circle cx="{x+7}" cy="{y-92}" r="46" fill="#2e7548"/>')
    if active('buildings'):
        for i in range(3):
            x = 90 + i * 245 + rng.randrange(-20, 20)
            svg.append(f'<rect x="{x}" y="235" width="130" height="105" fill="#e4c7a1"/>')
            svg.append(f'<polygon points="{x-12},237 {x+65},165 {x+142},237" fill="#a95342"/>')
            svg.append(f'<rect x="{x+48}" y="283" width="33" height="57" fill="#735441"/>')
    # Abstract actor glyphs are deliberately generic. Learning object anatomy
    # is a future milestone, not a capability of this prototype.
    count = 3 if active('group') else 1
    for i in range(count):
        x = 215 + i * 165 + scene_index * 35
        y = 325 + (i % 2) * 22
        svg.append(f'<ellipse cx="{x}" cy="{y}" rx="51" ry="32" fill="#b08c69"/>')
        svg.append(f'<circle cx="{x+45}" cy="{y-22}" r="24" fill="#b08c69"/>')
        for dx in (-30, 25):
            svg.append(f'<rect x="{x+dx}" y="{y+20}" width="12" height="49" rx="5" fill="#85694f"/>')
    svg.append('</svg>')
    return ''.join(svg)


def create_scenes(prompt: str, output_dir: str = 'melodia_gi_test') -> dict:
    if not prompt.strip():
        raise ValueError('Prompt cannot be empty')
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    learner = GeometricLearner()
    learner.train()
    scores = learner.predict(prompt)
    clauses = [s.strip() for s in re.split(r'[.;]|\bthen\b|\band\b', prompt, flags=re.I) if s.strip()]
    scenes = []
    for index in range(3):
        # Each draft uses a distinct layout, but semantic scene fidelity is
        # not guaranteed until the object/action generator is trained.
        scene_scores = dict(scores)
        scene_scores['movement'] = max(scene_scores['movement'], 0.6 if index == 1 else 0.0)
        filename = f'scene_{index + 1:03d}.svg'
        (output / filename).write_text(_scene_svg(scene_scores, index, prompt), encoding='utf-8')
        caption = clauses[min(index, len(clauses)-1)].strip().capitalize()
        scenes.append({'scene': index + 1, 'duration_seconds': 10,
                       'image': filename, 'caption': caption})
    manifest = {'prompt': prompt, 'model': 'MELODIA-GI-V1-prototype',
                'predicted_attributes': scores, 'scenes': scenes,
                'music': 'existing V5 assembler (not connected yet)',
                'limitations': 'limited vocabulary; generic actor glyph; no object anatomy learning yet'}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


if __name__ == '__main__':
    import sys
    user_prompt = ' '.join(sys.argv[1:]) or 'An elephant walks through a forest beside a river at sunset'
    result = create_scenes(user_prompt)
    print(json.dumps(result, indent=2))
