import copy

import pytest

from audio_analyze import ltx_live_run as live


def _valid_prompt() -> str:
    return (
        "[SUBJECT_LOCK]\nPreserve every visible person and the original body layout.\n\n"
        "[SEED_IMAGE_DESCRIPTION]\nTwo visible performers stand in a sunlit cathedral with a choir behind them.\n\n"
        "[AUDIO_TIMING]\nScene timing follows the supplied audio.\n\n"
        "[TAP_SYNC]\nUse sharp clap, snare, hi-hat accents. Land controlled visible action changes while ignoring bass-only boom hits.\n\n"
        "[MOTION_PROMPT]\nControlled continuous motion.\n\n"
        "[NEGATIVE_PROMPT]\nNo artifacts, missing subjects, or warped anatomy.\n"
    )


def valid_plan(*, run_id="ltx_test", filename="scene_01_solo_actor.png", multiple=False):
    prompt = _valid_prompt()
    return {
        "fresh_run": {"run_id": run_id},
        "plan_reuse_allowed": False,
        "results": [
            {
                "seed_filename_used_for_prompt_hint": filename,
                "prompt_transport_mode": "audio_and_image_to_video",
                "subject_count_policy": {"multiple_subjects": multiple},
                "filename_hint_expansion": {
                    "ltx_motion_prompt": (
                        "A solo actor moves naturally."
                        if not multiple
                        else "The pair moves together."
                    )
                },
                "seed_image_analysis": {
                    "status": "complete",
                    "analysis_mode": "freeform_native",
                    "description": "Complete native Gemma visual analysis.",
                    "model": "gemma3:4b",
                },
                "gemma_final_prompt_synthesis": {
                    "status": "complete",
                    "validation_passed": True,
                    "final_prompt": prompt,
                    "model": "gemma3:4b",
                    "attempt_count": 1,
                },
                "prompt_budget": {"status": "gemma_synthesized"},
                "prompt_text_is_exact_ltx_payload": True,
                "exact_prompt_sent_to_ltx": prompt,
                "tap_motion_profile": "generic_tap_action",
                "choreography_policy": {
                    "profile_id": "generic_tap_action",
                    "selection_method": "default_fallback",
                    "target_selection": {"mode": "all_reliable"},
                    "required_prompt_phrases": [],
                },
                "tap_sync": {"primary_sync_targets_seconds": [0.5]},
                "prompt_text": prompt,
            }
        ],
    }


def validate(plan, *, filename="scene_01_solo_actor.png", run_id="ltx_test"):
    return live._validate_plan(
        plan,
        {"status": "complete"},
        run_id=run_id,
        seed_filename=filename,
    )


def test_make_run_paths_creates_unique_run_scoped_locations(tmp_path, monkeypatch):
    monkeypatch.setattr(live, "generate_run_id", lambda: "ltx_unique")

    paths = live._make_run_paths(tmp_path)

    assert paths.run_id == "ltx_unique"
    assert paths.root == tmp_path / "outputs" / "ltx_video_run" / "live_runs" / "ltx_unique"
    assert paths.plan.parent == paths.root
    assert paths.live_result.parent == paths.root
    assert paths.seed_dir.parent == paths.root


def test_validate_plan_accepts_verified_gemma_exact_payload():
    scene = validate(valid_plan())

    assert scene["prompt_text_is_exact_ltx_payload"] is True
    assert scene["prompt_text"].startswith("[SUBJECT_LOCK]")


def test_validate_plan_accepts_pair_without_solitary_language():
    filename = "scene_01_woman_man_duet.png"
    scene = validate(valid_plan(filename=filename, multiple=True), filename=filename)

    assert scene["subject_count_policy"]["multiple_subjects"] is True


def test_validate_plan_rejects_stale_run_id():
    plan = valid_plan(run_id="ltx_old")

    with pytest.raises(RuntimeError, match="fresh-run ID does not match"):
        validate(plan, run_id="ltx_new")


def test_validate_plan_rejects_solitary_language_for_multi_subject_scene():
    filename = "scene_01_woman_man_duet.png"
    plan = valid_plan(filename=filename, multiple=True)
    plan["results"][0]["filename_hint_expansion"]["ltx_motion_prompt"] = (
        "A solitary dancer performs in the cathedral."
    )

    with pytest.raises(RuntimeError, match="solo/solitary"):
        validate(plan, filename=filename)


def test_validate_plan_enforces_selected_profile_contract_without_hardcoding_profile():
    filename = "scene_01_specialized_motion.png"
    plan = valid_plan(filename=filename)
    plan["results"][0]["choreography_policy"] = {
        "profile_id": "configured_specialized_profile",
        "required_prompt_phrases": ["required configured motion phrase"],
    }

    with pytest.raises(RuntimeError, match="configured_specialized_profile"):
        validate(plan, filename=filename)


def test_validate_plan_rejects_missing_gemma_analysis():
    plan = valid_plan()
    plan["results"][0]["seed_image_analysis"] = {}

    with pytest.raises(RuntimeError, match="Gemma seed-image analysis"):
        validate(plan)


def test_validate_plan_rejects_failed_gemma_synthesis():
    plan = valid_plan()
    plan["results"][0]["gemma_final_prompt_synthesis"]["status"] = "failed"

    with pytest.raises(RuntimeError, match="final-prompt synthesis did not complete"):
        validate(plan)


def test_validate_plan_rejects_duplicate_marker():
    plan = valid_plan()
    scene = plan["results"][0]
    bad = scene["prompt_text"] + "\n[NEGATIVE_PROMPT]\nduplicate"
    scene["prompt_text"] = bad
    scene["exact_prompt_sent_to_ltx"] = bad
    scene["gemma_final_prompt_synthesis"]["final_prompt"] = bad

    with pytest.raises(RuntimeError, match="appears 2 times"):
        validate(plan)


def test_validate_plan_rejects_out_of_order_marker():
    plan = valid_plan()
    scene = plan["results"][0]
    prompt = scene["prompt_text"]
    subject = prompt.split("[SUBJECT_LOCK]", 1)[1].split("[SEED_IMAGE_DESCRIPTION]", 1)[0]
    visual_and_rest = prompt.split("[SEED_IMAGE_DESCRIPTION]", 1)[1]
    bad = f"[SEED_IMAGE_DESCRIPTION]{visual_and_rest.split('[AUDIO_TIMING]', 1)[0]}[SUBJECT_LOCK]{subject}[AUDIO_TIMING]{visual_and_rest.split('[AUDIO_TIMING]', 1)[1]}"
    scene["prompt_text"] = bad
    scene["exact_prompt_sent_to_ltx"] = bad
    scene["gemma_final_prompt_synthesis"]["final_prompt"] = bad

    with pytest.raises(RuntimeError, match="out of order"):
        validate(plan)


def test_validate_plan_rejects_exact_payload_mismatch():
    plan = valid_plan()
    plan["results"][0]["exact_prompt_sent_to_ltx"] = "different payload"

    with pytest.raises(RuntimeError, match="does not match prompt_text"):
        validate(plan)


def test_validate_plan_rejects_legacy_prefix_payload():
    plan = valid_plan()
    scene = plan["results"][0]
    bad = live.LEGACY_PROMPT_PREFIX + ".\n\n" + scene["prompt_text"]
    scene["prompt_text"] = bad
    scene["exact_prompt_sent_to_ltx"] = bad
    scene["gemma_final_prompt_synthesis"]["final_prompt"] = bad

    with pytest.raises(RuntimeError, match="does not begin with \[SUBJECT_LOCK\]"):
        validate(plan)


def test_validate_plan_rejects_empty_visual_section():
    plan = valid_plan()
    scene = plan["results"][0]
    bad = scene["prompt_text"].replace(
        "[SEED_IMAGE_DESCRIPTION]\nTwo visible performers stand in a sunlit cathedral with a choir behind them.\n\n",
        "[SEED_IMAGE_DESCRIPTION]\n\n",
    )
    scene["prompt_text"] = bad
    scene["exact_prompt_sent_to_ltx"] = bad
    scene["gemma_final_prompt_synthesis"]["final_prompt"] = bad

    with pytest.raises(RuntimeError, match="section is empty"):
        validate(plan)


def test_parser_defaults_to_auto_choreography_policy():
    args = live.build_parser().parse_args([])
    assert args.choreography_profile == "auto"
