
# MELODIA AI - MULTILINGUAL CAPTION GENERATOR
# Step 1154
# Supports primary-language and bilingual captions.
# Preserves previously generated caption files.
# Existing video generation components remain unchanged.

import json
import os
import re
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PLANS = ROOT / "scene_plans"
CONTENT = ROOT / "generated_content"

CONTENT.mkdir(parents=True, exist_ok=True)

API_BASE = (
    "https://generativelanguage.googleapis.com/"
    "v1beta/models"
)

MODEL = os.getenv(
    "MELODIA_GEMINI_MODEL",
    "gemini-3.8-flash"
)

LANGUAGES = (
    "English",
    "Tamil",
    "Hindi",
    "Malayalam",
    "Telugu"
)

CAPTION_MODES = (
    "single",
    "bilingual",
    "none"
)


def validate_job_id(job_id):
    if not isinstance(job_id, str):
        raise ValueError("Invalid job ID")

    if not re.fullmatch(
        r"[A-Za-z0-9_-]+",
        job_id
    ):
        raise ValueError("Invalid job ID")

    return job_id


def call_gemini(prompt):
    key = os.getenv("GEMINI_API_KEY")

    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY is not configured"
        )

    url = f"{API_BASE}/{MODEL}:generateContent"

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.6,
            "responseMimeType": "application/json"
        }
    }

    request = urllib.request.Request(
        url,
        data=json.dumps(
            payload
        ).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": key
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=90
        ) as response:
            data = json.loads(
                response.read().decode("utf-8")
            )

    except urllib.error.HTTPError as error:
        details = error.read().decode(
            "utf-8",
            errors="replace"
        )

        raise RuntimeError(
            f"Gemini API HTTP {error.code}: "
            f"{details[:1000]}"
        ) from None

    except urllib.error.URLError as error:
        raise RuntimeError(
            "Gemini connection failed: "
            + str(error.reason)
        ) from None

    candidates = data.get("candidates", [])

    if not candidates:
        raise RuntimeError(
            "Gemini returned no candidates"
        )

    parts = (
        candidates[0]
        .get("content", {})
        .get("parts", [])
    )

    text = "".join(
        str(part.get("text", ""))
        for part in parts
    )

    if not text.strip():
        raise RuntimeError(
            "Gemini returned empty content"
        )

    try:
        return json.loads(text)

    except json.JSONDecodeError:
        raise RuntimeError(
            "Gemini returned invalid JSON"
        ) from None


def get_caption_settings(plan):
    scenes = plan.get("scenes", [])

    if not scenes:
        raise ValueError(
            "Scene plan contains no scenes"
        )

    first = scenes[0]

    primary = first.get(
        "primary_language",
        "English"
    )

    mode = first.get(
        "caption_mode",
        "single"
    )

    second = first.get(
        "second_language"
    )

    if primary not in LANGUAGES:
        raise ValueError(
            "Unsupported primary language: "
            + str(primary)
        )

    if mode not in CAPTION_MODES:
        raise ValueError(
            "Unsupported caption mode: "
            + str(mode)
        )

    if mode == "bilingual":
        if second not in LANGUAGES:
            raise ValueError(
                "Invalid secondary language"
            )

        if second == primary:
            raise ValueError(
                "Primary and secondary languages "
                "must be different"
            )
    else:
        second = None

    for scene in scenes:
        if scene.get(
            "primary_language",
            "English"
        ) != primary:
            raise ValueError(
                "Inconsistent primary languages"
            )

        if scene.get(
            "caption_mode",
            "single"
        ) != mode:
            raise ValueError(
                "Inconsistent caption modes"
            )

        if mode == "bilingual":
            if scene.get(
                "second_language"
            ) != second:
                raise ValueError(
                    "Inconsistent secondary languages"
                )

    return primary, mode, second


def existing_captions_match(
    data,
    scenes,
    primary,
    mode,
    second
):
    if not isinstance(data, dict):
        return False

    if data.get("caption_mode") != mode:
        return False

    if data.get("primary_language") != primary:
        return False

    if data.get("second_language") != second:
        return False

    records = data.get("records")

    if not isinstance(records, list):
        return False

    if len(records) != len(scenes):
        return False

    for index, (record, scene) in enumerate(
        zip(records, scenes),
        start=1
    ):
        if not isinstance(record, dict):
            return False

        if record.get("scene_number") != index:
            return False

        try:
            start = float(
                record["start_seconds"]
            )
            end = float(
                record["end_seconds"]
            )

            expected_start = float(
                scene["start_seconds"]
            )
            expected_end = float(
                scene["end_seconds"]
            )
        except (KeyError, TypeError, ValueError):
            return False

        if abs(start - expected_start) > 0.01:
            return False

        if abs(end - expected_end) > 0.01:
            return False

        if mode != "none":
            if not str(
                record.get("primary", "")
            ).strip():
                return False

        if mode == "bilingual":
            if not str(
                record.get("translated", "")
            ).strip():
                return False

    return True


def save_json_atomic(destination, data):
    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".tmp",
            prefix="melodia_captions_",
            dir=CONTENT,
            delete=False
        ) as file:
            temporary_path = Path(file.name)

            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2
            )

        os.replace(
            temporary_path,
            destination
        )

    finally:
        if (
            temporary_path is not None
            and temporary_path.exists()
        ):
            temporary_path.unlink()


def generate_multilingual_captions(
    job_id,
    second_language=None
):
    validate_job_id(job_id)

    manifest = (
        PLANS /
        f"{job_id}_scenes.json"
    )

    if not manifest.is_file():
        raise FileNotFoundError(
            "Scene plan missing: "
            + str(manifest)
        )

    plan = json.loads(
        manifest.read_text(
            encoding="utf-8"
        )
    )

    if plan.get("job_id") != job_id:
        raise ValueError(
            "Scene plan job ID mismatch"
        )

    scenes = plan.get("scenes", [])

    primary, mode, configured_second = (
        get_caption_settings(plan)
    )

    # The scene plan is authoritative.
    # The optional argument is retained for compatibility.
    if (
        second_language is not None
        and mode == "bilingual"
        and second_language != configured_second
    ):
        raise ValueError(
            "Requested second language differs "
            "from the saved scene plan"
        )

    second = configured_second

    destination = (
        CONTENT /
        f"{job_id}_captions.json"
    )

    if destination.is_file():
        try:
            previous = json.loads(
                destination.read_text(
                    encoding="utf-8"
                )
            )

            if existing_captions_match(
                previous,
                scenes,
                primary,
                mode,
                second
            ):
                print(
                    "Reusing existing caption file:",
                    destination
                )
                return destination

        except (OSError, ValueError):
            pass

        # Never silently overwrite earlier captions.
        raise RuntimeError(
            "An existing caption file has different "
            "settings or format. Preserve or migrate "
            "it before generating a replacement: "
            + str(destination)
        )

    records = []

    if mode == "none":
        for index, scene in enumerate(
            scenes,
            start=1
        ):
            records.append({
                "scene_number": index,
                "start_seconds": float(
                    scene["start_seconds"]
                ),
                "end_seconds": float(
                    scene["end_seconds"]
                ),
                "primary": "",
                "english": "",
                "translated": ""
            })

    else:
        descriptions = []

        for index, scene in enumerate(
            scenes,
            start=1
        ):
            descriptions.append({
                "scene_number": index,
                "start_seconds": scene[
                    "start_seconds"
                ],
                "end_seconds": scene[
                    "end_seconds"
                ],
                "visual_description": (
                    scene.get("visual_prompt")
                    or scene.get("description")
                    or ""
                )
            })

        user_prompt = (
            plan.get("video_prompt")
            or plan.get("prompt")
            or plan.get("user_prompt")
            or ""
        )

        second_instruction = (
            "Also translate each primary caption "
            f"accurately into {second}."
            if mode == "bilingual"
            else "Do not create a translation."
        )

        instruction = f"""
You are the multilingual scriptwriter for MELODIA AI.

Create meaningful on-screen captions for a video.

Original user request:
{user_prompt}

Primary caption language:
{primary}

Caption mode:
{mode}

{second_instruction}

Scene descriptions:
{json.dumps(descriptions, ensure_ascii=False)}

Requirements:
1. Write original, natural captions in {primary}.
2. Respect the original video's subject and tone.
3. Keep each caption concise and readable.
4. Preserve scene order and scene numbers.
5. Return exactly {len(scenes)} records.
6. Do not invent unrelated events or facts.
7. Do not copy technical image instructions.
8. For bilingual mode, provide accurate translations.
9. For single mode, use an empty translated field.
10. Use the requested languages, not transliteration.

Return JSON in this structure:

{{
  "captions": [
    {{
      "scene_number": 1,
      "primary": "Primary-language caption",
      "translated": "Secondary-language caption or empty string"
    }}
  ]
}}
"""

        response = call_gemini(instruction)

        captions = response.get(
            "captions", []
        )

        if (
            not isinstance(captions, list)
            or len(captions) != len(scenes)
        ):
            raise RuntimeError(
                "Gemini returned an incorrect "
                "number of captions"
            )

        for index, scene in enumerate(
            scenes,
            start=1
        ):
            caption = captions[index - 1]

            if not isinstance(caption, dict):
                raise RuntimeError(
                    "Invalid caption record"
                )

            if caption.get(
                "scene_number"
            ) != index:
                raise RuntimeError(
                    "Caption scene order mismatch"
                )

            primary_text = str(
                caption.get("primary", "")
            ).strip()

            translated = str(
                caption.get("translated", "")
            ).strip()

            if not primary_text:
                raise RuntimeError(
                    "Missing primary caption for scene "
                    + str(index)
                )

            if mode == "bilingual" and not translated:
                raise RuntimeError(
                    "Missing translation for scene "
                    + str(index)
                )

            if mode == "single":
                translated = ""

            records.append({
                "scene_number": index,
                "start_seconds": float(
                    scene["start_seconds"]
                ),
                "end_seconds": float(
                    scene["end_seconds"]
                ),
                "primary": primary_text,
                "english": (
                    primary_text
                    if primary == "English"
                    else ""
                ),
                "translated": translated,
                "second_language": second,
                "translation_status": (
                    "generated"
                    if mode == "bilingual"
                    else "not_required"
                )
            })

    result = {
        "job_id": job_id,
        "provider": (
            "gemini"
            if mode != "none"
            else "none"
        ),
        "model": (
            MODEL
            if mode != "none"
            else None
        ),
        "primary_language": primary,
        "second_language": second,
        "caption_mode": mode,
        "scene_count": len(records),
        "records": records
    }

    save_json_atomic(
        destination,
        result
    )

    print(
        "MELODIA AI - CAPTION GENERATION COMPLETE"
    )
    print("Job:", job_id)
    print("Primary language:", primary)
    print("Caption mode:", mode)
    print("Second language:", second)
    print("Scenes:", len(records))
    print("Saved:", destination)

    return destination


def main():
    print(
        "MELODIA AI - MULTILINGUAL GENERATOR"
    )
    print(
        "This module is called by the video pipeline."
    )
    print(
        "No API request was made."
    )


if __name__ == "__main__":
    main()
