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


def test_selected_seeds_can_come_from_different_folders(tmp_path):
    scene_1 = _touch(tmp_path / "a" / "scene_01_front.png")
    scene_2 = _touch(tmp_path / "b" / "scene_02_back.png")

    assert picker._ordered_selected_seed_files([scene_1, scene_2], None) == [scene_1, scene_2]


def test_single_unlabeled_seed_remains_backward_compatible(tmp_path):
    seed = _touch(tmp_path / "choir.png")

    assert picker._ordered_selected_seed_files([seed], None) == [seed]


def test_copy_selected_accepts_precreated_temporary_directory(tmp_path):
    seed = _touch(tmp_path / "source" / "scene_01_front.png")
    destination = tmp_path / "already_created"
    destination.mkdir()

    picker._copy_selected_for_pipeline([seed], destination)

    assert (destination / seed.name).read_bytes() == b"seed"


def test_live_pipeline_defaults_guidance_scale_to_twelve():
    args = picker.build_parser().parse_args([])

    assert args.guidance_scale == 12.0


@pytest.mark.parametrize("names", [
    ["scene_21_walking.png", "scene_42_dancing.jpg"],
    ["walking.png", "dancing.jpg"],
    ["scene_21_walking.png", "dancing.jpg"],
    ["scene_21_walking.png", "scene_21_dancing.jpg"],
    ["scene 21 walking.png"],
])
def test_descriptive_seeds_reach_downstream_mapper_without_renaming_originals(tmp_path, names):
    from audio_analyze.ltx_filename_hint_expander import clean_scene_hint
    selected = [_touch(tmp_path / "source" / name) for name in names]
    ordered = picker._ordered_selected_seed_files(selected, None)
    staging = tmp_path / "staged"
    picker._copy_selected_for_pipeline(ordered, staging)
    mapped = picker.base._collect_labeled_scene_seeds(staging, len(ordered))
    assert len(mapped) == len(selected)
    for index, (original, staged) in enumerate(zip(ordered, mapped), start=1):
        assert staged.name.startswith(f"scene_{index:02d}_")
        assert clean_scene_hint(staged.name) == clean_scene_hint(original.name)
        assert original.read_bytes() == staged.read_bytes() == b"seed"
    assert sorted(p.name for p in (tmp_path / "source").iterdir()) == sorted(names)


def test_description_is_required(tmp_path):
    seed = _touch(tmp_path / "scene_21.png")
    with pytest.raises(ValueError, match="description"):
        picker._ordered_selected_seed_files([seed], None)


@pytest.mark.parametrize("mode", ["picker", "seed", "seed_dir"])
def test_all_launcher_input_modes_normalize_before_base_runner(tmp_path, monkeypatch, mode):
    seed = _touch(tmp_path / "source" / "scene_21_walking.png")
    monkeypatch.setattr(picker.base, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(picker, "_choose_seed_files", lambda *args: [seed])
    args = picker.build_parser().parse_args(["--audio", "audio.wav", "--dry-run"])
    if mode == "seed":
        args.seed = str(seed)
    elif mode == "seed_dir":
        args.seed_dir = str(seed.parent)
    def run_base(received):
        assert received.dry_run is True
        assert received.seed is None
        mapped = picker.base._collect_labeled_scene_seeds(Path(received.seed_dir), 1)
        assert mapped[0].name == "scene_01_walking.png"
        return 0
    monkeypatch.setattr(picker.base, "run_interactive", run_base)
    assert picker.run_interactive(args) == 0
