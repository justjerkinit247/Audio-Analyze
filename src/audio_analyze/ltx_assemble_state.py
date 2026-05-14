from __future__ import annotations

from pathlib import Path
import argparse
import json

try:
    from .ltx_clip_assembler import merge_clips
    from .ltx_run_state import append_assembly_attempt
except ImportError:
    from ltx_clip_assembler import merge_clips
    from ltx_run_state import append_assembly_attempt


def main():
    parser = argparse.ArgumentParser(description="State-aware LTX assembler wrapper with attempt journaling.")
    parser.add_argument("--downloads", default="outputs/ltx_video_run/downloads")
    parser.add_argument("--state-root", default="outputs/ltx_video_run/_state")
    parser.add_argument("--output", default="outputs/ltx_video_run/assembled/state_sync_test.mp4")
    parser.add_argument("--plan-json", default="outputs/ltx_video_run/holy_cheeks_ltx_plan.json")
    parser.add_argument("--results-dir", default=None)
    parser.add_argument("--audio", default=None)
    parser.add_argument("--start-seconds", type=float, default=0.0)
    parser.add_argument("--audio-offset-seconds", type=float, default=0.0)
    parser.add_argument("--duration-seconds", type=float, default=None)
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--trim-tail-seconds", type=float, default=0.08)
    parser.add_argument("--transition-seconds", type=float, default=0.0)
    parser.add_argument("--expected-scenes", type=int, default=None)
    parser.add_argument("--strict-scenes", action="store_true")
    parser.add_argument("--timing-source", choices=["result-json", "plan-json", "clip", "auto"], default="result-json")
    parser.add_argument("--audio-mode", choices=["scene-json", "full-bed", "none"], default="scene-json")
    args = parser.parse_args()

    state_root = Path(args.state_root)
    results_dir = args.results_dir or str(state_root / "active" / "scene_returns")
    report_json = state_root / "active" / "assembler" / "latest_assembly_report.json"

    info = merge_clips(
        downloads_dir=args.downloads,
        results_dir=results_dir,
        output_path=args.output,
        plan_json=args.plan_json,
        audio_path=args.audio,
        start_seconds=args.start_seconds,
        audio_offset_seconds=args.audio_offset_seconds,
        duration_seconds=args.duration_seconds,
        fps=args.fps,
        trim_tail_seconds=args.trim_tail_seconds,
        transition_seconds=args.transition_seconds,
        expected_scenes=args.expected_scenes,
        strict_scenes=args.strict_scenes,
        report_json=report_json,
        timing_source=args.timing_source,
        audio_mode=args.audio_mode,
    )

    attempt = {
        "assembler_output": info.get("output_path"),
        "status": info.get("status"),
        "clip_count": info.get("clip_count"),
        "missing_scenes": info.get("missing_scenes"),
        "extra_scenes": info.get("extra_scenes"),
        "audio_offset_seconds": args.audio_offset_seconds,
        "trim_tail_seconds": args.trim_tail_seconds,
        "transition_seconds": args.transition_seconds,
        "timing_source": args.timing_source,
        "audio_mode": args.audio_mode,
        "final_video_duration": info.get("final_video_duration"),
        "report": info,
    }

    append_assembly_attempt(state_root, attempt)
    print(json.dumps(attempt, indent=2))


if __name__ == "__main__":
    main()
