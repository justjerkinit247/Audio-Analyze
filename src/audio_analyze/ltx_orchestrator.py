from pathlib import Path
import argparse
import json
from datetime import datetime

try:
    from .music_video_pipeline import main as pipeline_main
    from .ltx_holy_cheeks_pipeline import (
        build_plan,
        run_preflight,
        submit_all,
    )
except ImportError:
    from music_video_pipeline import main as pipeline_main
    from ltx_holy_cheeks_pipeline import (
        build_plan,
        run_preflight,
        submit_all,
    )


DEFAULT_PLAN_JSON = "outputs/ltx_video_run/holy_cheeks_ltx_plan.json"
DEFAULT_PREFLIGHT_JSON = "outputs/ltx_video_run/preflight_report.json"
DEFAULT_SUBMIT_DIR = "outputs/ltx_video_run/submissions"


def timestamp():
    return datetime.utcnow().isoformat() + "Z"


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

    print("[1/3] Building plan...")
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

    print("[2/3] Running preflight...")
    preflight = run_preflight(output_plan, DEFAULT_PREFLIGHT_JSON)

    print(f"Preflight status: {preflight['status']}")

    if preflight["status"] != "PASSED":
        print("Preflight failed. Refusing submit-all.")
        for problem in preflight.get("problems", []):
            print(f"PROBLEM: {problem}")
        return {
            "status": "failed_preflight",
            "timestamp": timestamp(),
            "plan_json": str(Path(output_plan).resolve()),
            "preflight": preflight,
        }

    print("[3/3] Running submit-all...")

    summary = submit_all(
        plan_json=output_plan,
        output_dir=DEFAULT_SUBMIT_DIR,
        model=model,
        guidance_scale=guidance_scale,
        dry_run=not live,
        live=live,
    )

    result = {
        "status": "complete",
        "timestamp": timestamp(),
        "live": live,
        "plan_json": str(Path(output_plan).resolve()),
        "preflight_json": str(Path(DEFAULT_PREFLIGHT_JSON).resolve()),
        "submit_dir": str(Path(DEFAULT_SUBMIT_DIR).resolve()),
        "summary": summary,
    }

    final_report = Path("outputs/ltx_video_run/orchestrator_report.json")
    final_report.parent.mkdir(parents=True, exist_ok=True)
    final_report.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print("=" * 60)
    print("LTX ORCHESTRATOR COMPLETE")
    print("=" * 60)
    print(f"Dry run: {not live}")
    print(f"Scenes processed: {len(summary.get('results', []))}")
    print(f"Final report: {final_report.resolve()}")

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
