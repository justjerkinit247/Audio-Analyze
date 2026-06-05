from pathlib import Path
import argparse
import hashlib
import json
import time
import traceback

from .ltx_holy_cheeks_pipeline import read_json, submit_one, safe_name
from .path_policy import resolve_runtime_path, serialize_path


DEFAULT_PLAN = "outputs/ltx_video_run/holy_cheeks_ltx_plan.json"
DEFAULT_OUTPUT_DIR = "outputs/ltx_video_run"
DEFAULT_MODEL = "ltx-2-3-pro"
DEFAULT_GUIDANCE_SCALE = 9.0
FINGERPRINT_SCHEMA = "ltx.submit_resilient.clip_fingerprint.v1"
METADATA_SCHEMA = "ltx.submit_resilient.clip_metadata.v1"
FINGERPRINT_FIELDS = [
    "clip_index",
    "file_stem",
    "prompt_text",
    "base_prompt_text",
    "seed_image_used",
    "seed_filename_prompt_hint",
    "seed_assignment",
    "source_audio_path",
    "scene_audio_path",
    "scene",
    "resolution",
    "audio_to_video_confirmed",
    "beat_alignment_enabled",
    "prompt_maximizer",
]


def write_json(path, data):
    path = resolve_runtime_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def expected_mp4_path(output_dir, item):
    downloads = resolve_runtime_path(output_dir) / "downloads"
    file_stem = safe_name(item.get("file_stem", "ltx_output"))
    clip_index = int(item["clip_index"])
    return downloads / f"{file_stem}_ltx_scene_{clip_index:02d}.mp4"


def metadata_path_for_mp4(mp4_path):
    mp4_path = Path(mp4_path)
    return mp4_path.with_name(f"{mp4_path.stem}.metadata.json")


def clip_fingerprint_payload(item, model=DEFAULT_MODEL, guidance_scale=DEFAULT_GUIDANCE_SCALE):
    payload = {
        "schema": FINGERPRINT_SCHEMA,
        "model": model,
        "guidance_scale": float(guidance_scale),
    }
    for field in FINGERPRINT_FIELDS:
        payload[field] = item.get(field)
    return payload


def clip_fingerprint(item, model=DEFAULT_MODEL, guidance_scale=DEFAULT_GUIDANCE_SCALE):
    payload = clip_fingerprint_payload(item, model=model, guidance_scale=guidance_scale)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def read_json_if_exists(path):
    path = Path(path)
    if not path.exists():
        return None, "missing"
    try:
        return read_json(path), None
    except Exception as exc:
        return None, f"unreadable: {exc}"


def stored_fingerprint_from_metadata(metadata):
    if not isinstance(metadata, dict):
        return None
    return metadata.get("clip_fingerprint") or metadata.get("fingerprint")


def validate_existing_clip(output_dir, item, result_path, model=DEFAULT_MODEL, guidance_scale=DEFAULT_GUIDANCE_SCALE):
    mp4_path = expected_mp4_path(output_dir, item)
    metadata_path = metadata_path_for_mp4(mp4_path)
    expected = clip_fingerprint(item, model=model, guidance_scale=guidance_scale)
    base = {
        "expected_fingerprint": expected,
        "mp4_path": serialize_path(mp4_path),
        "mp4_resolved_path": str(mp4_path.resolve()),
        "metadata_json": serialize_path(metadata_path),
        "metadata_resolved_path": str(metadata_path.resolve()),
        "result_json": serialize_path(result_path),
        "result_resolved_path": str(resolve_runtime_path(result_path).resolve()),
    }

    if not mp4_path.exists():
        return {**base, "status": "missing_mp4", "reusable": False, "reason": "expected MP4 does not exist"}
    if mp4_path.stat().st_size <= 0:
        return {**base, "status": "mp4_empty", "reusable": False, "reason": "expected MP4 is empty"}

    metadata, metadata_error = read_json_if_exists(metadata_path)
    result, result_error = read_json_if_exists(result_path)

    metadata_sources = []
    if metadata is not None:
        metadata_sources.append(("metadata_json", metadata, str(metadata_path.resolve())))
    if result is not None:
        metadata_sources.append(("result_json", result, str(Path(result_path).resolve())))

    if not metadata_sources:
        return {
            **base,
            "status": "metadata_missing_or_unreadable",
            "reusable": False,
            "reason": "missing or unreadable clip metadata",
            "metadata_error": metadata_error,
            "result_error": result_error,
        }

    for source_type, data, source_path in metadata_sources:
        stored = stored_fingerprint_from_metadata(data)
        if not stored:
            continue
        if stored == expected:
            return {
                **base,
                "status": "matched",
                "reusable": True,
                "reason": "existing MP4 fingerprint matches current plan",
                "stored_fingerprint": stored,
                "metadata_source": source_type,
                "metadata_source_path": source_path,
            }
        return {
            **base,
            "status": "fingerprint_mismatch",
            "reusable": False,
            "reason": "existing MP4 fingerprint does not match current plan",
            "stored_fingerprint": stored,
            "metadata_source": source_type,
            "metadata_source_path": source_path,
        }

    return {
        **base,
        "status": "fingerprint_missing",
        "reusable": False,
        "reason": "clip metadata does not contain a fingerprint",
    }


def write_clip_metadata(output_dir, item, result_path, result, model=DEFAULT_MODEL, guidance_scale=DEFAULT_GUIDANCE_SCALE):
    mp4_path = expected_mp4_path(output_dir, item)
    metadata_path = metadata_path_for_mp4(mp4_path)
    fingerprint_payload = clip_fingerprint_payload(item, model=model, guidance_scale=guidance_scale)
    fingerprint = clip_fingerprint(item, model=model, guidance_scale=guidance_scale)

    result["fingerprint_schema"] = FINGERPRINT_SCHEMA
    result["clip_fingerprint"] = fingerprint
    result["clip_fingerprint_payload"] = fingerprint_payload
    write_json(result_path, result)

    metadata = {
        "schema": METADATA_SCHEMA,
        "fingerprint_schema": FINGERPRINT_SCHEMA,
        "clip_fingerprint": fingerprint,
        "clip_fingerprint_payload": fingerprint_payload,
        "clip_index": item.get("clip_index"),
        "file_stem": item.get("file_stem"),
        "model": model,
        "guidance_scale": float(guidance_scale),
        "mp4_path": serialize_path(mp4_path),
        "mp4_resolved_path": str(mp4_path.resolve()),
        "result_json": serialize_path(result_path),
        "result_resolved_path": str(resolve_runtime_path(result_path).resolve()),
        "downloaded_mp4": result.get("downloaded_mp4"),
        "status": result.get("status"),
    }
    if mp4_path.exists() and mp4_path.stat().st_size > 0:
        write_json(metadata_path, metadata)
        return str(metadata_path.resolve())
    return None


def submit_resilient(
    plan_json=DEFAULT_PLAN,
    output_dir=DEFAULT_OUTPUT_DIR,
    model=DEFAULT_MODEL,
    guidance_scale=DEFAULT_GUIDANCE_SCALE,
    live=False,
    retries=2,
    retry_sleep_seconds=8.0,
    only_missing=True,
    allow_sorted_seed_fallback=False,
    allow_duplicate_seed_reuse=False,
):
    plan = read_json(plan_json)
    output_dir = resolve_runtime_path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "ltx_submit_resilient_summary.json"

    summary = {
        "status": "running",
        "live": bool(live),
        "dry_run": not bool(live),
        "plan_json": serialize_path(plan_json),
        "plan_json_resolved": str(resolve_runtime_path(plan_json).resolve()),
        "output_dir": serialize_path(output_dir),
        "output_dir_resolved": str(output_dir.resolve()),
        "retries": int(retries),
        "retry_sleep_seconds": float(retry_sleep_seconds),
        "only_missing": bool(only_missing),
        "allow_sorted_seed_fallback": bool(allow_sorted_seed_fallback),
        "allow_duplicate_seed_reuse": bool(allow_duplicate_seed_reuse),
        "results": [],
        "failed_scenes": [],
        "completed_scenes": [],
        "skipped_existing_scenes": [],
        "stale_existing_scenes": [],
        "stale_existing_details": [],
    }
    write_json(summary_path, summary)

    for item in plan.get("results", []):
        idx = int(item["clip_index"])
        mp4_path = expected_mp4_path(output_dir, item)
        result_path = output_dir / f"scene_{idx:02d}_result.json"

        if only_missing and mp4_path.exists():
            validation = validate_existing_clip(output_dir, item, result_path, model=model, guidance_scale=guidance_scale)
            if validation["reusable"]:
                row = {
                    "clip_index": idx,
                    "status": "skipped_existing",
                    "downloaded_mp4": serialize_path(mp4_path),
                    "downloaded_mp4_resolved": str(mp4_path.resolve()),
                    "result_json": serialize_path(result_path),
                    "result_resolved_path": str(result_path.resolve()),
                    "clip_fingerprint": validation["expected_fingerprint"],
                    "fingerprint_validation": validation,
                }
                summary["results"].append(row)
                summary["skipped_existing_scenes"].append(idx)
                write_json(summary_path, summary)
                print(f"Scene {idx:02d}: existing MP4 fingerprint matched, skipping.")
                continue

            stale_detail = {
                "clip_index": idx,
                "mp4_path": serialize_path(mp4_path),
                "mp4_resolved_path": str(mp4_path.resolve()),
                "result_json": serialize_path(result_path),
                "result_resolved_path": str(result_path.resolve()),
                "fingerprint_validation": validation,
                "reason": validation["reason"],
            }
            summary["stale_existing_scenes"].append(idx)
            summary["stale_existing_details"].append(stale_detail)
            write_json(summary_path, summary)
            print(f"Scene {idx:02d}: existing MP4 is stale; {validation['reason']}.")
            if not live:
                row = {
                    "clip_index": idx,
                    "status": "would_resubmit_stale",
                    "downloaded_mp4": None,
                    "result_json": serialize_path(result_path),
                    "result_resolved_path": str(result_path.resolve()),
                    "clip_fingerprint": validation["expected_fingerprint"],
                    "fingerprint_validation": validation,
                    "stale_existing": True,
                    "reason": "dry-run would resubmit stale existing MP4",
                }
                summary["results"].append(row)
                write_json(summary_path, summary)
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
                    allow_sorted_seed_fallback=allow_sorted_seed_fallback,
                    allow_duplicate_seed_reuse=allow_duplicate_seed_reuse,
                )
                metadata_path = write_clip_metadata(
                    output_dir=output_dir,
                    item=item,
                    result_path=result_path,
                    result=result,
                    model=model,
                    guidance_scale=guidance_scale,
                )
                row = {
                    "clip_index": idx,
                    "status": result.get("status"),
                    "scene_audio_path": result.get("scene_audio_path"),
                    "scene_audio_format": result.get("scene_audio_format"),
                    "downloaded_mp4": serialize_path(result["downloaded_mp4"]) if result.get("downloaded_mp4") else None,
                    "downloaded_mp4_resolved_path": (
                        str(resolve_runtime_path(result["downloaded_mp4"]).resolve())
                        if result.get("downloaded_mp4")
                        else None
                    ),
                    "result_json": serialize_path(result_path),
                    "result_resolved_path": str(result_path.resolve()),
                    "metadata_json": metadata_path,
                    "clip_fingerprint": result.get("clip_fingerprint"),
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
                "result_json": serialize_path(result_path),
                "result_resolved_path": str(result_path.resolve()),
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
    parser.add_argument("--allow-sorted-seed-fallback", action="store_true")
    parser.add_argument("--allow-duplicate-seed-reuse", action="store_true")
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
        allow_sorted_seed_fallback=args.allow_sorted_seed_fallback,
        allow_duplicate_seed_reuse=args.allow_duplicate_seed_reuse,
    )


if __name__ == "__main__":
    main()
