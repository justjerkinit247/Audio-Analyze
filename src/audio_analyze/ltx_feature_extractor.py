from __future__ import annotations

from pathlib import Path
import argparse
import json
import re


MOTION_WORDS = {
    "hip", "hips", "glute", "twerk", "squat", "thigh", "knees", "bounce",
    "groove", "dance", "choreo", "choreography", "movement", "body", "accent"
}
CAMERA_WORDS = {
    "camera", "dolly", "push", "tracking", "pan", "tilt", "zoom", "framing",
    "wide", "closeup", "close-up", "angle", "lens", "cinematic"
}
TIMING_WORDS = {
    "beat", "downbeat", "kick", "snare", "bass", "rhythm", "sync", "tempo",
    "locked", "accent", "hit"
}
CONFLICT_WORDS = {
    "chaotic", "spin", "random", "fast cuts", "teleport", "new people",
    "costume changes", "extra limbs", "contortion"
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


def count_terms(text: str, terms: set[str]) -> int:
    low = (text or "").lower()
    return sum(low.count(term) for term in terms)


def normalize_score(value, default=None):
    if value is None:
        return default
    try:
        v = float(value)
    except Exception:
        return default
    if v > 1:
        v = v / 10.0
    return max(0.0, min(1.0, v))


def extract_scene_features(result: dict, human_score: dict | None = None) -> dict:
    human_score = human_score or {}
    prompt = result.get("prompt_text") or ""
    scene = result.get("scene") or {}
    ltx_result = result.get("ltx_result") or {}

    prompt_words = re.findall(r"[A-Za-z0-9_-]+", prompt)
    motion_count = count_terms(prompt, MOTION_WORDS)
    camera_count = count_terms(prompt, CAMERA_WORDS)
    timing_count = count_terms(prompt, TIMING_WORDS)
    conflict_count = count_terms(prompt, CONFLICT_WORDS)

    duration = scene.get("duration") or scene.get("duration_seconds")
    try:
        duration = float(duration)
    except Exception:
        duration = None

    return {
        "clip_index": result.get("clip_index"),
        "status": result.get("status"),
        "failure_class": result.get("failure_class"),
        "retry_recommended": result.get("retry_recommended"),
        "model": result.get("model"),
        "guidance_scale": result.get("guidance_scale"),
        "resolution": result.get("resolution"),
        "scene_duration": duration,
        "scene_audio_format": result.get("scene_audio_format"),
        "has_downloaded_mp4": bool(result.get("downloaded_mp4") or ltx_result.get("downloaded_mp4")),
        "prompt_length_chars": len(prompt),
        "prompt_word_count": len(prompt_words),
        "motion_directive_count": motion_count,
        "camera_directive_count": camera_count,
        "timing_directive_count": timing_count,
        "conflict_directive_count": conflict_count,
        "prompt_density": round((motion_count + camera_count + timing_count) / max(len(prompt_words), 1), 4),
        "human_scores": {
            "beat_sync": normalize_score(human_score.get("beat_sync")),
            "motion_match": normalize_score(human_score.get("motion_match")),
            "camera_match": normalize_score(human_score.get("camera_match")),
            "visual_quality": normalize_score(human_score.get("visual_quality")),
            "prompt_obedience": normalize_score(human_score.get("prompt_obedience")),
        },
        "human_notes": human_score.get("notes"),
    }


def load_human_scorecard(state_root: Path) -> dict:
    path = Path(state_root) / "active" / "review" / "human_scorecard.json"
    return read_json(path, default={}) or {}


def score_for_clip(scorecard: dict, clip_index) -> dict:
    if clip_index is None:
        return {}
    keys = [f"scene_{int(clip_index):02d}", f"scene_{int(clip_index)}", str(int(clip_index))]
    for key in keys:
        if key in scorecard:
            return scorecard[key] or {}
    return {}


def extract_from_state(state_root: Path) -> list[dict]:
    state_root = Path(state_root)
    scorecard = load_human_scorecard(state_root)
    features = []
    for result_path in sorted((state_root / "active" / "scene_returns").glob("scene_*_result.json")):
        result = read_json(result_path, default={}) or {}
        human = score_for_clip(scorecard, result.get("clip_index"))
        features.append(extract_scene_features(result, human))
    return features


def write_features_jsonl(state_root: Path, features: list[dict]) -> Path:
    out = Path(state_root) / "active" / "features" / "scene_features.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for row in features:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    write_json(Path(state_root) / "active" / "features" / "scene_features_latest.json", {"features": features})
    return out


def main():
    parser = argparse.ArgumentParser(description="Extract compact features from active LTX live-session returns.")
    parser.add_argument("--state-root", default="outputs/ltx_video_run/_state")
    args = parser.parse_args()
    features = extract_from_state(Path(args.state_root))
    out = write_features_jsonl(Path(args.state_root), features)
    print(json.dumps({"feature_count": len(features), "output": str(out)}, indent=2))


if __name__ == "__main__":
    main()
