from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np


@dataclass(frozen=True)
class AudioFingerprint:
    duration_ms: int
    sample_rate: int
    tempo_bpm: float | None
    beat_times_ms: list[int]
    onset_times_ms: list[int]
    onset_strengths: list[float]
    rms_times_ms: list[int]
    rms_values: list[float]
    centroid_mean: float
    rms_mean: float
    onset_mean: float


class AudioFingerprintEngine:
    """Extract beat, onset, RMS, and spectral timing data from an audio file."""

    def analyze(self, audio_path: str | Path) -> AudioFingerprint:
        path = Path(audio_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {path.resolve()}")

        y, sr = librosa.load(str(path), sr=None, mono=True)
        duration_seconds = float(librosa.get_duration(y=y, sr=sr))
        duration_ms = int(round(duration_seconds * 1000.0))

        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        tempo_raw, beat_frames = librosa.beat.beat_track(y=y, sr=sr, onset_envelope=onset_env)
        tempo = self._scalarize(tempo_raw)

        beat_times = librosa.frames_to_time(beat_frames, sr=sr)
        onset_frames = librosa.onset.onset_detect(y=y, sr=sr, onset_envelope=onset_env, backtrack=False)
        onset_times = librosa.frames_to_time(onset_frames, sr=sr)

        rms = librosa.feature.rms(y=y)[0]
        rms_times = librosa.frames_to_time(np.arange(len(rms)), sr=sr)
        centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]

        onset_strengths: list[float] = []
        for frame in onset_frames:
            frame_i = int(frame)
            onset_strengths.append(float(onset_env[frame_i]) if 0 <= frame_i < len(onset_env) else 0.0)

        return AudioFingerprint(
            duration_ms=duration_ms,
            sample_rate=int(sr),
            tempo_bpm=round(float(tempo), 3) if tempo is not None else None,
            beat_times_ms=[int(round(t * 1000.0)) for t in beat_times],
            onset_times_ms=[int(round(t * 1000.0)) for t in onset_times],
            onset_strengths=onset_strengths,
            rms_times_ms=[int(round(t * 1000.0)) for t in rms_times],
            rms_values=[float(v) for v in rms],
            centroid_mean=float(np.mean(centroid)) if len(centroid) else 0.0,
            rms_mean=float(np.mean(rms)) if len(rms) else 0.0,
            onset_mean=float(np.mean(onset_env)) if len(onset_env) else 0.0,
        )

    @staticmethod
    def _scalarize(value) -> float | None:
        arr = np.asarray(value)
        if arr.size == 0:
            return None
        return float(arr.reshape(-1)[0])
