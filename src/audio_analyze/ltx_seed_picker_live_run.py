from __future__ import annotations

from pathlib import Path
import argparse
import shutil
import sys
import tempfile

from . import ltx_multi_scene_live_run as base
from .ltx_seed_mapper import ALLOWED_IMAGES, scene_number_from_name
from .ltx_filename_hint_expander import SCENE_PREFIX_PATTERNS, clean_scene_hint


DEFAULT_GUIDANCE_SCALE = 12.0


def _choose_seed_files(title: str, initial_dir: Path) -> list[Path]:
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askopenfilenames(
            title=title,
            initialdir=str(initial_dir),
            filetypes=[
                ("Seed images", "*.png *.jpg *.jpeg *.webp"),
                ("All files", "*.*"),
            ],
        )
        root.destroy()
        if selected:
            return [Path(value).resolve() for value in selected]
    except Exception:
        pass

    entered = input(
        f"{title}\nPaste one or more full image paths separated by semicolons: "
    ).strip()
    if not entered:
        raise RuntimeError("No seed images were selected.")
    return [
        Path(value.strip().strip('"')).expanduser().resolve()
        for value in entered.split(";")
        if value.strip()
    ]


def _ordered_selected_seed_files(
    selected: list[Path],
    requested_count: int | None,
) -> list[Path]:
    if not selected:
        raise RuntimeError("No seed images were selected.")

    unique: list[Path] = []
    seen: set[str] = set()
    for path in selected:
        resolved = path.expanduser().resolve()
        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)
        if not resolved.is_file() or resolved.suffix.lower() not in ALLOWED_IMAGES:
            raise FileNotFoundError(f"Seed image not found or unsupported: {resolved}")
        if not clean_scene_hint(resolved.name):
            raise ValueError(f"Seed filename needs a description: {resolved.name}")
        unique.append(resolved)

    count = base._validate_scene_count(len(unique) if requested_count is None else requested_count)
    if len(unique) != count:
        raise RuntimeError(
            f"Selected {len(unique)} seed images but the requested scene count is {count}. "
            "Select exactly one image per scene."
        )

    # Existing labels are optional ordering hints, never required scene IDs.
    # Stable sorting retains selection order for repeated labels.
    if all(scene_number_from_name(path) is not None for path in unique):
        return sorted(unique, key=lambda path: scene_number_from_name(path))
    return unique


def _copy_selected_for_pipeline(selected: list[Path], destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for index, source in enumerate(selected, start=1):
        description = source.stem
        for pattern in SCENE_PREFIX_PATTERNS:
            description = pattern.sub("", description)
        filename = f"scene_{index:02d}_{description}{source.suffix}"
        shutil.copy2(source, destination / filename)


def run_interactive(args: argparse.Namespace) -> int:
    repo = base._repo_root()
    if not args.audio:
        args.audio = str(
            base._choose_file(
                "Select the source audio",
                [
                    ("Audio files", "*.wav *.mp3 *.flac *.m4a *.aac *.ogg *.aiff *.aif"),
                    ("All files", "*.*"),
                ],
                repo / "inputs" / "audio",
            )
        )

    if args.seed:
        selected = [Path(args.seed)]
    elif args.seed_dir:
        seed_dir = Path(args.seed_dir).expanduser().resolve()
        if not seed_dir.is_dir():
            raise NotADirectoryError(f"Seed-image folder not found: {seed_dir}")
        selected = sorted(
            (path for path in seed_dir.iterdir()
             if path.is_file() and path.suffix.lower() in ALLOWED_IMAGES),
            key=lambda path: path.name.lower(),
        )
    else:
        selected = _choose_seed_files(
            "Select 1 to 20 seed images with descriptive filenames (numbers optional)",
            repo / "inputs" / "ltx_seed_images",
        )
    ordered = _ordered_selected_seed_files(selected, args.max_scenes)

    print("\nSeed order for this run:")
    for index, seed in enumerate(ordered, start=1):
        print(f"  {index}: {seed.name}")

    staging_parent = repo / "outputs" / "ltx_video_run" / "_selected_seed_staging"
    staging_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="selected_", dir=staging_parent) as temp_dir:
        staging_dir = Path(temp_dir)
        _copy_selected_for_pipeline(ordered, staging_dir)
        args.seed = None
        args.seed_dir = str(staging_dir)
        args.max_scenes = len(ordered)
        return base.run_interactive(args)


def build_parser() -> argparse.ArgumentParser:
    parser = base.build_parser()
    parser.set_defaults(guidance_scale=DEFAULT_GUIDANCE_SCALE)
    parser.description = "Build an LTX run from descriptive seed filenames; scene numbers are optional."
    for action in parser._actions:
        if action.dest == "seed_dir":
            action.help = "Folder of descriptive seed images; scene numbers are optional."
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
