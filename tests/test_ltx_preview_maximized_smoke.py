import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from audio_analyze.ltx_seed_mapper import make_preview_report


def test_preview_report_includes_prompt_maximizer_details(tmp_path):
    preview_path = tmp_path / "preview.md"
    plan = {
        "prompt_maximizer": {
            "max_chars": 5000,
            "target_chars": 4850,
            "problems": [],
        },
        "results": [
            {
                "clip_index": 1,
                "prompt_text": "x" * 4850,
                "seed_assignment": {
                    "seed_file": "scene_01_praying_pose.png",
                    "method": "scene_label",
                    "filename_prompt_hint": "praying pose",
                    "scene_addon": "Seed filename direction: praying pose.",
                },
                "prompt_maximizer": {
                    "enabled": True,
                    "remaining_chars": 150,
                },
            }
        ],
    }

    make_preview_report(plan, preview_path)
    text = preview_path.read_text(encoding="utf-8")

    assert "Prompt max chars: 5000" in text
    assert "Prompt target chars: 4850" in text
    assert "Prompt chars: 4850" in text
    assert "Prompt remaining chars: 150" in text
    assert "Prompt maximized: True" in text
