from __future__ import annotations

from pathlib import Path
import argparse
import json

try:
    from .ltx_run_state import rotate_for_new_live_session, ingest_result_folder, update_active_manifest
    from .ltx_holy_cheeks_pipeline import submit_all, submit_one
except ImportError:
    from ltx_run_state import rotate_for_new_live_session, ingest_result_folder, update_active_manifest
    from ltx_holy_cheeks_pipeline import submit_all, submit_one


def main():
    parser = argparse.ArgumentParser(description="State-aware LTX live-session wrapper.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_all = sub.add_parser("submit-all")
    p_all.add_argument("--plan-json", required=True)
    p_all.add_argument("--output-dir", default="outputs/ltx_video_run")
    p_all.add_argument("--state-root", default="outputs/ltx_video_run/_state")
    p_all.add_argument("--model", default="ltx-2-3-pro")
    p_all.add_argument("--guidance-scale", type=float, default=9.0)
    p_all.add_argument("--live", action="store_true")
    p_all.add_argument("--allow-sorted-seed-fallback", action="store_true")
    p_all.add_argument("--allow-duplicate-seed-reuse", action="store_true")

    p_one = sub.add_parser("submit-one")
    p_one.add_argument("--plan-json", required=True)
    p_one.add_argument("--output", required=True)
    p_one.add_argument("--clip-index", type=int, default=1)
    p_one.add_argument("--state-root", default="outputs/ltx_video_run/_state")
    p_one.add_argument("--model", default="ltx-2-3-pro")
    p_one.add_argument("--guidance-scale", type=float, default=9.0)
    p_one.add_argument("--live", action="store_true")
    p_one.add_argument("--allow-sorted-seed-fallback", action="store_true")
    p_one.add_argument("--allow-duplicate-seed-reuse", action="store_true")

    args = parser.parse_args()

    if args.command == "submit-all":
        manifest = rotate_for_new_live_session(Path(args.state_root)) if args.live else {"dry_run": True}
        summary = submit_all(
            args.plan_json,
            args.output_dir,
            model=args.model,
            guidance_scale=args.guidance_scale,
            dry_run=not args.live,
            live=args.live,
            allow_sorted_seed_fallback=args.allow_sorted_seed_fallback,
            allow_duplicate_seed_reuse=args.allow_duplicate_seed_reuse,
        )
        copied = ingest_result_folder(Path(args.state_root), Path(args.output_dir))
        update_active_manifest(
            Path(args.state_root),
            status="RETURNS_READY" if args.live else "DRY_RUN_RETURNS_READY",
            plan_json=str(Path(args.plan_json).resolve()),
            output_dir=str(Path(args.output_dir).resolve()),
            summary_status=summary.get("status"),
        )
        print(json.dumps({"manifest": manifest, "summary": summary, "ingested": copied}, indent=2))

    elif args.command == "submit-one":
        manifest = rotate_for_new_live_session(Path(args.state_root)) if args.live else {"dry_run": True}
        result = submit_one(
            args.plan_json,
            args.output,
            args.clip_index,
            model=args.model,
            guidance_scale=args.guidance_scale,
            dry_run=not args.live,
            live=args.live,
            allow_sorted_seed_fallback=args.allow_sorted_seed_fallback,
            allow_duplicate_seed_reuse=args.allow_duplicate_seed_reuse,
        )
        copied = ingest_result_folder(Path(args.state_root), Path(args.output).parent)
        update_active_manifest(
            Path(args.state_root),
            status="RETURNS_READY" if args.live else "DRY_RUN_RETURNS_READY",
            plan_json=str(Path(args.plan_json).resolve()),
            result_json=str(Path(args.output).resolve()),
        )
        print(json.dumps({"manifest": manifest, "result": result, "ingested": copied}, indent=2))


if __name__ == "__main__":
    main()
