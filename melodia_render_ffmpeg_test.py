
import os
import shutil
import subprocess
import tempfile


def run_command(command):
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=60,
        check=False
    )

    print("Return code:", result.returncode, flush=True)

    if result.stdout:
        print("STDOUT:", result.stdout, flush=True)

    if result.stderr:
        print("STDERR:", result.stderr, flush=True)

    return result.returncode


def test_ffmpeg():
    print("MELODIA AI - RENDER FFMPEG DIAGNOSTIC", flush=True)

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")

    print("FFmpeg executable:", ffmpeg, flush=True)
    print("FFprobe executable:", ffprobe, flush=True)

    if not ffmpeg:
        print("FAILED: FFmpeg not installed", flush=True)
        return False

    print("Checking FFmpeg version...", flush=True)

    run_command([ffmpeg, "-version"])

    with tempfile.TemporaryDirectory() as folder:
        filter_file = os.path.join(folder, "filters.txt")
        output_file = os.path.join(folder, "test.mp4")

        with open(filter_file, "w", encoding="utf-8") as file:
            file.write("[0:v]format=yuv420p[out]\n")

        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel", "error",
            "-nostdin",
            "-f", "lavfi",
            "-i", "color=c=blue:s=854x480:r=15:d=3",
            "-/filter_complex", filter_file,
            "-map", "[out]",
            "-t", "3",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            "-y", output_file
        ]

        print("Testing filter-file compatibility...", flush=True)

        return_code = run_command(command)

        if return_code != 0:
            print("FAILED: Filter-file test", flush=True)
            return False

        if not os.path.isfile(output_file):
            print("FAILED: MP4 not created", flush=True)
            return False

        size = os.path.getsize(output_file)

        print("Generated MP4 size:", size, "bytes", flush=True)

        if size == 0:
            print("FAILED: Empty MP4", flush=True)
            return False

        print("PASSED: Render FFmpeg compatibility", flush=True)
        return True


if __name__ == "__main__":
    success = test_ffmpeg()
    raise SystemExit(0 if success else 1)
