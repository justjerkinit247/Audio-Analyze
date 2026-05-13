from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CameraState:
    pan: float = 0.0
    tilt: float = 0.0
    push: float = 0.0
    roll: float = 0.0
    tension: float = 0.0


class CameraInertiaEngine:
    """Creates camera motion that carries momentum instead of random AI jumps."""

    def evolve(self, previous: CameraState, amplitude: float) -> CameraState:
        inertia = 0.68

        return CameraState(
            pan=round(previous.pan * inertia + amplitude * 0.10, 4),
            tilt=round(previous.tilt * inertia + amplitude * 0.05, 4),
            push=round(previous.push * inertia + amplitude * 0.12, 4),
            roll=round(previous.roll * inertia + amplitude * 0.02, 4),
            tension=round(min(1.0, previous.tension * 0.55 + amplitude * 0.45), 4),
        )
