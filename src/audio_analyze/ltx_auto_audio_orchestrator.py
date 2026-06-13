from pathlib import Path
import argparse
import importlib
import json


DEFAULT_AUDIO_DIR = "inputs/audio"
DEFAULT_STATE_ROOT = "outputs/ltx_video_run/_state"


def _load_pipeline_module():
    return importlib.import_module(".ltx_holy_" + "cheeks_pipeline", __package__)


def _load_orchestrator_module():
    return importlib.import_module(".ltx_orchestrator", __package__)


def _load_path_policy_module():
    return importlib.import_module(".path_policy", __package__)


def _load_plan_expander_module():
    return importlib.import_module(".ltx_plan_prompt_expander", __package__)


def _load_negative_memory_module():
    return importlib.import_module(".asmo_negative_prompt_memory", __package__)


def write_json(path, data):
    path_policy = _load_path_policy_module()
    path = path_policy.resolve_runtime_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


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
    filename_hint_provider="ollama",
    filename_hint_model="gemma3:4b",
    apply_asmo_negative_memory=True,
    state_root=DEFAULT_STATE_ROOT,
):
    pipeline = _load_pipeline_module()
    orchestrator = _load_orchestrator_module()
    path_policy = _load_path_policy_module()
    plan_expander = _load_plan_expander_module()

    selected_seed_dir = seed_dir or pipeline.DEFAULT_SEED_DIR
    selected_output_plan = output_plan or orchestrator.DEFAULT_PLAN_JSON
    selected_report_json = report_json or orchestrator.DEFAULT_ORCHESTRATOR_REPORT_JSON
    selected_scene_seconds = scene_seconds if scene_seconds is not None else pipeline.DEFAULT_SCENE_SECONDS
    selected_model = model or pipeline.DEFAULT_MODEL
    selected_guidance_scale = guidance_scale if guidance_scale is not None else pipeline.DEFAULT_GUIDANCE_SCALE

    audio_path, audio_selection_method = resolve_audio_argument(audio, audio_dir=audio_dir)
    print(f"Auto audio selection method: {audio_selection_method}")
    print(f"Audio selected: {audio_path.resolve()}")

    print("=" * 60)
    print("LTX AUTO-AUDIO ORCHESTRATOR START")
    print("=" * 60)

    print("[1/5] Building base plan...")
    plan = pipeline.build_plan(
        audio_path=path_policy.serialize_path(audio_path),
        seed_dir=selected_seed_dir,
        output_json=selected_output_plan,
        resolution=resolution,
        max_scenes=max_scenes,
        scene_seconds=selected_scene_seconds,
        start_offset_seconds=start_offset_seconds,
        beat_align=beat_align,
        allow_sorted_seed_fallback=allow_sorted_seed_fallback,
        allow_duplicate_seed_reuse=allow_duplicate_seed_reuse,
    )

    print("[2/5] Applying filename-hint prompt expansion...")
    plan = plan_expander.expand_plan_data(
        plan,
        provider=filename_hint_provider,
        model=filename_hint_model,
    )

    if apply_asmo_negative_memory:
        negative_memory = _load_negative_memory_module()
        plan = negative_memory.apply_negative_memory_to_plan_data(plan, state_root=state_root)
        plan["asmo_negative_memory_applied"] = True
    else:
        plan["asmo_negative_memory_applied"] = False

    plan["audio_selection_method"] = audio_selection_method
    plan["auto_selected_audio"] = path_policy.serialize_path(audio_path)
    plan["auto_selected_audio_resolved"] = str(audio_path.resolve())
    write_json(selected_output_plan, plan)
    print(f"Plan created: {path_policy.resolve_runtime_path(selected_output_plan).resolve()}")
    print(f"Scene count: {plan.get('scene_count')}")
    print(f"Filename-hint expansion: {plan.get('filename_hint_expansion')}")

    print("[3/5] Running preflight...")
    preflight = pipeline.run_preflight(
        selected_output_plan,
        orchestrator.DEFAULT_PREFLIGHT_JSON,
        allow_sorted_seed_fallback=allow_sorted_seed_fallback,
        allow_duplicate_seed_reuse=allow_duplicate_seed_reuse,
    )
    print(f"Preflight status: {preflight['status']}")

    submit_summary = None
    if preflight["status"] != "PASSED":
        print("Preflight failed. Refusing submit-all.")
        for problem in preflight.get("problems", []):
            print(f"PROBLEM: {problem}")
    else:
        print("[4/5] Running submit-all...")
        submit_summary = pipeline.submit_all(
            plan_json=selected_output_plan,
            output_dir=orchestrator.DEFAULT_SUBMIT_DIR,
            model=selected_model,
            guidance_scale=selected_guidance_scale,
            dry_run=not live,
            live=live,
            allow_sorted_seed_fallback=allow_sorted_seed_fallback,
            allow_duplicate_seed_reuse=allow_duplicate_seed_reuse,
        )

    print("[5/5] Writing orchestration manifests...")
    manifest_paths = orchestrator.write_orchestration_manifests(
        plan=plan,
        preflight=preflight,
        submit_summary=submit_summary,
        output_dir=orchestrator.DEFAULT_ORCHESTRATION_DIR,
        audio_path=path_policy.serialize_path(audio_path),
    )
    manifest_paths_resolved = {
        name: str(path_policy.resolve_runtime_path(path).resolve())
        for name, path in manifest_paths.items()
    }

    final_status = "complete" if preflight["status"] == "PASSED" else "failed_preflight"
    result = {
        "status": final_status,
        "live": live,
        "audio_selection_method": audio_selection_method,
        "auto_selected_audio": path_policy.serialize_path(audio_path),
        "auto_selected_audio_resolved": str(audio_path.resolve()),
        "filename_hint_expansion": plan.get("filename_hint_expansion"),
        "asmo_negative_memory_applied": plan.get("asmo_negative_memory_applied"),
        "plan_json": path_policy.serialize_path(selected_output_plan),
        "plan_json_resolved": str(path_policy.resolve_runtime_path(selected_output_plan).resolve()),
        "preflight_json": path_policy.serialize_path(orchestrator.DEFAULT_PREFLIGHT_JSON),
        "preflight_json_resolved": str(path_policy.resolve_runtime_path(orchestrator.DEFAULT_PREFLIGHT_JSON).resolve()),
        "submit_dir": path_policy.serialize_path(orchestrator.DEFAULT_SUBMIT_DIR),
        "submit_dir_resolved": str(path_policy.resolve_runtime_path(orchestrator.DEFAULT_SUBMIT_DIR).resolve()),
        "manifest_paths": manifest_paths,
        "manifest_paths_resolved": manifest_paths_resolved,
        "summary": submit_summary,
    }
    write_json(selected_report_json, result)

    print("=" * 60)
    print("LTX AUTO-AUDIO ORCHESTRATOR COMPLETE")
    print("=" * 60)
    print(f"Dry run: {not live}")
    print(f"Status: {final_status}")
    print(f"Final report: {path_policy.resolve_runtime_path(selected_report_json).resolve()}")
    return result


def main():
    pipeline = _load_pipeline_module()
    orchestrator = _load_orchestrator_module()

    parser = argparse.ArgumentParser(
        description="LTX orchestrator wrapper that auto-selects audio and applies filename-hint prompt expansion before submit."
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
    parser.add_argument("--filename-hint-provider", default="ollama", choices=["template", "openai", "ollama"])
    parser.add_argument("--filename-hint-model", default="gemma3:4b")
    parser.add_argument("--state-root", default=DEFAULT_STATE_ROOT)
    parser.add_argument("--no-asmo-negative-memory", action="store_true")
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
        filename_hint_provider=args.filename_hint_provider,
        filename_hint_model=args.filename_hint_model,
        apply_asmo_negative_memory=not args.no_asmo_negative_memory,
        state_root=args.state_root,
    )


if __name__ == "__main__":
    main()
