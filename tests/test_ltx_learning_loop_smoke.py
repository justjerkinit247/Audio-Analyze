from pathlib import Path
import json

from src.audio_analyze.ltx_run_state import rotate_for_new_live_session, ingest_scene_result, append_assembly_attempt, status
from src.audio_analyze.ltx_feedback_analyzer import build_feedback_packet
from src.audio_analyze.ltx_policy_store import update_policy_from_feedback
from src.audio_analyze.asmo_engine.feedback_adapter import apply_feedback_to_plan


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_learning_loop_smoke(tmp_path):
    state = tmp_path / "_state"
    manifest = rotate_for_new_live_session(state)
    assert manifest["session_id"].startswith("live_")

    result = tmp_path / "scene_01_result.json"
    write_json(result, {
        "clip_index": 1,
        "status": "complete",
        "model": "ltx-2-3-pro",
        "guidance_scale": 9.0,
        "resolution": "1080x1920",
        "downloaded_mp4": "scene_01.mp4",
        "scene_audio_format": "MP3",
        "scene": {"duration": 8.0},
        "prompt_text": "performance motion beat camera dolly downbeat rhythm " * 20,
    })
    ingest_scene_result(state, result)

    write_json(state / "active" / "review" / "human_scorecard.json", {
        "scene_01": {
            "beat_sync": 6,
            "motion_match": 6,
            "camera_match": 7,
            "visual_quality": 8,
            "prompt_obedience": 5,
            "notes": "motion lagged and prompt felt overloaded",
        }
    })

    append_assembly_attempt(state, {"status": "complete", "audio_offset_seconds": -0.15})

    packet = build_feedback_packet(state)
    assert packet["scene_feedback"]
    assert packet["global_adjustments"]["increase_downbeat_locking"] is True

    policy = update_policy_from_feedback(state, packet)
    assert "strategies" in policy

    plan = {"results": [{"clip_index": 1, "prompt_text": "original prompt"}]}
    patched = apply_feedback_to_plan(plan, packet, policy)
    assert "ASMO feedback update" in patched["results"][0]["prompt_text"]

    s = status(state)
    assert s["active_scene_returns"] == 1
    assert s["active_assembly_attempts"] == 1
