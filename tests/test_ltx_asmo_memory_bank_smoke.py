from pathlib import Path
import json

from src.audio_analyze.ltx_visual_critic import build_visual_critic_report
from src.audio_analyze.ltx_strategy_scorer import score_strategies
from src.audio_analyze.asmo_memory_bank import init_memory_bank, update_memory_from_active_state
from src.audio_analyze.ltx_next_scene_planner import build_next_plan


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_ltx_asmo_memory_bank_smoke(tmp_path):
    state = tmp_path / "_state"
    write_json(state / "active" / "manifest.json", {"session_id": "live_test"})
    write_json(state / "active" / "scene_returns" / "scene_01_result.json", {
        "clip_index": 1,
        "status": "complete",
        "prompt_text": "camera motion beat timing performance " * 30,
        "scene": {"duration": 8.0},
        "downloaded_mp4": "scene_01.mp4",
    })
    write_json(state / "active" / "review" / "human_scorecard.json", {
        "scene_01": {
            "beat_sync": 8,
            "motion_match": 8,
            "camera_match": 8,
            "visual_quality": 8,
            "prompt_obedience": 7,
            "notes": "strong timing and readable camera",
        }
    })
    write_json(state / "active" / "features" / "scene_features.jsonl", {})
    (state / "active" / "features" / "scene_features.jsonl").write_text(json.dumps({
        "clip_index": 1,
        "prompt_length_chars": 2000,
        "conflict_directive_count": 0,
        "camera_directive_count": 4,
        "motion_directive_count": 6,
    }) + "\n", encoding="utf-8")
    write_json(state / "active" / "feedback" / "feedback_packet.json", {
        "scene_feedback": [{
            "scene_id": 1,
            "scores": {
                "beat_sync": 0.8,
                "motion_intent_match": 0.8,
                "camera_intent_match": 0.8,
                "prompt_obedience": 0.7,
                "visual_quality": 0.8,
            },
            "detected_issues": ["winning_pattern_candidate"],
        }]
    })

    critic = build_visual_critic_report(state)
    assert critic["scene_count"] == 1

    scores = score_strategies(state)
    assert scores["ranked"]

    init_memory_bank(state)
    memory_summary = update_memory_from_active_state(state)
    assert memory_summary["winning_patterns"] >= 1

    plan = tmp_path / "plan.json"
    out = tmp_path / "plan_next.json"
    write_json(plan, {"results": [{"clip_index": 1, "prompt_text": "original prompt"}]})
    patched = build_next_plan(plan, state, out)
    assert patched["asmo_memory_bank_applied"] is True
    assert "ASMO Memory Bank update" in patched["results"][0]["prompt_text"]
