from __future__ import annotations

import re

_TIMECODE_RE = re.compile(
    r"^(?:(?P<hours>\d{1,2}):)?"
    r"(?P<minutes>\d{1,2}):"
    r"(?P<seconds>\d{1,2})"
    r"(?:[.,](?P<millis>\d{1,3}))?$"
)


def seconds_to_ms(seconds: float) -> int:
    """Convert seconds to integer milliseconds."""
    return int(round(float(seconds) * 1000.0))


def ms_to_seconds(milliseconds: int | float) -> float:
    """Convert milliseconds to seconds."""
    return float(milliseconds) / 1000.0


def format_ms(milliseconds: int | float) -> str:
    """Format milliseconds as HH:MM:SS.mmm."""
    total_ms = int(round(float(milliseconds)))
    if total_ms < 0:
        total_ms = 0

    ms = total_ms % 1000
    total_seconds = total_ms // 1000
    seconds = total_seconds % 60
    total_minutes = total_seconds // 60
    minutes = total_minutes % 60
    hours = total_minutes // 60

    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{ms:03d}"


def parse_timecode_to_ms(value: str) -> int:
    """Parse HH:MM:SS.mmm, MM:SS.mmm, or MM:SS into milliseconds."""
    text = value.strip()
    match = _TIMECODE_RE.match(text)
    if not match:
        raise ValueError(f"Invalid timecode: {value!r}")

    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes"))
    seconds = int(match.group("seconds"))
    millis_text = match.group("millis") or "0"
    millis = int(millis_text.ljust(3, "0")[:3])

    return (((hours * 60 + minutes) * 60 + seconds) * 1000) + millis


def clamp_ms(value: int | float, minimum: int | float, maximum: int | float) -> int:
    """Clamp a millisecond value."""
    return int(max(float(minimum), min(float(maximum), float(value))))
