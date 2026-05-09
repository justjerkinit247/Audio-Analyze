from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_AUDIO_DIR = REPO_ROOT / "inputs" / "audio"
DEFAULT_SEED_DIR = REPO_ROOT / "inputs" / "ltx_seed_images"
DEFAULT_PLAN_JSON = REPO_ROOT / "outputs" / "ltx_video_run" / "holy_cheeks_ltx_plan.json"
DEFAULT_ASSEMBLY_OUTPUT = REPO_ROOT / "outputs" / "ltx_video_run" / "assembled" / "ltx_assembled_reel.mp4"
DEFAULT_ASSEMBLY_REPORT = REPO_ROOT / "outputs" / "ltx_video_run" / "assembled" / "ffmpeg_assembly_report.json"
DEFAULT_STITCHING_MANIFEST = REPO_ROOT / "outputs" / "ltx_video_run" / "orchestration" / "stitching_manifest.json"


AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg"}


def repo_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


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


def print_header(title: str) -> None:
    print("=" * 60)
    print(title)
    print("=" * 60)


def print_json_file(path: Path, max_chars: int = 4000) -> None:
    if not path.exists():
        print(f"JSON file not found: {path}")
        return

    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) > max_chars:
        print(text[:max_chars])
        print(f"\n... truncated preview. Full file: {path.resolve()}")
    else:
        print(text)


def test_imports() -> int:
    print_header("IMPORT TEST")

    try:
        from src.audio_analyze import ltx_orchestrator
        print("OK: src.audio_analyze.ltx_orchestrator")
    except Exception as exc:
        print(f"FAILED: src.audio_analyze.ltx_orchestrator -> {exc}")
        return 1

    try:
        from src.audio_analyze import ltx_ffmpeg_assembler
        print("OK: src.audio_analyze.ltx_ffmpeg_assembler")
    except Exception as exc:
        print(f"FAILED: src.audio_analyze.ltx_ffmpeg_assembler -> {exc}")
        return 1

    try:
        from src.audio_analyze import ltx_holy_cheeks_pipeline
        print("OK: src.audio_analyze.ltx_holy_cheeks_pipeline")
    except Exception as exc:
        print(f"FAILED: src.audio_analyze.ltx_holy_cheeks_pipeline -> {exc}")
        return 1

    print("All core LTX modules imported successfully.")
    return 0


def run_orchestrator(args: argparse.Namespace) -> int:
    from src.audio_analyze.ltx_orchestrator import orchestrate

    audio_path = Path(args.audio).resolve() if args.audio else find_first_audio()

    if audio_path is None:
        print_header("NO AUDIO FILE FOUND")
        print(f"Put a .wav/.mp3/.flac/.m4a/.aac/.ogg file inside: {DEFAULT_AUDIO_DIR}")
        print("Then run:")
        print('py .\\main.py --dry-run')
        return 2

    if not audio_path.exists():
        print(f"Audio file does not exist: {audio_path}")
        return 2

    seed_dir = Path(args.seed_dir).resolve()

    print_header("LTX PROMPT ENGINE / ORCHESTRATOR")
    print(f"Mode: {'LIVE CREDIT-SPENDING RUN' if args.live else 'DRY RUN / NO CREDIT SPEND'}")
    print(f"Audio: {audio_path}")
    print(f"Seed dir: {seed_dir}")
    print(f"Resolution: {args.resolution}")
    print(f"Scene seconds: {args.scene_seconds}")
    print(f"Max scenes: {args.max_scenes}")
    print(f"Model: {args.model}")
    print(f"Guidance scale: {args.guidance_scale}")
    print("")

    result = orchestrate(
        audio=str(audio_path),
        seed_dir=str(seed_dir),
        output_plan=str(Path(args.output_plan).resolve()),
        resolution=args.resolution,
        max_scenes=args.max_scenes,
        scene_seconds=args.scene_seconds,
        model=args.model,
        guidance_scale=args.guidance_scale,
        live=args.live,
    )

    print_header("ORCHESTRATOR RESULT")
    print(json.dumps(result, indent=2))

    return 0 if result.get("status") == "complete" else 1


def run_assembly(args: argparse.Namespace) -> int:
    from src.audio_analyze.ltx_ffmpeg_assembler import assemble_from_manifest

    manifest = Path(args.stitching_manifest).resolve()
    output = Path(args.output).resolve()
    report = Path(args.report_json).resolve()
    audio = Path(args.audio).resolve() if args.audio else None

    print_header("LTX FFMPEG ASSEMBLY")
    print(f"Manifest: {manifest}")
    print(f"Output: {output}")
    print(f"Report: {report}")
    print(f"Audio: {audio if audio else 'None'}")
    print(f"Dry run: {args.dry_run}")

    assembly_report = assemble_from_manifest(
        stitching_manifest=str(manifest),
        output_mp4=str(output),
        audio_path=str(audio) if audio else None,
        report_json=str(report),
        dry_run=args.dry_run,
    )

    print_header("ASSEMBLY RESULT")
    print(json.dumps(assembly_report, indent=2))

    return 0 if assembly_report.get("status") in {"complete", "dry_run"} else 1


def show_outputs() -> int:
    print_header("CURRENT OUTPUT FILES")

    output_root = REPO_ROOT / "outputs" / "ltx_video_run"
    if not output_root.exists():
        print(f"No output folder yet: {output_root}")
        return 0

    files = sorted(
        [p for p in output_root.rglob("*") if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    for path in files[:80]:
        print(repo_relative(path))

    if len(files) > 80:
        print(f"... plus {len(files) - 80} more files")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Main launcher for the Audio-Analyze LTX prompt engine pipeline."
    )

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--test-imports", action="store_true", help="Compile/import smoke test only.")
    mode.add_argument("--dry-run", action="store_true", help="Run the LTX orchestrator without spending credits.")
    mode.add_argument("--live", action="store_true", help="Run the LTX orchestrator live. This can spend API credits.")
    mode.add_argument("--assemble", action="store_true", help="Assemble generated LTX clips using FFmpeg.")
    mode.add_argument("--show-outputs", action="store_true", help="List recent output files.")

    parser.add_argument("--audio", default=None, help="Path to audio file. If omitted, newest file in inputs/audio is used.")
    parser.add_argument("--seed-dir", default=str(DEFAULT_SEED_DIR), help="Seed image directory.")
    parser.add_argument("--output-plan", default=str(DEFAULT_PLAN_JSON), help="Output plan JSON path.")
    parser.add_argument("--resolution", default="9:16", help="Video resolution/aspect setting.")
    parser.add_argument("--max-scenes", type=int, default=None, help="Maximum number of scenes.")
    parser.add_argument("--scene-seconds", type=float, default=8.0, help="Scene length in seconds.")
    parser.add_argument("--model", default="ltx-2-3-pro", help="LTX model name.")
    parser.add_argument("--guidance-scale", type=float, default=9.0, help="LTX guidance scale.")

    parser.add_argument("--stitching-manifest", default=str(DEFAULT_STITCHING_MANIFEST), help="Stitching manifest for assembly.")
    parser.add_argument("--output", default=str(DEFAULT_ASSEMBLY_OUTPUT), help="Final assembled MP4 output path.")
    parser.add_argument("--report-json", default=str(DEFAULT_ASSEMBLY_REPORT), help="Assembly report JSON path.")

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

    if args.live:
        return run_orchestrator(args)

    # Default behavior is safe: dry run, no credit spend.
    return run_orchestrator(args)


if __name__ == "__main__":
    raise SystemExit(main())
