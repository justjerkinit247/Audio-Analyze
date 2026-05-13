from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MotionVector:
    x: float
    y: float
    z: float
    velocity: float
    acceleration: float
    amplitude: float
    smoothness: float


class MotionVectorEngine:
    """Synthesizes body-motion vectors from semantic intent and audio force."""

    def synthesize(
        self,
        beat_confidence: float,
        onset_strength: float,
        vocal_energy: float = 0.5,
    ) -> MotionVector:
        normalized_onset = min(1.0, max(0.0, float(onset_strength) / 8.0))

        energy = max(
            0.15,
            min(
                1.0,
                (normalized_onset * 0.45)
                + (beat_confidence * 0.35)
                + (vocal_energy * 0.20),
            ),
        )

        return MotionVector(
            x=round(0.45 * energy, 4),
            y=round(0.25 * energy, 4),
            z=round(0.15 * energy, 4),
            velocity=round(0.25 + energy * 0.70, 4),
            acceleration=round(0.15 + energy * 0.80, 4),
            amplitude=round(energy, 4),
            smoothness=round(0.55, 4),
        )
