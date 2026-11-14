"""MELODIA AI — Gemini cloud image generator (V2.7 compatibility update).

Preserves generate_image(prompt, output_path, timeout=180, aspect_ratio='16:9').
Requires google-genai and Pillow; set GEMINI_API_KEY in the environment.
This module makes an API request only when generate_image() is called.
"""
from __future__ import annotations

import base64
import binascii
import os
import tempfile
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "generated_visuals"
MODEL = os.getenv("MELODIA_IMAGE_MODEL", "gemini-3.1-flash-lite-image")

TEST_PROMPT = (
    "A breathtaking cinematic sunrise over lush green mountains, "
    "a flowing waterfall, soft golden morning light, realistic "
    "photography, detailed natural scenery, no text, no logos, no watermark."
)


def generate_image(prompt, output_path, timeout=180, aspect_ratio="16:9"):
    """Generate one image through Gemini and save an actual PNG atomically."""
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("Image prompt cannot be empty")
    if aspect_ratio not in ("16:9", "9:16"):
        raise ValueError(f"Unsupported aspect ratio: {aspect_ratio}")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 600:
        raise ValueError("timeout must be a number between 0 and 600 seconds")
    destination = Path(output_path)
    if destination.suffix.lower() != ".png":
        raise ValueError("output_path must end with .png")
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError("Install google-genai: python -m pip install -U google-genai") from exc

    # The SDK uses milliseconds for its HTTP timeout.
    client = genai.Client(
        api_key=key,
        http_options=types.HttpOptions(timeout=int(timeout * 1000)),
    )
    image_prompt = (
        prompt.strip()
        + "\nGenerate a photorealistic cinematic image."
        + f"\nRequired aspect ratio: {aspect_ratio}."
        + "\nDo not include captions, decorative text, logos, or visible watermarks."
    )
    try:
        interaction = client.interactions.create(
            model=MODEL,
            input=image_prompt,
            response_format={
                "type": "image",
                "mime_type": "image/jpeg",
                "aspect_ratio": aspect_ratio,
                "image_size": "1K",
            },
        )
        output_image = getattr(interaction, "output_image", None)
        encoded = getattr(output_image, "data", None) if output_image else None
        if not encoded:
            raise RuntimeError("Gemini returned no inline image data")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError, TypeError) as exc:
            raise RuntimeError("Gemini returned invalid base64 image data") from exc
        with Image.open(BytesIO(raw)) as image:
            if image.format not in ("PNG", "JPEG"):
                raise RuntimeError("Gemini returned an unsupported image format")
            image.load()
            normalized = ImageOps.exif_transpose(image).convert("RGB")
            output = BytesIO()
            normalized.save(output, format="PNG")
            png_bytes = output.getvalue()
    finally:
        client.close()

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=".tmp", prefix="melodia_image_",
            dir=destination.parent, delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(png_bytes)
        os.replace(temporary_path, destination)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    print("MELODIA IMAGE GENERATION SUCCESSFUL:", destination)
    return destination


def main():
    try:
        generate_image(TEST_PROMPT, OUTPUT_DIR / "gemini_test.png")
    except Exception as exc:
        print("IMAGE GENERATION FAILED:", type(exc).__name__, str(exc))
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
