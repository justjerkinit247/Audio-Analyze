import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from audio_analyze.ltx_control_prep import build_scene_control_status


def test_build_scene_control_status(tmp_path):
    plan_path = tmp_path / "plan.json"
    preflight_path = tmp_path / "preflight.json"
    status_path = tmp_path / "status.json"

    plan = {
        "seed_mapping": {
            "problems": [],
            "filename_hints_enabled": True,
            "manifest_json": None,
        },
        "results": [
            {
                "clip_index": 1,
                "seed_image_used": "C:/fake/scene_01_intro.png",
                "prompt_text": "Base prompt. Scene-specific control layer: intro.",
                "seed_assignment": {
                    "seed_file": "scene_01_intro.png",
                    "method": "scene_label",
                    "filename_prompt_hint": "intro",
                    "scene_addon": "Seed filename direction: intro.",
                },
            }
        ],
    }
    preflight = {"status": "PASSED", "problems": []}

    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    preflight_path.write_text(json.dumps(preflight), encoding="utf-8")

    status = build_scene_control_status(plan_path, preflight_path, status_path)

    assert status_path.exists()
    assert status["status"] == "PASSED"
    assert status["scene_count"] == 1
    assert status["scenes"][0]["seed_file"] == "scene_01_intro.png"
    assert status["scenes"][0]["filename_prompt_hint"] == "intro"
