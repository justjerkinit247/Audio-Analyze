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


def read_jsonl(path: Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def load_memory(state_root: Path) -> dict:
    root = Path(state_root) / "memory"
    return {
        "movement_skills": read_json(root / "movement_skills.json", default={}) or {},
        "camera_skills": read_json(root / "camera_skills.json", default={}) or {},
        "prompt_rules": read_json(root / "prompt_rules.json", default={}) or {},
        "winning_patterns": read_jsonl(root / "winning_patterns.jsonl"),
        "failure_patterns": read_jsonl(root / "failure_patterns.jsonl"),
        "strategy_scores": read_jsonl(root / "strategy_scores.jsonl"),
    }


def best_skill_name(skills: dict) -> str | None:
    items = (skills or {}).get("skills", {})
    if not items:
        return None
    return sorted(items.items(), key=lambda kv: float(kv[1].get("weight", 1.0)), reverse=True)[0][0]


def issue_set(feedback_packet: dict, scene_id: int) -> set[str]:
    for item in feedback_packet.get("scene_feedback", []):
        if int(item.get("scene_id") or -1) == int(scene_id):
            return set(item.get("detected_issues", []))
    return set()


def compress_prompt(prompt: str, max_chars: int = 4200) -> str:
    prompt = " ".join((prompt or "").split())
    if len(prompt) <= max_chars:
        return prompt
    return prompt[:max_chars].rsplit(" ", 1)[0].rstrip() + "."


def build_memory_directive(memory: dict, feedback_packet: dict, scene_id: int) -> str:
    issues = issue_set(feedback_packet, scene_id)
    movement_skill = best_skill_name(memory.get("movement_skills"))
    camera_skill = best_skill_name(memory.get("camera_skills"))
    rules = (memory.get("prompt_rules") or {}).get("rules", {})
    parts = []
    if movement_skill == "downbeat_locked_motion" or "weak_beat_sync" in issues:
        parts.append("Use strict downbeat-locked movement; visible action must land on strong beat accents.")
    if movement_skill == "simple_repeating_phrase" or "motion_overload" in issues:
        parts.append("Use one simple repeated movement phrase instead of stacking several movement ideas.")
    if camera_skill == "single_controlled_camera_move" or "camera_overload" in issues:
        parts.append("Use one controlled camera move only; avoid competing camera instructions.")
    if camera_skill == "camera_follows_motion":
        parts.append("Camera motion should follow the visible performance rhythm.")
    if "prompt_obedience_low" in issues and rules.get("compress_when_obedience_low", True):
        parts.append("Prioritize prompt obedience: motion, timing, camera, seed fidelity, then visual detail.")
    if "conflicting_directives_detected" in issues and rules.get("remove_conflicting_directives", True):
        parts.append("Remove conflicting instructions that could cause pose drift, continuity breaks, extra subjects, or chaotic camera.")
    if "seed_drift" in issues or rules.get("prioritize_seed_fidelity_when_drift_detected", True):
        parts.append("Preserve the seed image composition, subject count, framing, wardrobe, and background as source of truth.")
    winning = [p for p in memory.get("winning_patterns", []) if p.get("type") == "strategy"][-3:]
    if winning:
        parts.append("Favor learned winning strategies: " + ", ".join(p.get("name", "") for p in winning if p.get("name")) + ".")
    return " ".join(part for part in parts if part).strip()


def patch_plan_with_memory(plan: dict, feedback_packet: dict, strategy_scores: dict, memory: dict) -> dict:
    next_plan = json.loads(json.dumps(plan))
    ranked = strategy_scores.get("ranked", []) if isinstance(strategy_scores, dict) else []
    next_plan["asmo_memory_bank_applied"] = True
    next_plan["strategy_scores_applied"] = ranked[:5]
    next_plan["next_scene_planner_version"] = "ltx-asmo-integrated-intelligence-v1"
    for item in next_plan.get("results", []):
        scene_id = int(item.get("clip_index") or 0)
        original = item.get("prompt_text", "")
        directive = build_memory_directive(memory, feedback_packet, scene_id)
        prompt = compress_prompt(original)
        if directive:
            prompt = compress_prompt(prompt + " ASMO Memory Bank update: " + directive, max_chars=5000)
        item["base_prompt_before_memory_bank"] = original
        item["prompt_text"] = prompt
        item["asmo_memory_bank_directive"] = directive
    return next_plan


def build_next_plan(plan_json: Path, state_root: Path, output: Path) -> dict:
    plan = read_json(plan_json, default={}) or {}
    feedback = read_json(Path(state_root) / "active" / "feedback" / "feedback_packet.json", default={}) or {}
    scores = read_json(Path(state_root) / "active" / "feedback" / "strategy_scores.json", default={}) or {}
    memory = load_memory(Path(state_root))
    patched = patch_plan_with_memory(plan, feedback, scores, memory)
    write_json(output, patched)
    return patched


def main():
    parser = argparse.ArgumentParser(description="Create next LTX scene plan using feedback, strategy scores, and ASMO Memory Bank.")
    parser.add_argument("--plan-json", required=True)
    parser.add_argument("--state-root", default="outputs/ltx_video_run/_state")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    patched = build_next_plan(Path(args.plan_json), Path(args.state_root), Path(args.output))
    print(json.dumps({"status": "complete", "output": str(Path(args.output).resolve()), "scene_count": len(patched.get("results", []))}, indent=2))


if __name__ == "__main__":
    main()
