from pathlib import Path
import argparse
import json
from datetime import datetime

import librosa
import numpy as np

try:
    from .ltx_holy_cheeks_pipeline import (
        build_plan,
        run_preflight,
        submit_all,
    )
except ImportError:
    from ltx_holy_cheeks_pipeline import (
        build_plan,
        run_preflight,
        submit_all,
    )


DEFAULT_PLAN_JSON = "outputs/ltx_video_run/holy_cheeks_ltx_plan.json"
DEFAULT_PREFLIGHT_JSON = "outputs/ltx_video_run/preflight_report.json"
DEFAULT_SUBMIT_DIR = "outputs/ltx_video_run/submissions"
DEFAULT_ORCHESTRATION_DIR = "outputs/ltx_video_run/orchestration"
DEFAULT_ORCHESTRATOR_REPORT_JSON = "outputs/ltx_video_run/orchestrator_report.json"

CAMERA_PROFILES = [
    "smooth low tracking shot, stable vertical reel framing, readable subject geography",
    "slight side arc with controlled camera drift, readable over-shoulder performance moment",
    "wide vertical choreography frame, low-angle energy, full-body movement readable",
    "controlled camera orbit with mild parallax, no random spin or snap zoom",
    "medium-close performance confidence shot, stable identity, controlled rhythm",
    "smooth settle into final pose, camera stops cleanly on the last beat",
]

CHOREOGRAPHY_PROFILES = [
    "confident beat-synced movement, subtle shoulder and hip groove on the downbeat",
    "over-shoulder glance timed to a vocal, kick, or snare accent",
    "brief polished hip-accent choreography, rhythmic and performance-art focused",
    "group movement continues with synchronized lower-body accents and stable spacing",
    "camera-readable performance energy, controlled hand placement, no anatomy drift",
    "unified final pose or group finish landing visibly on the final beat",
]


def timestamp():
    return datetime.utcnow().isoformat() + "Z"


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def scalar(value):
    arr = np.asarray(value)
    if arr.size == 0:
        return 0.0
    return float(arr.reshape(-1)[0])


def extract_beat_markers(audio_path, plan):
    audio_path = Path(audio_path)
    y, sr = librosa.load(str(audio_path), sr=None, mono=True)
    duration = float(librosa.get_duration(y=y, sr=sr))
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    tempo_raw, beat_frames = librosa.beat.beat_track(y=y, sr=sr, onset_envelope=onset_env)
    tempo = scalar(tempo_raw)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    onset_times = librosa.times_like(onset_env, sr=sr)

    top_onsets = []
    if len(onset_env):
        count = min(64, len(onset_env))
        top_indices = np.argsort(onset_env)[-count:]
        top_onsets = sorted(
            {
                round(float(onset_times[i]), 3)
                for i in top_indices
                if 0 <= float(onset_times[i]) <= duration
            }
        )

    scene_markers = []
    for item in plan.get("results", []):
        idx = int(item.get("clip_index", 0))
        scene = item.get("scene", {})
        start = float(scene.get("start", 0.0))
        end = float(scene.get("end", start))
        beats_in_scene = [round(float(t), 3) for t in beat_times if start <= float(t) <= end]
        onsets_in_scene = [round(float(t), 3) for t in top_onsets if start <= float(t) <= end]
        scene_markers.append({
            "clip_index": idx,
            "start": round(start, 3),
            "end": round(end, 3),
            "duration": round(max(0.0, end - start), 3),
            "beat_times_seconds": beats_in_scene,
            "strong_onset_times_seconds": onsets_in_scene,
            "primary_sync_targets_seconds": onsets_in_scene[:8] if onsets_in_scene else beats_in_scene[:8],
            "sync_density": len(onsets_in_scene) if onsets_in_scene else len(beats_in_scene),
        })

    return {
        "status": "analyzed",
        "audio_path": str(audio_path.resolve()),
        "duration_seconds": round(duration, 3),
        "tempo_bpm": round(tempo, 3) if tempo else None,
        "beat_count": len(beat_times),
        "strong_onset_count": len(top_onsets),
        "beat_times_seconds": [round(float(t), 3) for t in beat_times],
        "strong_onset_times_seconds": top_onsets,
        "scenes": scene_markers,
    }


def build_continuity_memory(plan):
    scenes = plan.get("results", [])
    memory = {
        "status": "planned",
        "purpose": "Keep subject identity, body layout, camera geography, and scene direction stable across generated clips.",
        "global_continuity_rules": [
            "Use the seed image as the source of truth for subject count, identity, pose, and framing.",
            "Preserve vertical reel framing and readable subject geography.",
            "Keep movement polished, rhythmic, and beat-aware rather than chaotic.",
            "Avoid sudden body layout changes, face changes, extra limbs, and random scene teleportation.",
        ],
        "scenes": [],
    }
    for item in scenes:
        idx = int(item.get("clip_index", 0))
        previous_idx = idx - 1 if idx > 1 else None
        next_idx = idx + 1 if idx < len(scenes) else None
        memory["scenes"].append({
            "clip_index": idx,
            "seed_image_used": item.get("seed_image_used"),
            "scene_time": item.get("scene", {}),
            "previous_scene": previous_idx,
            "next_scene": next_idx,
            "continuity_goal": "Maintain subject identity, pose category, rhythm, and camera geography from adjacent scenes.",
        })
    return memory


def build_beat_camera_choreography_manifest(plan, beat_markers=None):
    analysis = plan.get("analysis", {})
    tempo = analysis.get("tempo_bpm") or analysis.get("tempo_bpm_from_full_track") or (beat_markers or {}).get("tempo_bpm")
    marker_by_clip = {
        int(item.get("clip_index")): item
        for item in (beat_markers or {}).get("scenes", [])
        if item.get("clip_index") is not None
    }
    scenes = []
    for item in plan.get("results", []):
        idx = int(item.get("clip_index", 1))
        scene = item.get("scene", {})
        camera = CAMERA_PROFILES[(idx - 1) % len(CAMERA_PROFILES)]
        choreography = CHOREOGRAPHY_PROFILES[(idx - 1) % len(CHOREOGRAPHY_PROFILES)]
        markers = marker_by_clip.get(idx, {})
        scenes.append({
            "clip_index": idx,
            "start": scene.get("start"),
            "end": scene.get("end"),
            "duration": scene.get("duration"),
            "tempo_bpm": tempo,
            "beat_alignment_enabled": bool(plan.get("beat_alignment_enabled")),
            "beat_sync_rule": "Prioritize visible motion accents on kick, snare, bass drops, vocal accents, and phrase transitions.",
            "primary_sync_targets_seconds": markers.get("primary_sync_targets_seconds", []),
            "sync_density": markers.get("sync_density"),
            "camera_profile": camera,
            "choreography_profile": choreography,
            "negative_motion_rules": [
                "no off-beat random shaking",
                "no chaotic camera spin",
                "no warped anatomy",
                "no random background or body layout mutation",
            ],
        })
    return {
        "status": "planned",
        "tempo_bpm": tempo,
        "start_offset_seconds": plan.get("start_offset_seconds"),
        "beat_alignment_enabled": bool(plan.get("beat_alignment_enabled")),
        "edit_pacing": analysis.get("edit_pacing"),
        "movement_notes": analysis.get("movement_notes"),
        "camera_notes": analysis.get("camera_notes"),
        "scenes": scenes,
    }


def build_sync_score_manifest(plan, beat_markers):
    scores = []
    for scene in beat_markers.get("scenes", []):
        density = int(scene.get("sync_density") or 0)
        duration = float(scene.get("duration") or 1.0)
        density_per_second = density / max(duration, 0.001)
        if density_per_second >= 2.0:
            difficulty = "high"
            recommendation = "Use fewer, stronger visible accents; avoid constant motion chaos."
        elif density_per_second >= 1.0:
            difficulty = "medium"
            recommendation = "Use clear downbeat and snare accents with controlled camera emphasis."
        else:
            difficulty = "low"
            recommendation = "Use broader groove movement and hold stable camera continuity."
        scores.append({
            "clip_index": scene.get("clip_index"),
            "duration": duration,
            "sync_density": density,
            "sync_density_per_second": round(density_per_second, 3),
            "sync_difficulty": difficulty,
            "recommendation": recommendation,
        })
    return {
        "status": "planned",
        "purpose": "Estimate which scenes need tighter motion timing or simpler choreography before generation.",
        "scores": scores,
    }


def build_retry_queue(preflight, submit_summary):
    queue = []
    if preflight.get("status") != "PASSED":
        for problem in preflight.get("problems", []):
            queue.append({
                "stage": "preflight",
                "reason": problem,
                "recommended_action": "Fix plan, seed path, audio path, duration, prompt length, or resolution before live submission.",
            })
    for item in (submit_summary or {}).get("results", []):
        status = str(item.get("status", "")).lower()
        if status not in {"complete", "dry_run", "submitted", "succeeded", "success"}:
            queue.append({
                "stage": "submit",
                "clip_index": item.get("clip_index"),
                "status": item.get("status"),
                "result_json": item.get("result_json"),
                "recommended_action": "Regenerate this scene only after reviewing result JSON and prompt/seed pairing.",
            })
    return {
        "status": "empty" if not queue else "needs_attention",
        "retry_count": len(queue),
        "queue": queue,
    }


def build_stitching_manifest(plan, submit_summary):
    clips = []
    by_clip = {
        int(item.get("clip_index")): item
        for item in (submit_summary or {}).get("results", [])
        if item.get("clip_index") is not None
    }
    for item in plan.get("results", []):
        idx = int(item.get("clip_index", 0))
        submit_item = by_clip.get(idx, {})
        clips.append({
            "clip_index": idx,
            "scene": item.get("scene", {}),
            "expected_mp4": submit_item.get("downloaded_mp4"),
            "scene_audio_path": submit_item.get("scene_audio_path"),
            "result_json": submit_item.get("result_json"),
            "stitch_order": idx,
            "transition": "hard_cut",
            "sync_rule": "Clip duration should match planned scene duration; cuts are aligned to planned scene beat boundaries when beat_align is enabled.",
        })
    return {
        "status": "planned",
        "assembly_strategy": "scene_order_hard_cuts_first_then_optional_transition_cleanup",
        "beat_alignment_enabled": bool(plan.get("beat_alignment_enabled")),
        "clips": clips,
    }


def write_orchestration_manifests(plan, preflight, submit_summary, output_dir, audio_path):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    beat_markers = extract_beat_markers(audio_path, plan)
    continuity = build_continuity_memory(plan)
    beat_manifest = build_beat_camera_choreography_manifest(plan, beat_markers=beat_markers)
    sync_scores = build_sync_score_manifest(plan, beat_markers)
    retry_queue = build_retry_queue(preflight, submit_summary)
    stitching = build_stitching_manifest(plan, submit_summary)

    paths = {
        "beat_markers": output_dir / "beat_markers.json",
        "continuity_memory": output_dir / "continuity_memory.json",
        "beat_camera_choreography": output_dir / "beat_camera_choreography_manifest.json",
        "sync_scores": output_dir / "sync_score_manifest.json",
        "retry_queue": output_dir / "retry_queue.json",
        "stitching_manifest": output_dir / "stitching_manifest.json",
    }

    write_json(paths["beat_markers"], beat_markers)
    write_json(paths["continuity_memory"], continuity)
    write_json(paths["beat_camera_choreography"], beat_manifest)
    write_json(paths["sync_scores"], sync_scores)
    write_json(paths["retry_queue"], retry_queue)
    write_json(paths["stitching_manifest"], stitching)

    return {name: str(path.resolve()) for name, path in paths.items()}


def orchestrate(
    audio,
    seed_dir,
    output_plan,
    resolution,
    max_scenes,
    scene_seconds,
    model,
    guidance_scale,
    live,
    report_json=None,
    start_offset_seconds=0.0,
    beat_align=False,
    allow_sorted_seed_fallback=False,
    allow_duplicate_seed_reuse=False,
):
    print("=" * 60)
    print("LTX ORCHESTRATOR START")
    print("=" * 60)

    print("[1/4] Building plan...")
    plan = build_plan(
        audio_path=audio,
        seed_dir=seed_dir,
        output_json=output_plan,
        resolution=resolution,
        max_scenes=max_scenes,
        scene_seconds=scene_seconds,
        start_offset_seconds=start_offset_seconds,
        beat_align=beat_align,
        allow_sorted_seed_fallback=allow_sorted_seed_fallback,
        allow_duplicate_seed_reuse=allow_duplicate_seed_reuse,
    )

    print(f"Plan created: {Path(output_plan).resolve()}")
    print(f"Scene count: {plan.get('scene_count')}")
    print(f"Seed image count: {plan.get('seed_image_count')}")
    print(f"Start offset seconds: {plan.get('start_offset_seconds')}")
    print(f"Beat alignment enabled: {plan.get('beat_alignment_enabled')}")
    print(f"Audio + seed image sent to LTX: {plan.get('audio_plus_seed_image_sent_to_ltx')}")

    print("[2/4] Running preflight...")
    preflight = run_preflight(
        output_plan,
        DEFAULT_PREFLIGHT_JSON,
        allow_sorted_seed_fallback=allow_sorted_seed_fallback,
        allow_duplicate_seed_reuse=allow_duplicate_seed_reuse,
    )
    print(f"Preflight status: {preflight['status']}")

    submit_summary = None
    if preflight["status"] != "PASSED":
        print("Preflight failed. Refusing submit-all.")
        for problem in preflight.get("problems", []):
            print(f"PROBLEM: {problem}")
    else:
        print("[3/4] Running submit-all...")
        submit_summary = submit_all(
            plan_json=output_plan,
            output_dir=DEFAULT_SUBMIT_DIR,
            model=model,
            guidance_scale=guidance_scale,
            dry_run=not live,
            live=live,
            allow_sorted_seed_fallback=allow_sorted_seed_fallback,
            allow_duplicate_seed_reuse=allow_duplicate_seed_reuse,
        )

    print("[4/4] Writing orchestration manifests...")
    manifest_paths = write_orchestration_manifests(
        plan=plan,
        preflight=preflight,
        submit_summary=submit_summary,
        output_dir=DEFAULT_ORCHESTRATION_DIR,
        audio_path=audio,
    )

    final_status = "complete" if preflight["status"] == "PASSED" else "failed_preflight"
    result = {
        "status": final_status,
        "timestamp": timestamp(),
        "live": live,
        "start_offset_seconds": plan.get("start_offset_seconds"),
        "beat_alignment_enabled": plan.get("beat_alignment_enabled"),
        "audio_to_video_enabled": plan.get("audio_to_video_enabled"),
        "audio_plus_seed_image_sent_to_ltx": plan.get("audio_plus_seed_image_sent_to_ltx"),
        "plan_json": str(Path(output_plan).resolve()),
        "preflight_json": str(Path(DEFAULT_PREFLIGHT_JSON).resolve()),
        "submit_dir": str(Path(DEFAULT_SUBMIT_DIR).resolve()),
        "manifest_paths": manifest_paths,
        "summary": submit_summary,
    }

    final_report = Path(report_json or DEFAULT_ORCHESTRATOR_REPORT_JSON)
    final_report.parent.mkdir(parents=True, exist_ok=True)
    final_report.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print("=" * 60)
    print("LTX ORCHESTRATOR COMPLETE")
    print("=" * 60)
    print(f"Dry run: {not live}")
    print(f"Status: {final_status}")
    print(f"Final report: {final_report.resolve()}")
    for label, path in manifest_paths.items():
        print(f"{label}: {path}")
    return result


def main():
    parser = argparse.ArgumentParser(description="LTX orchestration wrapper")
    parser.add_argument("--audio", required=True)
    parser.add_argument("--seed-dir", default="inputs/ltx_seed_images")
    parser.add_argument("--output-plan", default=DEFAULT_PLAN_JSON)
    parser.add_argument("--resolution", default="9:16")
    parser.add_argument("--max-scenes", type=int, default=None)
    parser.add_argument("--scene-seconds", type=float, default=8.0)
    parser.add_argument("--start-offset-seconds", type=float, default=0.0)
    parser.add_argument("--beat-align", action="store_true")
    parser.add_argument("--model", default="ltx-2-3-pro")
    parser.add_argument("--guidance-scale", type=float, default=9.0)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--allow-sorted-seed-fallback", action="store_true")
    parser.add_argument("--allow-duplicate-seed-reuse", action="store_true")
    parser.add_argument("--report-json", default=DEFAULT_ORCHESTRATOR_REPORT_JSON)
    args = parser.parse_args()

    orchestrate(
        audio=args.audio,
        seed_dir=args.seed_dir,
        output_plan=args.output_plan,
        resolution=args.resolution,
        max_scenes=args.max_scenes,
        scene_seconds=args.scene_seconds,
        model=args.model,
        guidance_scale=args.guidance_scale,
        live=args.live,
        report_json=args.report_json,
        start_offset_seconds=args.start_offset_seconds,
        beat_align=args.beat_align,
        allow_sorted_seed_fallback=args.allow_sorted_seed_fallback,
        allow_duplicate_seed_reuse=args.allow_duplicate_seed_reuse,
    )


if __name__ == "__main__":
    main()
