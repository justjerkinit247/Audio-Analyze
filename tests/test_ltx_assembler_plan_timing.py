import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from audio_analyze.ltx_clip_assembler import scene_number_from_path, safe_mtime


def test_safe_mtime_returns_zero_for_missing_path():
    assert safe_mtime(Path("missing_scene_01.mp4")) == 0.0


def test_scene_number_from_path_handles_single_digit_scene():
    assert scene_number_from_path(Path("scene_4_explode_on_beat.mp4")) == 4
