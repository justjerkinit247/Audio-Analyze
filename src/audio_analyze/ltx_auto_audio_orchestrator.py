from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse
import importlib
import json
import re
import secrets


DEFAULT_AUDIO_DIR = "inputs/audio"
DEFAULT_STATE_ROOT = "outputs/ltx_video_run/_state"
DEFAULT_RUNS_ROOT = "outputs/ltx_video_run/live_runs"
FRESH_RUN_KEY = "fresh_run"


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


def _load_tap_sync_module():
    return importlib.import_module(".tap_accent_sync", __package__)


def write_json(path, data):
    path_policy = _load_path_policy_module()
    path = path_policy.resolve_runtime_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _utc_now_text():
    return datetime.now(timezone.utc).isoformat()


def _utc_compact_timestamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def normalize_run_id(value):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip()).strip("._-")
    return cleaned


def generate_run_id():
    return f"ltx_{_utc_compact_timestamp()}_{secrets.token_hex(4)}"


def _is_within(child, parent):
    child = Path(child).resolve()
    parent = Path(parent).resolve()
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def resolve_fresh_run_paths(output_plan=None, report_json=None, run_id=None):
    path_policy = _load_path_policy_module()
    active_run_id = normalize_run_id(run_id) or generate_run_id()

    if output_plan and str(output_plan).strip():
        plan_path = path_policy.resolve_runtime_path(output_plan)
        run_root = plan_path.parent
    else:
        run_root = path_policy.resolve_runtime_path(DEFAULT_RUNS_ROOT) / active_run_id
        if run_root.exists() and any(run_root.iterdir()):
            raise FileExistsError(
                f"Fresh run folder already exists and is not empty: {run_root.resolve()}"
            )
        plan_path = run_root / "validated_plan.json"

    report_path = (
        path_policy.resolve_runtime_path(report_json)
        if report_json and str(report_json).strip()
        else run_root / "orchestrator_report.json"
    )

    return {
        "run_id": active_run_id,
        "run_root": run_root,
        "plan_path": plan_path,
        "report_path": report_path,
        "preflight_path": run_root / "preflight_report.json",
        "submit_dir": run_root / "submissions",
        "orchestration_dir": run_root / "orchestration",
    }


def archive_existing_plan(output_plan, run_id):
    path_policy = _load_path_policy_module()
    plan_path = path_policy.resolve_runtime_path(output_plan)
    if not plan_path.exists():
        return None

    archive_dir = plan_path.parent / "_archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    suffix = plan_path.suffix or ".json"
    archived_name = (
        f"{plan_path.stem}_replaced_{_utc_compact_timestamp()}_"
        f"{normalize_run_id(run_id)[:24]}{suffix}"
    )
    archived_path = archive_dir / archived_name
    counter = 1
    while archived_path.exists():
        archived_path = archive_dir / f"{Path(archived_name).stem}_{counter}{suffix}"
        counter += 1
    plan_path.replace(archived_path)
    return {
        "original_path": path_policy.serialize_path(plan_path),
        "original_resolved_path": str(plan_path.resolve()),
        "archived_path": path_policy.serialize_path(archived_path),
        "archived_resolved_path": str(archived_path.resolve()),
        "archived_at_utc": _utc_now_text(),
    }


def stamp_fresh_run_plan(
    plan,
    *,
    output_json,
    run_id,
    audio_path,
    seed_dir,
    archived_plan=None,
):
    path_policy = _load_path_policy_module()
    plan_path = path_policy.resolve_runtime_path(output_json)
    run_root = plan_path.parent
    stamped = dict(plan)
    metadata = {
        "run_id": normalize_run_id(run_id),
        "created_at_utc": _utc_now_text(),
        "status": "active",
        "plan_json": path_policy.serialize_path(plan_path),
        "plan_json_resolved": str(plan_path.resolve()),
        "run_root": path_policy.serialize_path(run_root),
        "run_root_resolved": str(run_root.resolve()),
        "source_audio": path_policy.serialize_path(audio_path),
        "source_audio_resolved": str(path_policy.resolve_runtime_path(audio_path).resolve()),
        "seed_dir": path_policy.serialize_path(seed_dir),
        "seed_dir_resolved": str(path_policy.resolve_runtime_path(seed_dir).resolve()),
        "archived_previous_plan": archived_plan,
        "reuse_policy": "fresh_plan_only",
    }
    stamped[FRESH_RUN_KEY] = metadata
    stamped["run_id"] = metadata["run_id"]
    stamped["plan_reuse_allowed"] = False

    results = []
    for raw_item in stamped.get("results", []):
        item = dict(raw_item)
        item["run_id"] = metadata["run_id"]
        item["plan_reuse_allowed"] = False
        results.append(item)
    stamped["results"] = results

    write_json(plan_path, stamped)
    return stamped


def validate_fresh_run_plan(
    plan,
    *,
    plan_json,
    expected_run_id,
    output_json=None,
):
    path_policy = _load_path_policy_module()
    problems = []
    expected = normalize_run_id(expected_run_id)
    metadata = plan.get(FRESH_RUN_KEY) or {}
    actual = normalize_run_id(metadata.get("run_id") or plan.get("run_id"))
    plan_path = path_policy.resolve_runtime_path(plan_json)

    if not expected:
        problems.append("expected_run_id is required")
    if not metadata:
        problems.append("plan is missing fresh-run metadata")
    if not actual:
        problems.append("plan is missing a run_id")
    if expected and actual and expected != actual:
        problems.append(f"run_id mismatch: expected {expected}, plan contains {actual}")
    if plan.get("plan_reuse_allowed") is not False:
        problems.append("plan is not marked fresh-plan-only")

    recorded_plan = metadata.get("plan_json_resolved")
    if recorded_plan and Path(recorded_plan).resolve() != plan_path.resolve():
        problems.append(
            "plan path mismatch: the JSON is not being submitted from the path recorded when it was created"
        )

    recorded_root = metadata.get("run_root_resolved")
    if recorded_root:
        run_root = Path(recorded_root).resolve()
        if not _is_within(plan_path, run_root):
            problems.append("plan JSON is outside its recorded run folder")
        if output_json is not None:
            output_path = path_policy.resolve_runtime_path(output_json)
            if not _is_within(output_path, run_root):
                problems.append("submission output is outside the plan's run folder")

    if not plan.get("results"):
        problems.append("plan contains no scene results")

    return problems


def submit_fresh_run_plan(
    *,
    plan_json,
    output_json,
    expected_run_id,
    clip_index=1,
    model=None,
    guidance_scale=None,
    live=False,
    allow_sorted_seed_fallback=False,
    allow_duplicate_seed_reuse=False,
):
    pipeline = _load_pipeline_module()
    plan = pipeline.read_json(plan_json)
    problems = validate_fresh_run_plan(
        plan,
        plan_json=plan_json,
        expected_run_id=expected_run_id,
        output_json=output_json,
    )
    if problems:
        raise RuntimeError(
            "Fresh-run identity check failed; refusing submission:\n" + "\n".join(problems)
        )

    active_model = model or pipeline.DEFAULT_MODEL
    active_guidance = (
        guidance_scale
        if guidance_scale is not None
        else pipeline.DEFAULT_GUIDANCE_SCALE
    )
    result = pipeline.submit_one(
        plan_json=plan_json,
        output_json=output_json,
        clip_index=clip_index,
        model=active_model,
        guidance_scale=active_guidance,
        dry_run=not live,
        live=live,
        allow_sorted_seed_fallback=allow_sorted_seed_fallback,
        allow_duplicate_seed_reuse=allow_duplicate_seed_reuse,
    )
    result["fresh_run_verified"] = True
    result["verified_run_id"] = normalize_run_id(expected_run_id)
    result["plan_reuse_allowed"] = False
    write_json(output_json, result)
    return result


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

    return sorted(
        candidates,
        key=lambda path: (path.stat().st_mtime, path.name.lower()),
        reverse=True,
    )[0]


def resolve_audio_argument(audio=None, audio_dir=DEFAULT_AUDIO_DIR):
    """Resolve an explicit audio path or auto-select the newest audio file."""
    path_policy = _load_path_policy_module()
    if audio and str(audio).strip():
        audio_path = path_policy.resolve_runtime_path(audio)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path.resolve()}")
        return audio_path, "explicit_audio"
    return find_newest_audio(audio_dir), "newest_audio_in_folder"


def _output_json_from_build_plan_call(args, kwargs):
    if "output_json" in kwargs:
        return kwargs["output_json"]
    if len(args) >= 3:
        return args[2]
    raise TypeError("Could not determine output_json from build_plan call.")


def _audio_path_from_build_plan_call(args, kwargs):
    if "audio_path" in kwargs:
        return kwargs["audio_path"]
    if args:
        return args[0]
    raise TypeError("Could not determine audio_path from build_plan call.")


def _seed_dir_from_build_plan_call(args, kwargs):
    if "seed_dir" in kwargs:
        return kwargs["seed_dir"]
    if len(args) >= 2:
        return args[1]
    raise TypeError("Could not determine seed_dir from build_plan call.")


def _patch_plan_after_old_build_plan(
    original_build_plan,
    filename_hint_provider="ollama",
    filename_hint_model="gemma3:4b",
    apply_asmo_negative_memory=True,
    apply_tap_accent_sync=True,
    state_root=DEFAULT_STATE_ROOT,
    run_id=None,
    archived_plan=None,
):
    """Wrap the old build_plan function without replacing the old orchestrator flow."""

    def wrapped_build_plan(*args, **kwargs):
        plan = original_build_plan(*args, **kwargs)
        output_json = _output_json_from_build_plan_call(args, kwargs)
        audio_path = _audio_path_from_build_plan_call(args, kwargs)
        seed_dir = _seed_dir_from_build_plan_call(args, kwargs)

        plan_expander = _load_plan_expander_module()
        patched = plan_expander.expand_plan_data(
            plan,
            provider=filename_hint_provider,
            model=filename_hint_model,
        )

        if apply_asmo_negative_memory:
            negative_memory = _load_negative_memory_module()
            patched = negative_memory.apply_negative_memory_to_plan_data(
                patched,
                state_root=state_root,
            )
            patched["asmo_negative_memory_applied"] = True
        else:
            patched["asmo_negative_memory_applied"] = False

        if apply_tap_accent_sync:
            tap_sync = _load_tap_sync_module()
            markers = tap_sync.extract_tap_beat_markers(audio_path, patched)
            patched = tap_sync.apply_tap_sync_to_plan_data(
                patched,
                audio_path=audio_path,
                markers=markers,
            )
            patched["tap_accent_sync_applied"] = True
        else:
            patched["tap_accent_sync_applied"] = False

        patched = stamp_fresh_run_plan(
            patched,
            output_json=output_json,
            run_id=run_id or generate_run_id(),
            audio_path=audio_path,
            seed_dir=seed_dir,
            archived_plan=archived_plan,
        )
        print(
            "Filename-hint expansion applied through old orchestrator build_plan: "
            f"{patched.get('filename_hint_expansion')}"
        )
        print(
            "Tap-accent sync policy: "
            f"{(patched.get('tap_sync') or {}).get('policy', 'disabled')}"
        )
        print(f"Fresh run ID: {(patched.get(FRESH_RUN_KEY) or {}).get('run_id')}")
        return patched

    return wrapped_build_plan


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
    beat_align=True,
    allow_sorted_seed_fallback=False,
    allow_duplicate_seed_reuse=False,
    filename_hint_provider="ollama",
    filename_hint_model="gemma3:4b",
    apply_asmo_negative_memory=True,
    apply_tap_accent_sync=True,
    state_root=DEFAULT_STATE_ROOT,
    run_id=None,
    archive_existing=True,
):
    pipeline = _load_pipeline_module()
    orchestrator = _load_orchestrator_module()
    path_policy = _load_path_policy_module()

    paths = resolve_fresh_run_paths(
        output_plan=output_plan,
        report_json=report_json,
        run_id=run_id,
    )
    active_run_id = paths["run_id"]
    output_plan_path = paths["plan_path"]
    selected_report_json = paths["report_path"]
    run_root = paths["run_root"]
    run_root.mkdir(parents=True, exist_ok=True)

    archived_plan = (
        archive_existing_plan(output_plan_path, active_run_id)
        if archive_existing
        else None
    )

    audio_path, audio_selection_method = resolve_audio_argument(
        audio,
        audio_dir=audio_dir,
    )
    selected_seed_dir = seed_dir or pipeline.DEFAULT_SEED_DIR
    print(f"Fresh run ID: {active_run_id}")
    print(f"Fresh run folder: {run_root.resolve()}")
    print(f"Active plan path: {output_plan_path.resolve()}")
    if archived_plan:
        print(
            "Previous plan removed from the active path and archived at: "
            f"{archived_plan['archived_resolved_path']}"
        )
    print(f"Auto audio selection method: {audio_selection_method}")
    print(f"Audio selected: {audio_path.resolve()}")
    print(f"Beat alignment enabled: {bool(beat_align)}")
    print(f"Tap-accent sync enabled: {bool(apply_tap_accent_sync)}")

    original_build_plan = orchestrator.build_plan
    original_extract_beat_markers = orchestrator.extract_beat_markers
    original_choreography_builder = orchestrator.build_beat_camera_choreography_manifest
    original_output_paths = {
        "DEFAULT_PREFLIGHT_JSON": orchestrator.DEFAULT_PREFLIGHT_JSON,
        "DEFAULT_SUBMIT_DIR": orchestrator.DEFAULT_SUBMIT_DIR,
        "DEFAULT_ORCHESTRATION_DIR": orchestrator.DEFAULT_ORCHESTRATION_DIR,
        "DEFAULT_ORCHESTRATOR_REPORT_JSON": orchestrator.DEFAULT_ORCHESTRATOR_REPORT_JSON,
    }

    orchestrator.build_plan = _patch_plan_after_old_build_plan(
        original_build_plan,
        filename_hint_provider=filename_hint_provider,
        filename_hint_model=filename_hint_model,
        apply_asmo_negative_memory=apply_asmo_negative_memory,
        apply_tap_accent_sync=apply_tap_accent_sync,
        state_root=state_root,
        run_id=active_run_id,
        archived_plan=archived_plan,
    )
    orchestrator.DEFAULT_PREFLIGHT_JSON = paths["preflight_path"]
    orchestrator.DEFAULT_SUBMIT_DIR = paths["submit_dir"]
    orchestrator.DEFAULT_ORCHESTRATION_DIR = paths["orchestration_dir"]
    orchestrator.DEFAULT_ORCHESTRATOR_REPORT_JSON = selected_report_json

    if apply_tap_accent_sync:
        tap_sync = _load_tap_sync_module()
        orchestrator.extract_beat_markers = tap_sync.extract_tap_beat_markers
        orchestrator.build_beat_camera_choreography_manifest = (
            tap_sync.wrap_choreography_manifest(original_choreography_builder)
        )

    try:
        result = orchestrator.orchestrate(
            audio=path_policy.serialize_path(audio_path),
            seed_dir=selected_seed_dir,
            output_plan=path_policy.serialize_path(output_plan_path),
            resolution=resolution,
            max_scenes=max_scenes,
            scene_seconds=(
                scene_seconds
                if scene_seconds is not None
                else pipeline.DEFAULT_SCENE_SECONDS
            ),
            model=model or pipeline.DEFAULT_MODEL,
            guidance_scale=(
                guidance_scale
                if guidance_scale is not None
                else pipeline.DEFAULT_GUIDANCE_SCALE
            ),
            live=live,
            report_json=path_policy.serialize_path(selected_report_json),
            start_offset_seconds=start_offset_seconds,
            beat_align=beat_align,
            allow_sorted_seed_fallback=allow_sorted_seed_fallback,
            allow_duplicate_seed_reuse=allow_duplicate_seed_reuse,
        )
    finally:
        orchestrator.build_plan = original_build_plan
        orchestrator.extract_beat_markers = original_extract_beat_markers
        orchestrator.build_beat_camera_choreography_manifest = (
            original_choreography_builder
        )
        for name, value in original_output_paths.items():
            setattr(orchestrator, name, value)

    result["run_id"] = active_run_id
    result["fresh_run"] = True
    result["plan_reuse_allowed"] = False
    result["run_root"] = path_policy.serialize_path(run_root)
    result["run_root_resolved"] = str(run_root.resolve())
    result["active_plan_json"] = path_policy.serialize_path(output_plan_path)
    result["active_plan_json_resolved"] = str(output_plan_path.resolve())
    result["archived_previous_plan"] = archived_plan
    result["audio_selection_method"] = audio_selection_method
    result["auto_selected_audio"] = path_policy.serialize_path(audio_path)
    result["auto_selected_audio_resolved"] = str(audio_path.resolve())
    result["beat_alignment_default"] = True
    result["beat_alignment_enabled"] = bool(beat_align)
    result["filename_hint_provider"] = filename_hint_provider
    result["filename_hint_model"] = filename_hint_model
    result["asmo_negative_memory_requested"] = bool(apply_asmo_negative_memory)
    result["tap_accent_sync_requested"] = bool(apply_tap_accent_sync)
    result["tap_sync_policy"] = (
        "tap_not_boom" if apply_tap_accent_sync else "disabled"
    )
    write_json(selected_report_json, result)
    return result


def main():
    pipeline = _load_pipeline_module()

    parser = argparse.ArgumentParser(
        description=(
            "LTX wrapper that creates a fresh isolated run, auto-selects audio, "
            "expands the exact seed filename with Ollama, and prevents stale-plan reuse."
        )
    )
    parser.add_argument(
        "--audio",
        default=None,
        help="Optional explicit audio path. If omitted, newest file in --audio-dir is used.",
    )
    parser.add_argument("--audio-dir", default=DEFAULT_AUDIO_DIR)
    parser.add_argument("--seed-dir", default=pipeline.DEFAULT_SEED_DIR)
    parser.add_argument("--output-plan", default=None)
    parser.add_argument("--resolution", default="9:16")
    parser.add_argument("--max-scenes", type=int, default=None)
    parser.add_argument(
        "--scene-seconds",
        type=float,
        default=pipeline.DEFAULT_SCENE_SECONDS,
    )
    parser.add_argument("--start-offset-seconds", type=float, default=0.0)
    parser.add_argument(
        "--no-beat-align",
        action="store_true",
        help="Disable default beat-aligned scene timing and use fixed scene intervals.",
    )
    parser.add_argument("--model", default=pipeline.DEFAULT_MODEL)
    parser.add_argument(
        "--guidance-scale",
        type=float,
        default=pipeline.DEFAULT_GUIDANCE_SCALE,
    )
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--allow-sorted-seed-fallback", action="store_true")
    parser.add_argument("--allow-duplicate-seed-reuse", action="store_true")
    parser.add_argument("--report-json", default=None)
    parser.add_argument(
        "--filename-hint-provider",
        default="ollama",
        choices=["template", "openai", "ollama"],
    )
    parser.add_argument("--filename-hint-model", default="gemma3:4b")
    parser.add_argument("--state-root", default=DEFAULT_STATE_ROOT)
    parser.add_argument("--no-asmo-negative-memory", action="store_true")
    parser.add_argument(
        "--no-tap-accent-sync",
        action="store_true",
        help=(
            "Disable clap/snare/hi-hat tap-accent motion targeting and use the "
            "legacy percussive beat-grid behavior."
        ),
    )
    parser.add_argument("--run-id", default=None)
    parser.add_argument(
        "--no-archive-existing-plan",
        action="store_true",
        help="Do not archive an existing JSON at --output-plan before creating the fresh plan.",
    )
    parser.add_argument(
        "--submit-existing-plan",
        default=None,
        help="Submit one previously prepared fresh-run plan after verifying its run ID.",
    )
    parser.add_argument("--expected-run-id", default=None)
    parser.add_argument("--submit-output", default=None)
    parser.add_argument("--clip-index", type=int, default=1)
    args = parser.parse_args()

    if args.submit_existing_plan:
        if not args.expected_run_id:
            parser.error("--expected-run-id is required with --submit-existing-plan")
        if not args.submit_output:
            parser.error("--submit-output is required with --submit-existing-plan")
        result = submit_fresh_run_plan(
            plan_json=args.submit_existing_plan,
            output_json=args.submit_output,
            expected_run_id=args.expected_run_id,
            clip_index=args.clip_index,
            model=args.model,
            guidance_scale=args.guidance_scale,
            live=args.live,
            allow_sorted_seed_fallback=args.allow_sorted_seed_fallback,
            allow_duplicate_seed_reuse=args.allow_duplicate_seed_reuse,
        )
        print("Fresh-run LTX scene submit complete.")
        print(f"Verified run ID: {result.get('verified_run_id')}")
        print(f"Status: {result.get('status')}")
        print(f"Result JSON: {Path(args.submit_output).resolve()}")
        return

    result = run_auto_audio_orchestrator(
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
        beat_align=not args.no_beat_align,
        allow_sorted_seed_fallback=args.allow_sorted_seed_fallback,
        allow_duplicate_seed_reuse=args.allow_duplicate_seed_reuse,
        filename_hint_provider=args.filename_hint_provider,
        filename_hint_model=args.filename_hint_model,
        apply_asmo_negative_memory=not args.no_asmo_negative_memory,
        apply_tap_accent_sync=not args.no_tap_accent_sync,
        state_root=args.state_root,
        run_id=args.run_id,
        archive_existing=not args.no_archive_existing_plan,
    )
    print(f"Fresh run ID: {result.get('run_id')}")
    print(f"Active plan: {result.get('active_plan_json_resolved')}")


if __name__ == "__main__":
    main()
