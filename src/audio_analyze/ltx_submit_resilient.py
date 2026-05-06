from pathlib import Path
import argparse
import json
import time
import traceback

from .ltx_holy_cheeks_pipeline import read_json, submit_one, safe_name


DEFAULT_PLAN = "outputs\\ltx_video_run\\holy_cheeks_ltx_plan.json"
DEFAULT_OUTPUT_DIR = "outputs\\ltx_video_run"
DEFAULT_MODEL = "ltx-2-3-pro"
DEFAULT_GUIDANCE_SCALE = 9.0


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def expected_mp4_path(output_dir, item):
    downloads = Path(output_dir) / "downloads"
    file_stem = safe_name(item.get("file_stem", "ltx_output"))
    clip_index = int(item["clip_index"])
    return downloads / f"{file_stem}_ltx_scene_{clip_index:02d}.mp4"


def submit_resilient(plan_json=DEFAULT_PLAN, output_dir=DEFAULT_OUTPUT_DIR, model=DEFAULT_MODEL, guidance_scale=DEFAULT_GUIDANCE_SCALE, live=False, retries=2, retry_sleep_seconds=8.0, only_missing=True):
    plan = read_json(plan_json)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "ltx_submit_resilient_summary.json"

    summary = {
        "status": "running",
        "live": bool(live),
        "dry_run": not bool(live),
        "plan_json": str(Path(plan_json).resolve()),
        "output_dir": str(output_dir.resolve()),
        "retries": int(retries),
        "retry_sleep_seconds": float(retry_sleep_seconds),
        "only_missing": bool(only_missing),
        "results": [],
        "failed_scenes": [],
        "completed_scenes": [],
        "skipped_existing_scenes": [],
    }
    write_json(summary_path, summary)

    for item in plan.get("results", []):
        idx = int(item["clip_index"])
        mp4_path = expected_mp4_path(output_dir, item)
        result_path = output_dir / f"scene_{idx:02d}_result.json"

        if only_missing and mp4_path.exists():
            row = {
                "clip_index": idx,
                "status": "skipped_existing",
                "downloaded_mp4": str(mp4_path.resolve()),
                "result_json": str(result_path.resolve()),
            }
            summary["results"].append(row)
            summary["skipped_existing_scenes"].append(idx)
            write_json(summary_path, summary)
            print(f"Scene {idx:02d}: existing MP4 found, skipping.")
            continue

        last_error = None
        for attempt in range(1, int(retries) + 2):
            print(f"Scene {idx:02d}: submitting attempt {attempt}...")
            try:
                result = submit_one(
                    plan_json=plan_json,
                    output_json=result_path,
                    clip_index=idx,
                    model=model,
                    guidance_scale=guidance_scale,
                    dry_run=not live,
                    live=live,
                )
                row = {
                    "clip_index": idx,
                    "status": result.get("status"),
                    "scene_audio_path": result.get("scene_audio_path"),
                    "scene_audio_format": result.get("scene_audio_format"),
                    "downloaded_mp4": result.get("downloaded_mp4"),
                    "result_json": str(result_path.resolve()),
                    "attempts": attempt,
                }
                summary["results"].append(row)
                summary["completed_scenes"].append(idx)
                write_json(summary_path, summary)
                print(f"Scene {idx:02d}: complete -> {result.get('downloaded_mp4')}")
                last_error = None
                break
            except Exception as exc:
                last_error = {
                    "clip_index": idx,
                    "attempt": attempt,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }
                print(f"Scene {idx:02d}: failed attempt {attempt}: {exc}")
                if attempt <= int(retries):
                    time.sleep(float(retry_sleep_seconds))

        if last_error:
            summary["results"].append({
                "clip_index": idx,
                "status": "failed",
                "result_json": str(result_path.resolve()),
                "error": last_error["error"],
            })
            summary["failed_scenes"].append(idx)
            write_json(summary_path, summary)
            print(f"Scene {idx:02d}: FAILED after retries; continuing.")

    summary["status"] = "complete_with_failures" if summary["failed_scenes"] else "complete"
    write_json(summary_path, summary)
    print("LTX resilient submit complete.")
    print(f"Status: {summary['status']}")
    print(f"Completed scenes: {summary['completed_scenes']}")
    print(f"Skipped existing scenes: {summary['skipped_existing_scenes']}")
    print(f"Failed scenes: {summary['failed_scenes']}")
    print(f"Summary: {summary_path.resolve()}")
    return summary


def main():
    parser = argparse.ArgumentParser(description="Resilient LTX submit runner. Retries failed scenes and continues instead of aborting the whole batch.")
    parser.add_argument("--plan-json", default=DEFAULT_PLAN)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--guidance-scale", type=float, default=DEFAULT_GUIDANCE_SCALE)
    parser.add_argument("--live", action="store_true", help="Actually call LTX and spend credits. Omit for dry-run.")
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--retry-sleep-seconds", type=float, default=8.0)
    parser.add_argument("--all", action="store_true", help="Submit all scenes even when an MP4 already exists. Default submits only missing scenes.")
    args = parser.parse_args()

    submit_resilient(
        plan_json=args.plan_json,
        output_dir=args.output_dir,
        model=args.model,
        guidance_scale=args.guidance_scale,
        live=args.live,
        retries=args.retries,
        retry_sleep_seconds=args.retry_sleep_seconds,
        only_missing=not args.all,
    )


if __name__ == "__main__":
    main()
