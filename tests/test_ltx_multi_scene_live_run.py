from pathlib import Path

import pytest
from PIL import Image

from audio_analyze import ltx_multi_scene_live_run as multi


def test_scene_count_is_bounded_from_one_to_twenty():
    assert multi._validate_scene_count(1) == 1
    assert multi._validate_scene_count(20) == 20
    with pytest.raises(ValueError):
        multi._validate_scene_count(0)
    with pytest.raises(ValueError):
        multi._validate_scene_count(21)


def test_labeled_seed_folder_maps_contiguous_scene_order(tmp_path):
    first = tmp_path / "scene_01_front_facing.png"
    second = tmp_path / "scene_02_180_degree_pivot.png"
    first.write_bytes(b"x")
    second.write_bytes(b"x")

    selected = multi._collect_labeled_scene_seeds(tmp_path, requested_count=None)

    assert [path.name for path in selected] == [first.name, second.name]


def test_labeled_seed_folder_rejects_missing_scene_number(tmp_path):
    (tmp_path / "scene_01_front_facing.png").write_bytes(b"x")
    (tmp_path / "scene_03_back_facing.png").write_bytes(b"x")

    with pytest.raises(RuntimeError, match="scene_02"):
        multi._collect_labeled_scene_seeds(tmp_path, requested_count=3)


def test_auto_resolution_uses_shared_seed_orientation(tmp_path):
    first = tmp_path / "scene_01.png"
    second = tmp_path / "scene_02.png"
    Image.new("RGB", (1600, 900)).save(first)
    Image.new("RGB", (1920, 1080)).save(second)

    assert multi._infer_resolution([first, second]) == "16:9"


def test_parser_defaults_to_seed_count_and_auto_resolution():
    args = multi.build_parser().parse_args([])

    assert args.max_scenes is None
    assert args.resolution == "auto"
    assert args.asmo_max_events_per_scene == 8
