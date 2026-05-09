from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_AUDIO_DIR = REPO_ROOT / "inputs" / "audio"
DEFAULT_SEED_DIR = REPO_ROOT / "inputs" / "ltx_seed_images"
DEFAULT_PLAN_JSON = REPO_ROOT / "outputs" / "ltx_video_run" / "holy_cheeks_ltx_plan.json"
DEFAULT_ASSEMBLY_OUTPUT = REPO_ROOT / "outputs" / "ltx_video_run" / "assembled" / "ltx_assembled_reel.mp4"
DEFAULT_ASSEMBLY_REPORT = REPO_ROOT / "outputs" / "ltx_video_run" / "assembled" / "ffmpeg_assembly_report.json"
DEFAULT_STITCHING_MANIFEST = REPO_ROOT / "outputs" / "ltx_video_run" / "orchestration" / "stitching_manifest.json"
DEFAULT_LTX_OUTPUT_ROOT = REPO_ROOT / "outputs" / "ltx_video_run"

AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg"}


CLEANUP_FILE_PATTERNS = [
    "holy_cheeks_ltx_plan.json",
    "preflight_report.json",
    "orchestrator_report.json",
    "scene_*.json",
    "submissions/*.json",
    "orchestration/*.json",
    "assembled/ffmpeg_assembly_report.json",
    "assembled/ffmpeg_concat_list.txt",
]


PRESERVE_PATTERNS = [
    "downloads/*.mp4",
    "assembled/*.mp4",
]


def repo_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def print_header(title: str) -> None:
    print("=" * 60)
    print(title)
    print("=" * 60)


def find_first_audio(audio_dir: Path = DEFAULT_AUDIO_DIR) -> Optional[Path]:
    if not audio_dir.exists():
        return None

    candidates = []
    for path in audio_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS:
            candidates.append(path)

    if not candidates:
        return None

    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def test_imports() -> int:
    print_header("IMPORT TEST")

    modules = [
        "ltx_orchestrator",
        "ltx_ffmpeg_assembler",
        "ltx_holy_cheeks_pipeline",
    ]

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


def collect_cleanup_targets(root: Path = DEFAULT_LTX_OUTPUT_ROOT) -> list[Path]:
    targets: list[Path] = []
    for pattern in CLEANUP_FILE_PATTERNS:
        targets.extend(path for path in root.glob(pattern) if path.is_file())
    return sorted(set(targets))


def cleanup_json_artifacts(root: Path = DEFAULT_LTX_OUTPUT_ROOT, dry_run: bool = False) -> dict[str, Any]:
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

    return {
        "root": str(root.resolve()),
        "dry_run": dry_run,
        "deleted_count": len(deleted),
        "deleted": deleted,
        "failed_count": len(failed),
        "failed": failed,
        "preserved_patterns": PRESERVE_PATTERNS,
    }


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


def run_orchestrator(args: argparse.Namespace) -> int:
    from src.audio_analyze.ltx_orchestrator import orchestrate

    audio_path = Path(args.audio).resolve() if args.audio else find_first_audio()

    if audio_path is None:
        print_header("NO AUDIO FILE FOUND")
        print(f"Put a .wav/.mp3/.flac/.m4a/.aac/.ogg file inside: {DEFAULT_AUDIO_DIR}")
        print("Then run:")
        print("python .\\main.py --dry-run")
        return 2

    if not audio_path.exists():
        print(f"Audio file does not exist: {audio_path}")
        return 2

    seed_dir = Path(args.seed_dir).resolve()
    output_plan = Path(args.output_plan).resolve()

    print_header("LTX PROMPT ENGINE / ORCHESTRATOR")
    print(f"Mode: {'LIVE CREDIT-SPENDING RUN' if args.live else 'DRY RUN / NO CREDIT SPEND'}")
    print(f"Audio: {audio_path}")
    print(f"Seed dir: {seed_dir}")
    print(f"Resolution: {args.resolution}")
    print(f"Scene seconds: {args.scene_seconds}")
    print(f"Max scenes: {args.max_scenes}")
    print(f"Model: {args.model}")
    print(f"Guidance scale: {args.guidance_scale}")
    print(f"Cleanup on success: {args.cleanup_json_on_success}")
    print(f"Assemble after orchestrator: {args.assemble_after}")
    print("")

    result = orchestrate(
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

    if args.assemble_after and pipeline_status == "complete":
        assembly_report = run_assembly_report(args, audio_path=audio_path)
        assembly_status = str(assembly_report.get("status", "unknown"))
    elif args.assemble_after:
        print("Skipping assembly because orchestrator did not complete successfully.")

    cleanup_report: Optional[dict[str, Any]] = None
    if should_cleanup_after_run(args, pipeline_status, assembly_status):
        if args.assemble_after:
            final_mp4 = Path(args.output).resolve()
            if assembly_status != "complete" or not output_mp4_is_valid(final_mp4):
                print("Cleanup refused: final MP4 was not confirmed valid.")
            else:
                cleanup_report = cleanup_json_artifacts(dry_run=False)
        else:
            cleanup_report = cleanup_json_artifacts(dry_run=False)

    print_header("ORCHESTRATOR RESULT")
    print(json.dumps(result, indent=2))

    if assembly_status is not None:
        print_header("ASSEMBLY STATUS")
        print(assembly_status)

    if cleanup_report is not None:
        print_header("CLEANUP REPORT")
        print(json.dumps(cleanup_report, indent=2))

    return 0 if pipeline_status == "complete" and (assembly_status in {None, "complete", "dry_run"}) else 1


def run_assembly_report(args: argparse.Namespace, audio_path: Optional[Path] = None) -> dict[str, Any]:
    from src.audio_analyze.ltx_ffmpeg_assembler import assemble_from_manifest

    manifest = Path(args.stitching_manifest).resolve()
    output = Path(args.output).resolve()
    report = Path(args.report_json).resolve()
    audio = Path(args.audio).resolve() if args.audio else audio_path

    print_header("LTX FFMPEG ASSEMBLY")
    print(f"Manifest: {manifest}")
    print(f"Output: {output}")
    print(f"Report: {report}")
    print(f"Audio: {audio if audio else 'None'}")
    print(f"Dry run: {args.assembly_dry_run}")

    return assemble_from_manifest(
        stitching_manifest=str(manifest),
        output_mp4=str(output),
        audio_path=str(audio) if audio else None,
        report_json=str(report),
        dry_run=args.assembly_dry_run,
    )


def run_assembly(args: argparse.Namespace) -> int:
    assembly_report = run_assembly_report(args)

    cleanup_report: Optional[dict[str, Any]] = None
    if args.cleanup_json_on_success and assembly_report.get("status") == "complete" and output_mp4_is_valid(Path(args.output).resolve()):
        cleanup_report = cleanup_json_artifacts(dry_run=False)

    print_header("ASSEMBLY RESULT")
    print(json.dumps(assembly_report, indent=2))

    if cleanup_report is not None:
        print_header("CLEANUP REPORT")
        print(json.dumps(cleanup_report, indent=2))

    return 0 if assembly_report.get("status") in {"complete", "dry_run"} else 1


def show_outputs() -> int:
    print_header("CURRENT OUTPUT FILES")

    output_root = DEFAULT_LTX_OUTPUT_ROOT
    if not output_root.exists():
        print(f"No output folder yet: {output_root}")
        return 0

    files = sorted(
        [p for p in output_root.rglob("*") if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    for path in files[:100]:
        print(repo_relative(path))

    if len(files) > 100:
        print(f"... plus {len(files) - 100} more files")

    return 0


def preview_cleanup() -> int:
    print_header("JSON CLEANUP PREVIEW")
    report = cleanup_json_artifacts(dry_run=True)
    print(json.dumps(report, indent=2))
    return 0


def run_cleanup_now() -> int:
    print_header("JSON CLEANUP NOW")
    report = cleanup_json_artifacts(dry_run=False)
    print(json.dumps(report, indent=2))
    return 0 if report["failed_count"] == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Main launcher for the Audio-Analyze LTX prompt engine pipeline."
    )

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--test-imports", action="store_true", help="Compile/import smoke test only.")
    mode.add_argument("--dry-run", action="store_true", help="Run the LTX orchestrator without spending credits. Default mode.")
    mode.add_argument("--live", action="store_true", help="Run the LTX orchestrator live. This can spend API credits.")
    mode.add_argument("--assemble", action="store_true", help="Assemble generated LTX clips using FFmpeg.")
    mode.add_argument("--show-outputs", action="store_true", help="List recent output files.")
    mode.add_argument("--preview-cleanup", action="store_true", help="Show JSON/report/temp files that would be deleted.")
    mode.add_argument("--cleanup-now", action="store_true", help="Delete JSON/report/temp files now while preserving audio, seed images, and MP4s.")

    parser.add_argument("--audio", default=None, help="Path to audio file. If omitted, newest file in inputs/audio is used.")
    parser.add_argument("--seed-dir", default=str(DEFAULT_SEED_DIR), help="Seed image directory.")
    parser.add_argument("--output-plan", default=str(DEFAULT_PLAN_JSON), help="Output plan JSON path.")
    parser.add_argument("--resolution", default="9:16", help="Video resolution/aspect setting.")
    parser.add_argument("--max-scenes", type=int, default=None, help="Maximum number of scenes.")
    parser.add_argument("--scene-seconds", type=float, default=8.0, help="Scene length in seconds.")
    parser.add_argument("--model", default="ltx-2-3-pro", help="LTX model name.")
    parser.add_argument("--guidance-scale", type=float, default=9.0, help="LTX guidance scale.")

    parser.add_argument("--assemble-after", action="store_true", help="Run assembly after successful orchestrator run.")
    parser.add_argument("--assembly-dry-run", action="store_true", help="Preview assembly command without creating final MP4.")
    parser.add_argument("--stitching-manifest", default=str(DEFAULT_STITCHING_MANIFEST), help="Stitching manifest for assembly.")
    parser.add_argument("--output", default=str(DEFAULT_ASSEMBLY_OUTPUT), help="Final assembled MP4 output path.")
    parser.add_argument("--report-json", default=str(DEFAULT_ASSEMBLY_REPORT), help="Assembly report JSON path.")

    parser.add_argument("--cleanup-json-on-success", action="store_true", default=True, help="Delete temp JSON/report files after successful run. Enabled by default.")
    parser.add_argument("--no-cleanup-json", action="store_true", help="Disable automatic temp JSON cleanup.")
    parser.add_argument("--cleanup-json", action="store_true", help="Force cleanup after run, even without full success. Use carefully.")
    parser.add_argument("--cleanup-after-dry-run", action="store_true", help="Allow auto cleanup after a successful dry-run. Default keeps dry-run JSON for inspection.")

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
        return preview_cleanup()

    if args.cleanup_now:
        return run_cleanup_now()

    return run_orchestrator(args)


if __name__ == "__main__":
    raise SystemExit(main())
