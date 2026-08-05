from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .asmo_engine import ASMOEngine
from .ltx_prompt_injector import build_ltx_motion_directive_block


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path: str | Path, data: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _offset_timeline_events(timeline: dict[str, Any], offset_ms: int) -> dict[str, Any]:
    if not offset_ms:
        return timeline

    shifted = dict(timeline)
    shifted_events: list[dict[str, Any]] = []

    for event in timeline.get("events", []):
        if not isinstance(event, dict):
            continue
        updated = dict(event)
        updated["timestamp_ms"] = int(updated.get("timestamp_ms", 0)) + offset_ms
        shifted_events.append(updated)

    shifted["events"] = shifted_events
    shifted["timestamp_offset_ms"] = offset_ms
    return shifted


def apply_asmo_timeline_to_plan_data(
    plan: dict[str, Any],
    lyric_path: str | Path,
    max_events_per_scene: int = 8,
    start_offset_seconds: float = 0.0,
    engine: ASMOEngine | None = None,
) -> dict[str, Any]:
    """Attach ASMO timing directives to in-memory LTX scene data.

    `start_offset_seconds` shifts lyric/ASMO event timestamps into the same absolute
    source-audio window used by the LTX scene plan. Example: if the run starts at
    01:26, pass 86.0 so relative lyric timestamps align to scenes starting at 86s.
    """
    if int(max_events_per_scene) < 1:
        raise ValueError("max_events_per_scene must be at least 1.")

    patched = deepcopy(plan)
    active_engine = engine or ASMOEngine()
    offset_ms = int(round(float(start_offset_seconds or 0.0) * 1000.0))

    results = patched.get("results", [])
    if not isinstance(results, list):
        raise ValueError("LTX plan JSON must contain a list field named 'results'.")

    timeline_cache: dict[str, dict[str, Any]] = {}

    for item in results:
        if not isinstance(item, dict):
            continue

        scene = item.get("scene", {}) if isinstance(item.get("scene", {}), dict) else {}
        audio_path = item.get("scene_audio_path") or item.get("source_audio_path")

        if not audio_path:
            item["asmo_injection_status"] = "skipped_no_audio_path"
            continue

        audio_path_obj = Path(str(audio_path))
        if not audio_path_obj.exists():
            item["asmo_injection_status"] = "skipped_audio_missing"
            item["asmo_audio_path_checked"] = str(audio_path_obj)
            continue

        cache_key = str(audio_path_obj.resolve())
        if cache_key not in timeline_cache:
            raw_timeline = active_engine.generate_timeline(
                lyric_path=lyric_path,
                audio_path=audio_path_obj,
            )
            timeline_cache[cache_key] = _offset_timeline_events(raw_timeline, offset_ms)

        timeline = timeline_cache[cache_key]

        start_ms = int(round(float(scene.get("start", 0.0)) * 1000.0))
        end_ms = int(round(float(scene.get("end", 10**9)) * 1000.0))

        scene_events = [
            event
            for event in timeline.get("events", [])
            if start_ms <= int(event.get("timestamp_ms", -1)) <= end_ms
        ][:max_events_per_scene]

        if not scene_events:
            item["asmo_injection_status"] = "skipped_no_events_in_scene_window"
            item["asmo_window_start_ms"] = start_ms
            item["asmo_window_end_ms"] = end_ms
            item["asmo_start_offset_seconds"] = float(start_offset_seconds or 0.0)
            continue

        block = build_ltx_motion_directive_block(
            events=scene_events,
            start_ms=start_ms,
        )

        item["asmo_injection_status"] = "injected"
        item["asmo_schema"] = timeline.get("schema")
        item["asmo_motion_event_count"] = len(scene_events)
        item["asmo_motion_events"] = scene_events
        item["asmo_motion_prompt_block"] = block
        item["asmo_start_offset_seconds"] = float(start_offset_seconds or 0.0)

    patched["asmo_ltx_run_integration"] = True
    patched["asmo_lyric_path"] = str(Path(lyric_path))
    patched["asmo_start_offset_seconds"] = float(start_offset_seconds or 0.0)
    return patched


def inject_asmo_into_ltx_run_plan(
    plan_json: str | Path,
    lyric_path: str | Path,
    output_json: str | Path | None = None,
    max_events_per_scene: int = 8,
    start_offset_seconds: float = 0.0,
) -> dict[str, Any]:
    """Inject ASMO timing directives into an existing LTX run-plan JSON file."""
    plan_path = Path(plan_json)
    plan = apply_asmo_timeline_to_plan_data(
        read_json(plan_path),
        lyric_path=lyric_path,
        max_events_per_scene=max_events_per_scene,
        start_offset_seconds=start_offset_seconds,
    )

    for item in plan.get("results", []):
        if not isinstance(item, dict) or item.get("asmo_injection_status") != "injected":
            continue
        base_prompt = str(item.get("prompt_text") or "").strip()
        if "TIMED ASMO MOTION DIRECTIVES:" in base_prompt:
            base_prompt = base_prompt.split("TIMED ASMO MOTION DIRECTIVES:", 1)[0].strip()
        block = str(item.get("asmo_motion_prompt_block") or "").strip()
        item["base_prompt_text_before_asmo"] = (
            item.get("base_prompt_text_before_asmo") or base_prompt
        )
        item["prompt_text"] = f"{base_prompt}\n\n{block}".strip()

    target = Path(output_json) if output_json else plan_path.with_name(plan_path.stem + "_asmo_injected.json")
    write_json(target, plan)
    plan["asmo_output_json"] = str(target)
    return plan
