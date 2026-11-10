
# MELODIA AI - GEMINI CLOUD IMAGE GENERATOR
# Step 1332.19
# Preserves generate_image() interface and earlier backups.

import os
import json
import base64
import tempfile
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "generated_visuals"

MODEL = os.getenv(
    "MELODIA_IMAGE_MODEL",
    "gemini-3.1-flash-lite-image"
)

API_URL = (
    "https://generativelanguage.googleapis.com/"
    f"v1beta/models/{MODEL}:generateContent"
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

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {
                "aspectRatio": aspect_ratio
            }
        }
    }

    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": key
        },
        method="POST"
    )

    print("MELODIA AI - GEMINI IMAGE GENERATION")
    print("Model:", MODEL)
    print("Aspect ratio:", aspect_ratio)

    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout
        ) as response:
            result = json.loads(
                response.read().decode("utf-8")
            )

    except urllib.error.HTTPError as error:
        details = error.read().decode(
            "utf-8",
            errors="replace"
        )
        raise RuntimeError(
            f"Gemini API HTTP {error.code}: "
            + details[:1000]
        ) from None

    except urllib.error.URLError as error:
        raise RuntimeError(
            "Gemini connection failed: "
            + str(error.reason)
        ) from None

    candidates = result.get("candidates", [])

    if not candidates:
        raise RuntimeError(
            "Gemini returned no image candidates"
        )

    parts = (
        candidates[0]
        .get("content", {})
        .get("parts", [])
    )

    image_bytes = None

    for part in parts:
        inline_data = part.get("inlineData", {})
        encoded = inline_data.get("data")

        if encoded:
            image_bytes = base64.b64decode(encoded)
            break

    if not image_bytes:
        raise RuntimeError(
            "Gemini returned no image data"
        )

    # Write atomically to avoid incomplete output files.
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

        os.replace(temporary_path, output_path)

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
