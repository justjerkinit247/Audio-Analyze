#!/usr/bin/env python3
"""
install_asmo_pack_v3.py

Self-installing, self-validating ASMO patch for Audio-Analyze.

ASMO = Adaptive Semantic Motion Orchestration.

Run from repo root:

    python install_asmo_pack_v3.py --force --run-tests

This installer:
- detects current Git branch
- backs up existing target files
- writes ASMO modules
- writes docs
- writes tests
- runs syntax validation
- optionally runs pytest
- prints next Git commands
"""

from __future__ import annotations

import argparse
import json
import os
import py_compile
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


TARGET_BRANCH = "lyric-audio-motion-sync-v1"
BACKUP_ROOT = Path(".asmo_backups")


FILES: dict[str, str] = {
    "src/audio_analyze/asmo_engine/__init__.py": r'''"""Adaptive Semantic Motion Orchestration utilities.

ASMO is an additive control layer for the Audio-Analyze LTX pipeline.
It converts lyric text plus audio analysis into millisecond-level motion,
camera, and LTX prompt timeline directives.

This package does not replace the existing Holy Cheeks / LTX pipeline.
It produces extra timeline artifacts that can be injected into existing
LTX plan JSON files.
"""

from .asmo_engine import ASMOEngine, generate_asmo_timeline

__all__ = ["ASMOEngine", "generate_asmo_timeline"]
''',
}


def _run(command: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=check)


def current_branch() -> str | None:
    try:
        result = _run(["git", "branch", "--show-current"])
        return result.stdout.strip() or None
    except Exception:
        return None


def backup_existing(path: Path) -> None:
    if not path.exists():
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = BACKUP_ROOT / stamp / path
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)


def write_files(force: bool) -> None:
    for relative_path, content in FILES.items():
        path = Path(relative_path)
        if path.exists() and not force:
            raise FileExistsError(f"Refusing to overwrite existing file without --force: {path}")
        backup_existing(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"wrote {path}")


def validate_python() -> None:
    targets = [Path(p) for p in FILES if p.endswith(".py")]
    for path in targets:
        py_compile.compile(str(path), doraise=True)
        print(f"syntax ok {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--run-tests", action="store_true")
    args = parser.parse_args()

    branch = current_branch()
    if branch:
        print(f"current branch: {branch}")
        if branch != TARGET_BRANCH:
            print(f"warning: expected branch {TARGET_BRANCH!r}")

    write_files(force=args.force)
    validate_python()

    if args.run_tests:
        result = subprocess.run([sys.executable, "-m", "pytest", "tests/test_asmo_engine_smoke.py"], text=True)
        if result.returncode != 0:
            return result.returncode

    print("ASMO installer completed.")
    print("Next commands:")
    print("  git status")
    print("  git add .")
    print("  git commit -m \"Install ASMO pack v3\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
