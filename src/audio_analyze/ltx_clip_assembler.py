from pathlib import Path
import argparse
import json
import re

from moviepy import VideoFileClip, AudioFileClip, concatenate_videoclips


SCENE_NUMBER_RE = re.compile(r"(?:scene[_-]?)(\d+)", re.IGNORECASE)
DEFAULT_TRIM_TAIL_SECONDS = 0.08
DEFAULT_TRANSITION_SECONDS = 0.0


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


def trim_clip_tail(clip, trim_tail_seconds):
    trim_tail_seconds = max(0.0, float(trim_tail_seconds or 0.0))
    if trim_tail_seconds <= 0:
        return clip
    if clip.duration <= trim_tail_seconds + 0.25:
        return clip
    return clip.subclipped(0, clip.duration - trim_tail_seconds)


def add_crossfades(clips, transition_seconds):
    """
    Add soft visual crossfades when the installed MoviePy version supports them.

    The assembler remains safe if crossfade support is unavailable: it raises a clear
    error instead of silently producing an unexpected edit. Use --transition-seconds 0
    for hard cuts with tail trimming only.
    """
    transition_seconds = max(0.0, float(transition_seconds or 0.0))
    if transition_seconds <= 0 or len(clips) <= 1:
        return clips, 0.0

    faded = [clips[0]]
    for clip in clips[1:]:
        if hasattr(clip, "crossfadein"):
            faded.append(clip.crossfadein(transition_seconds))
        else:
            try:
                from moviepy.video.fx.CrossFadeIn import CrossFadeIn
                faded.append(clip.with_effects([CrossFadeIn(transition_seconds)]))
            except Exception as exc:
                raise RuntimeError(
                    "This MoviePy install does not expose crossfade support. "
                    "Rerun with --transition-seconds 0 and use --trim-tail-seconds 0.08 for cleanup. "
                    f"Original error: {exc}"
                )
    return faded, -transition_seconds


def merge_clips(downloads_dir, output_path, plan_json=None, audio_path=None, start_seconds=0.0, duration_seconds=None, fps=24, trim_tail_seconds=DEFAULT_TRIM_TAIL_SECONDS, transition_seconds=DEFAULT_TRANSITION_SECONDS):
    clip_paths = collect_mp4s(downloads_dir)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    raw_clips = [VideoFileClip(str(path)) for path in clip_paths]
    video_clips = [trim_clip_tail(clip, trim_tail_seconds) for clip in raw_clips]
    video_clips, padding = add_crossfades(video_clips, transition_seconds)
    final_video = concatenate_videoclips(video_clips, method="compose", padding=padding)

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
        "trim_tail_seconds": trim_tail_seconds,
        "transition_seconds": transition_seconds,
        "transition_padding": padding,
        "final_video_duration": round(float(final_video.duration), 3) if final_video else None,
    }

    for clip in raw_clips:
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
    parser.add_argument("--trim-tail-seconds", type=float, default=DEFAULT_TRIM_TAIL_SECONDS, help="Trim this much from the end of each clip before assembly to remove damaged terminal frames.")
    parser.add_argument("--transition-seconds", type=float, default=DEFAULT_TRANSITION_SECONDS, help="Optional visual crossfade duration between clips. Use 0 for hard cuts.")
    args = parser.parse_args()

    info = merge_clips(
        downloads_dir=args.downloads,
        output_path=args.output,
        plan_json=args.plan_json,
        audio_path=args.audio,
        start_seconds=args.start_seconds,
        duration_seconds=args.duration_seconds,
        fps=args.fps,
        trim_tail_seconds=args.trim_tail_seconds,
        transition_seconds=args.transition_seconds,
    )

    print("LTX clip assembly complete.")
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
