
# MELODIA AI - UNIVERSAL GEOMETRIC SCENE ENGINE
# Step 1337.35.1
# Offline, prompt-responsive geometric illustration engine.
# Does not modify existing worker, captions, or V5 music.

import math
import random
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WIDTH = 854
HEIGHT = 480

SCENE_KEYWORDS = {
    "farm": (
        "farmer", "farm", "farming", "harvest",
        "rice", "paddy", "agriculture", "field"
    ),
    "village": (
        "village", "rural", "hut", "countryside"
    ),
    "ocean": (
        "ocean", "sea", "beach", "fish",
        "underwater", "boat", "island"
    ),
    "space": (
        "space", "planet", "galaxy", "moon",
        "stars", "astronaut", "universe"
    ),
    "city": (
        "city", "building", "urban", "street",
        "traffic", "skyscraper"
    ),
    "nature": (
        "forest", "mountain", "river",
        "tree", "nature", "waterfall"
    ),
    "religious": (
        "jesus", "prayer", "church", "bible",
        "apostle", "christian", "mary", "cross"
    ),
}

ACTION_KEYWORDS = {
    "harvesting": ("harvest", "harvesting", "cutting"),
    "walking": ("walk", "walking", "travel"),
    "praying": ("pray", "praying", "worship"),
    "working": ("work", "working", "build"),
    "sailing": ("sail", "sailing", "boat"),
    "celebrating": ("celebrate", "celebration", "festival"),
}

COLOR_THEMES = [
    ((115, 185, 220), (75, 150, 88)),
    ((245, 178, 118), (95, 143, 82)),
    ((85, 130, 188), (54, 120, 102)),
]


def detect_category(prompt):
    text = prompt.lower()
    scores = {}

    for category, words in SCENE_KEYWORDS.items():
        scores[category] = sum(
            1 for word in words
            if re.search(r"\b" + re.escape(word) + r"\b", text)
        )

    best = max(scores, key=scores.get)
    return best if scores[best] else "general"


def detect_action(prompt):
    text = prompt.lower()

    for action, words in ACTION_KEYWORDS.items():
        if any(word in text for word in words):
            return action

    return "standing"


def plan_scenes(prompt, count=3):
    category = detect_category(prompt)
    action = detect_action(prompt)

    stages = ["establishing", "main_action", "conclusion"]

    scenes = []

    for index in range(count):
        scenes.append({
            "scene_number": index + 1,
            "category": category,
            "action": action,
            "stage": stages[index % len(stages)],
            "prompt": prompt,
            "camera": (
                "wide" if index == 0
                else "medium" if index == 1
                else "close"
            ),
        })

    return scenes


def draw_person(draw, x, y, scale=1.0, color=(70, 90, 155)):
    head = max(5, int(12 * scale))

    draw.ellipse(
        (x-head, y-head, x+head, y+head),
        fill=(218, 166, 125)
    )

    shoulder = int(18 * scale)
    bottom = y + int(75 * scale)

    draw.polygon(
        [
            (x-shoulder, y+head),
            (x+shoulder, y+head),
            (x+int(24*scale), bottom),
            (x-int(24*scale), bottom),
        ],
        fill=color
    )

    draw.line(
        [(x-int(10*scale), bottom),
         (x-int(14*scale), bottom+int(25*scale))],
        fill=(52, 57, 67),
        width=max(3, int(7*scale))
    )

    draw.line(
        [(x+int(10*scale), bottom),
         (x+int(14*scale), bottom+int(25*scale))],
        fill=(52, 57, 67),
        width=max(3, int(7*scale))
    )


def draw_tree(draw, x, y, scale=1.0):
    trunk_width = int(15 * scale)
    trunk_height = int(95 * scale)

    draw.rectangle(
        (x-trunk_width//2, y-trunk_height,
         x+trunk_width//2, y),
        fill=(102, 68, 44)
    )

    radius = int(43 * scale)

    for dx, dy in [(-25, -105), (25, -110), (0, -140)]:
        cx = x + int(dx*scale)
        cy = y + int(dy*scale)

        draw.ellipse(
            (cx-radius, cy-radius,
             cx+radius, cy+radius),
            fill=(42, 116, 64)
        )


def draw_house(draw, x, y, scale=1.0):
    w = int(120 * scale)
    h = int(100 * scale)

    draw.rectangle(
        (x, y-h, x+w, y),
        fill=(211, 170, 116)
    )

    draw.polygon(
        [(x-12, y-h), (x+w//2, y-h-65),
         (x+w+12, y-h)],
        fill=(143, 75, 62)
    )

    draw.rectangle(
        (x+w//2-15, y-55, x+w//2+15, y),
        fill=(91, 67, 54)
    )


def draw_farm(draw, scene):
    draw.rectangle(
        (0, 0, WIDTH, 285),
        fill=(135, 194, 229)
    )

    draw.ellipse(
        (675, 45, 780, 150),
        fill=(250, 214, 120)
    )

    draw.rectangle(
        (0, 285, WIDTH, HEIGHT),
        fill=(107, 164, 76)
    )

    for row in range(8):
        y = 300 + row*23

        draw.line(
            [(0, y), (WIDTH, y+5)],
            fill=(166, 139, 71),
            width=5
        )

        for x in range(15, WIDTH, 42):
            draw.line(
                [(x, y), (x-6, y-18)],
                fill=(205, 185, 72),
                width=3
            )

    stage = scene["stage"]

    if stage == "establishing":
        draw_house(draw, 100, 310, 1.1)
        draw_tree(draw, 660, 320, 1.0)
        draw_person(draw, 430, 280, 0.8)

    elif stage == "main_action":
        draw_person(draw, 430, 205, 1.5)

        draw.line(
            [(475, 265), (530, 310)],
            fill=(94, 67, 43),
            width=5
        )

        draw.arc(
            (495, 270, 565, 330),
            20, 190,
            fill=(200, 205, 213),
            width=5
        )

    else:
        draw_person(draw, 370, 225, 1.2)

        for x in (520, 600, 680):
            draw.polygon(
                [(x-25, 340), (x, 260),
                 (x+25, 340)],
                fill=(219, 190, 91)
            )


def draw_ocean(draw, scene):
    draw.rectangle(
        (0, 0, WIDTH, 240),
        fill=(125, 193, 231)
    )

    draw.rectangle(
        (0, 240, WIDTH, HEIGHT),
        fill=(24, 111, 171)
    )

    for i in range(12):
        y = 250+i*20

        draw.arc(
            (30, y, 820, y+35),
            0, 180,
            fill=(116, 190, 218),
            width=2
        )

    if scene["stage"] == "establishing":
        draw.ellipse(
            (650, 55, 750, 155),
            fill=(248, 219, 143)
        )

    elif scene["stage"] == "main_action":
        draw.polygon(
            [(310, 280), (530, 280), (490, 335), (350, 335)],
            fill=(120, 74, 50)
        )

        draw.polygon(
            [(420, 120), (420, 275), (530, 275)],
            fill=(241, 232, 203)
        )

    else:
        for x in (250, 430, 610):
            draw.ellipse(
                (x, 310, x+90, 350),
                fill=(238, 168, 91)
            )

            draw.polygon(
                [(x, 330), (x-30, 305), (x-30, 355)],
                fill=(238, 168, 91)
            )


def draw_space(draw, scene):
    rng = random.Random(scene["scene_number"])

    draw.rectangle(
        (0, 0, WIDTH, HEIGHT),
        fill=(12, 17, 43)
    )

    for _ in range(130):
        x = rng.randrange(WIDTH)
        y = rng.randrange(HEIGHT)
        r = rng.choice((1, 1, 2))

        draw.ellipse(
            (x-r, y-r, x+r, y+r),
            fill=(220, 226, 243)
        )

    radius = (
        95 if scene["stage"] == "establishing"
        else 145
    )

    draw.ellipse(
        (427-radius, 240-radius,
         427+radius, 240+radius),
        fill=(91, 135, 197)
    )

    if scene["stage"] == "conclusion":
        draw.arc(
            (175, 130, 680, 360),
            10, 170,
            fill=(224, 193, 130),
            width=12
        )


def draw_city(draw, scene):
    draw.rectangle(
        (0, 0, WIDTH, HEIGHT),
        fill=(111, 159, 203)
    )

    rng = random.Random(scene["scene_number"])

    for i in range(11):
        x = i*80
        height = rng.randint(150, 370)

        draw.rectangle(
            (x, HEIGHT-height, x+65, HEIGHT),
            fill=(45, 65, 100)
        )

        for wy in range(HEIGHT-height+20, HEIGHT-20, 30):
            for wx in range(x+12, x+60, 18):
                draw.rectangle(
                    (wx, wy, wx+8, wy+13),
                    fill=(239, 204, 133)
                )


def draw_nature(draw, scene):
    draw.rectangle(
        (0, 0, WIDTH, HEIGHT),
        fill=(133, 197, 220)
    )

    draw.polygon(
        [(0, 380), (200, 100), (400, 380)],
        fill=(76, 119, 111)
    )

    draw.polygon(
        [(270, 390), (550, 75), (854, 390)],
        fill=(64, 106, 109)
    )

    draw.rectangle(
        (0, 390, WIDTH, HEIGHT),
        fill=(63, 126, 76)
    )

    for x in (100, 250, 680, 790):
        draw_tree(draw, x, 425, 0.8)


def draw_religious(draw, scene):
    draw.rectangle(
        (0, 0, WIDTH, HEIGHT),
        fill=(112, 104, 125)
    )

    draw.ellipse(
        (325, 65, 530, 270),
        fill=(229, 191, 122)
    )

    draw.rectangle(
        (415, 95, 442, 340),
        fill=(239, 218, 168)
    )

    draw.rectangle(
        (350, 150, 505, 180),
        fill=(239, 218, 168)
    )

    draw_person(
        draw, 425, 280, 1.2,
        color=(157, 68, 75)
    )

    if scene["stage"] != "establishing":
        draw_person(
            draw, 260, 310, 0.8,
            color=(77, 110, 154)
        )

        draw_person(
            draw, 590, 310, 0.8,
            color=(114, 111, 78)
        )


def draw_general(draw, scene):
    draw.rectangle(
        (0, 0, WIDTH, HEIGHT),
        fill=(122, 183, 216)
    )

    draw.ellipse(
        (650, 60, 760, 170),
        fill=(250, 214, 132)
    )

    draw.rectangle(
        (0, 350, WIDTH, HEIGHT),
        fill=(87, 151, 94)
    )

    draw_tree(draw, 150, 380, 1.0)
    draw_tree(draw, 720, 390, 0.9)

    draw_person(
        draw, 425, 250,
        1.2 if scene["stage"] == "main_action" else 0.9
    )


RENDERERS = {
    "farm": draw_farm,
    "village": draw_farm,
    "ocean": draw_ocean,
    "space": draw_space,
    "city": draw_city,
    "nature": draw_nature,
    "religious": draw_religious,
    "general": draw_general,
}


def render_scene(scene, output_path):
    image = Image.new(
        "RGB", (WIDTH, HEIGHT),
        (25, 35, 55)
    )

    draw = ImageDraw.Draw(image)

    renderer = RENDERERS.get(
        scene["category"], draw_general
    )

    renderer(draw, scene)

    # Small watermark only.
    draw.rounded_rectangle(
        (12, 12, 145, 36),
        radius=5,
        fill=(24, 35, 52)
    )

    draw.text(
        (20, 19),
        "MELODIA AI",
        fill=(235, 239, 245)
    )

    output_path = Path(output_path)
    output_path.parent.mkdir(
        parents=True, exist_ok=True
    )

    image.save(
        output_path, format="PNG"
    )

    return output_path


def generate_video_scenes(prompt, output_directory, count=3):
    output_directory = Path(output_directory)
    output_directory.mkdir(
        parents=True, exist_ok=True
    )

    plan = plan_scenes(prompt, count)

    results = []

    for scene in plan:
        number = scene["scene_number"]

        output_path = (
            output_directory /
            f"scene_{number:03d}.png"
        )

        render_scene(scene, output_path)

        results.append({
            **scene,
            "image_path": str(output_path.resolve())
        })

    return results


if __name__ == "__main__":
    test_prompt = (
        "[FREE TEST] A farmer harvesting rice "
        "in a Tamil Nadu village"
    )

    scenes = generate_video_scenes(
        test_prompt,
        "universal_scene_test",
        count=3
    )

    for scene in scenes:
        print(
            scene["scene_number"],
            scene["category"],
            scene["stage"],
            scene["image_path"]
        )
