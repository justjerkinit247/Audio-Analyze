from pathlib import Path
import numpy as np
import librosa


def _safe_float(value):
    try:
        if value is None:
            return None

        if isinstance(value, np.ndarray):
            if value.size == 0:
                return None
            value = np.asarray(value).squeeze()
            if getattr(value, "ndim", 0) > 0:
                value = value.flat[0]

        return float(value)
    except Exception:
        return None


def _tempo_fallback_from_beats(beat_frames, duration_seconds):
    try:
        if duration_seconds and duration_seconds > 0 and beat_frames is not None and len(beat_frames) > 1:
            return float(len(beat_frames) * 60.0 / duration_seconds)
    except Exception:
        pass
    return None


def analyze_audio_file(input_path):
    input_path = Path(input_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    y, sr = librosa.load(str(input_path), sr=None, mono=True)
    duration = librosa.get_duration(y=y, sr=sr)

    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    rms = librosa.feature.rms(y=y)[0]
    zcr = librosa.feature.zero_crossing_rate(y)[0]
    spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    spectral_rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)[0]

    pitch_estimate_hz = None
    pitch_min_hz = None
    pitch_max_hz = None
    voiced_frame_ratio = 0.0

    try:
        f0, voiced_flag, voiced_probs = librosa.pyin(
            y,
            fmin=librosa.note_to_hz("C2"),
            fmax=librosa.note_to_hz("C7")
        )

        voiced_f0 = f0[np.isfinite(f0)]
        total_frames = len(f0) if f0 is not None else 0

        if total_frames > 0:
            voiced_frame_ratio = float(len(voiced_f0) / total_frames)

        if len(voiced_f0) > 0:
            pitch_estimate_hz = float(np.median(voiced_f0))
            pitch_min_hz = float(np.min(voiced_f0))
            pitch_max_hz = float(np.max(voiced_f0))
    except Exception:
        pass

    tempo_bpm = _safe_float(tempo)
    if tempo_bpm is None:
        tempo_bpm = _tempo_fallback_from_beats(beat_frames, duration)

    result = {
        "file_name": input_path.name,
        "file_stem": input_path.stem,
        "sample_rate": int(sr),
        "duration_seconds": float(duration),
        "tempo_bpm": tempo_bpm,
        "beats_detected": int(len(beat_frames)),
        "pitch_estimate_hz": pitch_estimate_hz,
        "pitch_min_hz": pitch_min_hz,
        "pitch_max_hz": pitch_max_hz,
        "voiced_frame_ratio": float(voiced_frame_ratio),
        "rms_mean": float(np.mean(rms)),
        "rms_max": float(np.max(rms)),
        "zcr_mean": float(np.mean(zcr)),
        "spectral_centroid_mean_hz": float(np.mean(spectral_centroid)),
        "spectral_rolloff_mean_hz": float(np.mean(spectral_rolloff)),
    }

    return result
