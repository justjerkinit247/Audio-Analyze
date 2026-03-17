from __future__ import annotations

import argparse
import json
from pathlib import Path

import librosa
import numpy as np


def estimate_pitch(y: np.ndarray, sr: int) -> float | None:
    f0, voiced_flag, _ = librosa.pyin(
        y,
        fmin=librosa.note_to_hz("C2"),
        fmax=librosa.note_to_hz("C7"),
    )
    valid_f0 = f0[~np.isnan(f0)]
    if len(valid_f0) == 0:
        return None
    return float(np.median(valid_f0))


def analyze_audio(file_path: str) -> dict:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    y, sr = librosa.load(path, sr=None, mono=True)

    duration_sec = float(librosa.get_duration(y=y, sr=sr))
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    rms = librosa.feature.rms(y=y)[0]
    pitch_hz = estimate_pitch(y, sr)

    result = {
        "file": str(path),
        "sample_rate": int(sr),
        "duration_sec": round(duration_sec, 3),
        "tempo_bpm_est": round(float(tempo), 2),
        "rms_mean": round(float(np.mean(rms)), 6),
        "rms_max": round(float(np.max(rms)), 6),
        "median_pitch_hz": round(pitch_hz, 2) if pitch_hz is not None else None,
    }

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze an audio file.")
    parser.add_argument("audio_file", help="Path to WAV/MP3 audio file")
    parser.add_argument(
        "--save-json",
        action="store_true",
        help="Save results to outputs/analysis_result.json",
    )
    args = parser.parse_args()

    result = analyze_audio(args.audio_file)
    print(json.dumps(result, indent=2))

    if args.save_json:
        outputs_dir = Path("outputs")
        outputs_dir.mkdir(exist_ok=True)
        out_file = outputs_dir / "analysis_result.json"
        out_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"\nSaved: {out_file}")


if __name__ == "__main__":
    main()
