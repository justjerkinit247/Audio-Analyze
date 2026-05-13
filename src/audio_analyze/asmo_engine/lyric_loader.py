from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .timecode import parse_timecode_to_ms

_LRC_RE = re.compile(
    r"^\[(?P<time>\d{1,2}:\d{2}(?:[.,]\d{1,3})?)\]\s*(?P<text>.*)$"
)

@dataclass(frozen=True)
class LyricLine:
    text: str
    start_ms: int | None = None
    end_ms: int | None = None
    line_number: int = 0


def load_lyrics(path: str | Path) -> list[LyricLine]:
    """Load plain TXT or LRC lyric text."""
    p = Path(path)
    raw = p.read_text(encoding="utf-8-sig")
    lines: list[LyricLine] = []

    for index, raw_line in enumerate(raw.splitlines(), start=1):
        line = raw_line.strip()

        if not line:
            continue

        lrc_match = _LRC_RE.match(line)
        if lrc_match:
            lines.append(
                LyricLine(
                    text=lrc_match.group("text").strip(),
                    start_ms=parse_timecode_to_ms(lrc_match.group("time")),
                    end_ms=None,
                    line_number=index,
                )
            )
            continue

        lines.append(
            LyricLine(
                text=line,
                start_ms=None,
                end_ms=None,
                line_number=index,
            )
        )

    return [line for line in lines if line.text]
