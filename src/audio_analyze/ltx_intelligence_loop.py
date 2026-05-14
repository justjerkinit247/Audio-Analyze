from __future__ import annotations

from pathlib import Path
import argparse
import json

try:
    from .audio_analysis_upgrade import analyze_beat_grid, score_scene_boundaries
    from .ltx_feature_extractor import extract_from_state, write_features_jsonl
    from .ltx_feedback_analyzer import build_feedback_packet
    from .ltx_policy_store import update_policy_from_feedback
    from .ltx_visual_critic import build_visual_critic_report
    from .ltx_strategy_scorer import score_strategies
    from .asmo_memory_bank import init_memory_bank, update_memory_from_active_state
    from .ltx_next_scene_planner import build_next_plan
except ImportError:
    from audio_analysis_upgrade import analyze_beat_grid, score_scene_boundaries
    from ltx_feature_extractor import extract_from_state, write_features_jsonl
    from ltx_feedback_analyzer import build_feedback_packet
    from ltx_policy_store import update_policy_from_feedback
    from ltx_visual_critic import build_visual_critic_report
    from ltx_strategy_scorer import score_strategies
    from asmo_memory_bank import init_memory_bank, update_memory_from_active_state
    from ltx_next_scene_planner import build_next_plan


def read_json(path: Path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def run_intelligence_loop(
    plan_json: Path,
    state_root: Path,
    output_plan: Path,
    audio: Path | None = None,
    external_critic_json: Path | None = None,
    update_policy: bool = True,
    update_memory: bool = True,
) -> dict:
    plan_json = Path(plan_json)
    state_root = Path(state_root)
    output_plan = Path(output_plan)

    summary = {
        "status": "running",
        "plan_json": str(plan_json),
        "state_root": str(state_root),
        "output_plan": str(output_plan),
        "steps": [],
    }

    plan = read_json(plan_json, default={}) or {}

    if audio:
        audio_report = analyze_beat_grid(Path(audio))
        if plan:
            audio_report["scene_boundary_report"] = score_scene_boundaries(plan, audio_report)
        audio_out = state_root / "active" / "features" / "audio_analysis_upgrade.json"
        write_json(audio_out, audio_report)
        summary["steps"].append({"step": "audio_analysis", "output": str(audio_out), "beat_confidence": audio_report.get("beat_confidence")})

    features = extract_from_state(state_root)
    features_out = write_features_jsonl(state_root, features)
    summary["steps"].append({"step": "feature_extraction", "output": str(features_out), "feature_count": len(features)})

    visual_report = build_visual_critic_report(state_root, external_critic_json=external_critic_json)
    summary["steps"].append({"step": "visual_critic", "scene_count": visual_report.get("scene_count")})

    feedback_packet = build_feedback_packet(state_root)
    summary["steps"].append({"step": "feedback_packet", "scene_count": feedback_packet.get("summary", {}).get("scene_count")})

    if update_policy:
        policy = update_policy_from_feedback(state_root, feedback_packet)
        summary["steps"].append({"step": "policy_update", "strategy_count": len(policy.get("strategies", {}))})

    strategy_scores = score_strategies(state_root)
    summary["steps"].append({"step": "strategy_scoring", "top_strategy": strategy_scores.get("ranked", [{}])[0].get("name") if strategy_scores.get("ranked") else None})

    init_memory_bank(state_root)
    if update_memory:
        memory_summary = update_memory_from_active_state(state_root)
        summary["steps"].append({"step": "memory_bank_update", "winning_patterns": memory_summary.get("winning_patterns"), "failure_patterns": memory_summary.get("failure_patterns")})

    next_plan = build_next_plan(plan_json, state_root, output_plan)
    summary["steps"].append({"step": "next_plan", "output": str(output_plan), "scene_count": len(next_plan.get("results", []))})

    summary["status"] = "complete"
    loop_summary_path = state_root / "active" / "feedback" / "intelligence_loop_summary.json"
    write_json(loop_summary_path, summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description="Run integrated LTX-ASMO intelligence loop on the active state.")
    parser.add_argument("--plan-json", required=True)
    parser.add_argument("--state-root", default="outputs/ltx_video_run/_state")
    parser.add_argument("--output-plan", default="outputs/ltx_video_run/holy_cheeks_ltx_plan_next.json")
    parser.add_argument("--audio", default=None)
    parser.add_argument("--external-critic-json", default=None)
    parser.add_argument("--no-policy-update", action="store_true")
    parser.add_argument("--no-memory-update", action="store_true")
    args = parser.parse_args()

    summary = run_intelligence_loop(
        plan_json=Path(args.plan_json),
        state_root=Path(args.state_root),
        output_plan=Path(args.output_plan),
        audio=Path(args.audio) if args.audio else None,
        external_critic_json=Path(args.external_critic_json) if args.external_critic_json else None,
        update_policy=not args.no_policy_update,
        update_memory=not args.no_memory_update,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
