from __future__ import annotations

from pathlib import Path
from typing import Any

from .beat_grid_engine import BeatGridEngine
from .camera_inertia_engine import CameraInertiaEngine, CameraState
from .lyric_loader import load_lyrics
from .motion_vector_engine import MotionVectorEngine
from .timecode import format_ms


class ASMOEngine:
    """Adaptive Semantic Motion Orchestration engine."""

    def __init__(self, max_beat_lock_distance_ms: int = 140):
        self.beat_engine = BeatGridEngine(max_lock_distance_ms=max_beat_lock_distance_ms)
        self.motion_vector_engine = MotionVectorEngine()
        self.camera_engine = CameraInertiaEngine()

    def generate_timeline(
        self,
        lyric_path: str | Path,
    ) -> dict[str, Any]:
        lyrics = load_lyrics(lyric_path)
        events = []
        camera_state = CameraState()

        for line in lyrics:
            timestamp_ms = line.start_ms or (line.line_number * 2000)

            lock = self.beat_engine.lock_to_nearest_beat(
                target_ms=timestamp_ms,
                beat_times_ms=[0, 500, 1000, 1500, 2000, 2500, 3000, 3500, 4000],
            )

            motion = self.motion_vector_engine.synthesize(
                beat_confidence=lock.confidence,
                onset_strength=0.75,
                vocal_energy=0.65,
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
                    "motion_vector": motion.__dict__,
                    "camera_state": camera_state.__dict__,
                }
            )

        return {
            "schema": "asmo.motion_timeline.v1",
            "events": events,
        }


def generate_asmo_timeline(lyric_path: str | Path) -> dict[str, Any]:
    return ASMOEngine().generate_timeline(lyric_path=lyric_path)
