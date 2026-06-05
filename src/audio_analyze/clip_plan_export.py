from __future__ import annotations

from pathlib import Path
from typing import Any
import json

import librosa
import numpy as np

try:
    from .path_policy import resolve_runtime_path, serialize_path
except ImportError:
    from path_policy import resolve_runtime_path, serialize_path


def clip_plan_filename(clip_index: int) -> str:
    return f"scene_{int(clip_index):02d}_clip_plan.json"


def split_prompt_sections(prompt_text: str) -> dict[str, str]:
    prompt_text = str(prompt_text or "").strip()
    return {
        "visual_prompt": prompt_text,
        "motion_prompt": "See compiled prompt text for scene-specific motion instructions.",
        "camera_prompt": "See compiled prompt text for scene-specific camera instructions.",
        "constraint_prompt": "See compiled prompt text for scene-specific constraints.",
    }


def _as_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return fallback


def _scalar(value: Any) -> float:
    arr = np.asarray(value)
    if arr.size == 0:
        return 0.0
    return float(arr.reshape(-1)[0])


def _select_scene_sync_targets(beat_items: list[dict[str, float]], limit: int = 12) -> list[dict[str, float]]:
    if not beat_items:
        return []
    positive = [item for item in beat_items if item.get("strength", 0.0) > 0.0]
    source = positive or beat_items
    keep = min(limit, len(source))
    ranked = sorted(source, key=lambda item: item.get("strength", 0.0), reverse=True)[:keep]
    return sorted(ranked, key=lambda item: item.get("absolute", 0.0))


def build_scene_sync_targets(plan: dict[str, Any]) -> dict[int, dict[str, Any]]:
    results = plan.get("results", [])
    if not results:
        return {}
    audio_value = results[0].get("source_audio_path")
    if not audio_value:
        return {}
    audio_path = resolve_runtime_path(audio_value)
    if not audio_path.exists():
        return {}

    y, sr = librosa.load(str(audio_path), sr=None, mono=True)
    _, y_percussive = librosa.effects.hpss(y)
    onset_env = librosa.onset.onset_strength(y=y_percussive, sr=sr)
    tempo_raw, beat_frames = librosa.beat.beat_track(y=y_percussive, sr=sr, onset_envelope=onset_env)
    tempo = _scalar(tempo_raw)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)

    beat_grid: list[dict[str, float]] = []
    for frame, beat_time in zip(beat_frames, beat_times):
        frame_index = int(frame)
        strength = float(onset_env[frame_index]) if 0 <= frame_index < len(onset_env) else 0.0
        beat_grid.append({
            "absolute": round(float(beat_time), 3),
            "strength": round(strength, 6),
        })

    by_clip: dict[int, dict[str, Any]] = {}
    for item in results:
        clip_index = int(item.get("clip_index", 0))
        scene = item.get("scene", {}) if isinstance(item.get("scene"), dict) else {}
        start = _as_float(scene.get("start"), 0.0)
        end = _as_float(scene.get("end"), start)
        scene_beats = [beat for beat in beat_grid if start <= beat["absolute"] <= end]
        selected = _select_scene_sync_targets(scene_beats, limit=12)
        absolute_times = [round(beat["absolute"], 3) for beat in selected]
        local_times = [round(max(0.0, beat["absolute"] - start), 3) for beat in selected]
        strengths = [round(beat["strength"], 6) for beat in selected]
        by_clip[clip_index] = {
            "status": "planned" if selected else "no_targets",
            "tempo_bpm": round(tempo, 3) if tempo else None,
            "source": "percussive_beat_grid",
            "absolute_seconds": absolute_times,
            "clip_local_seconds": local_times,
            "strengths": strengths,
            "instruction": "Use the clip-local cue seconds as visible motion hit targets; keep motion between cue points continuous and controlled.",
        }
    return by_clip


def scene_specific_prompt_block(item: dict[str, Any]) -> str:
    clip_index = int(item.get("clip_index", 0))
    scene = item.get("scene", {}) if isinstance(item.get("scene"), dict) else {}
    seed_assignment = item.get("seed_assignment", {}) if isinstance(item.get("seed_assignment"), dict) else {}
    seed_file = seed_assignment.get("seed_file") or Path(str(item.get("seed_image_used", ""))).name
    seed_hint = item.get("seed_filename_prompt_hint") or seed_assignment.get("filename_prompt_hint") or ""
    sync_targets = item.get("sync_targets", {}) if isinstance(item.get("sync_targets"), dict) else {}
    cue_times = sync_targets.get("clip_local_seconds") or []
    cue_text = ", ".join(f"{_as_float(value):.2f}s" for value in cue_times)
    cue_sentence = (
        f"Hard motion cue times inside this clip: {cue_text}. "
        "Hit visible movement accents on these cue times only; keep the in-between motion smooth and controlled. "
        if cue_times
        else "Use the detected percussive beat grid for visible motion accents. "
    )
    return (
        f"SCENE-SPECIFIC CLIP {clip_index:02d}. "
        f"Use seed image file {seed_file} as the visual source of truth for this clip only. "
        f"Seed filename hint: {seed_hint}. "
        f"Scene timing: {scene.get('start')}s to {scene.get('end')}s, duration {scene.get('duration')}s. "
        f"{cue_sentence}"
        "Make this clip visually and rhythmically specific to its seed image, timestamp range, and scene index. "
        "Preserve the seed framing, layout, lighting direction, background continuity, and subject identity. "
        "Avoid off-grid random motion, geometry drift, identity drift, and unplanned scene changes."
    )


def apply_scene_specific_prompt_text(item: dict[str, Any]) -> None:
    base_prompt = str(item.get("prompt_text") or "").strip()
    block = scene_specific_prompt_block(item)
    if "SCENE-SPECIFIC CLIP" in base_prompt:
        prompt_text = base_prompt
    else:
        prompt_text = f"{block} {base_prompt}".strip()
    sync_targets = item.get("sync_targets", {}) if isinstance(item.get("sync_targets"), dict) else {}
    cue_times = sync_targets.get("clip_local_seconds") or []
    cue_text = ", ".join(f"{_as_float(value):.2f}s" for value in cue_times)
    item["base_prompt_text"] = base_prompt
    item["prompt_text"] = prompt_text
    item["ltx_payload_prompt"] = prompt_text
    item["scene_specific_prompt_applied"] = True
    item["scene_specific_prompt_source"] = "clip_plan_export.scene_specific_prompt_block"
    item["prompt_sections"] = {
        "visual_prompt": f"Seed image source: {item.get('seed_image_used')}. Seed filename hint: {item.get('seed_filename_prompt_hint') or ''}.",
        "motion_prompt": f"Scene-specific motion should match this exact timestamp range. Hard motion cue times inside this clip: {cue_text}.",
        "camera_prompt": "Camera behavior should preserve the seed image framing and scene continuity.",
        "constraint_prompt": "Avoid off-grid random motion, geometry drift, identity drift, and unplanned scene changes.",
    }


def build_clip_plan(item: dict[str, Any], analysis: dict[str, Any], clip_plan_json: str | None = None) -> dict[str, Any]:
    scene = item.get("scene", {}) if isinstance(item.get("scene"), dict) else {}
    return {
        "schema": "ltx.scene_clip_plan.v1",
        "clip_index": int(item.get("clip_index", 0)),
        "scene_index": int(scene.get("scene_index", item.get("clip_index", 0))),
        "clip_plan_json": clip_plan_json,
        "file_stem": item.get("file_stem"),
        "source_audio_path": item.get("source_audio_path"),
        "scene_audio_policy": {
            "source": "extract_from_source_audio",
            "start_seconds": scene.get("start"),
            "end_seconds": scene.get("end"),
            "duration_seconds": scene.get("duration"),
        },
        "scene": scene,
        "scene_timing": {
            "start_seconds": scene.get("start"),
            "end_seconds": scene.get("end"),
            "duration_seconds": scene.get("duration"),
            "scene_type": scene.get("scene_type"),
            "sync_start_rule": scene.get("sync_start_rule"),
            "sync_end_rule": scene.get("sync_end_rule"),
        },
        "seed_image_used": item.get("seed_image_used"),
        "seed_filename_prompt_hint": item.get("seed_filename_prompt_hint"),
        "seed_assignment": item.get("seed_assignment", {}),
        "sync_targets": item.get("sync_targets", {}),
        "prompt_sections": item.get("prompt_sections") or split_prompt_sections(item.get("prompt_text", "")),
        "base_prompt_text": item.get("base_prompt_text"),
        "ltx_payload_prompt": item.get("prompt_text"),
        "prompt_text": item.get("prompt_text"),
        "resolution": item.get("resolution"),
        "beat_alignment_enabled": bool(item.get("beat_alignment_enabled")),
        "sync_policy": {
            "beat_alignment_enabled": bool(item.get("beat_alignment_enabled")),
            "plan_sync_policy": analysis.get("sync_policy"),
            "tempo_bpm": analysis.get("tempo_bpm_from_full_track") or analysis.get("tempo_bpm"),
            "detected_beat_count": analysis.get("detected_beat_count"),
            "scene_change_timing": "scene timestamps are synced to the source audio timing when beat alignment is enabled",
            "movement_sync_target": "clip-local hard cue seconds from the percussive beat grid",
        },
        "audio_analysis": {
            "tempo_bpm": analysis.get("tempo_bpm"),
            "tempo_bpm_from_full_track": analysis.get("tempo_bpm_from_full_track"),
            "duration_seconds": analysis.get("duration_seconds"),
            "energy_profile": analysis.get("energy_profile"),
            "edit_pacing": analysis.get("edit_pacing"),
            "movement_notes": analysis.get("movement_notes"),
            "camera_notes": analysis.get("camera_notes"),
            "lighting_notes": analysis.get("lighting_notes"),
            "mix_reactivity_notes": analysis.get("mix_reactivity_notes"),
        },
        "status": item.get("status", "planned"),
    }


def write_clip_plans(output_json: str | Path, plan: dict[str, Any]) -> list[str]:
    output_json_path = resolve_runtime_path(output_json)
    clip_plan_dir = output_json_path.parent / "clip_plans"
    clip_plan_dir.mkdir(parents=True, exist_ok=True)
    analysis = plan.get("analysis", {}) if isinstance(plan.get("analysis"), dict) else {}
    sync_targets_by_clip = build_scene_sync_targets(plan)
    written: list[str] = []
    for item in plan.get("results", []):
        clip_index = int(item.get("clip_index", 0))
        clip_path = clip_plan_dir / clip_plan_filename(clip_index)
        clip_rel = serialize_path(clip_path)
        item["clip_plan_json"] = clip_rel
        item["clip_plan_resolved_path"] = str(clip_path.resolve())
        item["compiled_from_clip_plan"] = True
        item["sync_targets"] = sync_targets_by_clip.get(clip_index, {})
        apply_scene_specific_prompt_text(item)
        clip_plan = build_clip_plan(item, analysis, clip_plan_json=clip_rel)
        clip_path.write_text(json.dumps(clip_plan, indent=2), encoding="utf-8")
        written.append(clip_rel)
    plan["compiled_from_clip_plans"] = True
    plan["clip_plan_dir"] = serialize_path(clip_plan_dir)
    plan["clip_plan_dir_resolved"] = str(clip_plan_dir.resolve())
    plan["clip_plan_json_files"] = written
    return written
