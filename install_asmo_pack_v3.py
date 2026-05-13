#!/usr/bin/env python3
"""
install_asmo_pack_v3.py

Self-validating full installer payload for Audio-Analyze ASMO.

ASMO = Adaptive Semantic Motion Orchestration.

Run from repo root:

    python install_asmo_pack_v3.py --force --run-tests

This installer:
- detects current Git branch
- confirms the full ASMO payload exists
- backs up target files when --force is used
- validates every ASMO Python module with py_compile
- optionally runs pytest smoke tests
- prints next Git commands
"""

from __future__ import annotations

import argparse
import py_compile
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


TARGET_BRANCH = "lyric-audio-motion-sync-v1"
BACKUP_ROOT = Path(".asmo_backups")

FULL_INSTALLER_PAYLOAD: list[Path] = [
    Path("src/audio_analyze/asmo_engine/__init__.py"),
    Path("src/audio_analyze/asmo_engine/timecode.py"),
    Path("src/audio_analyze/asmo_engine/lyric_loader.py"),
    Path("src/audio_analyze/asmo_engine/beat_grid_engine.py"),
    Path("src/audio_analyze/asmo_engine/motion_vector_engine.py"),
    Path("src/audio_analyze/asmo_engine/camera_inertia_engine.py"),
    Path("src/audio_analyze/asmo_engine/timeline_exporter.py"),
    Path("src/audio_analyze/asmo_engine/asmo_engine.py"),
    Path("src/audio_analyze/asmo_engine/ltx_prompt_injector.py"),
    Path("src/audio_analyze/asmo_engine/cli.py"),
    Path("tests/test_asmo_engine_smoke.py"),
    Path("docs/asmo_engine_usage.md"),
]

OPTIONAL_PAYLOAD: list[Path] = [
    Path("src/audio_analyze/asmo_engine/audio_fingerprint_engine.py"),
    Path("src/audio_analyze/asmo_engine/motion_ontology.py"),
    Path(".github/workflows/asmo-smoke-test.yml"),
    Path("scripts/run_asmo_smoke_test.ps1"),
]


def run(command: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=check)


def current_branch() -> str | None:
    try:
        result = run(["git", "branch", "--show-current"])
        return result.stdout.strip() or None
    except Exception:
        return None


def ensure_repo_root() -> None:
    if not Path(".git").exists():
        raise SystemExit("Run this installer from the repository root. Could not find .git directory.")


def confirm_payload() -> None:
    missing = [path for path in FULL_INSTALLER_PAYLOAD if not path.exists()]

    if missing:
        print("Full installer payload is incomplete. Missing required files:")
        for path in missing:
            print(f"  missing {path}")
        raise SystemExit(2)

    print("Full installer payload present:")
    for path in FULL_INSTALLER_PAYLOAD:
        print(f"  ok {path}")

    present_optional = [path for path in OPTIONAL_PAYLOAD if path.exists()]
    if present_optional:
        print("Optional support payload present:")
        for path in present_optional:
            print(f"  ok {path}")


def backup_payload() -> None:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for path in FULL_INSTALLER_PAYLOAD + OPTIONAL_PAYLOAD:
        if not path.exists():
            continue

        backup_path = BACKUP_ROOT / stamp / path
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_path)
        print(f"backup {path} -> {backup_path}")


def validate_python() -> None:
    py_files = [
        path
        for path in FULL_INSTALLER_PAYLOAD + OPTIONAL_PAYLOAD
        if path.suffix == ".py" and path.exists()
    ]

    for path in py_files:
        py_compile.compile(str(path), doraise=True)
        print(f"syntax ok {path}")


def run_tests() -> int:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_asmo_engine_smoke.py", "-v"],
        text=True,
    ).returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Create a timestamped backup snapshot of payload files.")
    parser.add_argument("--run-tests", action="store_true", help="Run ASMO smoke tests after validation.")
    args = parser.parse_args()

    ensure_repo_root()

    branch = current_branch()
    if branch:
        print(f"current branch: {branch}")
        if branch != TARGET_BRANCH:
            print(f"warning: expected branch {TARGET_BRANCH!r}")

    confirm_payload()

    if args.force:
        backup_payload()

    validate_python()

    if args.run_tests:
        code = run_tests()
        if code != 0:
            return code

    print("ASMO full installer payload completed.")
    print("Next commands:")
    print("  git status")
    print("  git add install_asmo_pack_v3.py")
    print("  git commit -m \"Complete ASMO full installer payload\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
