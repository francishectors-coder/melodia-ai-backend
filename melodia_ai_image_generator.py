
# MELODIA AI - GEMINI CLOUD IMAGE GENERATOR
# Step 1333.72
# Google Gen AI SDK - Interactions API
# Preserves the existing generate_image() interface.
# Previous versions must remain backed up.

import os
import base64
import tempfile
from pathlib import Path
from io import BytesIO
from PIL import Image


ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "generated_visuals"

MODEL = os.getenv(
    "MELODIA_IMAGE_MODEL",
    "gemini-3.1-flash-lite-image"
)

TEST_PROMPT = (
    "A breathtaking cinematic sunrise over "
    "lush green mountains, a flowing waterfall, "
    "soft golden morning light, realistic "
    "photography, detailed natural scenery, "
    "no text, no logos, no watermark."
)


def generate_image(
    prompt,
    output_path,
    timeout=180,
    aspect_ratio="16:9"
):
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("Image prompt cannot be empty")

    if aspect_ratio not in ("16:9", "9:16"):
        raise ValueError(
            "Unsupported aspect ratio: " + str(aspect_ratio)
        )

    key = os.getenv("GEMINI_API_KEY")

    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY is not configured"
        )

    output_path = Path(output_path)
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    print("MELODIA AI - GEMINI IMAGE GENERATION")
    print("Model:", MODEL)
    print("Aspect ratio:", aspect_ratio)

    from google import genai
    client = genai.Client(api_key=key)

    image_prompt = (
        prompt.strip()
        + "\nGenerate a photorealistic cinematic image."
        + f"\nRequired composition: {aspect_ratio}."
        + "\nDo not include captions or decorative text."
    )

    generation_config = {
        "temperature": 1,
        "max_output_tokens": 65536,
        "top_p": 0.95,
        "thinking_level": "minimal",
        "image_config": {
            "image_size": "1K",
            "aspect_ratio": aspect_ratio
        }
    }

    try:
        interaction = client.interactions.create(
            model="models/" + MODEL,
            input=image_prompt,
            generation_config=generation_config,
            response_modalities=["image", "text"]
        )
    except Exception as error:
        raise RuntimeError(
            "Gemini Interactions API failed: "
            + str(error)
        ) from error

    image_bytes = None
    response_text = []

    for step in getattr(interaction, "steps", []) or []:
        if getattr(step, "type", None) != "model_output":
            continue

        for part in getattr(step, "content", []) or []:
            part_type = getattr(part, "type", None)

            if part_type == "image":
                encoded = getattr(part, "data", None)

                if encoded:
                    if isinstance(encoded, bytes):
                        image_bytes = base64.b64decode(encoded)
                    else:
                        image_bytes = base64.b64decode(
                            str(encoded)
                        )
                    break

            elif part_type == "text":
                message = getattr(part, "text", None)

                if message:
                    response_text.append(str(message))

        if image_bytes:
            break

    if not image_bytes:
        details = " | ".join(response_text)

        if not details:
            details = "No image content in model output"

        raise RuntimeError(
            "Gemini returned no image data. "
            + details[:1000]
        )

    # Verify the actual image format returned by Gemini.
    is_png = image_bytes.startswith(
        b"\x89PNG\r\n\x1a\n"
    )

    is_jpeg = image_bytes.startswith(
        b"\xff\xd8\xff"
    )

    if not (is_png or is_jpeg):
        raise RuntimeError(
            "Gemini returned an unsupported image format."
        )

    print(
        "Gemini image format:",
        "PNG" if is_png else "JPEG"
    )

    # Convert Gemini JPEG output to PNG.
    if is_jpeg:
        with Image.open(BytesIO(image_bytes)) as image:
            converted = BytesIO()
            image.convert("RGB").save(
                converted,
                format="PNG"
            )
            image_bytes = converted.getvalue()

        print("Gemini JPEG converted to PNG")
    # Atomic saving prevents incomplete image files.
    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            suffix=".tmp",
            prefix="melodia_image_",
            dir=output_path.parent,
            delete=False
        ) as file:
            temporary_path = Path(file.name)
            file.write(image_bytes)

        os.replace(
            temporary_path,
            output_path
        )

    finally:
        if (
            temporary_path is not None
            and temporary_path.exists()
        ):
            temporary_path.unlink()

    print("IMAGE GENERATION SUCCESSFUL")
    print("Saved:", output_path)

    return output_path


def main():
    destination = OUTPUT_DIR / "gemini_test.png"

    try:
        generate_image(
            TEST_PROMPT,
            destination,
            aspect_ratio="16:9"
        )
    except Exception as error:
        print("IMAGE GENERATION FAILED")
        print(type(error).__name__ + ":", error)


if __name__ == "__main__":
    main()
