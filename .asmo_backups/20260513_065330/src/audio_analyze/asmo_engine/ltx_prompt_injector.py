from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path: str | Path, data: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def inject_asmo_timeline_into_ltx_plan(
    plan_json: str | Path,
    asmo_timeline_json: str | Path,
    output_json: str | Path,
) -> dict[str, Any]:
    plan = read_json(plan_json)
    timeline = read_json(asmo_timeline_json)

    events = timeline.get("events", [])

    for item in plan.get("results", []):
        base_prompt = item.get("prompt_text", "").strip()

        lines = [
            "TIMED ASMO MOTION DIRECTIVES:",
        ]

        for event in events[:8]:
            lines.append(
                f"- {event.get('timecode')}: sync movement to lyric '{event.get('lyric')}'"
            )

        item["prompt_text"] = f"{base_prompt}\n\n" + "\n".join(lines)
        item["asmo_motion_event_count"] = len(events[:8])

    plan["asmo_timeline_injected"] = True

    write_json(output_json, plan)
    return plan
