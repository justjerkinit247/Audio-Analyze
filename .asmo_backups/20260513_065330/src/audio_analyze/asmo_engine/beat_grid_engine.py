from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BeatLock:
    original_ms: int
    locked_ms: int
    distance_ms: int
    confidence: float
    lock_type: str


class BeatGridEngine:
    """Snaps lyric/motion events to musically useful timing anchors."""

    def __init__(self, max_lock_distance_ms: int = 140):
        self.max_lock_distance_ms = int(max_lock_distance_ms)

    def lock_to_nearest_beat(self, target_ms: int, beat_times_ms: list[int]) -> BeatLock:
        if not beat_times_ms:
            return BeatLock(
                original_ms=int(target_ms),
                locked_ms=int(target_ms),
                distance_ms=0,
                confidence=0.0,
                lock_type="no_beat_grid",
            )

        nearest = min(beat_times_ms, key=lambda t: abs(t - target_ms))
        distance = abs(int(nearest) - int(target_ms))

        if distance <= self.max_lock_distance_ms:
            confidence = max(0.0, 1.0 - (distance / float(self.max_lock_distance_ms)))
            return BeatLock(
                original_ms=int(target_ms),
                locked_ms=int(nearest),
                distance_ms=distance,
                confidence=round(confidence, 4),
                lock_type="beat_locked",
            )

        return BeatLock(
            original_ms=int(target_ms),
            locked_ms=int(target_ms),
            distance_ms=distance,
            confidence=0.25,
            lock_type="kept_original_timing",
        )

    def nearest_onset_strength(
        self,
        target_ms: int,
        onset_times_ms: list[int],
        onset_strengths: list[float],
    ) -> float:
        if not onset_times_ms or not onset_strengths:
            return 0.0

        nearest_index, _ = min(
            enumerate(onset_times_ms),
            key=lambda item: abs(item[1] - target_ms),
        )

        if nearest_index >= len(onset_strengths):
            return 0.0

        return float(onset_strengths[nearest_index])
