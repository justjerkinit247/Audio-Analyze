from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
import json

try:
    from .ltx_filename_hint_expander import (
        DEFAULT_OLLAMA_MODEL,
        NEGATIVE_MARKER,
        DEFAULT_PROVIDER,
        MOTION_MARKER,
        clean_scene_hint,
        expand_scene_hint,
    )
    from .path_policy import resolve_runtime_path, serialize_path
except ImportError:
    from ltx_filename_hint_expander import (
        DEFAULT_OLLAMA_MODEL,
        NEGATIVE_MARKER,
        DEFAULT_PROVIDER,
        MOTION_MARKER,
        clean_scene_hint,
        expand_scene_hint,
    )
    from path_policy import resolve_runtime_path, serialize_path


DEFAULT_PLAN_EXPANSION_PROVIDER = "ollama"
AUDIO_TIMING_MARKER = "[AUDIO_TIMING]"


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(resolve_runtime_path(path).read_text(encoding="utf-8-sig"))


def write_json(path: str | Path, data: dict[str, Any]) -> None:
    path = resolve_runtime_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_seconds(value: Any) -> str:
    parsed = _as_float(value)
    if parsed is None:
        return "unknown"
    return f"{parsed:.2f}s"


def _format_bpm(value: Any) -> str:
    parsed = _as_float(value)
    if parsed is None:
        return "unknown BPM"
    return f"{parsed:.2f} BPM"


def build_audio_timing_metadata(item: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    scene = item.get("scene") or {}
    analysis = plan.get("analysis") or {}
    start = _as_float(scene.get("start"))
    end = _as_float(scene.get("end"))
    duration = _as_float(scene.get("duration"))
    tempo = analysis.get("tempo_bpm") or analysis.get("tempo_bpm_from_full_track")
    beat_alignment_enabled = bool(item.get("beat_alignment_enabled", plan.get("beat_alignment_enabled", analysis.get("beat_alignment_enabled", False))))

    estimated_beats_in_scene = None
    tempo_float = _as_float(tempo)
    if tempo_float and duration:
        estimated_beats_in_scene = round((duration / 60.0) * tempo_float, 2)

    return {
        "scene_index": scene.get("scene_index") or item.get("clip_index"),
        "source_audio_path": item.get("source_audio_path"),
        "start_seconds": round(start, 3) if start is not None else None,
        "end_seconds": round(end, 3) if end is not None else None,
        "duration_seconds": round(duration, 3) if duration is not None else None,
        "tempo_bpm": round(tempo_float, 3) if tempo_float is not None else None,
        "estimated_beats_in_scene": estimated_beats_in_scene,
        "beat_alignment_enabled": beat_alignment_enabled,
        "scene_type": scene.get("scene_type"),
        "sync_start_rule": scene.get("sync_start_rule"),
        "sync_end_rule": scene.get("sync_end_rule"),
        "sync_policy": analysis.get("sync_policy"),
        "detected_beat_count_full_track": analysis.get("detected_beat_count"),
        "energy_profile": analysis.get("energy_profile"),
        "edit_pacing": analysis.get("edit_pacing"),
        "movement_notes": analysis.get("movement_notes"),
        "camera_notes": analysis.get("camera_notes"),
        "lighting_notes": analysis.get("lighting_notes"),
        "mix_reactivity_notes": analysis.get("mix_reactivity_notes"),
    }


def render_audio_timing_block(audio_timing: dict[str, Any]) -> str:
    scene_index = audio_timing.get("scene_index") or "unknown"
    start = _format_seconds(audio_timing.get("start_seconds"))
    end = _format_seconds(audio_timing.get("end_seconds"))
    duration = _format_seconds(audio_timing.get("duration_seconds"))
    tempo = _format_bpm(audio_timing.get("tempo_bpm"))
    estimated_beats = audio_timing.get("estimated_beats_in_scene")
    beat_text = f"approximately {estimated_beats} beats in this clip" if estimated_beats is not None else "beat count unavailable for this clip"
    beat_alignment = "enabled" if audio_timing.get("beat_alignment_enabled") else "not enabled"
    scene_type = audio_timing.get("scene_type") or "planned phrase"
    sync_policy = audio_timing.get("sync_policy") or "Use the planned scene timestamp window."
    sync_start_rule = audio_timing.get("sync_start_rule") or "start at planned clip start"
    sync_end_rule = audio_timing.get("sync_end_rule") or "end at planned clip end"
    energy = audio_timing.get("energy_profile") or "unknown energy"
    pacing = audio_timing.get("edit_pacing") or "unknown pacing"
    movement = audio_timing.get("movement_notes") or "match visible motion to the clip rhythm"
    camera = audio_timing.get("camera_notes") or "keep camera motion controlled and rhythm-aware"
    lighting = audio_timing.get("lighting_notes") or "preserve seed-image lighting"
    mix = audio_timing.get("mix_reactivity_notes") or "audio reactivity values unavailable"

    return (
        f"{AUDIO_TIMING_MARKER}\n"
        f"Scene {scene_index} audio window: {start} to {end}, duration {duration}. "
        f"Tempo target: {tempo}; {beat_text}. Beat alignment: {beat_alignment}. "
        f"Scene type: {scene_type}. Sync policy: {sync_policy} "
        f"Start rule: {sync_start_rule}; end rule: {sync_end_rule}. "
        f"Motion timing cue: keep visible motion, camera drift, environmental movement, and any major action changes locked to this timestamp window and the detected rhythmic feel. "
        f"Energy/pacing cue: {energy}, {pacing}. Movement cue: {movement}. Camera cue: {camera}. Lighting cue: {lighting}. Mix cue: {mix}.\n"
    )


def build_scene_prompt_from_expansion(item: dict[str, Any], plan: dict[str, Any], expansion: dict[str, Any], audio_timing: dict[str, Any] | None = None) -> str:
    file_stem = item.get("file_stem") or plan.get("file_stem") or "ltx_scene"
    seed_hint = expansion.get("scene_hint") or item.get("seed_filename_prompt_hint") or ""
    audio_timing = audio_timing or build_audio_timing_metadata(item, plan)
    audio_timing_block = render_audio_timing_block(audio_timing)
    return (
        f"Image-to-video continuation for {file_stem}. "
        "Use the seed image as the exact source of truth for subject count, identity, pose, camera angle, framing, lighting, and background. "
        f"Seed filename scene direction: {seed_hint}. "
        "Do not import assumptions from previous projects, genres, songs, characters, religious imagery, nightclub imagery, or dance choreography unless directly present in the seed filename. "
        "Preserve the seed composition and make only the scene motion described below. "
        f"\n\n{audio_timing_block}\n{MOTION_MARKER}\n{expansion['ltx_motion_prompt']}\n\n{NEGATIVE_MARKER}\n{expansion['negative_prompt']}\n"
    )


def _seed_filename(item: dict[str, Any]) -> str:
    seed_path = item.get("seed_image_used") or (item.get("seed_assignment") or {}).get("seed_image_path") or "seed_image.png"
    return Path(str(seed_path)).name


def expand_plan_data(
    plan: dict[str, Any],
    provider: str = DEFAULT_PLAN_EXPANSION_PROVIDER,
    model: str | None = DEFAULT_OLLAMA_MODEL,
    expander: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    expander = expander or expand_scene_hint
    patched = dict(plan)
    results = []
    expansion_count = 0

    for raw_item in plan.get("results", []):
        item = dict(raw_item)
        filename = _seed_filename(item)
        scene_hint = clean_scene_hint(filename) or item.get("seed_filename_prompt_hint") or filename
        expansion = expander(scene_hint, filename=filename, provider=provider, model=model)
        audio_timing = build_audio_timing_metadata(item, plan)
        item["seed_filename_prompt_hint"] = expansion.get("scene_hint", scene_hint)
        item["filename_hint_expansion"] = expansion
        item["audio_timing"] = audio_timing
        item["audio_timing_prompt_block"] = render_audio_timing_block(audio_timing)
        item["prompt_text_before_filename_hint_expansion"] = raw_item.get("prompt_text")
        item["prompt_text"] = build_scene_prompt_from_expansion(item, plan, expansion, audio_timing=audio_timing)
        item["prompt_build_method"] = "filename_hint_expansion_with_audio_timing"
        item["prompt_expansion_provider"] = provider
        if model:
            item["prompt_expansion_model"] = model
        results.append(item)
        expansion_count += 1

    patched["results"] = results
    patched["filename_hint_expansion"] = {
        "status": "applied",
        "provider": provider,
        "model": model,
        "scene_count": expansion_count,
        "audio_timing_prompt_blocks": "applied",
    }
    patched["prompt_build_method"] = "filename_hint_expansion_with_audio_timing"
    return patched


def expand_plan_file(
    plan_json: str | Path,
    output_json: str | Path | None = None,
    provider: str = DEFAULT_PLAN_EXPANSION_PROVIDER,
    model: str | None = DEFAULT_OLLAMA_MODEL,
) -> dict[str, Any]:
    plan = read_json(plan_json)
    patched = expand_plan_data(plan, provider=provider, model=model)
    write_json(output_json or plan_json, patched)
    return patched


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Apply filename-hint prompt expansion to an existing LTX plan JSON.")
    parser.add_argument("--plan-json", required=True)
    parser.add_argument("--output", default=None)
    parser.add_argument("--provider", default=DEFAULT_PLAN_EXPANSION_PROVIDER, choices=["template", "openai", "ollama"])
    parser.add_argument("--model", default=DEFAULT_OLLAMA_MODEL)
    args = parser.parse_args()

    patched = expand_plan_file(
        args.plan_json,
        output_json=args.output,
        provider=args.provider,
        model=args.model,
    )
    print("Filename-hint prompt expansion applied.")
    print(f"Scenes: {patched.get('filename_hint_expansion', {}).get('scene_count')}")
    print(f"Provider: {patched.get('filename_hint_expansion', {}).get('provider')}")


if __name__ == "__main__":
    main()
