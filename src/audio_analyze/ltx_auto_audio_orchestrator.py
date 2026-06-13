from pathlib import Path
import argparse
import importlib


DEFAULT_AUDIO_DIR = "inputs/audio"


def _load_pipeline_module():
    return importlib.import_module(".ltx_holy_" + "cheeks_pipeline", __package__)


def _load_orchestrator_module():
    return importlib.import_module(".ltx_orchestrator", __package__)


def _load_path_policy_module():
    return importlib.import_module(".path_policy", __package__)


def find_newest_audio(audio_dir=DEFAULT_AUDIO_DIR):
    """Return the newest supported audio file in audio_dir."""
    pipeline = _load_pipeline_module()
    path_policy = _load_path_policy_module()
    audio_dir = path_policy.resolve_runtime_path(audio_dir)
    if not audio_dir.exists():
        raise FileNotFoundError(f"Audio folder not found: {audio_dir.resolve()}")
    if not audio_dir.is_dir():
        raise NotADirectoryError(f"Audio path is not a folder: {audio_dir.resolve()}")

    candidates = [
        path
        for path in audio_dir.iterdir()
        if path.is_file() and path.suffix.lower() in pipeline.ALLOWED_AUDIO
    ]
    if not candidates:
        allowed = ", ".join(sorted(pipeline.ALLOWED_AUDIO))
        raise FileNotFoundError(
            f"No supported audio files found in {audio_dir.resolve()}. Supported extensions: {allowed}"
        )

    return sorted(candidates, key=lambda path: (path.stat().st_mtime, path.name.lower()), reverse=True)[0]


def resolve_audio_argument(audio=None, audio_dir=DEFAULT_AUDIO_DIR):
    """Resolve an explicit audio path or auto-select the newest audio file."""
    path_policy = _load_path_policy_module()
    if audio and str(audio).strip():
        audio_path = path_policy.resolve_runtime_path(audio)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path.resolve()}")
        return audio_path, "explicit_audio"
    return find_newest_audio(audio_dir), "newest_audio_in_folder"


def run_auto_audio_orchestrator(
    audio=None,
    audio_dir=DEFAULT_AUDIO_DIR,
    seed_dir=None,
    output_plan=None,
    resolution="9:16",
    max_scenes=None,
    scene_seconds=None,
    model=None,
    guidance_scale=None,
    live=False,
    report_json=None,
    start_offset_seconds=0.0,
    beat_align=False,
    allow_sorted_seed_fallback=False,
    allow_duplicate_seed_reuse=False,
):
    pipeline = _load_pipeline_module()
    orchestrator = _load_orchestrator_module()
    path_policy = _load_path_policy_module()

    audio_path, audio_selection_method = resolve_audio_argument(audio, audio_dir=audio_dir)
    print(f"Auto audio selection method: {audio_selection_method}")
    print(f"Audio selected: {audio_path.resolve()}")

    result = orchestrator.orchestrate(
        audio=path_policy.serialize_path(audio_path),
        seed_dir=seed_dir or pipeline.DEFAULT_SEED_DIR,
        output_plan=output_plan or orchestrator.DEFAULT_PLAN_JSON,
        resolution=resolution,
        max_scenes=max_scenes,
        scene_seconds=scene_seconds if scene_seconds is not None else pipeline.DEFAULT_SCENE_SECONDS,
        model=model or pipeline.DEFAULT_MODEL,
        guidance_scale=guidance_scale if guidance_scale is not None else pipeline.DEFAULT_GUIDANCE_SCALE,
        live=live,
        report_json=report_json or orchestrator.DEFAULT_ORCHESTRATOR_REPORT_JSON,
        start_offset_seconds=start_offset_seconds,
        beat_align=beat_align,
        allow_sorted_seed_fallback=allow_sorted_seed_fallback,
        allow_duplicate_seed_reuse=allow_duplicate_seed_reuse,
    )
    result["audio_selection_method"] = audio_selection_method
    result["auto_selected_audio"] = path_policy.serialize_path(audio_path)
    result["auto_selected_audio_resolved"] = str(audio_path.resolve())
    return result


def main():
    pipeline = _load_pipeline_module()
    orchestrator = _load_orchestrator_module()

    parser = argparse.ArgumentParser(
        description="LTX orchestrator wrapper that auto-selects the newest audio file from inputs/audio when --audio is omitted."
    )
    parser.add_argument("--audio", default=None, help="Optional explicit audio path. If omitted, newest file in --audio-dir is used.")
    parser.add_argument("--audio-dir", default=DEFAULT_AUDIO_DIR)
    parser.add_argument("--seed-dir", default=pipeline.DEFAULT_SEED_DIR)
    parser.add_argument("--output-plan", default=orchestrator.DEFAULT_PLAN_JSON)
    parser.add_argument("--resolution", default="9:16")
    parser.add_argument("--max-scenes", type=int, default=None)
    parser.add_argument("--scene-seconds", type=float, default=pipeline.DEFAULT_SCENE_SECONDS)
    parser.add_argument("--start-offset-seconds", type=float, default=0.0)
    parser.add_argument("--beat-align", action="store_true")
    parser.add_argument("--model", default=pipeline.DEFAULT_MODEL)
    parser.add_argument("--guidance-scale", type=float, default=pipeline.DEFAULT_GUIDANCE_SCALE)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--allow-sorted-seed-fallback", action="store_true")
    parser.add_argument("--allow-duplicate-seed-reuse", action="store_true")
    parser.add_argument("--report-json", default=orchestrator.DEFAULT_ORCHESTRATOR_REPORT_JSON)
    args = parser.parse_args()

    run_auto_audio_orchestrator(
        audio=args.audio,
        audio_dir=args.audio_dir,
        seed_dir=args.seed_dir,
        output_plan=args.output_plan,
        resolution=args.resolution,
        max_scenes=args.max_scenes,
        scene_seconds=args.scene_seconds,
        model=args.model,
        guidance_scale=args.guidance_scale,
        live=args.live,
        report_json=args.report_json,
        start_offset_seconds=args.start_offset_seconds,
        beat_align=args.beat_align,
        allow_sorted_seed_fallback=args.allow_sorted_seed_fallback,
        allow_duplicate_seed_reuse=args.allow_duplicate_seed_reuse,
    )


if __name__ == "__main__":
    main()
