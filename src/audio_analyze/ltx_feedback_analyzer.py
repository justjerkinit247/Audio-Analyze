from __future__ import annotations

from pathlib import Path
import argparse
import json
import math

try:
    from .ltx_feature_extractor import extract_from_state, write_features_jsonl
    from .ltx_policy_store import update_policy_from_feedback, load_policy, choose_best_strategies
except ImportError:
    from ltx_feature_extractor import extract_from_state, write_features_jsonl
    from ltx_policy_store import update_policy_from_feedback, load_policy, choose_best_strategies


SCORE_SOURCE_HUMAN = "human_scorecard"
SCORE_SOURCE_MISSING = "missing"


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


def score_or_none(value) -> float | None:
    """Return a normalized score only when explicit numeric evidence exists."""
    if value is None or isinstance(value, bool):
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(score):
        return None
    if 1.0 < score <= 10.0:
        score /= 10.0
    if score < 0.0 or score > 1.0:
        return None
    return score


def score_or_default(value, default: float) -> float:
    """Backward-compatible helper; new feedback logic does not synthesize defaults."""
    score = score_or_none(value)
    return score if score is not None else default


def _rounded_score(value: float | None) -> float | None:
    return round(value, 3) if value is not None else None


def analyze_feature(row: dict) -> dict:
    raw_scores = row.get("human_scores", {}) or {}
    score_values = {
        "beat_sync": score_or_none(raw_scores.get("beat_sync")),
        "motion_intent_match": score_or_none(raw_scores.get("motion_match")),
        "camera_intent_match": score_or_none(raw_scores.get("camera_match")),
        "visual_quality": score_or_none(raw_scores.get("visual_quality")),
        "prompt_obedience": score_or_none(raw_scores.get("prompt_obedience")),
    }
    score_evidence = {
        metric: SCORE_SOURCE_HUMAN if value is not None else SCORE_SOURCE_MISSING
        for metric, value in score_values.items()
    }

    beat_sync = score_values["beat_sync"]
    motion_match = score_values["motion_intent_match"]
    camera_match = score_values["camera_intent_match"]
    visual_quality = score_values["visual_quality"]
    prompt_obedience = score_values["prompt_obedience"]

    issues = []
    adjustments = {}

    if row.get("status") == "failed":
        issues.append("generation_failed")
        adjustments["retry_scene"] = True
    if beat_sync is not None and beat_sync < 0.72:
        issues.append("weak_beat_sync")
        adjustments["increase_downbeat_locking"] = True
        adjustments["audio_offset_seconds"] = -0.10
    if motion_match is not None and motion_match < 0.70:
        issues.append("motion_intent_mismatch")
        adjustments["motion_intensity_delta"] = 0.12
        adjustments["simplify_motion_plan"] = True
    if camera_match is not None and camera_match < 0.70:
        issues.append("camera_intent_mismatch")
        adjustments["camera_motion_delta"] = 0.10
        adjustments["isolate_camera_directive"] = True
    if prompt_obedience is not None and prompt_obedience < 0.65:
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
    if (
        visual_quality is not None
        and motion_match is not None
        and camera_match is not None
        and visual_quality >= 0.80
        and motion_match >= 0.75
        and camera_match >= 0.75
    ):
        issues.append("winning_pattern_candidate")
        adjustments["preserve_successful_phrasing"] = True

    scored_metrics = [
        metric for metric, source in score_evidence.items() if source == SCORE_SOURCE_HUMAN
    ]
    unscored_metrics = [
        metric for metric, source in score_evidence.items() if source == SCORE_SOURCE_MISSING
    ]

    return {
        "scene_id": row.get("clip_index"),
        "scores": {metric: _rounded_score(value) for metric, value in score_values.items()},
        "score_evidence": score_evidence,
        "scored_metrics": scored_metrics,
        "unscored_metrics": unscored_metrics,
        "detected_issues": issues,
        "recommended_adjustments": adjustments,
        "source_features": row,
    }


def average(values):
    vals = [
        float(value)
        for value in values
        if isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    ]
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
        "scored_scene_count": sum(1 for scene in scene_feedback if scene.get("scored_metrics")),
        "fully_unscored_scene_count": sum(1 for scene in scene_feedback if not scene.get("scored_metrics")),
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
