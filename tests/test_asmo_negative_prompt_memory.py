import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from audio_analyze import asmo_negative_prompt_memory as memory
from audio_analyze import ltx_next_scene_planner


def sample_feedback_packet():
    return {
        "session_id": "session-1",
        "scene_feedback": [
            {
                "scene_id": 1,
                "detected_issues": ["motion_intent_mismatch", "camera_intent_mismatch"],
                "scores": {"motion_intent_match": 0.4, "camera_intent_match": 0.45},
            },
            {
                "scene_id": 2,
                "detected_issues": ["prompt_obedience_low", "seed_drift"],
                "scores": {"prompt_obedience": 0.35, "visual_quality": 0.55},
            },
        ],
    }


def test_update_negative_prompt_memory_writes_memory_and_ledger(tmp_path):
    state_root = tmp_path / "_state"

    report = memory.update_negative_prompt_memory_from_feedback(state_root, sample_feedback_packet())

    assert report["status"] == "complete"
    memory_path = state_root / "memory" / "asmo_negative_prompt_memory.json"
    ledger_path = state_root / "memory" / "negative_prompt_ledger.jsonl"
    feedback_terms_path = state_root / "active" / "feedback" / "asmo_negative_prompt_terms.json"
    assert memory_path.exists()
    assert ledger_path.exists()
    assert feedback_terms_path.exists()

    stored = json.loads(memory_path.read_text(encoding="utf-8"))
    assert stored["term_counts"]["motion drift"] == 1
    assert stored["term_counts"]["chaotic camera movement"] == 1
    assert stored["issue_counts"]["seed_drift"] == 1
    assert "changed subject identity" in stored["scene_terms"]["2"]

    ledger_lines = ledger_path.read_text(encoding="utf-8").splitlines()
    assert len(ledger_lines) == 2


def test_terms_for_next_run_combines_baseline_scene_subject_and_learned_terms(tmp_path):
    state_root = tmp_path / "_state"
    memory.update_negative_prompt_memory_from_feedback(state_root, sample_feedback_packet())

    terms = memory.terms_for_next_run(state_root, scene_id=1, scene_hint="duck flies toward clouds")

    assert "blurry motion" in terms
    assert "motion drift" in terms
    assert "camera drift away from subject" in terms
    assert "malformed wings" in terms


def test_apply_negative_memory_updates_negative_prompt_section(tmp_path):
    state_root = tmp_path / "_state"
    memory.update_negative_prompt_memory_from_feedback(state_root, sample_feedback_packet())
    plan = {
        "results": [
            {
                "clip_index": 1,
                "seed_filename_prompt_hint": "duck flies toward clouds",
                "prompt_text": "Base prompt.\n\n[MOTION_PROMPT]\nDuck flies.\n\n[NEGATIVE_PROMPT]\nblurry motion\n",
                "filename_hint_expansion": {
                    "scene_hint": "duck flies toward clouds",
                    "negative_prompt": "blurry motion",
                    "combined_ltx_text": "[MOTION_PROMPT]\nDuck flies.\n\n[NEGATIVE_PROMPT]\nblurry motion\n",
                },
            }
        ]
    }

    patched = memory.apply_negative_memory_to_plan_data(plan, state_root)
    item = patched["results"][0]
    negative = item["filename_hint_expansion"]["negative_prompt"]

    assert patched["asmo_negative_prompt_memory_applied"] is True
    assert "motion drift" in negative
    assert "chaotic camera movement" in negative
    assert "malformed wings" in negative
    assert "motion drift" in item["prompt_text"]
    assert item["filename_hint_expansion"]["negative_prompt_before_asmo_memory"] == "blurry motion"


def test_next_scene_planner_updates_and_applies_negative_memory(tmp_path):
    state_root = tmp_path / "_state"
    feedback_path = state_root / "active" / "feedback" / "feedback_packet.json"
    feedback_path.parent.mkdir(parents=True)
    feedback_path.write_text(json.dumps(sample_feedback_packet()), encoding="utf-8")
    (state_root / "active" / "feedback" / "strategy_scores.json").write_text(json.dumps({"ranked": []}), encoding="utf-8")

    plan_path = tmp_path / "plan.json"
    output_path = tmp_path / "next_plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "clip_index": 1,
                        "seed_filename_prompt_hint": "duck flies toward clouds",
                        "prompt_text": "Base prompt.\n\n[MOTION_PROMPT]\nDuck flies.\n\n[NEGATIVE_PROMPT]\nblurry motion\n",
                        "filename_hint_expansion": {
                            "scene_hint": "duck flies toward clouds",
                            "negative_prompt": "blurry motion",
                            "combined_ltx_text": "[MOTION_PROMPT]\nDuck flies.\n\n[NEGATIVE_PROMPT]\nblurry motion\n",
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    patched = ltx_next_scene_planner.build_next_plan(plan_path, state_root, output_path)

    assert output_path.exists()
    assert patched["asmo_negative_prompt_memory_applied"] is True
    assert "asmo_negative_prompt_memory_summary" in patched
    negative = patched["results"][0]["filename_hint_expansion"]["negative_prompt"]
    assert "motion drift" in negative
    assert "camera drift away from subject" in negative
