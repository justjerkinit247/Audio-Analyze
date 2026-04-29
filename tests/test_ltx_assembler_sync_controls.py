import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from audio_analyze.ltx_clip_assembler import scene_number_from_path, select_latest_scene_clips


def test_scene_number_from_path_accepts_scene_numbers():
    assert scene_number_from_path(Path("Gospel_Twerk_ltx_scene_01.mp4")) == 1
    assert scene_number_from_path(Path("Gospel_Twerk_ltx_scene_12.mp4")) == 12
    assert scene_number_from_path(Path("no_number.mp4")) is None


def test_select_latest_scene_clips_handles_duplicates(tmp_path):
    old_scene_1 = tmp_path / "song_ltx_scene_01_old.mp4"
    new_scene_1 = tmp_path / "song_ltx_scene_01_new.mp4"
    scene_2 = tmp_path / "song_ltx_scene_02.mp4"
    unnumbered = tmp_path / "random.mp4"

    for path in [old_scene_1, new_scene_1, scene_2, unnumbered]:
        path.write_bytes(b"fake")

    os.utime(old_scene_1, (1000, 1000))
    os.utime(new_scene_1, (2000, 2000))
    os.utime(scene_2, (1500, 1500))

    result = select_latest_scene_clips(
        [old_scene_1, new_scene_1, scene_2, unnumbered],
        expected_scenes=3,
        strict_scenes=False,
    )

    selected_names = [path.name for path in result["selected"]]
    assert selected_names == ["song_ltx_scene_01_new.mp4", "song_ltx_scene_02.mp4"]
    assert result["missing_scenes"] == [3]
    assert result["duplicate_notes"][0]["scene"] == 1
    assert result["unnumbered"]
