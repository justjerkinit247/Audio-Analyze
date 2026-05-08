from pathlib import Path
import argparse
import json
from datetime import datetime

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

CAMERA_PROFILES = [
    "smooth backward tracking shot, vertical reel framing, stable group geography",
    "slight side arc while tracking backward, readable over-shoulder performance moment",
    "wide vertical choreography frame, low-angle energy, full-body movement readable",
    "controlled camera orbit with mild parallax, no random spin or snap zoom",
    "medium-close performer confidence shot, stable faces, controlled upper-body rhythm",
    "smooth settle into final pose, camera stops cleanly on the last beat",
]

CHOREOGRAPHY_PROFILES = [
    "confident synchronized walk, subtle shoulder groove on the downbeat",
    "over-shoulder glance timed to a vocal or snare accent",
    "brief polished hip-accent choreography, rhythmic and performance-art focused",
    "group walk continues with synchronized footwork and robe movement",
    "face-forward charisma, shoulder accents, clean hand placement",
    "unified final pose or group finish landing visibly on the final beat",
]


def timestamp():
    return datetime.utcnow().isoformat() + "Z"


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def build_continuity_memory(plan):
    scenes = plan.get("results", [])
    memory = {
        "status": "planned",
        "purpose": "Keep visual identity, wardrobe, camera geography, and scene direction stable across generated clips.",
        "global_continuity_rules": [
            "Use the same performer identities across all scenes.",
            "Preserve white robe-inspired wardrobe unless explicitly changed.",
            "Preserve vertical reel framing and forward walking geography.",
            "Keep movement polished, rhythmic, and beat-aware rather than chaotic.",
            "Avoid sudden costume changes, face changes, extra limbs, and random scene teleportation.",
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
            "continuity_goal": "Maintain performer identity, wardrobe, rhythm, and camera geography from adjacent scenes.",
        })
    return memory


def build_beat_camera_choreography_manifest(plan):
    analysis = plan.get("analysis", {})
    tempo = analysis.get("tempo_bpm")
    scenes = []
    for item in plan.get("results", []):
        idx = int(item.get("clip_index", 1))
        scene = item.get("scene", {})
        camera = CAMERA_PROFILES[(idx - 1) % len(CAMERA_PROFILES)]
        choreography = CHOREOGRAPHY_PROFILES[(idx - 1) % len(CHOREOGRAPHY_PROFILES)]
        scenes.append({
            "clip_index": idx,
            "start": scene.get("start"),
            "end": scene.get("end"),
            "duration": scene.get("duration"),
            "tempo_bpm": tempo,
            "beat_sync_rule": "Prioritize visible motion accents on kick, snare, bass drops, vocal accents, and phrase transitions.",
            "camera_profile": camera,
            "choreography_profile": choreography,
            "negative_motion_rules": [
                "no off-beat random shaking",
                "no chaotic camera spin",
                "no warped anatomy",
                "no random background or wardrobe mutation",
            ],
        })
    return {
        "status": "planned",
        "tempo_bpm": tempo,
        "edit_pacing": analysis.get("edit_pacing"),
        "movement_notes": analysis.get("movement_notes"),
        "camera_notes": analysis.get("camera_notes"),
        "scenes": scenes,
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
            "sync_rule": "Clip duration should match planned scene duration; align cuts to scene start/end times.",
        })
    return {
        "status": "planned",
        "assembly_strategy": "scene_order_hard_cuts_first_then_optional_transition_cleanup",
        "clips": clips,
    }


def write_orchestration_manifests(plan, preflight, submit_summary, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    continuity = build_continuity_memory(plan)
    beat_manifest = build_beat_camera_choreography_manifest(plan)
    retry_queue = build_retry_queue(preflight, submit_summary)
    stitching = build_stitching_manifest(plan, submit_summary)

    paths = {
        "continuity_memory": output_dir / "continuity_memory.json",
        "beat_camera_choreography": output_dir / "beat_camera_choreography_manifest.json",
        "retry_queue": output_dir / "retry_queue.json",
        "stitching_manifest": output_dir / "stitching_manifest.json",
    }

    write_json(paths["continuity_memory"], continuity)
    write_json(paths["beat_camera_choreography"], beat_manifest)
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
    )

    print(f"Plan created: {Path(output_plan).resolve()}")
    print(f"Scene count: {plan.get('scene_count')}")
    print(f"Seed image count: {plan.get('seed_image_count')}")

    print("[2/4] Running preflight...")
    preflight = run_preflight(output_plan, DEFAULT_PREFLIGHT_JSON)

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
        )

    print("[4/4] Writing orchestration manifests...")
    manifest_paths = write_orchestration_manifests(
        plan=plan,
        preflight=preflight,
        submit_summary=submit_summary,
        output_dir=DEFAULT_ORCHESTRATION_DIR,
    )

    final_status = "complete" if preflight["status"] == "PASSED" else "failed_preflight"
    result = {
        "status": final_status,
        "timestamp": timestamp(),
        "live": live,
        "plan_json": str(Path(output_plan).resolve()),
        "preflight_json": str(Path(DEFAULT_PREFLIGHT_JSON).resolve()),
        "submit_dir": str(Path(DEFAULT_SUBMIT_DIR).resolve()),
        "manifest_paths": manifest_paths,
        "summary": submit_summary,
    }

    final_report = Path("outputs/ltx_video_run/orchestrator_report.json")
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
    parser.add_argument("--model", default="ltx-2-3-pro")
    parser.add_argument("--guidance-scale", type=float, default=9.0)
    parser.add_argument("--live", action="store_true")

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
    )


if __name__ == "__main__":
    main()
