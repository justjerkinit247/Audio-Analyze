from __future__ import annotations

import argparse
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


REPO_ROOT = Path(__file__).resolve().parent
AUDIO_DIR = REPO_ROOT / "inputs" / "audio"
SEED_DIR = REPO_ROOT / "inputs" / "ltx_seed_images"
OUTPUT_ROOT = REPO_ROOT / "outputs" / "ltx_video_run"
RUNS_DIR = OUTPUT_ROOT / "runs"
FINALS_DIR = OUTPUT_ROOT / "final_videos"
AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg"}


@dataclass(frozen=True)
class RunPaths:
    run_id: str
    run_dir: Path
    plan_json: Path
    preflight_json: Path
    submissions_dir: Path
    orchestration_dir: Path
    stitching_manifest: Path
    assembled_dir: Path
    assembly_output: Path
    assembly_report: Path
    run_orchestrator_report: Path


def header(text: str) -> None:
    print("=" * 60)
    print(text)
    print("=" * 60)


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def slugify(value: str, fallback: str = "run") -> str:
    value = Path(value).stem if value else fallback
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_ .-")
    return value[:90] or fallback


def make_run_id(audio_path: Optional[Path], label: Optional[str] = None) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = label or (audio_path.stem if audio_path else "manual")
    return f"{stamp}_{slugify(name)}"


def build_run_paths(run_id: str) -> RunPaths:
    safe_id = slugify(run_id)
    run_dir = RUNS_DIR / safe_id
    return RunPaths(
        run_id=safe_id,
        run_dir=run_dir,
        plan_json=run_dir / "holy_cheeks_ltx_plan.json",
        preflight_json=run_dir / "preflight_report.json",
        submissions_dir=run_dir / "submissions",
        orchestration_dir=run_dir / "orchestration",
        stitching_manifest=run_dir / "orchestration" / "stitching_manifest.json",
        assembled_dir=run_dir / "assembled",
        assembly_output=run_dir / "assembled" / "final_music_video.mp4",
        assembly_report=run_dir / "assembled" / "assembly_report.json",
        run_orchestrator_report=run_dir / "orchestrator_report.json",
    )


def find_audio() -> Optional[Path]:
    if not AUDIO_DIR.exists():
        return None
    files = [p for p in AUDIO_DIR.rglob("*") if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS]
    if not files:
        return None
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0]


def ensure_run_dirs(paths: RunPaths) -> None:
    paths.run_dir.mkdir(parents=True, exist_ok=True)
    paths.submissions_dir.mkdir(parents=True, exist_ok=True)
    paths.orchestration_dir.mkdir(parents=True, exist_ok=True)
    paths.assembled_dir.mkdir(parents=True, exist_ok=True)
    FINALS_DIR.mkdir(parents=True, exist_ok=True)


def configure_orchestrator(paths: RunPaths):
    from src.audio_analyze import ltx_orchestrator

    ltx_orchestrator.DEFAULT_PLAN_JSON = str(paths.plan_json)
    ltx_orchestrator.DEFAULT_PREFLIGHT_JSON = str(paths.preflight_json)
    ltx_orchestrator.DEFAULT_SUBMIT_DIR = str(paths.submissions_dir)
    ltx_orchestrator.DEFAULT_ORCHESTRATION_DIR = str(paths.orchestration_dir)
    ltx_orchestrator.DEFAULT_ORCHESTRATOR_REPORT_JSON = str(paths.run_orchestrator_report)
    return ltx_orchestrator


def copy_final_video(paths: RunPaths) -> Optional[str]:
    if not paths.assembly_output.exists() or paths.assembly_output.stat().st_size <= 0:
        return None
    final_path = FINALS_DIR / f"{paths.run_id}_{paths.assembly_output.name}"
    shutil.copy2(paths.assembly_output, final_path)
    return rel(final_path)


def cleanup_temp_files(root: Path, dry_run: bool = False) -> dict[str, Any]:
    patterns = ["*.json", "*.md", "*.txt", "**/*.json", "**/*.md", "**/*.txt"]
    targets: list[Path] = []
    for pattern in patterns:
        targets.extend([p for p in root.glob(pattern) if p.is_file()])
    targets = sorted(set(targets), key=lambda p: str(p).lower())

    deleted: list[str] = []
    failed: list[dict[str, str]] = []
    for path in targets:
        try:
            deleted.append(rel(path))
            if not dry_run:
                path.unlink()
        except Exception as exc:
            failed.append({"path": rel(path), "error": str(exc)})

    return {
        "root": rel(root),
        "dry_run": dry_run,
        "deleted_count": len(deleted),
        "deleted": deleted,
        "failed_count": len(failed),
        "failed": failed,
        "preserved": ["*.mp4", "**/scene_audio/*.mp3", "final_videos/*.mp4"],
    }


def test_imports() -> int:
    header("IMPORT TEST")
    modules = ["ltx_orchestrator", "ltx_ffmpeg_assembler", "ltx_holy_cheeks_pipeline"]
    for name in modules:
        try:
            __import__(f"src.audio_analyze.{name}")
            print(f"OK: src.audio_analyze.{name}")
        except Exception as exc:
            print(f"FAILED: src.audio_analyze.{name} -> {exc}")
            return 1
    return 0


def assert_no_root_leaks(run_id: str) -> dict[str, Any]:
    allowed_dirs = {"runs", "final_videos"}
    leaks = []
    if OUTPUT_ROOT.exists():
        for path in OUTPUT_ROOT.iterdir():
            if path.name in allowed_dirs:
                continue
            leaks.append(rel(path))
    return {"run_id": run_id, "root_leak_count": len(leaks), "root_leaks": leaks}


def enforce_submit_hard_stop(result: dict[str, Any], render_output_expected: bool = False) -> Optional[str]:
    if str(result.get("status", "unknown")) != "complete":
        return None

    if not render_output_expected:
        return None

    summary = result.get("summary")
    summary_status = summary.get("status") if isinstance(summary, dict) else None
    if summary_status == "complete":
        return None

    reason = (
        f"Submit summary status is {summary_status!r}; expected 'complete'. "
        "Refusing downstream assembly from partial or failed render output."
    )
    result["status"] = "failed_submit"
    result["hard_stop_reason"] = reason
    return reason


def run_pipeline(args: argparse.Namespace) -> int:
    audio = Path(args.audio).resolve() if args.audio else find_audio()
    if not audio or not audio.exists():
        header("NO AUDIO FOUND")
        print(f"Put an audio file in: {AUDIO_DIR}")
        return 2

    run_id = slugify(args.run_id) if args.run_id else make_run_id(audio)
    paths = build_run_paths(run_id)
    ensure_run_dirs(paths)
    orchestrator = configure_orchestrator(paths)

    output_plan = Path(args.output_plan).resolve() if args.output_plan else paths.plan_json
    seed_dir = Path(args.seed_dir).resolve()

    header("LTX MAIN PIPELINE")
    print(f"Run ID: {paths.run_id}")
    print(f"Run folder: {rel(paths.run_dir)}")
    print(f"Mode: {'LIVE' if args.live else 'DRY RUN / NO CREDIT SPEND'}")
    print(f"Audio: {audio}")
    print(f"Seed dir: {seed_dir}")
    print(f"Plan: {rel(output_plan)}")
    print(f"Submissions: {rel(paths.submissions_dir)}")
    print(f"Orchestration: {rel(paths.orchestration_dir)}")
    print(f"Orchestrator report: {rel(paths.run_orchestrator_report)}")
    print(f"Start offset seconds: {args.start_offset_seconds}")
    print(f"Beat alignment enabled: {args.beat_align}")

    result = orchestrator.orchestrate(
        audio=str(audio),
        seed_dir=str(seed_dir),
        output_plan=str(output_plan),
        resolution=args.resolution,
        max_scenes=args.max_scenes,
        scene_seconds=args.scene_seconds,
        model=args.model,
        guidance_scale=args.guidance_scale,
        live=args.live,
        report_json=str(paths.run_orchestrator_report),
        start_offset_seconds=args.start_offset_seconds,
        beat_align=args.beat_align,
    )

    render_output_expected = bool(args.live or args.assemble_after)
    hard_stop_reason = enforce_submit_hard_stop(result, render_output_expected=render_output_expected)
    pipeline_status = str(result.get("status", "unknown"))
    assembly_report: Optional[dict[str, Any]] = None
    final_copy: Optional[str] = None

    if args.assemble_after and pipeline_status == "complete":
        from src.audio_analyze.ltx_ffmpeg_assembler import assemble_from_manifest

        header("ASSEMBLING FINAL VIDEO")
        assembly_report = assemble_from_manifest(
            stitching_manifest=str(paths.stitching_manifest),
            output_mp4=str(paths.assembly_output),
            audio_path=str(audio),
            report_json=str(paths.assembly_report),
            dry_run=args.assembly_dry_run,
        )
        if assembly_report.get("status") == "complete":
            final_copy = copy_final_video(paths)

    cleanup_report = None
    should_cleanup = args.cleanup_json or (
        args.cleanup_json_on_success
        and pipeline_status == "complete"
        and (not args.dry_run or args.cleanup_after_dry_run)
        and (not args.assemble_after or (assembly_report or {}).get("status") == "complete")
    )
    if should_cleanup and not args.no_cleanup_json:
        cleanup_report = cleanup_temp_files(paths.run_dir, dry_run=False)

    leak_report = assert_no_root_leaks(paths.run_id)

    if hard_stop_reason:
        header("PIPELINE HARD STOP")
        print(hard_stop_reason)
    header("PIPELINE RESULT")
    print(json.dumps(result, indent=2))
    if assembly_report is not None:
        header("ASSEMBLY RESULT")
        print(json.dumps(assembly_report, indent=2))
    if final_copy:
        header("FINAL VIDEO COPY")
        print(final_copy)
    if cleanup_report:
        header("CLEANUP REPORT")
        print(json.dumps(cleanup_report, indent=2))
    header("ROOT LEAK CHECK")
    print(json.dumps(leak_report, indent=2))
    header("RUN FOLDER")
    print(rel(paths.run_dir))

    ok = pipeline_status == "complete" and leak_report["root_leak_count"] == 0
    if args.assemble_after:
        ok = ok and assembly_report is not None and assembly_report.get("status") in {"complete", "dry_run"}
    return 0 if ok else 1


def show_outputs() -> int:
    header("CURRENT OUTPUT FILES")
    if not OUTPUT_ROOT.exists():
        print(f"No output folder yet: {OUTPUT_ROOT}")
        return 0
    files = sorted([p for p in OUTPUT_ROOT.rglob("*") if p.is_file()], key=lambda p: p.stat().st_mtime, reverse=True)
    for path in files[:220]:
        print(rel(path))
    if len(files) > 220:
        print(f"... plus {len(files) - 220} more files")
    return 0


def cleanup_now(args: argparse.Namespace) -> int:
    root = Path(args.cleanup_root).resolve() if args.cleanup_root else OUTPUT_ROOT
    header("TEMP CLEANUP")
    report = cleanup_temp_files(root, dry_run=args.preview_cleanup)
    print(json.dumps(report, indent=2))
    return 0 if report["failed_count"] == 0 else 1


def organize_existing(args: argparse.Namespace) -> int:
    run_id = slugify(args.run_id or "legacy_ltx_output_archive")
    target = RUNS_DIR / run_id
    target.mkdir(parents=True, exist_ok=True)
    moved: list[str] = []
    failed: list[dict[str, str]] = []

    for source in sorted([p for p in OUTPUT_ROOT.rglob("*") if p.is_file()], key=lambda p: str(p).lower()):
        rel_to_output = source.resolve().relative_to(OUTPUT_ROOT.resolve())
        if rel_to_output.parts[0] in {"runs", "final_videos"}:
            continue
        destination = target / rel_to_output
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if source.suffix.lower() == ".mp4" and "assembled" in rel_to_output.parts:
                FINALS_DIR.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, FINALS_DIR / f"{run_id}_{source.name}")
            moved.append(f"{rel(source)} -> {rel(destination)}")
            if not args.dry_run_organize:
                shutil.move(str(source), str(destination))
        except Exception as exc:
            failed.append({"path": rel(source), "error": str(exc)})

    header("ORGANIZE EXISTING RESULT")
    print(json.dumps({"run_dir": rel(target), "dry_run": args.dry_run_organize, "moved_count": len(moved), "moved": moved, "failed": failed}, indent=2))
    return 0 if not failed else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audio-Analyze LTX main pipeline launcher")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--test-imports", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--live", action="store_true")
    mode.add_argument("--show-outputs", action="store_true")
    mode.add_argument("--cleanup-now", action="store_true")
    mode.add_argument("--preview-cleanup", action="store_true")
    mode.add_argument("--organize-existing", action="store_true")

    parser.add_argument("--audio", default=None)
    parser.add_argument("--seed-dir", default=str(SEED_DIR))
    parser.add_argument("--output-plan", default=None)
    parser.add_argument("--resolution", default="9:16")
    parser.add_argument("--max-scenes", type=int, default=None)
    parser.add_argument("--scene-seconds", type=float, default=8.0)
    parser.add_argument("--start-offset-seconds", type=float, default=0.0)
    parser.add_argument("--beat-align", action="store_true")
    parser.add_argument("--model", default="ltx-2-3-pro")
    parser.add_argument("--guidance-scale", type=float, default=9.0)
    parser.add_argument("--run-id", default=None)

    parser.add_argument("--assemble-after", action="store_true")
    parser.add_argument("--assembly-dry-run", action="store_true")
    parser.add_argument("--cleanup-json-on-success", action="store_true", default=True)
    parser.add_argument("--no-cleanup-json", action="store_true")
    parser.add_argument("--cleanup-json", action="store_true")
    parser.add_argument("--cleanup-after-dry-run", action="store_true")
    parser.add_argument("--cleanup-root", default=None)
    parser.add_argument("--dry-run-organize", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.test_imports:
        return test_imports()
    if args.show_outputs:
        return show_outputs()
    if args.cleanup_now or args.preview_cleanup:
        return cleanup_now(args)
    if args.organize_existing:
        return organize_existing(args)
    return run_pipeline(args)


if __name__ == "__main__":
    raise SystemExit(main())
