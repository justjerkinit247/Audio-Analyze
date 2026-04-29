import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from audio_analyze.ltx_clip_assembler import natural_scene_key


def test_natural_scene_key_sorts_scene_numbers():
    assert natural_scene_key(Path("Gospel_Twerk_ltx_scene_02.mp4"))[0] == 2
    assert natural_scene_key(Path("Gospel_Twerk_ltx_scene_10.mp4"))[0] == 10
