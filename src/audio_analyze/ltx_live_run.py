from __future__ import annotations

from dataclasses import dataclass
from getpass import getpass
from pathlib import Path
from typing import Any
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

from .ltx_auto_audio_orchestrator import (
    generate_run_id,
    run_auto_audio_orchestrator,
    submit_fresh_run_plan,
)
from .ltx_choreography_profiles import (
    AUTO_PROFILE,
    PROFILE_ENV_VAR,
    normalize_requested_profile,
)


DEFAULT_MODEL = "ltx-2-3-pro"
DEFAULT_GUIDANCE_SCALE = 9.0
DEFAULT_SCENE_SECONDS = 8.0
DEFAULT_OLLAMA_MODEL = "gemma3:4b"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
REQUIRED_MARKERS = (
    "[SUBJECT_LOCK]",
    "[AUDIO_TIMING]",
    "[TAP_SYNC]",
    "[MOTION_PROMPT]",
    "[NEGATIVE_PROMPT]",
)


@dataclass(frozen=True)
class RunPaths:
    run_id: str
    root: Path
    seed_dir: Path
    plan: Path
    report: Path
    prompt: Path
    live_result: Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _choose_file(title: str, filetypes: list[tuple[str, str]], initial_dir: Path) -> Path:
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askopenfilename(
            title=title,
            initialdir=str(initial_dir),
            filetypes=filetypes,
        )
        root.destroy()
        if selected:
            return Path(selected).resolve()
    except Exception:
        pass

    entered = input(f"{title}\nPaste the full file path: ").strip().strip('"')
    if not entered:
        raise RuntimeError("No file was selected.")
    return Path(entered).expanduser().resolve()


def _ask_start_offset(default: float = 0.0) -> float:
    answer = input(f"Audio starting second [{default:g}]: ").strip()
    if not answer:
        return float(default)
    value = float(answer)
    if value < 0:
        raise ValueError("Audio starting second cannot be negative.")
    return value


def _ensure_ollama(url: str, model: str) -> None:
    tags_url = f"{url.rstrip('/')}/api/tags"

    def read_tags() -> dict[str, Any] | None:
        try:
            with urllib.request.urlopen(tags_url, timeout=4) as response:
                return json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError):
            return None

    tags = read_tags()
    if tags is None:
        try:
            creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
            )
        except (FileNotFoundError, OSError) as exc:
            raise RuntimeError("Ollama is not installed or is not available on PATH.") from exc

        for _ in range(25):
            time.sleep(1)
            tags = read_tags()
            if tags is not None:
                break
    if tags is None:
        raise RuntimeError("Ollama did not start or respond.")

    installed = {
        str(item.get("name") or item.get("model") or "")
        for item in tags.get("models", [])
    }
    if model not in installed:
        print(f"Downloading Ollama model {model}...")
        completed = subprocess.run(["ollama", "pull", model], check=False)
        if completed.returncode != 0:
            raise RuntimeError(f"Unable to download Ollama model {model}.")


def _make_run_paths(repo: Path) -> RunPaths:
    run_id = generate_run_id()
    root = repo / "outputs" / "ltx_video_run" / "live_runs" / run_id
    return RunPaths(
        run_id=run_id,
        root=root,
        seed_dir=root / "seed",
        plan=root / "validated_plan.json",
        report=root / "orchestrator_report.json",
        prompt=root / "final_prompt_sent_to_ltx.txt",
        live_result=root / "live_result.json",
    )


def _validate_plan(
    plan: dict[str, Any],
    report: dict[str, Any],
    *,
    run_id: str,
    seed_filename: str,
) -> dict[str, Any]:
    problems: list[str] = []
    results = list(plan.get("results") or [])
    scene = results[0] if results else None

    if report.get("status") != "complete":
        problems.append(f"orchestrator status is {report.get('status')!r}")
    if not scene:
        problems.append("plan contains no scene")
    if (plan.get("fresh_run") or {}).get("run_id") != run_id:
        problems.append("fresh-run ID does not match")
    if plan.get("plan_reuse_allowed") is not False:
        problems.append("plan is not marked fresh-only")

    if scene:
        prompt = str(scene.get("prompt_text") or "")
        if scene.get("seed_filename_used_for_prompt_hint") != seed_filename:
            problems.append("Ollama did not receive the exact seed filename")
        if scene.get("prompt_transport_mode") != "audio_and_image_to_video":
            problems.append("prompt transport is not audio-and-image-to-video")
        if len(prompt) > 5000:
            problems.append(f"prompt is over 5,000 characters ({len(prompt)})")
        for marker in REQUIRED_MARKERS:
            if marker not in prompt:
                problems.append(f"prompt is missing {marker}")

        subject_policy = scene.get("subject_count_policy") or {}
        motion = str(
            (scene.get("filename_hint_expansion") or {}).get("ltx_motion_prompt") or ""
        )
        if subject_policy.get("multiple_subjects") and any(
            token in motion.lower()
            for token in ("solitary", "solo dancer", "lone dancer")
        ):
            problems.append("multiple-subject scene still contains solo/solitary wording")

        choreography_policy = scene.get("choreography_policy") or {}
        profile_id = choreography_policy.get("profile_id") or scene.get(
            "tap_motion_profile"
        )
        for phrase in choreography_policy.get("required_prompt_phrases") or []:
            if phrase not in prompt:
                problems.append(
                    f"choreography profile {profile_id!r} prompt is missing: {phrase}"
                )

    if problems:
        raise RuntimeError(
            "Fresh plan validation failed:\n- " + "\n- ".join(problems)
        )
    return scene


def _open_file(path: Path) -> None:
    try:
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except OSError:
        pass


def _show_result(result: dict[str, Any], run_root: Path) -> None:
    print("\n================ LIVE RESULT ================")
    print(f"Status: {result.get('status')}")
    print(f"Verified run ID: {result.get('verified_run_id')}")
    print(f"Fresh-run verified: {result.get('fresh_run_verified')}")

    if result.get("status") == "failed":
        print(f"LTX error: {result.get('error')}")
        _open_file(run_root)
        return

    video = result.get("downloaded_mp4_resolved_path")
    if video and Path(str(video)).is_file():
        print(f"Video: {video}")
        _open_file(Path(str(video)).parent)
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
    seed = Path(args.seed).expanduser().resolve() if args.seed else _choose_file(
        "Select the seed image",
        [("Image files", "*.png *.jpg *.jpeg *.webp"), ("All files", "*.*")],
        repo / "inputs" / "ltx_seed_images",
    )

    if not audio.is_file():
        raise FileNotFoundError(f"Audio file not found: {audio}")
    if not seed.is_file():
        raise FileNotFoundError(f"Seed image not found: {seed}")

    start_offset = args.start if args.start is not None else _ask_start_offset(0.0)
    if start_offset < 0:
        raise ValueError("Audio starting second cannot be negative.")

    requested_profile = normalize_requested_profile(args.choreography_profile)
    _ensure_ollama(args.ollama_url, args.ollama_model)

    paths = _make_run_paths(repo)
    paths.seed_dir.mkdir(parents=True, exist_ok=False)
    copied_seed = paths.seed_dir / seed.name
    shutil.copy2(seed, copied_seed)

    print("\nBuilding a brand-new isolated plan...")
    print(f"Run ID: {paths.run_id}")
    print(f"Audio: {audio.name}")
    print(f"Seed: {seed.name}")
    print(f"Choreography policy request: {requested_profile}")

    previous_profile = os.environ.get(PROFILE_ENV_VAR)
    os.environ[PROFILE_ENV_VAR] = requested_profile
    try:
        report = run_auto_audio_orchestrator(
            audio=audio,
            seed_dir=paths.seed_dir,
            output_plan=paths.plan,
            report_json=paths.report,
            run_id=paths.run_id,
            resolution="9:16",
            max_scenes=1,
            scene_seconds=args.scene_seconds,
            start_offset_seconds=start_offset,
            model=args.model,
            guidance_scale=args.guidance_scale,
            filename_hint_provider="ollama",
            filename_hint_model=args.ollama_model,
            allow_sorted_seed_fallback=True,
            live=False,
        )
    finally:
        if previous_profile is None:
            os.environ.pop(PROFILE_ENV_VAR, None)
        else:
            os.environ[PROFILE_ENV_VAR] = previous_profile

    plan = _read_json(paths.plan)
    report = _read_json(paths.report) if paths.report.is_file() else report
    scene = _validate_plan(
        plan,
        report,
        run_id=paths.run_id,
        seed_filename=seed.name,
    )

    prompt = str(scene["prompt_text"])
    _write_text(paths.prompt, prompt)
    policy = scene.get("choreography_policy") or {}

    print("\n================ PLAN READY ================")
    print(f"Prompt length: {len(prompt)} / 5000")
    print(f"Choreography profile: {policy.get('profile_id') or scene.get('tap_motion_profile')}")
    print(f"Profile selection: {policy.get('selection_method')}")
    print(
        "Tap target policy: "
        f"{(policy.get('target_selection') or {}).get('mode', 'all_reliable')}"
    )
    print(
        "Tap count: "
        f"{len((scene.get('tap_sync') or {}).get('primary_sync_targets_seconds') or [])}"
    )
    print(f"Prompt: {paths.prompt}")
    print("Paid submissions so far: NONE")
    _open_file(paths.prompt)

    if args.dry_run:
        print("Dry run complete. Nothing was submitted.")
        return 0

    confirmation = input("\nType LIVE to submit exactly one paid LTX request: ").strip()
    if confirmation != "LIVE":
        print("Cancelled. Nothing was submitted.")
        return 0

    if not os.environ.get("LTXV_API_KEY", "").strip():
        key = getpass("Paste the LTX API key; typing stays hidden: ").strip()
        if not key:
            raise RuntimeError("No LTX API key was entered.")
        os.environ["LTXV_API_KEY"] = key

    result = submit_fresh_run_plan(
        plan_json=paths.plan,
        output_json=paths.live_result,
        expected_run_id=paths.run_id,
        clip_index=1,
        model=args.model,
        guidance_scale=args.guidance_scale,
        live=True,
        allow_sorted_seed_fallback=True,
    )
    _show_result(result, paths.root)
    return 0 if result.get("status") != "failed" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="One-command interactive fresh-run LTX audio-and-image pipeline."
    )
    parser.add_argument("--audio", default=None, help="Optional source audio path.")
    parser.add_argument("--seed", default=None, help="Optional seed image path.")
    parser.add_argument("--start", type=float, default=None, help="Audio starting second.")
    parser.add_argument("--scene-seconds", type=float, default=DEFAULT_SCENE_SECONDS)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--guidance-scale", type=float, default=DEFAULT_GUIDANCE_SCALE)
    parser.add_argument("--ollama-model", default=DEFAULT_OLLAMA_MODEL)
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument(
        "--choreography-profile",
        default=AUTO_PROFILE,
        help=(
            "Per-run choreography policy. Use auto for seed-directed selection or "
            "supply a configured profile ID for an explicit controlled run."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and validate without offering live submission.",
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
