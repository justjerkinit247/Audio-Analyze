from __future__ import annotations

from pathlib import Path
import argparse
import json


DEFAULT_POLICY = {
    "version": 1,
    "strategies": {
        "simple_downbeat_locked_choreo": {"weight": 1.0, "wins": 0, "losses": 0},
        "camera_follows_hips": {"weight": 1.0, "wins": 0, "losses": 0},
        "prompt_compressed_motion_first": {"weight": 1.0, "wins": 0, "losses": 0},
        "cinematic_detail_rich": {"weight": 1.0, "wins": 0, "losses": 0},
    },
    "rules": {
        "max_prompt_chars_soft": 4200,
        "prefer_short_motion_phrases": True,
        "preserve_winning_phrases": True,
        "penalize_conflicting_directives": True,
    },
    "learned_adjustments": {
        "guidance_scale_delta": 0.0,
        "motion_intensity_delta": 0.0,
        "camera_motion_delta": 0.0,
        "downbeat_lock_boost": 0.0,
        "prompt_compression_bias": 0.0,
    },
}


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


def policy_path(state_root: Path) -> Path:
    return Path(state_root) / "policy" / "asmo_policy.json"


def load_policy(state_root: Path) -> dict:
    path = policy_path(state_root)
    existing = read_json(path, default=None)
    if existing:
        return existing
    write_json(path, DEFAULT_POLICY)
    return json.loads(json.dumps(DEFAULT_POLICY))


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def update_weight(policy: dict, strategy: str, score: float) -> None:
    item = policy.setdefault("strategies", {}).setdefault(strategy, {"weight": 1.0, "wins": 0, "losses": 0})
    score = clamp(float(score), 0.0, 1.0)
    if score >= 0.7:
        item["wins"] = int(item.get("wins", 0)) + 1
        item["weight"] = round(clamp(float(item.get("weight", 1.0)) * (1.0 + 0.15 * score), 0.1, 5.0), 4)
    elif score <= 0.45:
        item["losses"] = int(item.get("losses", 0)) + 1
        item["weight"] = round(clamp(float(item.get("weight", 1.0)) * (1.0 - 0.18 * (1.0 - score)), 0.1, 5.0), 4)


def average(values):
    vals = [v for v in values if isinstance(v, (int, float))]
    return sum(vals) / len(vals) if vals else None


def update_policy_from_feedback(state_root: Path, feedback_packet: dict) -> dict:
    policy = load_policy(state_root)
    scene_feedback = feedback_packet.get("scene_feedback", [])
    beat = average([s.get("scores", {}).get("beat_sync") for s in scene_feedback])
    motion = average([s.get("scores", {}).get("motion_intent_match") for s in scene_feedback])
    camera = average([s.get("scores", {}).get("camera_intent_match") for s in scene_feedback])
    obedience = average([s.get("scores", {}).get("prompt_obedience") for s in scene_feedback])
    visual = average([s.get("scores", {}).get("visual_quality") for s in scene_feedback])

    if beat is not None:
        update_weight(policy, "simple_downbeat_locked_choreo", beat)
    if motion is not None:
        update_weight(policy, "prompt_compressed_motion_first", motion)
    if camera is not None:
        update_weight(policy, "camera_follows_hips", camera)
    if obedience is not None:
        update_weight(policy, "cinematic_detail_rich", obedience)

    learned = policy.setdefault("learned_adjustments", {})
    if beat is not None and beat < 0.75:
        learned["downbeat_lock_boost"] = round(clamp(float(learned.get("downbeat_lock_boost", 0.0)) + 0.08, 0.0, 1.0), 4)
    if obedience is not None and obedience < 0.65:
        learned["prompt_compression_bias"] = round(clamp(float(learned.get("prompt_compression_bias", 0.0)) + 0.10, 0.0, 1.0), 4)
    if motion is not None:
        learned["motion_intensity_delta"] = round(clamp((0.75 - motion) * 0.25, -0.25, 0.25), 4)
    if camera is not None:
        learned["camera_motion_delta"] = round(clamp((0.75 - camera) * 0.20, -0.20, 0.20), 4)
    if visual is not None and visual < 0.60:
        learned["guidance_scale_delta"] = round(clamp(float(learned.get("guidance_scale_delta", 0.0)) - 0.25, -2.0, 2.0), 4)

    write_json(policy_path(state_root), policy)
    return policy


def choose_best_strategies(policy: dict, limit: int = 3) -> list[str]:
    ranked = sorted(policy.get("strategies", {}).items(), key=lambda kv: float(kv[1].get("weight", 1.0)), reverse=True)
    return [name for name, _ in ranked[:limit]]


def main():
    parser = argparse.ArgumentParser(description="Update ASMO policy memory from feedback packet.")
    sub = parser.add_subparsers(dest="command", required=True)
    p_init = sub.add_parser("init")
    p_init.add_argument("--state-root", default="outputs/ltx_video_run/_state")
    p_update = sub.add_parser("update")
    p_update.add_argument("--state-root", default="outputs/ltx_video_run/_state")
    p_update.add_argument("--feedback", default=None)
    args = parser.parse_args()
    if args.command == "init":
        print(json.dumps(load_policy(Path(args.state_root)), indent=2))
    elif args.command == "update":
        feedback_path = Path(args.feedback) if args.feedback else Path(args.state_root) / "active" / "feedback" / "feedback_packet.json"
        feedback = read_json(feedback_path, default={}) or {}
        print(json.dumps(update_policy_from_feedback(Path(args.state_root), feedback), indent=2))


if __name__ == "__main__":
    main()
