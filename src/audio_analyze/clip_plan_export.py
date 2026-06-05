from __future__ import annotations

from pathlib import Path
from typing import Any
import json

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


def scene_specific_prompt_block(item: dict[str, Any]) -> str:
    clip_index = int(item.get("clip_index", 0))
    scene = item.get("scene", {}) if isinstance(item.get("scene"), dict) else {}
    seed_assignment = item.get("seed_assignment", {}) if isinstance(item.get("seed_assignment"), dict) else {}
    seed_file = seed_assignment.get("seed_file") or Path(str(item.get("seed_image_used", ""))).name
    seed_hint = item.get("seed_filename_prompt_hint") or seed_assignment.get("filename_prompt_hint") or ""
    return (
        f"SCENE-SPECIFIC CLIP {clip_index:02d}. "
        f"Use seed image file {seed_file} as the visual source of truth for this clip only. "
        f"Seed filename hint: {seed_hint}. "
        f"Scene timing: {scene.get('start')}s to {scene.get('end')}s, duration {scene.get('duration')}s. "
        "Make this clip visually and rhythmically specific to its seed image, timestamp range, and scene index. "
        "Preserve the seed framing, layout, lighting direction, background continuity, and subject identity. "
        "Sync visible motion to percussive beat-grid targets from the source audio. "
        "Avoid off-grid random motion, geometry drift, identity drift, and unplanned scene changes."
    )


def apply_scene_specific_prompt_text(item: dict[str, Any]) -> None:
    base_prompt = str(item.get("prompt_text") or "").strip()
    block = scene_specific_prompt_block(item)
    if "SCENE-SPECIFIC CLIP" in base_prompt:
        prompt_text = base_prompt
    else:
        prompt_text = f"{block} {base_prompt}".strip()
    item["base_prompt_text"] = base_prompt
    item["prompt_text"] = prompt_text
    item["ltx_payload_prompt"] = prompt_text
    item["scene_specific_prompt_applied"] = True
    item["scene_specific_prompt_source"] = "clip_plan_export.scene_specific_prompt_block"
    item["prompt_sections"] = {
        "visual_prompt": f"Seed image source: {item.get('seed_image_used')}. Seed filename hint: {item.get('seed_filename_prompt_hint') or ''}.",
        "motion_prompt": "Scene-specific motion should match this exact timestamp range and the source audio beat grid.",
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
            "movement_sync_target": "percussive beat-grid targets from the audio analysis layer",
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
    written: list[str] = []
    for item in plan.get("results", []):
        clip_index = int(item.get("clip_index", 0))
        clip_path = clip_plan_dir / clip_plan_filename(clip_index)
        clip_rel = serialize_path(clip_path)
        item["clip_plan_json"] = clip_rel
        item["clip_plan_resolved_path"] = str(clip_path.resolve())
        item["compiled_from_clip_plan"] = True
        apply_scene_specific_prompt_text(item)
        clip_plan = build_clip_plan(item, analysis, clip_plan_json=clip_rel)
        clip_path.write_text(json.dumps(clip_plan, indent=2), encoding="utf-8")
        written.append(clip_rel)
    plan["compiled_from_clip_plans"] = True
    plan["clip_plan_dir"] = serialize_path(clip_plan_dir)
    plan["clip_plan_dir_resolved"] = str(clip_plan_dir.resolve())
    plan["clip_plan_json_files"] = written
    return written
