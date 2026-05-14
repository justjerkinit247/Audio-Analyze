from __future__ import annotations

from pathlib import Path
import argparse
import json

import librosa
import numpy as np


SUPPORTED_LOSSLESS = {".wav", ".flac", ".aiff", ".aif"}
SUPPORTED_COMPRESSED = {".mp3", ".ogg", ".m4a", ".aac"}


def write_json(path: Path, data) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def scalarize(value):
    arr = np.asarray(value)
    if arr.size == 0:
        return None
    return float(arr.reshape(-1)[0])


def classify_audio_source(audio_path: Path) -> dict:
    audio_path = Path(audio_path)
    suffix = audio_path.suffix.lower()
    if suffix in SUPPORTED_LOSSLESS:
        quality_class = "lossless_preferred"
        recommendation = "Good analysis source. Keep this as the beat-analysis master."
    elif suffix in SUPPORTED_COMPRESSED:
        quality_class = "compressed_usable"
        recommendation = "Usable, but WAV or FLAC is recommended for cleaner onset and beat detection."
    else:
        quality_class = "unknown"
        recommendation = "Unknown audio container. Use WAV 48kHz/24-bit when possible."
    return {
        "path": str(audio_path),
        "suffix": suffix,
        "quality_class": quality_class,
        "recommendation": recommendation,
    }


def analyze_beat_grid(audio_path: Path, hop_length: int = 512) -> dict:
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    y, sr = librosa.load(str(audio_path), sr=None, mono=True)
    duration = float(librosa.get_duration(y=y, sr=sr))
    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop_length)
    tempo_raw, beat_frames = librosa.beat.beat_track(y=y, sr=sr, onset_envelope=onset_env, hop_length=hop_length)
    tempo = scalarize(tempo_raw)
    beat_times = [float(t) for t in librosa.frames_to_time(beat_frames, sr=sr, hop_length=hop_length)]
    onset_times = [float(t) for t in librosa.onset.onset_detect(y=y, sr=sr, units="time", hop_length=hop_length)]

    onset_strength_mean = float(np.mean(onset_env)) if len(onset_env) else 0.0
    onset_strength_std = float(np.std(onset_env)) if len(onset_env) else 0.0
    beat_intervals = np.diff(beat_times) if len(beat_times) > 1 else np.array([])
    interval_std = float(np.std(beat_intervals)) if len(beat_intervals) else None
    interval_mean = float(np.mean(beat_intervals)) if len(beat_intervals) else None

    if interval_mean and interval_mean > 0:
        stability = max(0.0, min(1.0, 1.0 - (interval_std or 0.0) / interval_mean))
    else:
        stability = 0.0

    density = len(onset_times) / duration if duration > 0 else 0.0
    strength_score = max(0.0, min(1.0, onset_strength_mean / 5.0))
    beat_count_score = max(0.0, min(1.0, len(beat_times) / max(duration / 0.75, 1.0)))
    beat_confidence = round((stability * 0.45) + (strength_score * 0.30) + (beat_count_score * 0.25), 4)

    return {
        "audio_source": classify_audio_source(audio_path),
        "sample_rate": int(sr),
        "duration_seconds": round(duration, 4),
        "tempo_bpm": round(float(tempo), 4) if tempo is not None else None,
        "beat_count": len(beat_times),
        "onset_count": len(onset_times),
        "onset_density_per_second": round(density, 4),
        "onset_strength_mean": round(onset_strength_mean, 6),
        "onset_strength_std": round(onset_strength_std, 6),
        "beat_interval_mean": round(interval_mean, 6) if interval_mean is not None else None,
        "beat_interval_std": round(interval_std, 6) if interval_std is not None else None,
        "beat_stability_score": round(stability, 4),
        "beat_confidence": beat_confidence,
        "beat_times": [round(t, 4) for t in beat_times],
        "onset_times": [round(t, 4) for t in onset_times],
    }


def nearest_beat_distance(time_value: float, beat_times: list[float]) -> float | None:
    if not beat_times:
        return None
    return min(abs(float(time_value) - float(b)) for b in beat_times)


def score_scene_boundaries(plan: dict, beat_report: dict) -> dict:
    beat_times = beat_report.get("beat_times", []) or []
    scenes = []
    for item in plan.get("results", []):
        scene = item.get("scene", {}) or {}
        start = scene.get("start")
        end = scene.get("end")
        try:
            start = float(start)
            end = float(end)
        except Exception:
            continue
        start_dist = nearest_beat_distance(start, beat_times)
        end_dist = nearest_beat_distance(end, beat_times)
        start_score = 1.0 - min((start_dist or 1.0) / 0.5, 1.0)
        end_score = 1.0 - min((end_dist or 1.0) / 0.5, 1.0)
        scenes.append({
            "clip_index": item.get("clip_index"),
            "start": start,
            "end": end,
            "start_nearest_beat_distance": round(start_dist, 4) if start_dist is not None else None,
            "end_nearest_beat_distance": round(end_dist, 4) if end_dist is not None else None,
            "boundary_confidence": round((start_score + end_score) / 2.0, 4),
        })
    avg_conf = round(float(np.mean([s["boundary_confidence"] for s in scenes])), 4) if scenes else None
    return {"average_boundary_confidence": avg_conf, "scenes": scenes}


def read_json(path: Path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main():
    parser = argparse.ArgumentParser(description="WAV-first beat/onset analysis upgrade for LTX planning.")
    parser.add_argument("--audio", required=True)
    parser.add_argument("--plan-json", default=None)
    parser.add_argument("--output", default="outputs/ltx_video_run/audio_analysis_upgrade.json")
    args = parser.parse_args()

    report = analyze_beat_grid(Path(args.audio))
    if args.plan_json:
        plan = read_json(Path(args.plan_json), default={}) or {}
        report["scene_boundary_report"] = score_scene_boundaries(plan, report)
    write_json(Path(args.output), report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
