
# MELODIA AI - AUTOMATIC PROMPT ANALYZER
# Step 1176
# Multilingual video recommendations
# No external API requests
# Compatible with existing scene generator

import re

SUBJECT_KEYWORDS = {
    "prayer": [
        "prayer", "pray", "devotional",
        "worship", "god", "jesus",
        "allah", "spiritual", "meditation",
        "பிரார்த்தனை", "ஜெபம்", "இறைவன்",
        "प्रार्थना", "भक्ति",
        "പ്രാർത്ഥന", "దేవుని ప్రార్థన"
    ],
    "story": [
        "story", "fairy tale", "adventure",
        "character", "fiction", "narrative",
        "கதை", "कहानी", "കഥ", "కథ"
    ],
    "education": [
        "educational", "explain", "science",
        "history", "learning", "lesson",
        "tutorial", "education",
        "விளக்கம்", "அறிவியல்", "கல்வி",
        "शिक्षा", "विज्ञान",
        "വിദ്യാഭ്യാസം", "ശാസ്ത്രം",
        "విద్య", "శాస్త్రం"
    ],
    "music": [
        "song", "lyrics", "musical",
        "instrumental", "music video",
        "பாடல்", "இசை",
        "गीत", "संगीत",
        "പാട്ട്", "സംഗീതം",
        "పాట", "సంగీతం"
    ],
    "inspiration": [
        "inspirational", "motivation",
        "hope", "success", "encouragement",
        "inspiring", "motivational",
        "நம்பிக்கை", "ஊக்கம்",
        "प्रेरणा", "उम्मीद",
        "പ്രചോദനം", "ప్రేరణ"
    ],
    "news": [
        "news", "breaking news", "report",
        "headlines", "current affairs",
        "செய்தி", "समाचार",
        "വാർത്ത", "వార్తలు"
    ],
    "promotional": [
        "advertisement", "advertising",
        "promotion", "promotional",
        "business", "product launch",
        "commercial", "marketing",
        "விளம்பரம்", "प्रचार",
        "പരസ്യം", "ప్రకటన"
    ]
}

LANGUAGE_KEYWORDS = {
    "English": [
        "english", "ஆங்கிலம்",
        "अंग्रेजी", "ഇംഗ്ലീഷ്", "ఇంగ్లీష్"
    ],
    "Tamil": [
        "tamil", "தமிழ்", "तमिल",
        "തമിഴ്", "తమిళం"
    ],
    "Hindi": [
        "hindi", "இந்தி", "हिंदी",
        "ഹിന്ദി", "హిందీ"
    ],
    "Malayalam": [
        "malayalam", "மலையாளம்",
        "मलयालम", "മലയാളം", "మలయాళం"
    ],
    "Telugu": [
        "telugu", "தெலுங்கு",
        "तेलुगु", "തെലുങ്ക്", "తెలుగు"
    ]
}

BILINGUAL_TERMS = [
    "bilingual", "dual language",
    "two languages", "both languages",
    "இரு மொழி", "இருமொழி",
    "द्विभाषी"
]

VERTICAL_TERMS = [
    "vertical", "portrait", "9:16",
    "youtube shorts", "shorts",
    "instagram reel", "reels",
    "tiktok"
]

LANDSCAPE_TERMS = [
    "landscape", "horizontal", "16:9",
    "widescreen"
]

SILENCE_TERMS = [
    "no music", "without music",
    "silent", "silence",
    "no audio", "without audio",
    "மௌனம்", "இசை வேண்டாம்"
]

NATURE_AUDIO_TERMS = [
    "nature sounds", "natural sounds",
    "birds singing", "birdsong",
    "ocean waves", "rain sounds",
    "ambient nature"
]

MUSIC_TERMS = [
    "background music", "instrumental",
    "gentle music", "peaceful music",
    "cinematic music", "uplifting music"
]

PLAIN_BACKGROUND_TERMS = [
    "plain background", "solid background",
    "simple background", "gradient background",
    "navy blue background", "text only"
]

SCENIC_BACKGROUND_TERMS = [
    "scenery", "scenic", "landscape",
    "mountains", "forest", "sunrise",
    "sunset", "ocean", "nature background"
]


def contains_term(text, term):
    pattern = (
        r"(?<!\w)"
        + re.escape(term.casefold())
        + r"(?!\w)"
    )
    return re.search(pattern, text) is not None


def matches_any(text, terms):
    return any(
        contains_term(text, term)
        for term in terms
    )


def detect_subject(text):
    scores = {}

    for category, keywords in SUBJECT_KEYWORDS.items():
        scores[category] = sum(
            1
            for keyword in keywords
            if contains_term(text, keyword)
        )

    best = max(scores, key=scores.get)

    if scores[best] == 0:
        best = "general"

    return best, scores


def detect_languages(text):
    detected = []

    for language, keywords in LANGUAGE_KEYWORDS.items():
        if matches_any(text, keywords):
            detected.append(language)

    bilingual_requested = matches_any(
        text,
        BILINGUAL_TERMS
    )

    if not detected:
        primary = "English"
        second = None

    else:
        primary = detected[0]
        second = None

    if bilingual_requested:
        if len(detected) >= 2:
            primary = detected[0]
            second = detected[1]

        elif len(detected) == 1:
            second = (
                "English"
                if primary != "English"
                else "Tamil"
            )

        else:
            primary = "English"
            second = "Tamil"

    caption_mode = (
        "bilingual"
        if bilingual_requested
        else "single"
    )

    return primary, second, caption_mode


def detect_aspect_ratio(text):
    vertical = matches_any(
        text,
        VERTICAL_TERMS
    )

    horizontal = matches_any(
        text,
        LANDSCAPE_TERMS
    )

    if vertical and not horizontal:
        return "9:16"

    return "16:9"


def detect_background(text, subject):
    if matches_any(
        text,
        PLAIN_BACKGROUND_TERMS
    ):
        return "plain"

    if matches_any(
        text,
        SCENIC_BACKGROUND_TERMS
    ):
        return "scenic"

    if subject in (
        "prayer",
        "inspiration",
        "story",
        "music"
    ):
        return "scenic"

    return "auto"


def detect_audio(text, subject):
    if matches_any(
        text,
        SILENCE_TERMS
    ):
        return "none", "none"

    if matches_any(
        text,
        NATURE_AUDIO_TERMS
    ):
        return "nature", "none"

    if matches_any(
        text,
        MUSIC_TERMS
    ):
        if contains_term(
            text,
            "uplifting music"
        ):
            return "music", "uplifting"

        if contains_term(
            text,
            "cinematic music"
        ):
            return "music", "cinematic"

        return "music", "peaceful"

    # Text-first output defaults to silence.
    if subject in (
        "education",
        "news",
        "promotional",
        "general"
    ):
        return "none", "none"

    return "none", "none"


def recommend_style(subject):
    styles = {
        "prayer": "prayer",
        "story": "cinematic",
        "education": "educational",
        "music": "cinematic",
        "inspiration": "quotes",
        "news": "news",
        "promotional": "promotional",
        "general": "auto"
    }

    return styles.get(
        subject,
        "auto"
    )


def analyze_prompt(prompt):
    if not isinstance(prompt, str):
        raise TypeError(
            "Prompt must be a string"
        )

    prompt = prompt.strip()

    if not prompt:
        raise ValueError(
            "Prompt cannot be empty"
        )

    text = prompt.casefold()

    subject, scores = detect_subject(text)

    primary, second, captions = (
        detect_languages(text)
    )

    aspect_ratio = detect_aspect_ratio(text)

    background = detect_background(
        text,
        subject
    )

    audio, music = detect_audio(
        text,
        subject
    )

    return {
        "prompt": prompt,
        "subject": subject,
        "scores": scores,
        "recommended_style": recommend_style(
            subject
        ),
        "language": primary,
        "captions": captions,
        "second_language": second,
        "aspect_ratio": aspect_ratio,
        "background": background,
        "audio": audio,
        "music": music,
        "movement": "still",
        "recommendation_source": "local_rules"
    }


def main():
    print(
        "MELODIA AI - AUTOMATIC PROMPT ANALYZER"
    )

    prompts = [
        "Create a peaceful prayer video",
        "Create a Tamil prayer video",
        "Create bilingual English and Tamil captions",
        "Explain the solar system in Hindi",
        "Create a vertical motivational video",
        "Create a news video without music",
        "Create a promotional video with scenic images"
    ]

    for prompt in prompts:
        result = analyze_prompt(prompt)

        print("\nPROMPT:", prompt)
        print("Subject:", result["subject"])
        print("Style:", result["recommended_style"])
        print("Language:", result["language"])
        print("Captions:", result["captions"])
        print("Second language:", result["second_language"])
        print("Format:", result["aspect_ratio"])
        print("Background:", result["background"])
        print("Audio:", result["audio"])

    print()
    print(
        "MELODIA AI - PROMPT ANALYSIS COMPLETE"
    )


if __name__ == "__main__":
    main()
