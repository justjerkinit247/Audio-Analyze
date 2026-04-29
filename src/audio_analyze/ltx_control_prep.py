from pathlib import Path
import argparse
import json

from .ltx_seed_mapper import apply_seed_mapping, read_json, write_json, make_preview_report
from .ltx_holy_cheeks_pipeline import run_preflight
from .ltx_prompt_maximizer import maximize_plan_prompts, DEFAULT_PROMPT_MAX_CHARS, DEFAULT_PROMPT_TARGET_CHARS


DEFAULT_PLAN = "outputs\\ltx_video_run\\holy_cheeks_ltx_plan.json"
DEFAULT_SEED_DIR = "inputs\\ltx_seed_images"
DEFAULT_PREVIEW = "outputs\\ltx_video_run\\scene_control_preview.md"
DEFAULT_PREFLIGHT = "outputs\\ltx_video_run\\preflight_report.json"
DEFAULT_STATUS = "outputs\\ltx_video_run\\scene_control_status.json"


def build_scene_control_status(plan_json, preflight_report, output_json):
    plan = read_json(plan_json)
    preflight = read_json(preflight_report) if Path(preflight_report).exists() else {}
    mapping = plan.get("seed_mapping", {})
    maximizer = plan.get("prompt_maximizer", {})
    results = plan.get("results", [])

    problems = list(mapping.get("problems", [])) + list(maximizer.get("problems", [])) + list(preflight.get("problems", []))

    status = {
        "status": "PASSED" if not problems and preflight.get("status") == "PASSED" else "NEEDS_ATTENTION",
        "plan_json": str(Path(plan_json).resolve()),
        "preflight_report": str(Path(preflight_report).resolve()),
        "scene_count": len(results),
        "mapping_problem_count": len(mapping.get("problems", [])),
        "prompt_maximizer_problem_count": len(maximizer.get("problems", [])),
        "preflight_status": preflight.get("status"),
        "filename_hints_enabled": mapping.get("filename_hints_enabled"),
        "manifest_json": mapping.get("manifest_json"),
        "prompt_max_chars": maximizer.get("max_chars"),
        "prompt_target_chars": maximizer.get("target_chars"),
        "scenes": [],
        "problems": problems,
    }

    for item in results:
        assignment = item.get("seed_assignment", {})
        prompt_max = item.get("prompt_maximizer", {})
        status["scenes"].append({
            "clip_index": item.get("clip_index"),
            "seed_file": assignment.get("seed_file"),
            "method": assignment.get("method"),
            "filename_prompt_hint": assignment.get("filename_prompt_hint"),
            "scene_addon": assignment.get("scene_addon"),
            "prompt_chars": len(item.get("prompt_text", "")),
            "prompt_remaining_chars": prompt_max.get("remaining_chars"),
            "seed_image_used": item.get("seed_image_used"),
        })

    write_json(output_json, status)
    return status


def main():
    parser = argparse.ArgumentParser(description="One-shot LTX scene-control prep: apply seed mapping, optionally maximize prompts, preflight, and write status.")
    parser.add_argument("--plan-json", default=DEFAULT_PLAN)
    parser.add_argument("--seed-dir", default=DEFAULT_SEED_DIR)
    parser.add_argument("--manifest-json", default=None)
    parser.add_argument("--preview-md", default=DEFAULT_PREVIEW)
    parser.add_argument("--preflight-output", default=DEFAULT_PREFLIGHT)
    parser.add_argument("--status-output", default=DEFAULT_STATUS)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--no-filename-hints", action="store_true")
    parser.add_argument("--maximize-prompts", action="store_true", help="Expand each scene prompt toward the configured character target before preflight.")
    parser.add_argument("--prompt-max-chars", type=int, default=DEFAULT_PROMPT_MAX_CHARS)
    parser.add_argument("--prompt-target-chars", type=int, default=DEFAULT_PROMPT_TARGET_CHARS)
    args = parser.parse_args()

    apply_seed_mapping(
        plan_json=args.plan_json,
        seed_dir=args.seed_dir,
        strict=args.strict,
        manifest_json=args.manifest_json,
        no_filename_hints=args.no_filename_hints,
        preview_md=args.preview_md,
    )

    if args.maximize_prompts:
        plan = maximize_plan_prompts(
            plan_json=args.plan_json,
            max_chars=args.prompt_max_chars,
            target_chars=args.prompt_target_chars,
        )
        make_preview_report(plan, args.preview_md)

    preflight = run_preflight(args.plan_json, args.preflight_output)
    status = build_scene_control_status(args.plan_json, args.preflight_output, args.status_output)

    print("LTX scene-control prep complete.")
    print(f"Status: {status['status']}")
    print(f"Scene count: {status['scene_count']}")
    print(f"Preflight: {preflight['status']}")
    print(f"Prompt max chars: {status.get('prompt_max_chars')}")
    print(f"Prompt target chars: {status.get('prompt_target_chars')}")
    print(f"Preview: {Path(args.preview_md).resolve()}")
    print(f"Status JSON: {Path(args.status_output).resolve()}")
    if status["problems"]:
        for problem in status["problems"]:
            print(f"PROBLEM: {problem}")


if __name__ == "__main__":
    main()
