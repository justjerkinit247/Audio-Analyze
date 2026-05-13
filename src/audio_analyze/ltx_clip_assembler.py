from pathlib import Path
import argparse
import json
import re

from moviepy import VideoFileClip, AudioFileClip, ImageClip, concatenate_videoclips


SCENE_NUMBER_RE = re.compile(r"(?:scene[_-]?)(\d+)", re.IGNORECASE)
DEFAULT_TRIM_TAIL_SECONDS = 0.08
DEFAULT_TRANSITION_SECONDS = 0.0
DEFAULT_AUDIO_OFFSET_SECONDS = 0.0
DEFAULT_MIN_PAD_SECONDS = 0.01
DEFAULT_TIMING_SOURCE = "result-json"
DEFAULT_AUDIO_MODE = "scene-json"


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


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def collect_mp4s(downloads_dir):
    downloads_dir = Path(downloads_dir)
    if not downloads_dir.exists():
        raise FileNotFoundError(f"Downloads folder not found: {downloads_dir.resolve()}")
    clips = sorted(downloads_dir.glob("*.mp4"), key=natural_scene_key)
    if not clips:
        raise FileNotFoundError(f"No MP4 clips found in: {downloads_dir.resolve()}")
    return clips


def collect_result_jsons(results_dir):
    if not results_dir:
        return {}
    results_dir = Path(results_dir)
    if not results_dir.exists():
        return {}
    result_map = {}
    for path in sorted(results_dir.glob("scene_*_result.json"), key=natural_scene_key):
        scene_number = scene_number_from_path(path)
        if scene_number is None:
            continue
        try:
            result_map[scene_number] = read_json(path)
        except Exception:
            continue
    return result_map


def select_latest_scene_clips(clip_paths, expected_scenes=None, strict_scenes=False):
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


def load_plan(plan_json):
    if not plan_json:
        return None
    path = Path(plan_json)
    if not path.exists():
        return None
    return read_json(path)


def load_source_audio(plan_json):
    plan = load_plan(plan_json)
    if not plan:
        return None
    results = plan.get("results") or []
    if not results:
        return None
    audio_path = results[0].get("source_audio_path") or plan.get("source_audio_path")
    return Path(audio_path) if audio_path else None


def load_expected_scene_count(plan_json):
    plan = load_plan(plan_json)
    if not plan:
        return None
    if plan.get("scene_count"):
        return int(plan["scene_count"])
    results = plan.get("results") or []
    return len(results) or None


def plan_items_by_scene(plan_json):
    plan = load_plan(plan_json)
    if not plan:
        return {}
    items = {}
    for item in plan.get("results", []):
        clip_index = item.get("clip_index")
        if clip_index is not None:
            items[int(clip_index)] = item
    return items


def scene_duration_from_metadata(scene_number, plan_items, result_items, timing_source):
    result = result_items.get(scene_number) or {}
    plan_item = plan_items.get(scene_number) or {}

    if timing_source == "clip":
        return None, "clip"

    sources = []
    if timing_source in {"result-json", "auto"}:
        sources.append(("result-json", result))
        sources.append(("plan-json", plan_item))
    elif timing_source == "plan-json":
        sources.append(("plan-json", plan_item))
        sources.append(("result-json", result))
    else:
        raise ValueError(f"Unsupported timing source: {timing_source}")

    for source_name, item in sources:
        scene = item.get("scene") or {}
        for key in ("duration", "duration_seconds"):
            value = scene.get(key)
            if value is not None:
                try:
                    value = float(value)
                    if value > 0:
                        return value, source_name
                except Exception:
                    pass
        start = scene.get("start")
        end = scene.get("end")
        try:
            if start is not None and end is not None:
                duration = float(end) - float(start)
                if duration > 0:
                    return duration, source_name
        except Exception:
            pass
    return None, None


def scene_audio_from_result(scene_number, result_items):
    result = result_items.get(scene_number) or {}
    scene_audio = result.get("scene_audio_path")
    if scene_audio and Path(scene_audio).exists():
        return Path(scene_audio)
    return None


def trim_clip_tail(clip, trim_tail_seconds):
    trim_tail_seconds = max(0.0, float(trim_tail_seconds or 0.0))
    if trim_tail_seconds <= 0:
        return clip
    if clip.duration <= trim_tail_seconds + 0.25:
        return clip
    return clip.subclipped(0, clip.duration - trim_tail_seconds)


def pad_clip_to_duration(clip, target_duration, fps=24, min_pad_seconds=DEFAULT_MIN_PAD_SECONDS):
    if target_duration is None:
        return clip, 0.0
    target_duration = float(target_duration)
    if target_duration <= 0:
        return clip, 0.0
    current_duration = float(clip.duration)
    delta = target_duration - current_duration
    if abs(delta) < min_pad_seconds:
        return clip, 0.0
    if delta < 0:
        return clip.subclipped(0, target_duration), delta

    frame_time = max(0.0, current_duration - (1.0 / max(float(fps), 1.0)))
    last_frame = clip.get_frame(frame_time)
    hold = ImageClip(last_frame).with_duration(delta).with_fps(fps)
    padded = concatenate_videoclips([clip, hold], method="compose")
    return padded, delta


def attach_scene_audio(clip, scene_number, result_items, audio_mode):
    if audio_mode != "scene-json":
        return clip, None
    scene_audio = scene_audio_from_result(scene_number, result_items)
    if not scene_audio:
        return clip, None
    audio_clip = AudioFileClip(str(scene_audio))
    target_duration = min(float(clip.duration), float(audio_clip.duration))
    video = clip.subclipped(0, target_duration).with_audio(audio_clip.subclipped(0, target_duration))
    return video, audio_clip


def add_crossfades(clips, transition_seconds):
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
                    "Rerun with --transition-seconds 0. "
                    f"Original error: {exc}"
                )
    return faded, -transition_seconds


def apply_audio_offset(audio_full, final_duration, start_seconds, audio_offset_seconds):
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


def merge_clips(
    downloads_dir,
    output_path,
    plan_json=None,
    results_dir=None,
    audio_path=None,
    start_seconds=0.0,
    duration_seconds=None,
    fps=24,
    trim_tail_seconds=DEFAULT_TRIM_TAIL_SECONDS,
    transition_seconds=DEFAULT_TRANSITION_SECONDS,
    audio_offset_seconds=DEFAULT_AUDIO_OFFSET_SECONDS,
    expected_scenes=None,
    strict_scenes=False,
    report_json=None,
    timing_source=DEFAULT_TIMING_SOURCE,
    audio_mode=DEFAULT_AUDIO_MODE,
):
    all_clip_paths = collect_mp4s(downloads_dir)
    if expected_scenes is None:
        expected_scenes = load_expected_scene_count(plan_json)

    plan_items = plan_items_by_scene(plan_json)
    result_items = collect_result_jsons(results_dir or Path(downloads_dir).parent)

    selection = select_latest_scene_clips(all_clip_paths, expected_scenes=expected_scenes, strict_scenes=strict_scenes)
    clip_paths = selection["selected"]
    if not clip_paths:
        raise FileNotFoundError("No selected scene clips available after validation.")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    raw_clips = [VideoFileClip(str(path)) for path in clip_paths]
    processed_clips = []
    scene_audio_clips = []
    raw_clip_info = []

    for path, clip in zip(clip_paths, raw_clips):
        scene_number = scene_number_from_path(path)
        trimmed = trim_clip_tail(clip, trim_tail_seconds)
        target_duration, duration_source = scene_duration_from_metadata(
            scene_number,
            plan_items=plan_items,
            result_items=result_items,
            timing_source=timing_source,
        )
        normalized, pad_delta = pad_clip_to_duration(trimmed, target_duration, fps=fps)
        with_scene_audio, scene_audio_clip = attach_scene_audio(normalized, scene_number, result_items, audio_mode)
        if scene_audio_clip:
            scene_audio_clips.append(scene_audio_clip)
        processed_clips.append(with_scene_audio)
        raw_clip_info.append({
            "scene": scene_number,
            "path": str(path.resolve()),
            "raw_duration": round(float(clip.duration), 3),
            "trimmed_duration": round(float(trimmed.duration), 3),
            "target_duration": round(float(target_duration), 3) if target_duration is not None else None,
            "target_duration_source": duration_source,
            "duration_adjustment": round(float(pad_delta), 3),
            "final_scene_duration": round(float(with_scene_audio.duration), 3),
            "scene_audio_path": str(scene_audio_from_result(scene_number, result_items).resolve()) if scene_audio_from_result(scene_number, result_items) else None,
            "audio_mode": audio_mode,
        })

    video_clips, padding = add_crossfades(processed_clips, transition_seconds)
    final_video = concatenate_videoclips(video_clips, method="compose", padding=padding)

    audio_source = Path(audio_path) if audio_path else load_source_audio(plan_json)
    audio_full = None
    full_audio_clip = None

    if audio_mode == "full-bed" and audio_source and audio_source.exists():
        audio_full = AudioFileClip(str(audio_source))
        final_duration = duration_seconds if duration_seconds is not None else min(final_video.duration, audio_full.duration - max(start_seconds, 0.0))
        if final_duration <= 0:
            raise ValueError("Computed final audio duration is not valid.")
        full_audio_clip = apply_audio_offset(audio_full, final_duration, start_seconds, audio_offset_seconds)
        final_video = final_video.subclipped(0, min(final_video.duration, final_duration)).with_audio(full_audio_clip)
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
        "audio_mode": audio_mode,
        "timing_source": timing_source,
        "results_dir": str(Path(results_dir or Path(downloads_dir).parent).resolve()),
        "start_seconds": start_seconds,
        "audio_offset_seconds": audio_offset_seconds,
        "duration_seconds": duration_seconds,
        "trim_tail_seconds": trim_tail_seconds,
        "transition_seconds": transition_seconds,
        "transition_padding": padding,
        "final_video_duration": round(float(final_video.duration), 3) if final_video else None,
    }

    if report_json:
        write_json(report_json, info)

    for clip in raw_clips:
        clip.close()
    for clip in processed_clips:
        if clip not in raw_clips:
            try:
                clip.close()
            except Exception:
                pass
    for audio_clip in scene_audio_clips:
        try:
            audio_clip.close()
        except Exception:
            pass
    if full_audio_clip:
        full_audio_clip.close()
    if audio_full:
        audio_full.close()
    final_video.close()

    return info


def main():
    parser = argparse.ArgumentParser(description="Merge downloaded LTX scene clips into one MP4.")
    parser.add_argument("--downloads", default="outputs\\ltx_video_run\\downloads")
    parser.add_argument("--results-dir", default=None, help="Folder containing scene_XX_result.json files. Defaults to parent of downloads folder.")
    parser.add_argument("--output", default="outputs\\ltx_video_run\\assembled\\holy_cheeks_ltx_assembled.mp4")
    parser.add_argument("--plan-json", default="outputs\\ltx_video_run\\holy_cheeks_ltx_plan.json")
    parser.add_argument("--audio", default=None)
    parser.add_argument("--start-seconds", type=float, default=0.0)
    parser.add_argument("--audio-offset-seconds", type=float, default=DEFAULT_AUDIO_OFFSET_SECONDS)
    parser.add_argument("--duration-seconds", type=float, default=None)
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--trim-tail-seconds", type=float, default=DEFAULT_TRIM_TAIL_SECONDS)
    parser.add_argument("--transition-seconds", type=float, default=DEFAULT_TRANSITION_SECONDS)
    parser.add_argument("--expected-scenes", type=int, default=None)
    parser.add_argument("--strict-scenes", action="store_true")
    parser.add_argument("--report-json", default="outputs\\ltx_video_run\\assembled\\assembly_report.json")
    parser.add_argument("--timing-source", choices=["result-json", "plan-json", "clip", "auto"], default=DEFAULT_TIMING_SOURCE)
    parser.add_argument("--audio-mode", choices=["scene-json", "full-bed", "none"], default=DEFAULT_AUDIO_MODE)
    args = parser.parse_args()

    info = merge_clips(
        downloads_dir=args.downloads,
        results_dir=args.results_dir,
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
        timing_source=args.timing_source,
        audio_mode=args.audio_mode,
    )

    print("LTX clip assembly complete.")
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
