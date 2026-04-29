from pathlib import Path
import argparse
import json
import re

from moviepy import VideoFileClip, AudioFileClip, concatenate_videoclips


SCENE_NUMBER_RE = re.compile(r"(?:scene[_-]?)(\d+)", re.IGNORECASE)
DEFAULT_TRIM_TAIL_SECONDS = 0.08
DEFAULT_TRANSITION_SECONDS = 0.0
DEFAULT_AUDIO_OFFSET_SECONDS = 0.0


def scene_number_from_path(path):
    match = SCENE_NUMBER_RE.search(Path(path).stem)
    if match:
        return int(match.group(1))
    return None


def safe_mtime(path):
    try:
        return Path(path).stat().st_mtime
    except FileNotFoundError:
        return 0.0


def natural_scene_key(path):
    path = Path(path)
    scene_number = scene_number_from_path(path)
    if scene_number is not None:
        return scene_number, safe_mtime(path), path.name.lower()
    return 9999, safe_mtime(path), path.name.lower()


def collect_mp4s(downloads_dir):
    downloads_dir = Path(downloads_dir)
    if not downloads_dir.exists():
        raise FileNotFoundError(f"Downloads folder not found: {downloads_dir.resolve()}")
    clips = sorted(downloads_dir.glob("*.mp4"), key=natural_scene_key)
    if not clips:
        raise FileNotFoundError(f"No MP4 clips found in: {downloads_dir.resolve()}")
    return clips


def select_latest_scene_clips(clip_paths, expected_scenes=None, strict_scenes=False):
    """
    Select exactly one clip per scene number.

    If duplicates exist, choose the newest file for that scene. This prevents old failed
    or earlier-generation clips from silently entering the assembly.
    """
    by_scene = {}
    unnumbered = []

    for path in clip_paths:
        scene_number = scene_number_from_path(path)
        if scene_number is None:
            unnumbered.append(path)
            continue
        by_scene.setdefault(scene_number, []).append(path)

    duplicate_scenes = {
        scene: sorted(paths, key=lambda p: safe_mtime(p), reverse=True)
        for scene, paths in by_scene.items()
        if len(paths) > 1
    }

    selected = []
    duplicate_notes = []
    for scene in sorted(by_scene):
        newest = sorted(by_scene[scene], key=lambda p: safe_mtime(p), reverse=True)[0]
        selected.append(newest)
        if scene in duplicate_scenes:
            duplicate_notes.append({
                "scene": scene,
                "selected": str(newest.resolve()),
                "ignored": [str(p.resolve()) for p in duplicate_scenes[scene][1:]],
            })

    expected = list(range(1, expected_scenes + 1)) if expected_scenes else sorted(by_scene)
    present = sorted(by_scene)
    missing = [scene for scene in expected if scene not in by_scene]
    extra = [scene for scene in present if expected_scenes and scene not in expected]

    if strict_scenes and missing:
        raise RuntimeError(f"Missing expected scene clips: {missing}")

    selected = [path for path in selected if not expected_scenes or scene_number_from_path(path) in expected]
    selected = sorted(selected, key=lambda p: (scene_number_from_path(p) or 9999, p.name.lower()))

    return {
        "selected": selected,
        "missing_scenes": missing,
        "extra_scenes": extra,
        "duplicate_notes": duplicate_notes,
        "unnumbered": [str(p.resolve()) for p in unnumbered],
    }


def load_source_audio(plan_json):
    if not plan_json:
        return None
    data = json.loads(Path(plan_json).read_text(encoding="utf-8-sig"))
    results = data.get("results") or []
    if not results:
        return None
    audio_path = results[0].get("source_audio_path")
    return Path(audio_path) if audio_path else None


def load_expected_scene_count(plan_json):
    if not plan_json:
        return None
    data = json.loads(Path(plan_json).read_text(encoding="utf-8-sig"))
    if data.get("scene_count"):
        return int(data["scene_count"])
    results = data.get("results") or []
    return len(results) or None


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


def apply_audio_offset(audio_full, final_duration, start_seconds, audio_offset_seconds):
    """
    Apply audio sync offset.

    Positive offset delays the song under the video by adding silence before the audio.
    Negative offset starts the song later by skipping ahead in the source audio.
    """
    audio_offset_seconds = float(audio_offset_seconds or 0.0)
    start_seconds = float(start_seconds or 0.0)

    if audio_offset_seconds >= 0:
        source_start = start_seconds
        source_duration = max(0.0, final_duration - audio_offset_seconds)
        if source_duration <= 0:
            raise ValueError("Audio offset is longer than the final video duration.")
        audio_clip = audio_full.subclipped(source_start, source_start + source_duration)
        if audio_offset_seconds > 0:
            try:
                audio_clip = audio_clip.with_start(audio_offset_seconds)
            except AttributeError:
                audio_clip = audio_clip.set_start(audio_offset_seconds)
        return audio_clip

    source_start = start_seconds + abs(audio_offset_seconds)
    return audio_full.subclipped(source_start, source_start + final_duration)


def merge_clips(downloads_dir, output_path, plan_json=None, audio_path=None, start_seconds=0.0, duration_seconds=None, fps=24, trim_tail_seconds=DEFAULT_TRIM_TAIL_SECONDS, transition_seconds=DEFAULT_TRANSITION_SECONDS, audio_offset_seconds=DEFAULT_AUDIO_OFFSET_SECONDS, expected_scenes=None, strict_scenes=False, report_json=None):
    all_clip_paths = collect_mp4s(downloads_dir)
    if expected_scenes is None:
        expected_scenes = load_expected_scene_count(plan_json)
    selection = select_latest_scene_clips(all_clip_paths, expected_scenes=expected_scenes, strict_scenes=strict_scenes)
    clip_paths = selection["selected"]
    if not clip_paths:
        raise FileNotFoundError("No selected scene clips available after validation.")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    raw_clips = [VideoFileClip(str(path)) for path in clip_paths]
    raw_clip_info = [
        {
            "scene": scene_number_from_path(path),
            "path": str(path.resolve()),
            "raw_duration": round(float(clip.duration), 3),
            "trimmed_duration": round(float(trim_clip_tail(clip, trim_tail_seconds).duration), 3),
        }
        for path, clip in zip(clip_paths, raw_clips)
    ]
    video_clips = [trim_clip_tail(clip, trim_tail_seconds) for clip in raw_clips]
    video_clips, padding = add_crossfades(video_clips, transition_seconds)
    final_video = concatenate_videoclips(video_clips, method="compose", padding=padding)

    audio_source = Path(audio_path) if audio_path else load_source_audio(plan_json)
    audio_full = None
    audio_clip = None

    if audio_source and audio_source.exists():
        audio_full = AudioFileClip(str(audio_source))
        final_duration = duration_seconds if duration_seconds is not None else min(final_video.duration, audio_full.duration - max(start_seconds, 0.0))
        if final_duration <= 0:
            raise ValueError("Computed final audio duration is not valid.")
        audio_clip = apply_audio_offset(audio_full, final_duration, start_seconds, audio_offset_seconds)
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
        "expected_scenes": expected_scenes,
        "missing_scenes": selection["missing_scenes"],
        "extra_scenes": selection["extra_scenes"],
        "duplicate_notes": selection["duplicate_notes"],
        "unnumbered_clips": selection["unnumbered"],
        "clips": [str(path.resolve()) for path in clip_paths],
        "clip_info": raw_clip_info,
        "audio_source": str(audio_source.resolve()) if audio_source and audio_source.exists() else None,
        "start_seconds": start_seconds,
        "audio_offset_seconds": audio_offset_seconds,
        "duration_seconds": duration_seconds,
        "trim_tail_seconds": trim_tail_seconds,
        "transition_seconds": transition_seconds,
        "transition_padding": padding,
        "final_video_duration": round(float(final_video.duration), 3) if final_video else None,
    }

    if report_json:
        report_path = Path(report_json)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(info, indent=2), encoding="utf-8")

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
    parser.add_argument("--audio-offset-seconds", type=float, default=DEFAULT_AUDIO_OFFSET_SECONDS, help="Positive delays audio under video; negative starts audio later.")
    parser.add_argument("--duration-seconds", type=float, default=None)
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--trim-tail-seconds", type=float, default=DEFAULT_TRIM_TAIL_SECONDS, help="Trim this much from the end of each clip before assembly to remove damaged terminal frames.")
    parser.add_argument("--transition-seconds", type=float, default=DEFAULT_TRANSITION_SECONDS, help="Optional visual crossfade duration between clips. Use 0 for hard cuts.")
    parser.add_argument("--expected-scenes", type=int, default=None, help="Expected number of scene clips. Defaults to scene_count from the plan JSON.")
    parser.add_argument("--strict-scenes", action="store_true", help="Fail if any expected scene clip is missing.")
    parser.add_argument("--report-json", default="outputs\\ltx_video_run\\assembled\\assembly_report.json")
    args = parser.parse_args()

    info = merge_clips(
        downloads_dir=args.downloads,
        output_path=args.output,
        plan_json=args.plan_json,
        audio_path=args.audio,
        start_seconds=args.start_seconds,
        audio_offset_seconds=args.audio_offset_seconds,
        duration_seconds=args.duration_seconds,
        fps=args.fps,
        trim_tail_seconds=args.trim_tail_seconds,
        transition_seconds=args.transition_seconds,
        expected_scenes=args.expected_scenes,
        strict_scenes=args.strict_scenes,
        report_json=args.report_json,
    )

    print("LTX clip assembly complete.")
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
