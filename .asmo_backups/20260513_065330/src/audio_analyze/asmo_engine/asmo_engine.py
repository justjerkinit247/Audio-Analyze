from __future__ import annotations

from pathlib import Path
from typing import Any

from .audio_fingerprint_engine import AudioFingerprintEngine
from .beat_grid_engine import BeatGridEngine
from .camera_inertia_engine import CameraInertiaEngine, CameraState
from .lyric_loader import load_lyrics
from .motion_ontology import MotionOntology
from .motion_vector_engine import MotionVectorEngine
from .timecode import format_ms


class ASMOEngine:
    """Adaptive Semantic Motion Orchestration engine."""

    def __init__(self, max_beat_lock_distance_ms: int = 140):
        self.audio_engine = AudioFingerprintEngine()
        self.beat_engine = BeatGridEngine(max_lock_distance_ms=max_beat_lock_distance_ms)
        self.motion_vector_engine = MotionVectorEngine()
        self.camera_engine = CameraInertiaEngine()
        self.motion_ontology = MotionOntology()

    def generate_timeline(
        self,
        lyric_path: str | Path,
        audio_path: str | Path | None = None,
    ) -> dict[str, Any]:
        lyrics = load_lyrics(lyric_path)

        fingerprint = None
        beat_times_ms: list[int] = []
        onset_times_ms: list[int] = []
        onset_strengths: list[float] = []

        if audio_path is not None:
            fingerprint = self.audio_engine.analyze(audio_path)
            beat_times_ms = fingerprint.beat_times_ms
            onset_times_ms = fingerprint.onset_times_ms
            onset_strengths = fingerprint.onset_strengths

        events = []
        camera_state = CameraState()

        for line in lyrics:
            timestamp_ms = line.start_ms or (line.line_number * 2000)

            lock = self.beat_engine.lock_to_nearest_beat(
                target_ms=timestamp_ms,
                beat_times_ms=beat_times_ms,
            )

            onset_strength = self.beat_engine.nearest_onset_strength(
                target_ms=lock.locked_ms,
                onset_times_ms=onset_times_ms,
                onset_strengths=onset_strengths,
            )

            directive = self.motion_ontology.resolve(line.text)

            motion = self.motion_vector_engine.synthesize(
                beat_confidence=lock.confidence,
                onset_strength=max(onset_strength, directive.energy),
                vocal_energy=directive.energy,
            )

            camera_state = self.camera_engine.evolve(
                previous=camera_state,
                amplitude=motion.amplitude,
            )

            events.append(
                {
                    "timecode": format_ms(lock.locked_ms),
                    "timestamp_ms": lock.locked_ms,
                    "lyric": line.text,
                    "motion_directive": directive.__dict__,
                    "motion_vector": motion.__dict__,
                    "camera_state": camera_state.__dict__,
                    "beat_lock": lock.__dict__,
                }
            )

        return {
            "schema": "asmo.motion_timeline.v2",
            "audio_fingerprint": None if fingerprint is None else {
                "tempo_bpm": fingerprint.tempo_bpm,
                "duration_ms": fingerprint.duration_ms,
                "sample_rate": fingerprint.sample_rate,
            },
            "events": events,
        }


def generate_asmo_timeline(
    lyric_path: str | Path,
    audio_path: str | Path | None = None,
) -> dict[str, Any]:
    return ASMOEngine().generate_timeline(
        lyric_path=lyric_path,
        audio_path=audio_path,
    )
