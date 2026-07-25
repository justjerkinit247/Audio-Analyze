from __future__ import annotations

from getpass import getpass
from pathlib import Path
from typing import Any
import argparse
import json
import os
import shutil
import subprocess
import sys

from PIL import Image

from .ltx_auto_audio_orchestrator import run_auto_audio_orchestrator, submit_fresh_run_plan
from .ltx_choreography_profiles import (
    AUTO_PROFILE,
    PROFILE_ENV_VAR,
    normalize_requested_profile,
)
from .ltx_live_run import (
    DEFAULT_GUIDANCE_SCALE,
    DEFAULT_MODEL,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OLLAMA_URL,
    DEFAULT_SCENE_SECONDS,
    _ask_start_offset,
    _choose_file,
    _ensure_ollama,
    _make_run_paths,
    _open_file,
    _read_json,
    _repo_root,
    _validate_gemma_exact_payload,
    _write_text,
)
from .ltx_seed_mapper import ALLOWED_IMAGES, collect_labeled_seed_images

MIN_SCENES = 1
MAX_SCENES = 20
RESOLUTION_CHOICES = ("auto", "9:16", "16:9", "1:1")


def _choose_directory(title: str, initial_dir: Path) -> Path:
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(
            title=title,
            initialdir=str(initial_dir),
        )
        root.destroy()
        if selected:
            return Path(selected).resolve()
    except Exception:
        pass

    entered = input(f"{title}\nPaste the full folder path: ").strip().strip('"')
    if not entered:
        raise RuntimeError("No seed-image folder was selected.")
    return Path(entered).expanduser().resolve()


def _validate_scene_count(value: int) -> int:
    count = int(value)
    if not MIN_SCENES <= count <= MAX_SCENES:
        raise ValueError(
            f"Scene count must be between {MIN_SCENES} and {MAX_SCENES}; got {count}."
        )
    return count


def _collect_labeled_scene_seeds(
    seed_dir: Path,
    requested_count: int | None,
) -> list[Path]:
    if not seed_dir.is_dir():
        raise NotADirectoryError(f"Seed-image folder not found: {seed_dir}")

    labeled, unlabeled = collect_labeled_seed_images(seed_dir)
    if unlabeled:
        names = ", ".join(path.name for path in unlabeled)
        raise RuntimeError(
            "Every seed must have an explicit scene label such as scene_01 or "
            f"scene_02. Unlabeled files: {names}"
        )

    duplicates = {
        number: paths for number, paths in labeled.items() if len(paths) != 1
    }
    if duplicates:
        details = "; ".join(
            f"scene_{number:02d}: {', '.join(path.name for path in paths)}"
            for number, paths in sorted(duplicates.items())
        )
        raise RuntimeError(f"Duplicate scene labels are not allowed: {details}")

    if requested_count is None:
        requested_count = len(labeled)
    count = _validate_scene_count(requested_count)

    missing = [number for number in range(1, count + 1) if number not in labeled]
    if missing:
        labels = ", ".join(f"scene_{number:02d}" for number in missing)
        raise RuntimeError(f"Missing required labeled seed images: {labels}")

    return [labeled[number][0] for number in range(1, count + 1)]


def _single_seed_as_scene_one(seed: Path, staging_dir: Path) -> list[Path]:
    if not seed.is_file() or seed.suffix.lower() not in ALLOWED_IMAGES:
        raise FileNotFoundError(f"Seed image not found or unsupported: {seed}")
    staging_dir.mkdir(parents=True, exist_ok=True)
    destination = staging_dir / f"scene_01_{seed.name}"
    shutil.copy2(seed, destination)
    return [destination]


def _infer_resolution(seed_paths: list[Path]) -> str:
    categories: list[str] = []
    for path in seed_paths:
        with Image.open(path) as image:
            width, height = image.size
        if width <= 0 or height <= 0:
            raise ValueError(f"Seed image has invalid dimensions: {path}")
        ratio = width / height
        if ratio >= 1.2:
            categories.append("16:9")
        elif ratio <= 0.8:
            categories.append("9:16")
        else:
            categories.append("1:1")

    first = categories[0]
    if any(category != first for category in categories[1:]):
        raise RuntimeError(
            "All seed images in one run must use the same orientation/aspect category."
        )
    return first


def _copy_scene_seeds(seed_paths: list[Path], destination: Path) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=False)
    copied: list[Path] = []
    for path in seed_paths:
        target = destination / path.name
        shutil.copy2(path, target)
        copied.append(target)
    return copied


def _validate_multi_scene_plan(
    plan: dict[str, Any],
    report: dict[str, Any],
    *,
    run_id: str,
    seed_filenames: list[str],
) -> list[dict[str, Any]]:
    problems: list[str] = []
    results = list(plan.get("results") or [])

    if report.get("status") != "complete":
        problems.append(f"orchestrator status is {report.get('status')!r}")
    if (plan.get("fresh_run") or {}).get("run_id") != run_id:
        problems.append("fresh-run ID does not match")
    if plan.get("plan_reuse_allowed") is not False:
        problems.append("plan is not marked fresh-only")
    if len(results) != len(seed_filenames):
        problems.append(
            f"plan contains {len(results)} scenes but {len(seed_filenames)} were requested"
        )

    for index, expected_filename in enumerate(seed_filenames, start=1):
        if index > len(results):
            break
        scene = results[index - 1]
        scene_problems: list[str] = []
        prompt = _validate_gemma_exact_payload(scene, scene_problems)

        if int(scene.get("clip_index") or 0) != index:
            scene_problems.append(
                f"clip index is {scene.get('clip_index')!r} instead of {index}"
            )
        if scene.get("seed_filename_used_for_prompt_hint") != expected_filename:
            scene_problems.append(
                "Gemma did not receive the expected seed filename "
                f"{expected_filename!r}"
            )
        if scene.get("prompt_transport_mode") != "audio_and_image_to_video":
            scene_problems.append("prompt transport is not audio-and-image-to-video")

        subject_policy = scene.get("subject_count_policy") or {}
        motion = str(
            (scene.get("filename_hint_expansion") or {}).get("ltx_motion_prompt")
            or ""
        )
        if subject_policy.get("multiple_subjects") and any(
            token in motion.lower()
            for token in ("solitary", "solo dancer", "lone dancer")
        ):
            scene_problems.append(
                "multiple-subject scene still contains solo/solitary wording"
            )

        choreography_policy = scene.get("choreography_policy") or {}
        profile_id = choreography_policy.get("profile_id") or scene.get(
            "tap_motion_profile"
        )
        for phrase in choreography_policy.get("required_prompt_phrases") or []:
            if phrase not in prompt:
                scene_problems.append(
                    f"choreography profile {profile_id!r} prompt is missing: {phrase}"
                )

        problems.extend(f"Scene {index}: {problem}" for problem in scene_problems)

    if problems:
        raise RuntimeError(
            "Fresh multi-scene plan validation failed:\n- "
            + "\n- ".join(problems)
        )
    return results


def _prompt_bundle(scenes: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for scene in scenes:
        index = int(scene.get("clip_index") or len(blocks) + 1)
        filename = scene.get("seed_filename_used_for_prompt_hint") or "unknown"
        blocks.append(
            f"================ SCENE {index:02d}: {filename} ================\n"
            f"{str(scene.get('prompt_text') or '').strip()}"
        )
    return "\n\n".join(blocks).strip() + "\n"


def _ffmpeg_executable() -> str | None:
    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    try:
        from imageio_ffmpeg import get_ffmpeg_exe

        return get_ffmpeg_exe()
    except Exception:
        return None


def _concat_file_line(path: Path) -> str:
    normalized = path.resolve().as_posix().replace("'", r"'\''")
    return f"file '{normalized}'"


def _stitch_downloaded_scenes(
    results: list[dict[str, Any]],
    run_root: Path,
) -> Path | None:
    mp4_paths: list[Path] = []
    for result in results:
        path_text = result.get("downloaded_mp4_resolved_path")
        if not path_text:
            return None
        path = Path(str(path_text))
        if not path.is_file():
            return None
        mp4_paths.append(path)

    if len(mp4_paths) < 2:
        return mp4_paths[0] if mp4_paths else None

    ffmpeg = _ffmpeg_executable()
    if not ffmpeg:
        print("FFmpeg was not found; scene MP4 files were generated but not stitched.")
        return None

    concat_list = run_root / "scene_concat_list.txt"
    concat_list.write_text(
        "\n".join(_concat_file_line(path) for path in mp4_paths) + "\n",
        encoding="utf-8",
    )
    output = run_root / "stitched_multi_scene.mp4"

    copy_command = [
        ffmpeg,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list),
        "-c",
        "copy",
        str(output),
    ]
    copied = subprocess.run(copy_command, capture_output=True, text=True)
    if copied.returncode == 0 and output.is_file():
        return output

    transcode_command = [
        ffmpeg,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list),
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(output),
    ]
    transcoded = subprocess.run(transcode_command, capture_output=True, text=True)
    if transcoded.returncode != 0 or not output.is_file():
        print("FFmpeg could not stitch the generated scenes.")
        return None
    return output


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _show_multi_scene_result(summary: dict[str, Any], run_root: Path) -> None:
    print("\n================ MULTI-SCENE LIVE RESULT ================")
    print(f"Status: {summary.get('status')}")
    print(f"Scene count: {summary.get('scene_count')}")
    print(f"Successful scenes: {summary.get('successful_scene_count')}")
    print(f"Failed scenes: {summary.get('failed_scene_count')}")
    stitched = summary.get("stitched_mp4_resolved_path")
    if stitched and Path(str(stitched)).is_file():
        print(f"Stitched video: {stitched}")
        _open_file(Path(str(stitched)).parent)
    else:
        print(f"Run folder: {run_root}")
        _open_file(run_root)


def run_interactive(args: argparse.Namespace) -> int:
    repo = _repo_root()
    audio = Path(args.audio).expanduser().resolve() if args.audio else _choose_file(
        "Select the source audio",
        [
            ("Audio files", "*.wav *.mp3 *.flac *.m4a *.aac *.ogg *.aiff *.aif"),
            ("All files", "*.*"),
        ],
        repo / "inputs" / "audio",
    )
    if not audio.is_file():
        raise FileNotFoundError(f"Audio file not found: {audio}")

    paths = _make_run_paths(repo)
    if args.seed:
        single_staging = paths.root / "_single_seed_staging"
        seed_paths = _single_seed_as_scene_one(
            Path(args.seed).expanduser().resolve(),
            single_staging,
        )
        requested_count = 1
    else:
        source_seed_dir = (
            Path(args.seed_dir).expanduser().resolve()
            if args.seed_dir
            else _choose_directory(
                "Select the folder containing labeled scene seed images",
                repo / "inputs" / "ltx_seed_images",
            )
        )
        seed_paths = _collect_labeled_scene_seeds(
            source_seed_dir,
            args.max_scenes,
        )
        requested_count = len(seed_paths)

    copied_seeds = _copy_scene_seeds(seed_paths, paths.seed_dir)
    seed_filenames = [path.name for path in copied_seeds]

    resolution = (
        _infer_resolution(copied_seeds)
        if args.resolution == "auto"
        else args.resolution
    )
    start_offset = args.start if args.start is not None else _ask_start_offset(0.0)
    if start_offset < 0:
        raise ValueError("Audio starting second cannot be negative.")

    requested_profile = normalize_requested_profile(args.choreography_profile)
    _ensure_ollama(args.ollama_url, args.ollama_model)

    print("\nBuilding a brand-new isolated multi-scene plan...")
    print(f"Run ID: {paths.run_id}")
    print(f"Audio: {audio.name}")
    print(f"Scene count: {requested_count}")
    print(f"Resolution: {resolution}")
    print(f"Choreography policy request: {requested_profile}")
    for index, filename in enumerate(seed_filenames, start=1):
        print(f"Scene {index:02d} seed: {filename}")

    previous_profile = os.environ.get(PROFILE_ENV_VAR)
    os.environ[PROFILE_ENV_VAR] = requested_profile
    try:
        report = run_auto_audio_orchestrator(
            audio=audio,
            seed_dir=paths.seed_dir,
            output_plan=paths.plan,
            report_json=paths.report,
            run_id=paths.run_id,
            resolution=resolution,
            max_scenes=requested_count,
            scene_seconds=args.scene_seconds,
            start_offset_seconds=start_offset,
            model=args.model,
            guidance_scale=args.guidance_scale,
            filename_hint_provider="ollama",
            filename_hint_model=args.ollama_model,
            allow_sorted_seed_fallback=False,
            allow_duplicate_seed_reuse=False,
            live=False,
        )
    finally:
        if previous_profile is None:
            os.environ.pop(PROFILE_ENV_VAR, None)
        else:
            os.environ[PROFILE_ENV_VAR] = previous_profile

    plan = _read_json(paths.plan)
    report = _read_json(paths.report) if paths.report.is_file() else report
    scenes = _validate_multi_scene_plan(
        plan,
        report,
        run_id=paths.run_id,
        seed_filenames=seed_filenames,
    )

    prompts = _prompt_bundle(scenes)
    _write_text(paths.prompt, prompts)

    print("\n================ MULTI-SCENE PLAN READY ================")
    print(f"Scene count: {len(scenes)}")
    print(f"Resolution: {resolution}")
    print("Gemma exact payload verified for every scene: YES")
    print(f"Prompt bundle: {paths.prompt}")
    for scene in scenes:
        policy = scene.get("choreography_policy") or {}
        synthesis = scene.get("gemma_final_prompt_synthesis") or {}
        taps = (scene.get("tap_sync") or {}).get(
            "primary_sync_targets_seconds"
        ) or []
        print(
            f"Scene {int(scene.get('clip_index') or 0):02d}: "
            f"{len(str(scene.get('prompt_text') or ''))}/5000 chars, "
            f"{len(taps)} taps, "
            f"profile={policy.get('profile_id') or scene.get('tap_motion_profile')}, "
            f"Gemma={synthesis.get('model')}"
        )
    print("Paid submissions so far: NONE")
    _open_file(paths.prompt)

    if args.dry_run:
        print("Dry run complete. Nothing was submitted.")
        return 0

    request_count = len(scenes)
    confirmation = input(
        f"\nType LIVE to submit {request_count} paid LTX request"
        f"{'s' if request_count != 1 else ''}: "
    ).strip().upper()
    if confirmation != "LIVE":
        print("Cancelled. Nothing was submitted.")
        return 0

    if not os.environ.get("LTXV_API_KEY", "").strip():
        key = getpass("Paste the LTX API key; typing stays hidden: ").strip()
        if not key:
            raise RuntimeError("No LTX API key was entered.")
        os.environ["LTXV_API_KEY"] = key

    submission_dir = paths.root / "submissions"
    results: list[dict[str, Any]] = []
    for scene in scenes:
        index = int(scene["clip_index"])
        print(f"\nSubmitting scene {index:02d} of {request_count}...")
        result = submit_fresh_run_plan(
            plan_json=paths.plan,
            output_json=submission_dir / f"scene_{index:02d}_live_result.json",
            expected_run_id=paths.run_id,
            clip_index=index,
            model=args.model,
            guidance_scale=args.guidance_scale,
            live=True,
            allow_sorted_seed_fallback=False,
        )
        results.append(result)

    failed = [result for result in results if result.get("status") == "failed"]
    stitched = _stitch_downloaded_scenes(results, paths.root) if not failed else None
    summary = {
        "status": "complete" if not failed else "complete_with_failures",
        "verified_run_id": paths.run_id,
        "fresh_run_verified": True,
        "scene_count": len(results),
        "successful_scene_count": len(results) - len(failed),
        "failed_scene_count": len(failed),
        "resolution": resolution,
        "results": results,
        "stitched_mp4_resolved_path": str(stitched.resolve()) if stitched else None,
    }
    _write_json(paths.live_result, summary)
    _show_multi_scene_result(summary, paths.root)
    return 0 if not failed else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Interactive fresh-run LTX audio-and-image pipeline for one to twenty "
            "explicitly labeled seed-image scenes."
        )
    )
    parser.add_argument("--audio", default=None, help="Optional source audio path.")
    parser.add_argument(
        "--seed-dir",
        default=None,
        help="Folder containing scene_01 through scene_20 labeled seed images.",
    )
    parser.add_argument(
        "--seed",
        default=None,
        help="Backward-compatible single seed image path.",
    )
    parser.add_argument("--max-scenes", type=int, default=None)
    parser.add_argument("--start", type=float, default=None, help="Audio starting second.")
    parser.add_argument("--scene-seconds", type=float, default=DEFAULT_SCENE_SECONDS)
    parser.add_argument(
        "--resolution",
        choices=RESOLUTION_CHOICES,
        default="auto",
        help="Output aspect ratio. Auto infers one shared category from all seeds.",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--guidance-scale", type=float, default=DEFAULT_GUIDANCE_SCALE)
    parser.add_argument("--ollama-model", default=DEFAULT_OLLAMA_MODEL)
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument(
        "--choreography-profile",
        default=AUTO_PROFILE,
        help=(
            "Per-run choreography policy. Use auto for seed-directed selection or "
            "supply a configured profile ID."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and validate every scene without offering live submission.",
    )
    return parser


def main() -> None:
    try:
        raise SystemExit(run_interactive(build_parser().parse_args()))
    except KeyboardInterrupt:
        print("\nCancelled.")
        raise SystemExit(130)
    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
