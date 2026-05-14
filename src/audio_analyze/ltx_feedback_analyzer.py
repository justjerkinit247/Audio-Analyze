from __future__ import annotations

from pathlib import Path
import argparse
import json

try:
    from .ltx_feature_extractor import extract_from_state, write_features_jsonl
    from .ltx_policy_store import update_policy_from_feedback, load_policy, choose_best_strategies
except ImportError:
    from ltx_feature_extractor import extract_from_state, write_features_jsonl
    from ltx_policy_store import update_policy_from_feedback, load_policy, choose_best_strategies


def read_json(path: Path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def score_or_default(value, default: float) -> float:
    return float(value) if isinstance(value, (int, float)) else default


def analyze_feature(row: dict) -> dict:
    scores = row.get("human_scores", {}) or {}
    beat_sync = score_or_default(scores.get("beat_sync"), 0.65)
    motion_match = score_or_default(scores.get("motion_match"), 0.65)
    camera_match = score_or_default(scores.get("camera_match"), 0.65)
    visual_quality = score_or_default(scores.get("visual_quality"), 0.70)
    prompt_obedience = score_or_default(scores.get("prompt_obedience"), 0.60)

    issues = []
    adjustments = {}

    if row.get("status") == "failed":
        issues.append("generation_failed")
        adjustments["retry_scene"] = True
    if beat_sync < 0.72:
        issues.append("weak_beat_sync")
        adjustments["increase_downbeat_locking"] = True
        adjustments["audio_offset_seconds"] = -0.10
    if motion_match < 0.70:
        issues.append("motion_intent_mismatch")
        adjustments["motion_intensity_delta"] = 0.12
        adjustments["simplify_motion_plan"] = True
    if camera_match < 0.70:
        issues.append("camera_intent_mismatch")
        adjustments["camera_motion_delta"] = 0.10
        adjustments["isolate_camera_directive"] = True
    if prompt_obedience < 0.65:
        issues.append("prompt_obedience_low")
        adjustments["prompt_compression"] = True
        adjustments["reduce_conflicting_directives"] = True
    if row.get("prompt_length_chars", 0) > 4300:
        issues.append("prompt_too_long")
        adjustments["prompt_compression"] = True
    if row.get("conflict_directive_count", 0) > 0:
        issues.append("conflicting_directives_detected")
        adjustments["remove_conflicting_directives"] = True
    if row.get("motion_directive_count", 0) > 16:
        issues.append("motion_overload")
        adjustments["simplify_motion_plan"] = True
    if row.get("camera_directive_count", 0) > 12:
        issues.append("camera_overload")
        adjustments["isolate_camera_directive"] = True
    if visual_quality >= 0.80 and motion_match >= 0.75 and camera_match >= 0.75:
        issues.append("winning_pattern_candidate")
        adjustments["preserve_successful_phrasing"] = True

    return {
        "scene_id": row.get("clip_index"),
        "scores": {
            "beat_sync": round(beat_sync, 3),
            "motion_intent_match": round(motion_match, 3),
            "camera_intent_match": round(camera_match, 3),
            "prompt_obedience": round(prompt_obedience, 3),
            "visual_quality": round(visual_quality, 3),
        },
        "detected_issues": issues,
        "recommended_adjustments": adjustments,
        "source_features": row,
    }


def average(values):
    vals = [v for v in values if isinstance(v, (int, float))]
    return round(sum(vals) / len(vals), 3) if vals else None


def build_feedback_packet(state_root: Path) -> dict:
    state_root = Path(state_root)
    manifest = read_json(state_root / "active" / "manifest.json", default={}) or {}
    features = extract_from_state(state_root)
    write_features_jsonl(state_root, features)
    scene_feedback = [analyze_feature(row) for row in features]
    policy = load_policy(state_root)
    best = choose_best_strategies(policy)

    summary = {
        "scene_count": len(scene_feedback),
        "avg_beat_sync": average([s["scores"]["beat_sync"] for s in scene_feedback]),
        "avg_motion_match": average([s["scores"]["motion_intent_match"] for s in scene_feedback]),
        "avg_camera_match": average([s["scores"]["camera_intent_match"] for s in scene_feedback]),
        "avg_prompt_obedience": average([s["scores"]["prompt_obedience"] for s in scene_feedback]),
        "avg_visual_quality": average([s["scores"]["visual_quality"] for s in scene_feedback]),
    }

    all_issues = []
    for scene in scene_feedback:
        all_issues.extend(scene.get("detected_issues", []))

    global_adjustments = {
        "prefer_shorter_motion_phrases": "prompt_obedience_low" in all_issues or "motion_overload" in all_issues,
        "increase_downbeat_locking": "weak_beat_sync" in all_issues,
        "reuse_successful_camera_phrasing": "winning_pattern_candidate" in all_issues,
        "reduce_conflicting_directives": "conflicting_directives_detected" in all_issues,
        "best_current_strategies": best,
    }

    packet = {
        "session_id": manifest.get("session_id"),
        "created_at_utc": manifest.get("created_at_utc"),
        "summary": summary,
        "scene_feedback": scene_feedback,
        "global_adjustments": global_adjustments,
    }

    write_json(state_root / "active" / "feedback" / "feedback_packet.json", packet)
    movement_packet = {
        "session_id": packet["session_id"],
        "movement_rules": [
            "Lock visible movement accents to downbeats." if global_adjustments["increase_downbeat_locking"] else "Keep timing natural and readable.",
            "Use fewer, stronger movement commands." if global_adjustments["prefer_shorter_motion_phrases"] else "Maintain current motion density.",
            "Remove conflicting visual/camera/motion directives." if global_adjustments["reduce_conflicting_directives"] else "Avoid adding new conflicts.",
        ],
        "scene_adjustments": [
            {"scene_id": s["scene_id"], "recommended_adjustments": s["recommended_adjustments"], "detected_issues": s["detected_issues"]}
            for s in scene_feedback
        ],
    }
    write_json(state_root / "active" / "feedback" / "asmo_feedback_packet.json", movement_packet)
    return packet


def main():
    parser = argparse.ArgumentParser(description="Analyze latest LTX live-session evidence and write ASMO feedback.")
    parser.add_argument("--state-root", default="outputs/ltx_video_run/_state")
    parser.add_argument("--update-policy", action="store_true")
    args = parser.parse_args()
    packet = build_feedback_packet(Path(args.state_root))
    if args.update_policy:
        packet["updated_policy"] = update_policy_from_feedback(Path(args.state_root), packet)
    print(json.dumps(packet, indent=2))


if __name__ == "__main__":
    main()
