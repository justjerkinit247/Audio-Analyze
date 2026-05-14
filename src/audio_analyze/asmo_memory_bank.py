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


def append_jsonl(path: Path, row: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
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


def memory_root(state_root: Path) -> Path:
    root = Path(state_root) / "memory"
    root.mkdir(parents=True, exist_ok=True)
    return root


def init_memory_bank(state_root: Path) -> dict:
    root = memory_root(state_root)
    defaults = {
        "movement_skills.json": {"skills": {"downbeat_locked_motion": {"weight": 1.0}, "simple_repeating_phrase": {"weight": 1.0}}},
        "camera_skills.json": {"skills": {"single_controlled_camera_move": {"weight": 1.0}, "camera_follows_motion": {"weight": 1.0}}},
        "prompt_rules.json": {"rules": {"compress_when_obedience_low": True, "remove_conflicting_directives": True, "preserve_winning_fragments": True, "prioritize_seed_fidelity_when_drift_detected": True}},
    }
    for filename, payload in defaults.items():
        path = root / filename
        if not path.exists():
            write_json(path, payload)
    for filename in ("winning_patterns.jsonl", "failure_patterns.jsonl", "strategy_scores.jsonl"):
        (root / filename).touch(exist_ok=True)
    return {"memory_root": str(root), "files": sorted(p.name for p in root.iterdir())}


def update_skill_weight(file_path: Path, skill_name: str, delta: float) -> None:
    data = read_json(file_path, default={"skills": {}}) or {"skills": {}}
    skill = data.setdefault("skills", {}).setdefault(skill_name, {"weight": 1.0})
    skill["weight"] = round(max(0.1, min(5.0, float(skill.get("weight", 1.0)) + float(delta))), 4)
    write_json(file_path, data)


def update_memory_from_active_state(state_root: Path) -> dict:
    state_root = Path(state_root)
    init_memory_bank(state_root)
    root = memory_root(state_root)
    strategy_scores = read_json(state_root / "active" / "feedback" / "strategy_scores.json", default={}) or {}
    feedback = read_json(state_root / "active" / "feedback" / "feedback_packet.json", default={}) or {}
    for item in strategy_scores.get("ranked", []):
        append_jsonl(root / "strategy_scores.jsonl", item)
        score = float(item.get("score", 0.0))
        name = item.get("name")
        if not name:
            continue
        if score >= 0.78:
            append_jsonl(root / "winning_patterns.jsonl", {"type": "strategy", "name": name, "score": score, "reason": item.get("reason")})
        elif score <= 0.50:
            append_jsonl(root / "failure_patterns.jsonl", {"type": "strategy", "name": name, "score": score, "avoid_rule": item.get("reason")})
        if name in {"simple_downbeat_locked_choreo", "movement_simplicity"}:
            update_skill_weight(root / "movement_skills.json", "downbeat_locked_motion", 0.12 if score >= 0.7 else -0.08)
        if name in {"camera_follows_motion", "single_camera_move"}:
            update_skill_weight(root / "camera_skills.json", "single_controlled_camera_move", 0.12 if score >= 0.7 else -0.08)
    for scene in feedback.get("scene_feedback", []):
        issues = scene.get("detected_issues", [])
        scores = scene.get("scores", {})
        scene_id = scene.get("scene_id")
        if "winning_pattern_candidate" in issues:
            append_jsonl(root / "winning_patterns.jsonl", {"type": "scene", "scene_id": scene_id, "scores": scores})
        for issue in issues:
            if issue != "winning_pattern_candidate":
                append_jsonl(root / "failure_patterns.jsonl", {"type": "scene_issue", "scene_id": scene_id, "issue": issue, "scores": scores})
    return summarize_memory_bank(state_root)


def summarize_memory_bank(state_root: Path) -> dict:
    root = memory_root(state_root)
    summary = {
        "memory_root": str(root),
        "winning_patterns": len(read_jsonl(root / "winning_patterns.jsonl")),
        "failure_patterns": len(read_jsonl(root / "failure_patterns.jsonl")),
        "strategy_score_rows": len(read_jsonl(root / "strategy_scores.jsonl")),
        "movement_skills": read_json(root / "movement_skills.json", default={}),
        "camera_skills": read_json(root / "camera_skills.json", default={}),
        "prompt_rules": read_json(root / "prompt_rules.json", default={}),
    }
    write_json(root / "memory_summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description="Manage ASMO compact memory bank.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "update", "summary"):
        p = sub.add_parser(name)
        p.add_argument("--state-root", default="outputs/ltx_video_run/_state")
    args = parser.parse_args()
    if args.command == "init":
        print(json.dumps(init_memory_bank(Path(args.state_root)), indent=2))
    elif args.command == "update":
        print(json.dumps(update_memory_from_active_state(Path(args.state_root)), indent=2))
    elif args.command == "summary":
        print(json.dumps(summarize_memory_bank(Path(args.state_root)), indent=2))


if __name__ == "__main__":
    main()
