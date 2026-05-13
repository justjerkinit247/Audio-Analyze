from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def write_json(path: str | Path, data: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def write_csv(path: str | Path, events: list[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    fields = [
        "timecode",
        "timestamp_ms",
        "lyric",
        "motion_vector",
        "camera_state",
    ]

    with p.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for event in events:
            writer.writerow({field: event.get(field, "") for field in fields})


def write_markdown_preview(path: str | Path, timeline: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# ASMO Motion Timeline Preview",
        "",
        f"Schema: `{timeline.get('schema', '')}`",
        f"Events: `{len(timeline.get('events', []))}`",
        "",
        "## Motion Events",
        "",
    ]

    for event in timeline.get("events", []):
        lines.extend(
            [
                f"### {event.get('timecode')}",
                "",
                f"- Lyric: `{event.get('lyric')}`",
                f"- Timestamp ms: `{event.get('timestamp_ms')}`",
                "",
            ]
        )

    p.write_text("\n".join(lines), encoding="utf-8")
