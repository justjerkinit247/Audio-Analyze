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


def normalize_score(value, default=0.65):
    if value is None:
        return default
    try:
        v = float(value)
    except Exception:
        return default
    if v > 1:
        v = v / 10.0
    return max(0.0, min(1.0, v))


def load_scorecard(state_root: Path) -> dict:
    return read_json(Path(state_root) / "active" / "review" / "human_scorecard.json", default={}) or {}


def score_for_scene(scorecard: dict, scene_id: int) -> dict:
    for key in (f"scene_{scene_id:02d}", f"scene_{scene_id}", str(scene_id)):
        if key in scorecard:
            return scorecard[key] or {}
    return {}


def build_visual_critic_report(state_root: Path, external_critic_json: Path | None = None) -> dict:
    state_root = Path(state_root)
    scorecard = load_scorecard(state_root)
    external = read_json(external_critic_json, default={}) if external_critic_json else {}
    scenes = []
    for result_path in sorted((state_root / "active" / "scene_returns").glob("scene_*_result.json")):
        result = read_json(result_path, default={}) or {}
        scene_id = int(result.get("clip_index") or 0)
        human = score_for_scene(scorecard, scene_id)
        external_scene = (external or {}).get(f"scene_{scene_id:02d}", {}) if isinstance(external, dict) else {}
        prompt_match = normalize_score(external_scene.get("prompt_match"), normalize_score(human.get("prompt_obedience"), 0.65))
        motion_readability = normalize_score(external_scene.get("motion_readability"), normalize_score(human.get("motion_match"), 0.65))
        camera_match = normalize_score(external_scene.get("camera_match"), normalize_score(human.get("camera_match"), 0.65))
        seed_fidelity = normalize_score(external_scene.get("seed_fidelity"), 0.75)
        continuity = normalize_score(external_scene.get("continuity"), 0.75)
        flags = []
        if camera_match < 0.6:
            flags.append("camera_problem")
        if motion_readability < 0.6:
            flags.append("motion_not_readable")
        if prompt_match < 0.6:
            flags.append("prompt_mismatch")
        if seed_fidelity < 0.65:
            flags.append("seed_drift")
        if continuity < 0.65:
            flags.append("continuity_problem")
        if prompt_match >= 0.78 and motion_readability >= 0.78 and camera_match >= 0.78:
            flags.append("winning_visual_pattern")
        scenes.append({
            "scene_id": scene_id,
            "source_result": str(result_path),
            "visual_scores": {
                "prompt_match": round(prompt_match, 3),
                "motion_readability": round(motion_readability, 3),
                "camera_match": round(camera_match, 3),
                "seed_fidelity": round(seed_fidelity, 3),
                "continuity": round(continuity, 3),
            },
            "detected_flags": flags,
            "notes": external_scene.get("notes") or human.get("notes"),
            "external_critic_used": bool(external_scene),
        })
    report = {"scene_count": len(scenes), "scenes": scenes}
    write_json(state_root / "active" / "critic" / "visual_critic_report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description="Build optional visual critic report for the active LTX session.")
    parser.add_argument("--state-root", default="outputs/ltx_video_run/_state")
    parser.add_argument("--external-critic-json", default=None)
    args = parser.parse_args()
    report = build_visual_critic_report(Path(args.state_root), Path(args.external_critic_json) if args.external_critic_json else None)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
