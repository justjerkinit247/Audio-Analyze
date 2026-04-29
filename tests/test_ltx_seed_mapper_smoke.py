import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from audio_analyze.ltx_seed_mapper import apply_seed_mapping, scene_number_from_name, hint_from_filename


def test_scene_number_and_hint_extraction():
    path = Path("scene_03_twerk_accent_wide_angle.png")
    assert scene_number_from_name(path) == 3
    assert hint_from_filename(path) == "twerk accent wide angle"


def test_apply_seed_mapping_with_filename_hint_and_manifest(tmp_path):
    seed_dir = tmp_path / "seeds"
    seed_dir.mkdir()
    image = seed_dir / "scene_02_over_shoulder_glance.png"
    image.write_bytes(b"fake image bytes")

    plan_path = tmp_path / "plan.json"
    preview_path = tmp_path / "preview.md"
    manifest_path = tmp_path / "manifest.json"

    plan = {
        "results": [
            {
                "clip_index": 2,
                "seed_image_used": str(image),
                "prompt_text": "Base prompt for scene two.",
                "scene": {"duration": 8},
            }
        ]
    }
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    manifest = {
        "scenes": [
            {
                "scene": 2,
                "camera": "slow side arc",
                "motion": "controlled shoulder glance",
                "negative_prompt": "avoid extra limbs",
            }
        ]
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    updated = apply_seed_mapping(
        plan_json=plan_path,
        seed_dir=seed_dir,
        manifest_json=manifest_path,
        preview_md=preview_path,
    )

    item = updated["results"][0]
    assignment = item["seed_assignment"]

    assert assignment["method"] == "scene_label"
    assert assignment["filename_prompt_hint"] == "over shoulder glance"
    assert assignment["manifest_applied"] is True
    assert "Scene-specific control layer" in item["prompt_text"]
    assert "slow side arc" in item["prompt_text"]
    assert "controlled shoulder glance" in item["prompt_text"]
    assert "avoid extra limbs" in item["prompt_text"]
    assert preview_path.exists()
