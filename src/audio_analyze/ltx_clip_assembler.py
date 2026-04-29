from pathlib import Path
import argparse
import json
import re

from moviepy import VideoFileClip, AudioFileClip, concatenate_videoclips


SCENE_NUMBER_RE = re.compile(r"(?:scene[_-]?)(\d+)", re.IGNORECASE)


def natural_scene_key(path):
    match = SCENE_NUMBER_RE.search(path.stem)
    if match:
        return int(match.group(1)), path.name.lower()
    return 9999, path.name.lower()


def collect_mp4s(downloads_dir):
    downloads_dir = Path(downloads_dir)
    if not downloads_dir.exists():
        raise FileNotFoundError(f"Downloads folder not found: {downloads_dir.resolve()}")
    clips = sorted(downloads_dir.glob("*.mp4"), key=natural_scene_key)
    if not clips:
        raise FileNotFoundError(f"No MP4 clips found in: {downloads_dir.resolve()}")
    return clips


def load_source_audio(plan_json):
    if not plan_json:
        return None
    data = json.loads(Path(plan_json).read_text(encoding="utf-8-sig"))
    results = data.get("results") or []
    if not results:
        return None
    audio_path = results[0].get("source_audio_path")
    return Path(audio_path) if audio_path else None


def merge_clips(downloads_dir, output_path, plan_json=None, audio_path=None, start_seconds=0.0, duration_seconds=None, fps=24):
    clip_paths = collect_mp4s(downloads_dir)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    video_clips = [VideoFileClip(str(path)) for path in clip_paths]
    final_video = concatenate_videoclips(video_clips, method="compose")

    audio_source = Path(audio_path) if audio_path else load_source_audio(plan_json)
    audio_full = None
    audio_clip = None

    if audio_source and audio_source.exists():
        audio_full = AudioFileClip(str(audio_source))
        final_duration = duration_seconds if duration_seconds is not None else min(final_video.duration, audio_full.duration - start_seconds)
        if final_duration <= 0:
            raise ValueError("Computed final audio duration is not valid.")
        audio_clip = audio_full.subclipped(start_seconds, start_seconds + final_duration)
        final_video = final_video.subclipped(0, min(final_video.duration, final_duration)).with_audio(audio_clip)
    elif duration_seconds is not None:
        final_video = final_video.subclipped(0, min(final_video.duration, duration_seconds))

    final_video.write_videofile(
        str(output_path),
        codec="libx264",
        audio_codec="aac",
        fps=fps,
        preset="veryfast",
    )

    info = {
        "status": "complete",
        "output_path": str(output_path.resolve()),
        "clip_count": len(clip_paths),
        "clips": [str(path.resolve()) for path in clip_paths],
        "audio_source": str(audio_source.resolve()) if audio_source and audio_source.exists() else None,
        "start_seconds": start_seconds,
        "duration_seconds": duration_seconds,
    }

    for clip in video_clips:
        clip.close()
    if audio_clip:
        audio_clip.close()
    if audio_full:
        audio_full.close()
    final_video.close()

    return info


def main():
    parser = argparse.ArgumentParser(description="Merge downloaded LTX scene clips into one MP4.")
    parser.add_argument("--downloads", default="outputs\\ltx_video_run\\downloads")
    parser.add_argument("--output", default="outputs\\ltx_video_run\\assembled\\holy_cheeks_ltx_assembled.mp4")
    parser.add_argument("--plan-json", default="outputs\\ltx_video_run\\holy_cheeks_ltx_plan.json")
    parser.add_argument("--audio", default=None)
    parser.add_argument("--start-seconds", type=float, default=0.0)
    parser.add_argument("--duration-seconds", type=float, default=None)
    parser.add_argument("--fps", type=int, default=24)
    args = parser.parse_args()

    info = merge_clips(
        downloads_dir=args.downloads,
        output_path=args.output,
        plan_json=args.plan_json,
        audio_path=args.audio,
        start_seconds=args.start_seconds,
        duration_seconds=args.duration_seconds,
        fps=args.fps,
    )

    print("LTX clip assembly complete.")
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
