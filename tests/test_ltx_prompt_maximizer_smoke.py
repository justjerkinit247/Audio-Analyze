import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from audio_analyze.ltx_prompt_maximizer import maximize_plan_prompts


def test_prompt_maximizer_respects_configured_limit(tmp_path):
    plan_path = tmp_path / "plan.json"
    plan = {
        "analysis": {"tempo_bpm": 100.446},
        "results": [
            {
                "clip_index": 3,
                "prompt_text": "Base prompt for scene three.",
                "scene": {"start": 16, "end": 24, "duration": 8},
                "seed_image_used": "scene_03_twerk_accent_wide_angle.png",
                "seed_assignment": {
                    "seed_file": "scene_03_twerk_accent_wide_angle.png",
                    "filename_prompt_hint": "twerk accent wide angle",
                    "scene_addon": "Seed filename direction: twerk accent wide angle.",
                },
            }
        ],
    }
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    updated = maximize_plan_prompts(plan_path, max_chars=2000, target_chars=1800)
    prompt = updated["results"][0]["prompt_text"]

    assert "Maximum scene-control expansion" in prompt
    assert len(prompt) <= 2000
    assert updated["prompt_maximizer"]["max_chars"] == 2000
    assert updated["results"][0]["prompt_maximizer"]["actual_chars"] == len(prompt)
