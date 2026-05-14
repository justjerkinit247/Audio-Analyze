from __future__ import annotations

from pathlib import Path
import argparse
import json


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


def scene_feedback_map(feedback_packet: dict) -> dict:
    return {
        int(item["scene_id"]): item
        for item in feedback_packet.get("scene_feedback", [])
        if item.get("scene_id") is not None
    }


def policy_directive(policy: dict) -> str:
    learned = policy.get("learned_adjustments", {}) if policy else {}
    rules = []
    if learned.get("downbeat_lock_boost", 0) > 0:
        rules.append("Prioritize strict downbeat locking: visible motion accents and camera pulses must land on strong beat hits.")
    if learned.get("prompt_compression_bias", 0) > 0:
        rules.append("Use compact motion-first wording; remove decorative prompt bloat that competes with timing and camera instructions.")
    if learned.get("motion_intensity_delta", 0) > 0:
        rules.append("Increase readable performance movement intensity while keeping anatomy stable and believable.")
    if learned.get("camera_motion_delta", 0) > 0:
        rules.append("Make camera movement more intentional: one clear dolly, track, or pulse behavior, not multiple competing moves.")
    return " ".join(rules)


def patch_prompt(prompt: str, scene_feedback: dict | None, global_adjustments: dict, policy: dict) -> str:
    prompt = prompt or ""
    additions = []
    pd = policy_directive(policy)
    if pd:
        additions.append(pd)
    if global_adjustments.get("increase_downbeat_locking"):
        additions.append("Timing correction: lock visible motion accents to the detected beat grid; no drifting after midpoint.")
    if global_adjustments.get("prefer_shorter_motion_phrases"):
        additions.append("Prompt discipline correction: fewer motion commands, stronger verbs, no competing movement ideas.")
    if global_adjustments.get("reduce_conflicting_directives"):
        additions.append("Conflict correction: remove instructions that cause pose drift, continuity breaks, chaotic camera, or extra subjects.")
    if scene_feedback:
        adj = scene_feedback.get("recommended_adjustments", {})
        issues = scene_feedback.get("detected_issues", [])
        if adj.get("simplify_motion_plan"):
            additions.append("Scene correction: use one repeated readable performance movement phrase instead of several different moves.")
        if adj.get("isolate_camera_directive"):
            additions.append("Scene correction: camera follows the performer rhythm with one controlled cinematic move only.")
        if adj.get("prompt_compression"):
            additions.append("Scene correction: compress visual instructions and prioritize motion, timing, and camera obedience.")
        if adj.get("increase_downbeat_locking"):
            additions.append("Scene correction: downbeat hits must be visibly emphasized by performer motion and camera pulse.")
        if "winning_pattern_candidate" in issues:
            additions.append("Preserve the successful phrasing and visual rhythm from this scene; do not overcorrect.")
    if not additions:
        return prompt
    feedback_block = " ASMO feedback update: " + " ".join(additions)
    max_chars = 5000
    combined = prompt.strip() + feedback_block
    if len(combined) <= max_chars:
        return combined
    keep = max_chars - len(feedback_block) - 20
    if keep < 1000:
        return combined[:max_chars]
    return prompt[:keep].rstrip() + feedback_block


def apply_feedback_to_plan(plan: dict, feedback_packet: dict, policy: dict | None = None) -> dict:
    policy = policy or {}
    global_adjustments = feedback_packet.get("global_adjustments", {})
    sfm = scene_feedback_map(feedback_packet)
    new_plan = json.loads(json.dumps(plan))
    new_plan.setdefault("asmo_feedback_applied", True)
    new_plan["asmo_feedback_source_session"] = feedback_packet.get("session_id")
    new_plan["asmo_policy_snapshot"] = policy.get("learned_adjustments", {})
    for item in new_plan.get("results", []):
        idx = item.get("clip_index")
        try:
            idx_int = int(idx)
        except Exception:
            idx_int = None
        original = item.get("prompt_text", "")
        item["base_prompt_before_feedback"] = original
        item["prompt_text"] = patch_prompt(original, sfm.get(idx_int), global_adjustments, policy)
        item["asmo_feedback_applied"] = True
        item["asmo_feedback_adjustments"] = sfm.get(idx_int, {}).get("recommended_adjustments", {}) if idx_int else {}
    return new_plan


def main():
    parser = argparse.ArgumentParser(description="Apply LTX feedback/policy memory back into an ASMO/LTX scene plan.")
    parser.add_argument("--plan-json", required=True)
    parser.add_argument("--state-root", default="outputs/ltx_video_run/_state")
    parser.add_argument("--feedback", default=None)
    parser.add_argument("--policy", default=None)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    plan = read_json(Path(args.plan_json), default={}) or {}
    feedback_path = Path(args.feedback) if args.feedback else Path(args.state_root) / "active" / "feedback" / "feedback_packet.json"
    policy_path = Path(args.policy) if args.policy else Path(args.state_root) / "policy" / "asmo_policy.json"
    feedback = read_json(feedback_path, default={}) or {}
    policy = read_json(policy_path, default={}) or {}
    patched = apply_feedback_to_plan(plan, feedback, policy)
    write_json(Path(args.output), patched)
    print(json.dumps({"status": "complete", "output": str(Path(args.output).resolve()), "scene_count": len(patched.get("results", []))}, indent=2))


if __name__ == "__main__":
    main()
