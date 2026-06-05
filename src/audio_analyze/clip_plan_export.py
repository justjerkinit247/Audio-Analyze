from __future__ import annotations

from pathlib import Path
from typing import Any

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
        "choreography_motion_prompt": "See compiled prompt text for scene-specific movement instructions.",
        "camera_prompt": "See compiled prompt text for scene-specific camera instructions.",
        "negative_prompt": "See compiled prompt text for scene-specific negative constraints.",
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
        clip_plan = build_clip_plan(item, analysis, clip_plan_json=clip_rel)
        clip_path.write_text(__import__("json").dumps(clip_plan, indent=2), encoding="utf-8")
        written.append(clip_rel)
    plan["compiled_from_clip_plans"] = True
    plan["clip_plan_dir"] = serialize_path(clip_plan_dir)
    plan["clip_plan_dir_resolved"] = str(clip_plan_dir.resolve())
    plan["clip_plan_json_files"] = written
    return written
