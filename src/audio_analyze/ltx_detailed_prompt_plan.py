from __future__ import annotations

from pathlib import Path
import argparse
import json

try:
    from .detailed_prompt_engine import compose_detailed_prompt
    from .ltx_holy_cheeks_pipeline import (
        analyze_audio,
        build_scenes,
        detect_beats,
        list_seed_images,
        normalize_resolution,
        seed_filename_hint,
        write_json,
    )
    from .asmo_engine.asmo_engine import generate_asmo_timeline
except ImportError:
    from detailed_prompt_engine import compose_detailed_prompt
    from ltx_holy_cheeks_pipeline import (
        analyze_audio,
        build_scenes,
        detect_beats,
        list_seed_images,
        normalize_resolution,
        seed_filename_hint,
        write_json,
    )
    from asmo_engine.asmo_engine import generate_asmo_timeline


DEFAULT_OUTPUT = "outputs/ltx_video_run/detailed_ltx_plan.json"
DEFAULT_SEED_DIR = "inputs/ltx_seed_images"


def read_json(path: str | Path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def resolve_scene_count(duration: float, scene_seconds: float, max_scenes: int | None, seed_count: int) -> int:
    if max_scenes is not None:
        return max(1, int(max_scenes))
    # General media-to-prompt pipeline default: cover the usable audio, not merely the number of seed images.
    # Seed images are reusable references; they should not cap scene count.
    estimated = int(max(1, -(-duration // max(float(scene_seconds), 0.001))))
    return max(estimated, min(seed_count, estimated))


def build_detailed_ltx_plan(
    audio: str | Path,
    seed_dir: str | Path = DEFAULT_SEED_DIR,
    output: str | Path = DEFAULT_OUTPUT,
    resolution: str = "9:16",
    max_scenes: int | None = None,
    scene_seconds: float = 8.0,
    start_offset_seconds: float = 0.0,
    beat_align: bool = False,
    style_profile: str = "generic_performance",
    lyric_path: str | Path | None = None,
    timeline_json: str | Path | None = None,
    timeline_output: str | Path | None = None,
) -> dict:
    audio_path = Path(audio)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path.resolve()}")

    images = list_seed_images(seed_dir)
    analysis = analyze_audio(audio_path)
    duration, tempo, beat_times = detect_beats(audio_path)

    start_offset_seconds = max(0.0, float(start_offset_seconds or 0.0))
    if start_offset_seconds >= duration:
        raise ValueError(f"Start offset {start_offset_seconds:.3f}s is beyond audio duration {duration:.3f}s")

    scene_count = resolve_scene_count(duration - start_offset_seconds, scene_seconds, max_scenes, len(images))
    scenes = build_scenes(
        duration,
        max_scenes=scene_count,
        scene_seconds=scene_seconds,
        start_offset_seconds=start_offset_seconds,
        beat_align=beat_align,
        beat_times=beat_times,
    )
    resolution = normalize_resolution(resolution)

    analysis["start_offset_seconds"] = round(start_offset_seconds, 3)
    analysis["beat_alignment_enabled"] = bool(beat_align)
    analysis["tempo_bpm_from_full_track"] = round(tempo, 3) if tempo else analysis.get("tempo_bpm")
    analysis["detected_beat_count"] = len(beat_times)
    analysis["sync_policy"] = "Scene starts and scene changes are snapped to detected beat positions." if beat_align else "Fixed scene intervals with all visible motion still locked to detected audio accents."
    analysis["detailed_prompt_engine_enabled"] = True
    analysis["style_profile"] = style_profile

    timeline = None
    if timeline_json:
        timeline = read_json(timeline_json)
    elif lyric_path:
        timeline = generate_asmo_timeline(lyric_path=lyric_path, audio_path=audio_path)
        if timeline_output:
            write_json(timeline_output, timeline)

    results = []
    for idx, scene in enumerate(scenes, start=1):
        image = images[(idx - 1) % len(images)]
        hint = seed_filename_hint(image)
        prompt = compose_detailed_prompt(
            file_stem=audio_path.stem,
            analysis=analysis,
            scene=scene,
            seed_image=image,
            seed_hint=hint,
            style_profile=style_profile,
            timeline=timeline,
        )
        results.append({
            "clip_index": idx,
            "file_stem": audio_path.stem,
            "source_audio_path": str(audio_path.resolve()),
            "seed_image_used": str(image.resolve()),
            "seed_filename_prompt_hint": hint,
            "scene": scene,
            "resolution": resolution,
            "prompt_text": prompt,
            "status": "planned",
            "audio_to_video_confirmed": True,
            "beat_alignment_enabled": bool(beat_align),
            "detailed_prompt_engine_enabled": True,
            "style_profile": style_profile,
        })

    plan = {
        "schema": "audio_analyze.detailed_ltx_plan.v1",
        "file_stem": audio_path.stem,
        "analysis": analysis,
        "scene_count": len(results),
        "seed_image_count": len(images),
        "scene_count_source": "audio_duration_scene_grid_with_reusable_seed_images" if max_scenes is None else "manual_max_scenes_with_reusable_seed_images",
        "resolution": resolution,
        "scene_seconds": scene_seconds,
        "start_offset_seconds": round(start_offset_seconds, 3),
        "beat_alignment_enabled": bool(beat_align),
        "audio_to_video_enabled": True,
        "audio_plus_seed_image_sent_to_ltx": True,
        "detailed_prompt_engine_enabled": True,
        "style_profile": style_profile,
        "lyrics_or_timeline_injected": bool(timeline),
        "results": results,
        "status": "planned",
    }
    write_json(output, plan)
    return plan


def main():
    parser = argparse.ArgumentParser(description="Build a general audio/image/lyrics-to-detailed-prompt LTX plan.")
    parser.add_argument("--audio", required=True)
    parser.add_argument("--seed-dir", default=DEFAULT_SEED_DIR)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--resolution", default="9:16")
    parser.add_argument("--max-scenes", type=int, default=None)
    parser.add_argument("--scene-seconds", type=float, default=8.0)
    parser.add_argument("--start-offset-seconds", type=float, default=0.0)
    parser.add_argument("--beat-align", action="store_true")
    parser.add_argument("--style-profile", default="generic_performance", choices=["generic_performance", "gospel_twerk"])
    parser.add_argument("--lyrics", default=None, help="Optional lyric/transcript file for ASMO semantic motion sync.")
    parser.add_argument("--timeline-json", default=None, help="Optional existing ASMO timeline JSON.")
    parser.add_argument("--timeline-output", default=None, help="Optional path to save generated ASMO timeline JSON.")
    args = parser.parse_args()

    plan = build_detailed_ltx_plan(
        audio=args.audio,
        seed_dir=args.seed_dir,
        output=args.output,
        resolution=args.resolution,
        max_scenes=args.max_scenes,
        scene_seconds=args.scene_seconds,
        start_offset_seconds=args.start_offset_seconds,
        beat_align=args.beat_align,
        style_profile=args.style_profile,
        lyric_path=args.lyrics,
        timeline_json=args.timeline_json,
        timeline_output=args.timeline_output,
    )
    print("Detailed LTX plan created.")
    print(Path(args.output).resolve())
    print(f"Scenes: {plan['scene_count']}")
    print(f"Seed images: {plan['seed_image_count']}")
    print(f"Style profile: {plan['style_profile']}")
    print(f"Lyrics/timeline injected: {plan['lyrics_or_timeline_injected']}")


if __name__ == "__main__":
    main()
