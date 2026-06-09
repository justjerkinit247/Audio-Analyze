import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from audio_analyze import ltx_filename_hint_expander as expander


def test_clean_scene_hint_uses_filename_as_source_of_truth():
    hint = expander.clean_scene_hint("scene_01_duck_flies_off_keyhole_through_open_view_out_to_ocean_clouds.png")
    assert hint == "duck flies off keyhole through open view out to ocean clouds"


def test_clean_scene_hint_does_not_remove_project_specific_words():
    hint = expander.clean_scene_hint("scene_02_gospel_duck_crosses_holy_water.webp")
    assert "gospel" in hint
    assert "holy" in hint
    assert "duck crosses" in hint


def test_render_and_parse_combined_ltx_text():
    text = expander.render_combined_ltx_text(
        "The camera slowly pushes forward as the duck flies into open clouds.",
        "blurry motion, malformed wings",
    )

    assert "[MOTION_PROMPT]" in text
    assert "[NEGATIVE_PROMPT]" in text

    parsed = expander.parse_combined_ltx_text(text)
    assert parsed["prompt"].startswith("The camera slowly pushes")
    assert parsed["negative_prompt"] == "blurry motion, malformed wings"


def test_template_expansion_includes_motion_and_negative_cleanup_terms():
    expansion = expander.expand_scene_hint(
        "duck flies off keyhole to ocean clouds",
        filename="scene_01_duck_flies_off_keyhole_to_ocean_clouds.png",
        provider="template",
    )

    assert expansion["provider"] == "template"
    assert "duck flies off keyhole to ocean clouds" in expansion["ltx_motion_prompt"]
    assert "malformed wings" in expansion["negative_prompt"]
    assert "[MOTION_PROMPT]" in expansion["combined_ltx_text"]
    assert "[NEGATIVE_PROMPT]" in expansion["combined_ltx_text"]


def test_expand_seed_dir_writes_one_combined_ltx_text_file(tmp_path):
    seed_dir = tmp_path / "seeds"
    seed_dir.mkdir()
    (seed_dir / "scene_01_duck_flies_to_ocean_clouds.png").write_bytes(b"seed image bytes")
    out_dir = tmp_path / "prompts"

    report = expander.expand_seed_dir(seed_dir, out_dir, provider="template")

    assert report["status"] == "complete"
    assert report["expanded_count"] == 1
    txt_path = out_dir / "scene_01_duck_flies_to_ocean_clouds_ltx.txt"
    json_path = out_dir / "scene_01_duck_flies_to_ocean_clouds_ltx.json"
    assert txt_path.exists()
    assert json_path.exists()
    text = txt_path.read_text(encoding="utf-8")
    assert "[MOTION_PROMPT]" in text
    assert "[NEGATIVE_PROMPT]" in text


def test_apply_expansions_to_plan_data_appends_combined_prompt():
    plan = {
        "results": [
            {
                "clip_index": 1,
                "seed_image_used": "inputs/ltx_seed_images/scene_01_duck_flies_to_ocean_clouds.png",
                "seed_filename_prompt_hint": "duck flies to ocean clouds",
                "prompt_text": "Base LTX prompt.",
            }
        ]
    }

    updated = expander.apply_expansions_to_plan_data(plan, provider="template")
    item = updated["results"][0]

    assert updated["filename_hint_expander"]["expanded_count"] == 1
    assert item["filename_hint_expansion"]["status"] == "expanded"
    assert "Filename-hint LTX motion expansion:" in item["prompt_text"]
    assert "[MOTION_PROMPT]" in item["prompt_text"]
    assert "[NEGATIVE_PROMPT]" in item["prompt_text"]


def test_apply_expansions_to_plan_round_trips_file(tmp_path):
    plan_path = tmp_path / "plan.json"
    out_path = tmp_path / "expanded_plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "clip_index": 1,
                        "seed_image_used": "scene_01_shadow_moves_across_empty_room.jpg",
                        "prompt_text": "Base prompt.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    plan = expander.apply_expansions_to_plan(plan_path, output_json=out_path, provider="template")

    assert out_path.exists()
    assert plan["filename_hint_expander"]["expanded_count"] == 1
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["results"][0]["filename_hint_expansion"]["scene_hint"] == "shadow moves across empty room"
