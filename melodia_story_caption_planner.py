
"""MELODIA AI: Offline story caption planner.
Step 1337.35.16
Independent module; does not change the existing worker.
"""

import re


TOPICS = {
    "farm": (
        "farmer", "farm", "harvest", "harvesting",
        "paddy", "rice", "agriculture", "crop", "crops"
    ),
    "village": (
        "village", "rural", "countryside", "hamlet"
    ),
    "ocean": (
        "ocean", "sea", "beach", "reef",
        "fish", "underwater", "boat", "sailing"
    ),
    "space": (
        "space", "planet", "galaxy", "galaxies",
        "astronaut", "stars", "moon", "saturn"
    ),
    "city": (
        "city", "urban", "street", "skyscraper",
        "traffic", "buildings"
    ),
    "nature": (
        "nature", "forest", "mountain", "river",
        "waterfall", "wildlife", "trees"
    ),
    "religious": (
        "jesus", "apostle", "apostles", "prayer",
        "church", "bible", "mary", "christian"
    ),
    "education": (
        "teacher", "students", "school",
        "classroom", "learning", "education"
    ),
}


STORIES = {
    "farm": (
        "Fields of ripening crops stretch across the countryside.",
        "A farmer works carefully among the crops.",
        "The harvest brings the rewards of patient work."
    ),
    "village": (
        "A peaceful village welcomes another day.",
        "Daily life unfolds around its homes and fields.",
        "The community carries on its traditions."
    ),
    "ocean": (
        "The vast ocean stretches toward the horizon.",
        "Life and movement fill the waters.",
        "The sea reveals its remarkable beauty."
    ),
    "space": (
        "Beyond Earth lies an extraordinary universe.",
        "Stars and planets fill the vast darkness.",
        "The wonders of space invite exploration."
    ),
    "city": (
        "A busy city rises beneath the sky.",
        "People and streets bring the city to life.",
        "The skyline marks another chapter in city life."
    ),
    "nature": (
        "A remarkable natural landscape comes into view.",
        "The land reveals its many living details.",
        "The beauty of nature invites reflection."
    ),
    "religious": (
        "A quiet moment invites faith and reflection.",
        "Prayer offers comfort and renewed hope.",
        "The gathering ends in peace and gratitude."
    ),
    "education": (
        "A new lesson begins with curiosity.",
        "Learning grows through questions and discovery.",
        "New knowledge opens the way forward."
    ),
    "general": (
        "A new story begins to unfold.",
        "The central moment brings the story to life.",
        "The journey reaches its closing scene."
    ),
}


def _words(prompt):
    return set(re.findall(r"[a-z]+", prompt.lower()))


def _contains_phrase(prompt, phrase):
    return bool(re.search(
        r"\b" + re.escape(phrase) + r"\b",
        prompt,
        re.IGNORECASE
    ))


def detect_story_topic(prompt):
    scores = {
        topic: sum(
            _contains_phrase(prompt, word)
            for word in keywords
        )
        for topic, keywords in TOPICS.items()
    }

    best = max(scores, key=scores.get)
    return best if scores[best] else "general"


def generate_story_captions(prompt):
    """Return three connected English story captions."""

    if not isinstance(prompt, str):
        raise TypeError("Prompt must be a string")

    clean = re.sub(
        r"\[FREE TEST\]", "",
        prompt,
        flags=re.IGNORECASE
    ).strip()

    topic = detect_story_topic(clean)
    captions = list(STORIES[topic])
    words = _words(clean)

    if topic == "farm":
        if "tamil" in words and "nadu" in words:
            captions[0] = (
                "Rice fields spread across the Tamil Nadu countryside."
            )

        if "rice" in words or "paddy" in words:
            captions[0] = (
                "Golden paddy fields stretch across Tamil Nadu."
                if "tamil" in words and "nadu" in words
                else "Golden rice fields stretch across the countryside."
            )

        if "sickle" in words and (
            "harvest" in words or "harvesting" in words
        ):
            captions[1] = (
                "A farmer cuts ripe rice stalks with a sickle."
            )
        elif "harvest" in words or "harvesting" in words:
            captions[1] = (
                "A farmer gathers the ripe crops from the fields."
            )

        if "bundle" in words or "bundles" in words:
            captions[2] = (
                "The harvested rice is gathered into bundles."
            )

    elif topic == "religious":
        if _contains_phrase(clean, "last supper"):
            captions = [
                "Jesus gathers with his apostles for a final meal.",
                "Bread and wine are shared around the table.",
                "The gathering becomes a moment of remembrance."
            ]

    elif topic == "ocean":
        if "coral" in words or "reef" in words:
            captions[1] = (
                "Colourful reefs provide shelter for marine life."
            )

        if "boat" in words or "sailing" in words:
            captions[1] = (
                "A boat makes its way across the water."
            )

    elif topic == "space":
        if "saturn" in words:
            captions[1] = (
                "Saturn's magnificent rings circle the planet."
            )
        elif "moon" in words:
            captions[1] = (
                "The Moon hangs above the distant horizon."
            )

    elif topic == "education":
        if "teacher" in words and "students" in words:
            captions[1] = (
                "A teacher guides students through a new lesson."
            )

    return captions


def build_caption_records(prompt, seconds_per_scene=10.0):
    """Return records compatible with MELODIA caption JSON."""

    if seconds_per_scene <= 0:
        raise ValueError(
            "seconds_per_scene must be positive"
        )

    captions = generate_story_captions(prompt)

    return [
        {
            "scene_number": index,
            "start_seconds": (index - 1) * seconds_per_scene,
            "end_seconds": index * seconds_per_scene,
            "primary": caption,
            "translated": ""
        }
        for index, caption in enumerate(captions, 1)
    ]


if __name__ == "__main__":
    example = (
        "[FREE TEST] Create a video showing a farmer "
        "harvesting golden rice in a Tamil Nadu village "
        "using a sickle and gathering rice bundles."
    )

    for record in build_caption_records(example):
        print(
            f"Scene {record['scene_number']}: "
            f"{record['primary']}"
        )
