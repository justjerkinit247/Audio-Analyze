from pathlib import Path

import pytest

from audio_analyze import ltx_seed_picker_live_run as picker


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"seed")
    return path


def test_selected_seed_files_are_sorted_by_scene_label(tmp_path):
    scene_2 = _touch(tmp_path / "scene_02_back_facing.png")
    scene_1 = _touch(tmp_path / "scene_01_front_facing.png")

    ordered = picker._ordered_selected_seed_files([scene_2, scene_1], None)

    assert [path.name for path in ordered] == [
        "scene_01_front_facing.png",
        "scene_02_back_facing.png",
    ]


def test_selected_seeds_must_come_from_same_folder(tmp_path):
    scene_1 = _touch(tmp_path / "a" / "scene_01_front.png")
    scene_2 = _touch(tmp_path / "b" / "scene_02_back.png")

    with pytest.raises(RuntimeError, match="same folder"):
        picker._ordered_selected_seed_files([scene_1, scene_2], None)


def test_single_unlabeled_seed_remains_backward_compatible(tmp_path):
    seed = _touch(tmp_path / "choir.png")

    assert picker._ordered_selected_seed_files([seed], None) == [seed]


def test_copy_selected_accepts_precreated_temporary_directory(tmp_path):
    seed = _touch(tmp_path / "source" / "scene_01_front.png")
    destination = tmp_path / "already_created"
    destination.mkdir()

    picker._copy_selected_for_pipeline([seed], destination)

    assert (destination / seed.name).read_bytes() == b"seed"
