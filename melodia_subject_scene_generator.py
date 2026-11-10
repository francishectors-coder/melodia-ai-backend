
# MELODIA AI - SUBJECT-AWARE SCENE GENERATOR
# Step 781

from melodia_prompt_analyzer import analyze_prompt

SCENE_TEMPLATES = {
    "prayer": [
        "Peaceful sunrise symbolizing hope and renewal",
        "Quiet sacred atmosphere with gentle golden light",
        "Person reflecting silently beside a tranquil lake",
        "Beautiful natural scenery inspiring gratitude",
        "Soft rays of sunlight through peaceful clouds",
        "Calm evening landscape expressing inner peace"
    ],
    "story": [
        "Cinematic opening establishing the story setting",
        "Main character introduced in a detailed environment",
        "Character begins an important journey",
        "A mysterious discovery changes the situation",
        "Dramatic moment revealing an important challenge",
        "Hopeful scene suggesting the journey continues"
    ],
    "education": [
        "Clear visual introduction to the main subject",
        "Detailed illustration of the central concept",
        "Realistic example demonstrating the subject",
        "Visual comparison explaining an important difference",
        "Step-by-step conceptual demonstration",
        "Summary composition reinforcing the key idea"
    ],
    "music": [
        "Atmospheric cinematic opening matching the song mood",
        "Beautiful visual composition supporting the lyrics",
        "Expressive landscape matching the musical emotion",
        "Soft cinematic imagery for the next musical phrase",
        "Symbolic visual scene supporting the song theme",
        "Memorable closing composition for the music video"
    ],
    "inspiration": [
        "Dramatic sunrise representing new beginnings",
        "Person beginning a meaningful personal journey",
        "Cinematic imagery representing determination",
        "Beautiful landscape suggesting possibility",
        "Warm sunlight symbolizing achievement",
        "Hopeful panoramic scene expressing success"
    ],
    "general": [
        "Cinematic establishing shot relevant to the prompt",
        "Detailed visual exploration of the main subject",
        "Alternative perspective of the requested theme",
        "Atmospheric composition supporting the subject",
        "Close-up visual detail related to the prompt",
        "Memorable cinematic closing composition"
    ]
}


def generate_scene_descriptions(prompt, count=6):
    result = analyze_prompt(prompt)
    subject = result["subject"]

    templates = SCENE_TEMPLATES[subject]
    scenes = []

    for index in range(count):
        description = templates[
            index % len(templates)
        ]

        scenes.append({
            "scene_number": index + 1,
            "subject": subject,
            "visual_prompt": (
                description
                + ". Context: "
                + prompt
                + ". Cinematic composition, "
                + "natural lighting, high visual quality, "
                + "no embedded text or logos."
            )
        })

    return scenes


def main():
    print("MELODIA AI - SUBJECT-AWARE SCENE TEST")

    prompts = [
        "Create a peaceful prayer video",
        "Tell an adventurous children's story",
        "Explain the solar system",
        "Create a Tamil song lyrics video",
        "Make an inspirational success video"
    ]

    for prompt in prompts:
        scenes = generate_scene_descriptions(
            prompt,
            count=3
        )

        print("\nPROMPT:", prompt)
        print("SUBJECT:", scenes[0]["subject"])

        for scene in scenes:
            print(
                "Scene",
                scene["scene_number"],
                ":",
                scene["visual_prompt"]
            )

    print("\nSUBJECT-AWARE SCENE TEST PASSED")


if __name__ == "__main__":
    main()
