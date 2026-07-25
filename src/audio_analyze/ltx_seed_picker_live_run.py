from __future__ import annotations

from pathlib import Path
import argparse
import shutil
import sys
import tempfile

from . import ltx_multi_scene_live_run as base
from .ltx_seed_mapper import ALLOWED_IMAGES, scene_number_from_name


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
        unique.append(resolved)

    count = base._validate_scene_count(requested_count or len(unique))
    if len(unique) != count:
        raise RuntimeError(
            f"Selected {len(unique)} seed images but the requested scene count is {count}. "
            "Select exactly one image per scene."
        )

    parents = {str(path.parent).lower() for path in unique}
    if len(parents) != 1:
        raise RuntimeError("All selected seed images must come from the same folder.")

    if count == 1 and scene_number_from_name(unique[0]) is None:
        return unique

    by_scene: dict[int, Path] = {}
    unlabeled: list[str] = []
    for path in unique:
        scene_number = scene_number_from_name(path)
        if scene_number is None:
            unlabeled.append(path.name)
            continue
        if scene_number in by_scene:
            raise RuntimeError(
                f"Duplicate scene_{scene_number:02d} selection: "
                f"{by_scene[scene_number].name}, {path.name}"
            )
        by_scene[scene_number] = path

    if unlabeled:
        raise RuntimeError(
            "Multiple selected seeds must include scene labels in their filenames. "
            f"Unlabeled selections: {', '.join(unlabeled)}"
        )

    missing = [number for number in range(1, count + 1) if number not in by_scene]
    if missing:
        labels = ", ".join(f"scene_{number:02d}" for number in missing)
        raise RuntimeError(f"Missing selected seed labels: {labels}")

    extra = sorted(number for number in by_scene if number > count)
    if extra:
        labels = ", ".join(f"scene_{number:02d}" for number in extra)
        raise RuntimeError(f"Selected scene labels exceed the requested count: {labels}")

    return [by_scene[number] for number in range(1, count + 1)]


def _copy_selected_for_pipeline(selected: list[Path], destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    for index, source in enumerate(selected, start=1):
        scene_number = scene_number_from_name(source)
        filename = source.name
        if scene_number is None:
            filename = f"scene_{index:02d}_{source.name}"
        shutil.copy2(source, destination / filename)


def run_interactive(args: argparse.Namespace) -> int:
    if args.seed or args.seed_dir:
        return base.run_interactive(args)

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

    default_seed_dir = repo / "inputs" / "ltx_seed_images"
    selected = _choose_seed_files(
        "Select 1 to 20 seed images from the existing LTX seed-image folder",
        default_seed_dir,
    )
    ordered = _ordered_selected_seed_files(selected, args.max_scenes)

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
    return base.build_parser()


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
