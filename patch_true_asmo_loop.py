from pathlib import Path

path = Path("src/audio_analyze/ltx_intelligence_loop.py")
text = path.read_text(encoding="utf-8")

# 1. Import true ASMO injector in both import paths.
text = text.replace(
    "from .ltx_next_scene_planner import build_next_plan",
    "from .ltx_next_scene_planner import build_next_plan\n    from .asmo_engine.ltx_run_integrator import inject_asmo_into_ltx_run_plan",
)

text = text.replace(
    "from ltx_next_scene_planner import build_next_plan",
    "from ltx_next_scene_planner import build_next_plan\n    from asmo_engine.ltx_run_integrator import inject_asmo_into_ltx_run_plan",
)

# 2. Add helper functions before run_intelligence_loop.
marker = "\ndef run_intelligence_loop(\n"
helper = r'''

def first_scene_start_seconds(plan: dict) -> float:
    results = plan.get("results", []) if isinstance(plan, dict) else []
    if not results:
        return 0.0
    scene = results[0].get("scene", {}) if isinstance(results[0], dict) else {}
    try:
        return float(scene.get("start", 0.0) or 0.0)
    except Exception:
        return 0.0


def assert_true_asmo_injected(plan: dict, output_plan: Path) -> None:
    results = plan.get("results", []) if isinstance(plan, dict) else []
    if not results:
        raise ValueError(f"True ASMO requested, but output plan has no results: {output_plan}")

    failures = []
    for item in results:
        clip_index = item.get("clip_index")
        status = item.get("asmo_injection_status")
        count = item.get("asmo_motion_event_count") or 0
        prompt = item.get("prompt_text") or ""

        if status != "injected":
            failures.append(f"scene {clip_index}: asmo_injection_status={status!r}")
        if int(count) <= 0:
            failures.append(f"scene {clip_index}: asmo_motion_event_count={count!r}")
        if "TIMED ASMO MOTION DIRECTIVES:" not in prompt:
            failures.append(f"scene {clip_index}: missing TIMED ASMO MOTION DIRECTIVES block")

    if failures:
        raise ValueError(
            "True ASMO injection proof failed for output plan "
            f"{output_plan}: " + "; ".join(failures)
        )
'''
if helper.strip() not in text:
    text = text.replace(marker, helper + marker)

# 3. Extend run_intelligence_loop signature.
text = text.replace(
    "require_audio: bool = False,\n) -> dict:",
    "require_audio: bool = False,\n    apply_true_asmo: bool = False,\n    lyrics: Path | None = None,\n    start_offset_from_scene: bool = False,\n    true_asmo_output_plan: Path | None = None,\n) -> dict:",
)

# 4. Replace next-plan block with true ASMO optional injection.
old = '''    next_plan = build_next_plan(plan_json, state_root, output_plan)
    summary["steps"].append({"step": "next_plan", "output": str(output_plan), "scene_count": len(next_plan.get("results", []))})
'''
new = '''    next_plan = build_next_plan(plan_json, state_root, output_plan)
    summary["steps"].append({"step": "next_plan", "output": str(output_plan), "scene_count": len(next_plan.get("results", []))})

    if apply_true_asmo:
        if lyrics is None:
            raise ValueError("--apply-true-asmo requires --lyrics")
        lyrics = Path(lyrics)
        if not lyrics.exists():
            raise FileNotFoundError(f"True ASMO lyrics file not found: {lyrics}")

        start_offset_seconds = first_scene_start_seconds(next_plan) if start_offset_from_scene else 0.0
        true_asmo_target = Path(true_asmo_output_plan) if true_asmo_output_plan else output_plan

        true_asmo_plan = inject_asmo_into_ltx_run_plan(
            plan_json=output_plan,
            lyric_path=lyrics,
            output_json=true_asmo_target,
            max_events_per_scene=8,
            start_offset_seconds=start_offset_seconds,
        )
        assert_true_asmo_injected(true_asmo_plan, true_asmo_target)
        next_plan = true_asmo_plan
        output_plan = true_asmo_target
        summary["output_plan"] = str(output_plan)
        summary["steps"].append({
            "step": "true_asmo_injection",
            "output": str(true_asmo_target),
            "lyrics": str(lyrics),
            "start_offset_seconds": start_offset_seconds,
            "scene_count": len(true_asmo_plan.get("results", [])),
            "proof": [
                "asmo_injection_status == injected",
                "asmo_motion_event_count > 0",
                "TIMED ASMO MOTION DIRECTIVES present in prompt_text",
            ],
        })
'''
if old not in text:
    raise SystemExit("Could not find next_plan block to patch. Stop and inspect ltx_intelligence_loop.py.")
text = text.replace(old, new)

# 5. Add CLI args.
text = text.replace(
    '    parser.add_argument("--require-audio", action="store_true", help="Fail if no explicit, plan-derived, or auto-discovered audio file can be found.")',
    '    parser.add_argument("--require-audio", action="store_true", help="Fail if no explicit, plan-derived, or auto-discovered audio file can be found.")\n'
    '    parser.add_argument("--apply-true-asmo", action="store_true", help="Inject real timed ASMO directives into the generated next plan.")\n'
    '    parser.add_argument("--lyrics", default=None, help="Lyrics file used for true ASMO timed directive generation.")\n'
    '    parser.add_argument("--start-offset-from-scene", action="store_true", help="Use the first scene start time as the ASMO timestamp offset.")\n'
    '    parser.add_argument("--true-asmo-output-plan", default=None, help="Optional output path for the true ASMO injected plan.")',
)

# 6. Pass CLI args into run_intelligence_loop.
text = text.replace(
    "        require_audio=args.require_audio,\n    )",
    "        require_audio=args.require_audio,\n        apply_true_asmo=args.apply_true_asmo,\n        lyrics=Path(args.lyrics) if args.lyrics else None,\n        start_offset_from_scene=args.start_offset_from_scene,\n        true_asmo_output_plan=Path(args.true_asmo_output_plan) if args.true_asmo_output_plan else None,\n    )",
)

path.write_text(text, encoding="utf-8")
print("Patched src/audio_analyze/ltx_intelligence_loop.py")
