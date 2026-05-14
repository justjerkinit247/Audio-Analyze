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


def clamp(value: float, low=0.0, high=1.0) -> float:
    return max(low, min(high, float(value)))


def avg(values, default=0.65):
    vals = [float(v) for v in values if isinstance(v, (int, float))]
    return sum(vals) / len(vals) if vals else default


def score_strategies(state_root: Path) -> dict:
    state_root = Path(state_root)
    features = read_jsonl(state_root / "active" / "features" / "scene_features.jsonl")
    visual = read_json(state_root / "active" / "critic" / "visual_critic_report.json", default={}) or {}
    feedback = read_json(state_root / "active" / "feedback" / "feedback_packet.json", default={}) or {}
    critic_scenes = visual.get("scenes", []) if isinstance(visual, dict) else []
    scene_feedback = feedback.get("scene_feedback", []) if isinstance(feedback, dict) else []

    beat_score = avg([s.get("scores", {}).get("beat_sync") for s in scene_feedback])
    motion_score = avg([s.get("scores", {}).get("motion_intent_match") for s in scene_feedback])
    camera_score = avg([s.get("scores", {}).get("camera_intent_match") for s in scene_feedback])
    obedience_score = avg([s.get("scores", {}).get("prompt_obedience") for s in scene_feedback])
    visual_quality = avg([s.get("scores", {}).get("visual_quality") for s in scene_feedback])
    seed_fidelity = avg([s.get("visual_scores", {}).get("seed_fidelity") for s in critic_scenes], default=0.75)
    continuity = avg([s.get("visual_scores", {}).get("continuity") for s in critic_scenes], default=0.75)
    prompt_length_avg = avg([f.get("prompt_length_chars") for f in features], default=3500)
    conflict_avg = avg([f.get("conflict_directive_count") for f in features], default=0)
    camera_directives = avg([f.get("camera_directive_count") for f in features], default=5)
    motion_directives = avg([f.get("motion_directive_count") for f in features], default=7)

    scores = {
        "simple_downbeat_locked_choreo": {"score": round(clamp(beat_score * 0.70 + motion_score * 0.30), 3), "reason": "Rewards beat sync and motion-intent match."},
        "camera_follows_motion": {"score": round(clamp(camera_score * 0.75 + visual_quality * 0.25), 3), "reason": "Rewards camera intent match and visual quality."},
        "prompt_compressed_motion_first": {"score": round(clamp(obedience_score * 0.55 + (1.0 - min(prompt_length_avg / 5000.0, 1.0)) * 0.30 + (1.0 - min(conflict_avg, 1.0)) * 0.15), 3), "reason": "Rewards prompt obedience, shorter prompts, and fewer conflicts."},
        "cinematic_detail_rich": {"score": round(clamp(visual_quality * 0.60 + obedience_score * 0.40 - (0.12 if prompt_length_avg > 4300 else 0.0)), 3), "reason": "Useful only when rich prompts still obey well."},
        "single_camera_move": {"score": round(clamp(camera_score * 0.70 + (1.0 - min(camera_directives / 14.0, 1.0)) * 0.30), 3), "reason": "Rewards camera match and fewer competing camera instructions."},
        "movement_simplicity": {"score": round(clamp(motion_score * 0.70 + (1.0 - min(motion_directives / 18.0, 1.0)) * 0.30), 3), "reason": "Rewards motion match and fewer competing movement instructions."},
        "seed_fidelity_priority": {"score": round(clamp(seed_fidelity * 0.70 + continuity * 0.30), 3), "reason": "Rewards seed-image consistency and continuity."},
    }
    ranked = sorted(scores.items(), key=lambda kv: kv[1]["score"], reverse=True)
    result = {"strategies": scores, "ranked": [{"name": k, **v} for k, v in ranked]}
    write_json(state_root / "active" / "feedback" / "strategy_scores.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description="Score LTX-ASMO strategies from active session evidence.")
    parser.add_argument("--state-root", default="outputs/ltx_video_run/_state")
    args = parser.parse_args()
    print(json.dumps(score_strategies(Path(args.state_root)), indent=2))


if __name__ == "__main__":
    main()
