
# MELODIA AI - RENDER FFMPEG COMPATIBILITY TEST
# Tests -filter_complex_script on Render.
# Does not use Gemini or modify the video assembler.

import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def run_command(command):
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=90,
        check=False
    )

    print("Return code:", result.returncode, flush=True)

    if result.stdout:
        print("STDOUT:", result.stdout, flush=True)

    if result.stderr:
        print("STDERR:", result.stderr, flush=True)

    return result.returncode


def test_ffmpeg():
    print(
        "MELODIA AI - RENDER FFMPEG COMPATIBILITY TEST",
        flush=True
    )

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")

    print("FFmpeg executable:", ffmpeg, flush=True)
    print("FFprobe executable:", ffprobe, flush=True)

    if not ffmpeg:
        print("FAILED: FFmpeg not installed", flush=True)
        return False

    print("Checking FFmpeg version...", flush=True)

    if run_command([ffmpeg, "-version"]) != 0:
        return False

    with tempfile.TemporaryDirectory() as folder:
        folder = Path(folder)

        filter_file = folder / "filters.txt"
        output_file = folder / "melodia_test.mp4"

        filter_file.write_text(
            "[0:v]format=yuv420p[out]\n",
            encoding="utf-8"
        )

        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel", "error",
            "-nostdin",
            "-y",
            "-f", "lavfi",
            "-i", "color=c=blue:s=854x480:r=15:d=3",
            "-filter_complex_script", str(filter_file),
            "-map", "[out]",
            "-t", "3",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            str(output_file)
        ]

        print(
            "Testing -filter_complex_script...",
            flush=True
        )

        if run_command(command) != 0:
            print(
                "FAILED: Render rejected filter_complex_script",
                flush=True
            )
            return False

        if not output_file.is_file():
            print("FAILED: MP4 not created", flush=True)
            return False

        size = os.path.getsize(output_file)

        print("Generated MP4 size:", size, flush=True)

        if size <= 0:
            print("FAILED: MP4 is empty", flush=True)
            return False

        if ffprobe:
            probe_command = [
                ffprobe,
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1",
                str(output_file)
            ]

            if run_command(probe_command) != 0:
                print("FAILED: MP4 validation", flush=True)
                return False

        print(
            "PASSED: Render supports -filter_complex_script",
            flush=True
        )

        return True


if __name__ == "__main__":
    success = test_ffmpeg()
    raise SystemExit(0 if success else 1)
