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
DEFAULT_AUDIO_DIR = REPO_ROOT / "inputs" / "audio"
DEFAULT_SEED_DIR = REPO_ROOT / "inputs" / "ltx_seed_images"
DEFAULT_LTX_OUTPUT_ROOT = REPO_ROOT / "outputs" / "ltx_video_run"
DEFAULT_RUNS_DIR = DEFAULT_LTX_OUTPUT_ROOT / "runs"
DEFAULT_FINALS_DIR = DEFAULT_LTX_OUTPUT_ROOT / "final_videos"

AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg"}
EXCLUDED_ORGANIZE_DIRS = {"runs", "final_videos"}

# Temporary/debug artifacts. Final MP4s and scene audio are preserved by run folder isolation.
CLEANUP_FILE_PATTERNS = [
    "*.json",
    "*.md",
    "*.txt",
    "submissions/*.json",
    "submissions/**/*.json",
    "orchestration/*.json",
    "assembled/*.json",
    "assembled/*.txt",
    "live_batch/*.json",
]

PRESERVE_PATTERNS = [
    "runs/**",
    "final_videos/*.mp4",
    "**/*.mp4",
    "**/scene_audio/*.mp3",
]


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


def repo_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def output_relative(path: Path) -> Path:
    return path.resolve().relative_to(DEFAULT_LTX_OUTPUT_ROOT.resolve())


def print_header(title: str) -> None:
    print("=" * 60)
    print(title)
    print("=" * 60)


def slugify(value: str, fallback: str = "run") -> str:
    value = Path(value).stem if value else fallback
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_ .-")
    return value[:80] or fallback


def make_run_id(audio_path: Optional[Path], label: Optional[str] = None) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = label or (audio_path.stem if audio_path else "manual")
    return f"{stamp}_{slugify(name)}"


def build_run_paths(run_id: str) -> RunPaths:
    run_dir = DEFAULT_RUNS_DIR / slugify(run_id, fallback="run")
    return RunPaths(
        run_id=run_id,
        run_dir=run_dir,
        plan_json=run_dir / "holy_cheeks_ltx_plan.json",
        preflight_json=run_dir / "preflight_report.json",
        submissions_dir=run_dir / "submissions",
        orchestration_dir=run_dir / "orchestration",
        stitching_manifest=run_dir / "orchestration" / "stitching_manifest.json",
        assembled_dir=run_dir / "assembled",
        assembly_output=run_dir / "assembled" / "final_music_video.mp4",
        assembly_report=run_dir / "assembled" / "assembly_report.json",
    )


def find_first_audio(audio_dir: Path = DEFAULT_AUDIO_DIR) -> Optional[Path]:
    if not audio_dir.exists():
        return None
    candidates = [p for p in audio_dir.rglob("*") if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS]
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def test_imports() -> int:
    print_header("IMPORT TEST")
    modules = ["ltx_orchestrator", "ltx_ffmpeg_assembler", "ltx_holy_cheeks_pipeline"]
    for module_name in modules:
        try:
            __import__(f"src.audio_analyze.{module_name}")
            print(f"OK: src.audio_analyze.{module_name}")
        except Exception as exc:
            print(f"FAILED: src.audio_analyze.{module_name} -> {exc}")
            return 1
    print("All core LTX modules imported successfully.")
    return 0


def output_mp4_is_valid(path: Path) -> bool:
    return path.exists() and path.is_file() and path.stat().st_size > 0


def copy_final_mp4_to_final_videos(mp4_path: Path, run_id: str) -> Optional[str]:
    if not output_mp4_is_valid(mp4_path):
        return None
    DEFAULT_FINALS_DIR.mkdir(parents=True, exist_ok=True)
    destination = DEFAULT_FINALS_DIR / f"{slugify(run_id)}_{mp4_path.name}"
    shutil.copy2(mp4_path, destination)
    return repo_relative(destination)


def collect_cleanup_targets(root: Path) -> list[Path]:
    targets: list[Path] = []
    if not root.exists():
        return targets
    for pattern in CLEANUP_FILE_PATTERNS:
        targets.extend(path for path in root.glob(pattern) if path.is_file())
    return sorted(set(targets), key=lambda p: str(p).lower())


def cleanup_temp_artifacts(root: Path, dry_run: bool = False) -> dict[str, Any]:
    targets = collect_cleanup_targets(root)
    deleted: list[str] = []
    failed: list[dict[str, str]] = []
    for path in targets:
        rel = repo_relative(path)
        if dry_run:
            deleted.append(rel)
            continue
        try:
            path.unlink()
            deleted.append(rel)
        except Exception as exc:
            failed.append({"path": rel, "error": str(exc)})
    if not dry_run:
        remove_empty_dirs(root)
    return {
        "root": repo_relative(root),
        "dry_run": dry_run,
        "deleted_count": len(deleted),
        "deleted": deleted,
        "failed_count": len(failed),
        "failed": failed,
        "preserved_patterns": PRESERVE_PATTERNS,
    }


def remove_empty_dirs(root: Path) -> None:
    if not root.exists():
        return
    for path in sorted([p for p in root.rglob("*") if p.is_dir()], key=lambda p: len(p.parts), reverse=True):
        try:
            path.rmdir()
        except OSError:
            pass


def should_cleanup_after_run(args: argparse.Namespace, pipeline_status: str, assembly_status: Optional[str]) -> bool:
    if args.no_cleanup_json:
        return False
    if args.cleanup_json:
        return True
    if not args.cleanup_json_on_success:
        return False
    if args.dry_run and not args.cleanup_after_dry_run:
        return False
    if args.assemble_after:
        return pipeline_status == "complete" and assembly_status == "complete"
    return pipeline_status == "complete"


def configure_orchestrator_for_run(run_paths: RunPaths):
    from src.audio_analyze import ltx_orchestrator

    # The underlying orchestrator has module-level defaults. Redirect them before execution
    # so future runs write directly into isolated run folders instead of shared flat folders.
    ltx_orchestrator.DEFAULT_PLAN_JSON = str(run_paths.plan_json)
    ltx_orchestrator.DEFAULT_PREFLIGHT_JSON = str(run_paths.preflight_json)
    ltx_orchestrator.DEFAULT_SUBMIT_DIR = str(run_paths.submissions_dir)
    ltx_orchestrator.DEFAULT_ORCHESTRATION_DIR = str(run_paths.orchestration_dir)
    return ltx_orchestrator


def run_orchestrator(args: argparse.Namespace) -> int:
    audio_path = Path(args.audio).resolve() if args.audio else find_first_audio()
    if audio_path is None:
        print_header("NO AUDIO FILE FOUND")
        print(f"Put a .wav/.mp3/.flac/.m4a/.aac/.ogg file inside: {DEFAULT_AUDIO_DIR}")
        return 2
    if not audio_path.exists():
        print(f"Audio file does not exist: {audio_path}")
        return 2

    run_id = args.run_id or make_run_id(audio_path)
    run_paths = build_run_paths(run_id)
    run_paths.run_dir.mkdir(parents=True, exist_ok=True)
    run_paths.assembled_dir.mkdir(parents=True, exist_ok=True)

    ltx_orchestrator = configure_orchestrator_for_run(run_paths)

    seed_dir = Path(args.seed_dir).resolve()
    output_plan = Path(args.output_plan).resolve() if args.output_plan else run_paths.plan_json

    print_header("LTX PROMPT ENGINE / ORCHESTRATOR")
    print(f"Run ID: {run_id}")
    print(f"Run folder: {repo_relative(run_paths.run_dir)}")
    print(f"Mode: {'LIVE CREDIT-SPENDING RUN' if args.live else 'DRY RUN / NO CREDIT SPEND'}")
    print(f"Audio: {audio_path}")
    print(f"Seed dir: {seed_dir}")
    print(f"Plan JSON: {repo_relative(output_plan)}")
    print(f"Submissions dir: {repo_relative(run_paths.submissions_dir)}")
    print(f"Orchestration dir: {repo_relative(run_paths.orchestration_dir)}")
    print(f"Resolution: {args.resolution}")
    print(f"Scene seconds: {args.scene_seconds}")
    print(f"Max scenes: {args.max_scenes}")
    print(f"Model: {args.model}")
    print(f"Guidance scale: {args.guidance_scale}")
    print(f"Assemble after orchestrator: {args.assemble_after}")
    print("")

    result = ltx_orchestrator.orchestrate(
        audio=str(audio_path),
        seed_dir=str(seed_dir),
        output_plan=str(output_plan),
        resolution=args.resolution,
        max_scenes=args.max_scenes,
        scene_seconds=args.scene_seconds,
        model=args.model,
        guidance_scale=args.guidance_scale,
        live=args.live,
    )

    pipeline_status = str(result.get("status", "unknown"))
    assembly_status: Optional[str] = None
    assembly_report: Optional[dict[str, Any]] = None
    final_video_copy: Optional[str] = None

    if args.assemble_after and pipeline_status == "complete":
        assembly_report = run_assembly_report(
            args=args,
            audio_path=audio_path,
            stitching_manifest=run_paths.stitching_manifest,
            output=run_paths.assembly_output,
            report_json=run_paths.assembly_report,
        )
        assembly_status = str(assembly_report.get("status", "unknown"))
        if assembly_status == "complete":
            final_video_copy = copy_final_mp4_to_final_videos(run_paths.assembly_output, run_id)
    elif args.assemble_after:
        print("Skipping assembly because orchestrator did not complete successfully.")

    cleanup_report: Optional[dict[str, Any]] = None
    if should_cleanup_after_run(args, pipeline_status, assembly_status):
        if args.assemble_after:
            if assembly_status != "complete" or not output_mp4_is_valid(run_paths.assembly_output):
                print("Cleanup refused: final MP4 was not confirmed valid.")
            else:
                cleanup_report = cleanup_temp_artifacts(run_paths.run_dir, dry_run=False)
        else:
            cleanup_report = cleanup_temp_artifacts(run_paths.run_dir, dry_run=False)

    print_header("ORCHESTRATOR RESULT")
    print(json.dumps(result, indent=2))
    if assembly_report is not None:
        print_header("ASSEMBLY RESULT")
        print(json.dumps(assembly_report, indent=2))
    if final_video_copy:
        print_header("FINAL VIDEO COPY")
        print(final_video_copy)
    if cleanup_report is not None:
        print_header("CLEANUP REPORT")
        print(json.dumps(cleanup_report, indent=2))

    print_header("RUN FOLDER")
    print(repo_relative(run_paths.run_dir))

    return 0 if pipeline_status == "complete" and (assembly_status in {None, "complete", "dry_run"}) else 1


def run_assembly_report(
    args: argparse.Namespace,
    audio_path: Optional[Path] = None,
    stitching_manifest: Optional[Path] = None,
    output: Optional[Path] = None,
    report_json: Optional[Path] = None,
) -> dict[str, Any]:
    from src.audio_analyze.ltx_ffmpeg_assembler import assemble_from_manifest

    manifest = (stitching_manifest or Path(args.stitching_manifest)).resolve()
    output_path = (output or Path(args.output)).resolve()
    report_path = (report_json or Path(args.report_json)).resolve()
    audio = Path(args.audio).resolve() if args.audio else audio_path

    print_header("LTX FFMPEG ASSEMBLY")
    print(f"Manifest: {manifest}")
    print(f"Output: {output_path}")
    print(f"Report: {report_path}")
    print(f"Audio: {audio if audio else 'None'}")
    print(f"Dry run: {args.assembly_dry_run}")

    return assemble_from_manifest(
        stitching_manifest=str(manifest),
        output_mp4=str(output_path),
        audio_path=str(audio) if audio else None,
        report_json=str(report_path),
        dry_run=args.assembly_dry_run,
    )


def run_assembly(args: argparse.Namespace) -> int:
    run_id = args.run_id or make_run_id(Path(args.audio).resolve() if args.audio else None, label="assembly")
    run_paths = build_run_paths(run_id)
    run_paths.run_dir.mkdir(parents=True, exist_ok=True)

    assembly_report = run_assembly_report(args)
    final_video_copy: Optional[str] = None
    if assembly_report.get("status") == "complete" and output_mp4_is_valid(Path(args.output).resolve()):
        final_video_copy = copy_final_mp4_to_final_videos(Path(args.output).resolve(), run_id)

    cleanup_report: Optional[dict[str, Any]] = None
    if args.cleanup_json_on_success and assembly_report.get("status") == "complete":
        cleanup_report = cleanup_temp_artifacts(DEFAULT_LTX_OUTPUT_ROOT, dry_run=False)

    print_header("ASSEMBLY RESULT")
    print(json.dumps(assembly_report, indent=2))
    if final_video_copy:
        print_header("FINAL VIDEO COPY")
        print(final_video_copy)
    if cleanup_report is not None:
        print_header("CLEANUP REPORT")
        print(json.dumps(cleanup_report, indent=2))
    return 0 if assembly_report.get("status") in {"complete", "dry_run"} else 1


def show_outputs() -> int:
    print_header("CURRENT OUTPUT FILES")
    if not DEFAULT_LTX_OUTPUT_ROOT.exists():
        print(f"No output folder yet: {DEFAULT_LTX_OUTPUT_ROOT}")
        return 0
    files = sorted([p for p in DEFAULT_LTX_OUTPUT_ROOT.rglob("*") if p.is_file()], key=lambda p: p.stat().st_mtime, reverse=True)
    for path in files[:200]:
        print(repo_relative(path))
    if len(files) > 200:
        print(f"... plus {len(files) - 200} more files")
    return 0


def preview_cleanup(args: argparse.Namespace) -> int:
    root = Path(args.cleanup_root).resolve() if args.cleanup_root else DEFAULT_LTX_OUTPUT_ROOT
    print_header("TEMP FILE CLEANUP PREVIEW")
    print(json.dumps(cleanup_temp_artifacts(root, dry_run=True), indent=2))
    return 0


def run_cleanup_now(args: argparse.Namespace) -> int:
    root = Path(args.cleanup_root).resolve() if args.cleanup_root else DEFAULT_LTX_OUTPUT_ROOT
    print_header("TEMP FILE CLEANUP NOW")
    report = cleanup_temp_artifacts(root, dry_run=False)
    print(json.dumps(report, indent=2))
    return 0 if report["failed_count"] == 0 else 1


def collect_flat_existing_outputs(root: Path = DEFAULT_LTX_OUTPUT_ROOT) -> list[Path]:
    if not root.exists():
        return []
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            rel = output_relative(path)
        except ValueError:
            continue
        if rel.parts and rel.parts[0] in EXCLUDED_ORGANIZE_DIRS:
            continue
        files.append(path.resolve())
    return sorted(files, key=lambda p: str(p).lower())


def organize_existing_outputs(args: argparse.Namespace) -> int:
    print_header("ORGANIZE EXISTING FLAT OUTPUTS")
    files = collect_flat_existing_outputs()
    run_id = args.run_id or make_run_id(None, label="legacy_archive")
    run_dir = DEFAULT_RUNS_DIR / slugify(run_id)
    moved: list[str] = []
    failed: list[dict[str, str]] = []
    copied_finals: list[str] = []

    if not args.dry_run_organize:
        run_dir.mkdir(parents=True, exist_ok=True)

    for source in files:
        try:
            rel = output_relative(source)
            destination = run_dir / rel
            moved.append(f"{repo_relative(source)} -> {repo_relative(destination)}")
            if args.dry_run_organize:
                continue
            if source.suffix.lower() == ".mp4" and "assembled" in rel.parts:
                copied = copy_final_mp4_to_final_videos(source, run_id)
                if copied:
                    copied_finals.append(copied)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                destination = destination.with_name(f"{destination.stem}_{datetime.now().strftime('%H%M%S')}{destination.suffix}")
            shutil.move(str(source), str(destination))
        except Exception as exc:
            failed.append({"path": repo_relative(source), "error": str(exc)})

    if not args.dry_run_organize:
        remove_empty_dirs(DEFAULT_LTX_OUTPUT_ROOT)

    report = {
        "run_id": run_id,
        "run_dir": repo_relative(run_dir),
        "dry_run": args.dry_run_organize,
        "moved_count": len(moved),
        "moved": moved,
        "final_videos_copied": copied_finals,
        "failed_count": len(failed),
        "failed": failed,
    }
    print(json.dumps(report, indent=2))
    return 0 if not failed else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Main launcher for the Audio-Analyze LTX prompt engine pipeline.")

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--test-imports", action="store_true", help="Compile/import smoke test only.")
    mode.add_argument("--dry-run", action="store_true", help="Run the LTX orchestrator without spending credits. Default mode.")
    mode.add_argument("--live", action="store_true", help="Run the LTX orchestrator live. This can spend API credits.")
    mode.add_argument("--assemble", action="store_true", help="Assemble generated LTX clips using FFmpeg.")
    mode.add_argument("--show-outputs", action="store_true", help="List recent output files.")
    mode.add_argument("--preview-cleanup", action="store_true", help="Show temp files that would be deleted.")
    mode.add_argument("--cleanup-now", action="store_true", help="Delete temp JSON/report/preview files while preserving MP4s and scene audio.")
    mode.add_argument("--organize-existing", action="store_true", help="Move current flat output clutter into one legacy run folder.")

    parser.add_argument("--audio", default=None, help="Path to audio file. If omitted, newest file in inputs/audio is used.")
    parser.add_argument("--seed-dir", default=str(DEFAULT_SEED_DIR), help="Seed image directory.")
    parser.add_argument("--output-plan", default=None, help="Optional custom plan JSON path. Defaults to the run folder.")
    parser.add_argument("--resolution", default="9:16", help="Video resolution/aspect setting.")
    parser.add_argument("--max-scenes", type=int, default=None, help="Maximum number of scenes.")
    parser.add_argument("--scene-seconds", type=float, default=8.0, help="Scene length in seconds.")
    parser.add_argument("--model", default="ltx-2-3-pro", help="LTX model name.")
    parser.add_argument("--guidance-scale", type=float, default=9.0, help="LTX guidance scale.")

    parser.add_argument("--assemble-after", action="store_true", help="Run assembly after successful orchestrator run.")
    parser.add_argument("--assembly-dry-run", action="store_true", help="Preview assembly command without creating final MP4.")
    parser.add_argument("--stitching-manifest", default=str(DEFAULT_LTX_OUTPUT_ROOT / "orchestration" / "stitching_manifest.json"), help="Stitching manifest for standalone assembly.")
    parser.add_argument("--output", default=str(DEFAULT_LTX_OUTPUT_ROOT / "assembled" / "ltx_assembled_reel.mp4"), help="Standalone assembly MP4 output path.")
    parser.add_argument("--report-json", default=str(DEFAULT_LTX_OUTPUT_ROOT / "assembled" / "ffmpeg_assembly_report.json"), help="Standalone assembly report JSON path.")

    parser.add_argument("--run-id", default=None, help="Optional explicit run folder name.")
    parser.add_argument("--dry-run-organize", action="store_true", help="Preview --organize-existing without moving files.")
    parser.add_argument("--cleanup-root", default=None, help="Optional cleanup root. Defaults to outputs/ltx_video_run.")

    parser.add_argument("--cleanup-json-on-success", action="store_true", default=True, help="Delete temp JSON/report files after successful run. Enabled by default.")
    parser.add_argument("--no-cleanup-json", action="store_true", help="Disable automatic temp cleanup.")
    parser.add_argument("--cleanup-json", action="store_true", help="Force cleanup after run, even without full success. Use carefully.")
    parser.add_argument("--cleanup-after-dry-run", action="store_true", help="Allow auto cleanup after a successful dry-run. Default keeps dry-run files inside the run folder.")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.test_imports:
        return test_imports()
    if args.assemble:
        return run_assembly(args)
    if args.show_outputs:
        return show_outputs()
    if args.preview_cleanup:
        return preview_cleanup(args)
    if args.cleanup_now:
        return run_cleanup_now(args)
    if args.organize_existing:
        return organize_existing_outputs(args)
    return run_orchestrator(args)


if __name__ == "__main__":
    raise SystemExit(main())
