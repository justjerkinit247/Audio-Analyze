from pathlib import Path

import pytest

from audio_analyze import ltx_live_run as live


def valid_plan(*, run_id="ltx_test", filename="scene_01_solo_actor.png", multiple=False):
    prompt = (
        "Audio-and-image-to-video continuation synchronized to the supplied audio.\n\n"
        "[SUBJECT_LOCK]\nPreserve every visible person.\n\n"
        "[AUDIO_TIMING]\nScene timing.\n\n"
        "[TAP_SYNC]\nTap timing.\n\n"
        "[MOTION_PROMPT]\nControlled motion.\n\n"
        "[NEGATIVE_PROMPT]\nNo artifacts.\n"
    )
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


def test_make_run_paths_creates_unique_run_scoped_locations(tmp_path, monkeypatch):
    monkeypatch.setattr(live, "generate_run_id", lambda: "ltx_unique")

    paths = live._make_run_paths(tmp_path)

    assert paths.run_id == "ltx_unique"
    assert paths.root == tmp_path / "outputs" / "ltx_video_run" / "live_runs" / "ltx_unique"
    assert paths.plan.parent == paths.root
    assert paths.live_result.parent == paths.root
    assert paths.seed_dir.parent == paths.root


def test_validate_plan_accepts_a_real_solo_scene():
    plan = valid_plan(filename="scene_01_solo_male_actor_walks_to_camera.png", multiple=False)

    scene = live._validate_plan(
        plan,
        {"status": "complete"},
        run_id="ltx_test",
        seed_filename="scene_01_solo_male_actor_walks_to_camera.png",
    )

    assert scene["subject_count_policy"]["multiple_subjects"] is False


def test_validate_plan_accepts_pair_without_solitary_language():
    plan = valid_plan(filename="scene_01_woman_man_duet.png", multiple=True)

    scene = live._validate_plan(
        plan,
        {"status": "complete"},
        run_id="ltx_test",
        seed_filename="scene_01_woman_man_duet.png",
    )

    assert scene["subject_count_policy"]["multiple_subjects"] is True


def test_validate_plan_rejects_stale_run_id():
    plan = valid_plan(run_id="ltx_old")

    with pytest.raises(RuntimeError, match="fresh-run ID does not match"):
        live._validate_plan(
            plan,
            {"status": "complete"},
            run_id="ltx_new",
            seed_filename="scene_01_solo_actor.png",
        )


def test_validate_plan_rejects_solitary_language_for_multi_subject_scene():
    plan = valid_plan(filename="scene_01_woman_man_duet.png", multiple=True)
    plan["results"][0]["filename_hint_expansion"]["ltx_motion_prompt"] = (
        "A solitary female dancer performs in the cathedral."
    )

    with pytest.raises(RuntimeError, match="solo/solitary"):
        live._validate_plan(
            plan,
            {"status": "complete"},
            run_id="ltx_test",
            seed_filename="scene_01_woman_man_duet.png",
        )


def test_validate_plan_enforces_selected_profile_contract_without_hardcoding_profile():
    plan = valid_plan(filename="scene_01_specialized_motion.png", multiple=False)
    plan["results"][0]["choreography_policy"] = {
        "profile_id": "configured_specialized_profile",
        "required_prompt_phrases": ["required configured motion phrase"],
    }

    with pytest.raises(RuntimeError, match="configured_specialized_profile"):
        live._validate_plan(
            plan,
            {"status": "complete"},
            run_id="ltx_test",
            seed_filename="scene_01_specialized_motion.png",
        )


def test_parser_defaults_to_auto_choreography_policy():
    args = live.build_parser().parse_args([])

    assert args.choreography_profile == "auto"
