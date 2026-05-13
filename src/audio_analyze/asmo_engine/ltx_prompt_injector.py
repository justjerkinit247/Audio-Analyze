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


def build_ltx_motion_directive_block(
    events: list[dict[str, Any]],
    start_ms: int = 0,
) -> str:
    """Build a prompt-safe timed ASMO directive block for LTX scene prompts."""
    lines = ["TIMED ASMO MOTION DIRECTIVES:"]

    for event in events:
        absolute_ms = int(event.get("timestamp_ms", 0))
        relative_ms = max(0, absolute_ms - int(start_ms))
        seconds = relative_ms / 1000.0
        lyric = str(event.get("lyric", "")).strip()
        directive = event.get("motion_directive", {}) or {}
        motion = directive.get("prompt_fragment") or "sync movement tightly to lyric and beat"
        camera = directive.get("camera_behavior") or "steady_tracking"

        lines.append(
            f"- +{seconds:0.3f}s: {motion}; camera={camera}; lyric='{lyric}'"
        )

    return "\n".join(lines)


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
        block = build_ltx_motion_directive_block(events[:8], start_ms=0)
        item["prompt_text"] = f"{base_prompt}\n\n{block}".strip()
        item["asmo_motion_event_count"] = len(events[:8])

    plan["asmo_timeline_injected"] = True

    write_json(output_json, plan)
    return plan
