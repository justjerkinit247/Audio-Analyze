import subprocess
from pathlib import Path
import json


def stitch_clips_with_audio(clips_dir, audio_path, output_path="final_output.mp4"):
    clips_dir = Path(clips_dir)
    audio_path = Path(audio_path)

    clip_files = sorted(clips_dir.glob("*.mp4"))

    if not clip_files:
        raise ValueError("No clips found to stitch.")

    concat_file = clips_dir / "concat_list.txt"

    with open(concat_file, "w") as f:
        for clip in clip_files:
            f.write(f"file '{clip.resolve()}'\n")

    temp_output = clips_dir / "temp_video.mp4"

    # Step 1: Concatenate clips
    subprocess.run([
        "ffmpeg",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-c", "copy",
        str(temp_output)
    ], check=True)

    final_output = clips_dir / output_path

    # Step 2: Add audio and sync
    subprocess.run([
        "ffmpeg",
        "-i", str(temp_output),
        "-i", str(audio_path),
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        str(final_output)
    ], check=True)

    return str(final_output)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--clips-dir", required=True)
    parser.add_argument("--audio", required=True)

    args = parser.parse_args()

    output = stitch_clips_with_audio(args.clips_dir, args.audio)

    print("FINAL VIDEO CREATED:")
    print(output)
