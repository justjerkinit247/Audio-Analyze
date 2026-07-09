from audio_analyze.tap_accent_sync import (
    TAP_SYNC_MARKER,
    apply_tap_sync_to_plan_data,
    build_tap_sync_prompt_block,
    choose_primary_sync_targets,
    insert_tap_sync_prompt,
    is_localized_glute_scene,
    merge_negative_prompt_terms,
    select_tap_accent_targets,
)


def _generic_tap_candidates(count: int) -> list[dict]:
    return [
        {
            "time": round(index * 0.1, 3),
            "strength": 1.0,
            "high_frequency_ratio": 0.8,
            "tap_score": 0.8,
        }
        for index in range(count)
    ]


def test_select_tap_accent_targets_keeps_off_grid_high_scores_in_time_order():
    candidates = [
        {"time": 1.00, "strength": 0.9, "high_frequency_ratio": 0.30, "tap_score": 0.27},
        {"time": 1.25, "strength": 0.8, "high_frequency_ratio": 0.80, "tap_score": 0.64},
        {"time": 1.50, "strength": 0.7, "high_frequency_ratio": 0.70, "tap_score": 0.49},
    ]

    selected = select_tap_accent_targets(candidates, limit=2)

    assert [row["time"] for row in selected] == [1.25, 1.50]


def test_analysis_derived_selection_has_no_fixed_floor_or_ceiling():
    for count in (6, 24, 55):
        candidates = _generic_tap_candidates(count)

        selected = select_tap_accent_targets(candidates)
        targets, source = choose_primary_sync_targets(candidates, [])

        assert len(selected) == count
        assert len(targets) == count
        assert source == "high_frequency_percussive_onsets"
        assert targets[0] == candidates[0]["time"]
        assert targets[-1] == candidates[-1]["time"]


def test_explicit_limit_remains_available_without_becoming_the_default():
    candidates = _generic_tap_candidates(55)

    selected = select_tap_accent_targets(candidates, limit=7)

    assert len(selected) == 7


def test_audio_derived_prompt_can_carry_fifty_five_targets():
    targets = [round(index * 0.1, 3) for index in range(55)]

    block = build_tap_sync_prompt_block(
        {"primary_sync_targets_relative_seconds": targets},
        scene_hint="generic performer choreography",
    )

    assert "0.000s" in block
    assert "5.400s" in block
    assert block.count("s") >= 55
    assert len(block) < 5000


def test_primary_targets_prefer_taps_over_stronger_beat_grid_fallback():
    tap_candidates = [
        {"time": 0.50, "strength": 0.4, "high_frequency_ratio": 0.9, "tap_score": 0.36},
        {"time": 1.50, "strength": 0.4, "high_frequency_ratio": 0.9, "tap_score": 0.36},
    ]
    beat_grid = [
        {"time": 0.00, "percussive_strength": 99.0},
        {"time": 1.00, "percussive_strength": 98.0},
    ]

    targets, source = choose_primary_sync_targets(
        tap_candidates,
        beat_grid,
        limit=8,
    )

    assert targets == [0.5, 1.5]
    assert source == "high_frequency_percussive_onsets"


def test_insert_tap_sync_prompt_places_policy_before_motion_prompt():
    original = (
        "[AUDIO_TIMING]\nTiming.\n\n"
        "[MOTION_PROMPT]\nMove.\n\n"
        "[NEGATIVE_PROMPT]\nNo drift.\n"
    )
    tap_block = (
        "[TAP_SYNC]\n"
        "Pulse on clap and snare taps; not on bass-only boom hits.\n"
    )

    updated = insert_tap_sync_prompt(original, tap_block)

    assert updated.index("[AUDIO_TIMING]") < updated.index(TAP_SYNC_MARKER)
    assert updated.index(TAP_SYNC_MARKER) < updated.index("[MOTION_PROMPT]")
    assert "bass-only boom" in updated
    assert "[NEGATIVE_PROMPT]" in updated


def test_twerk_filename_activates_localized_glute_profile():
    hint = (
        "sunlit cathedral gospel twerk duet woman deep squat hip glute "
        "reversals on clap snare hi hat"
    )

    assert is_localized_glute_scene(hint) is True
    assert is_localized_glute_scene("bird flies through ocean clouds") is False


def test_localized_glute_block_translates_taps_without_changing_times():
    marker = {
        "primary_sync_targets_relative_seconds": [0.5, 1.5, 2.5],
    }

    block = build_tap_sync_prompt_block(
        marker,
        scene_hint="woman deep squat gospel twerk hip glute cheek pulses",
    )

    assert "0.500s, 1.500s, 2.500s" in block
    assert "compact localized twerk pulse" in block
    assert "glute-cheek contraction" in block
    assert "Both feet remain planted" in block
    assert "overall body height nearly constant" in block
    assert "Do not convert the accents into jumping" in block
    assert "begins immediately at 0.00 seconds" in block


def test_merge_negative_prompt_terms_deduplicates_jump_guards():
    prompt = (
        "[MOTION_PROMPT]\nMove.\n\n"
        "[NEGATIVE_PROMPT]\nblurry motion, jumping\n"
    )

    updated = merge_negative_prompt_terms(
        prompt,
        ["jumping", "feet leaving the floor", "whole-body bouncing"],
    )

    negative = updated.split("[NEGATIVE_PROMPT]", 1)[1]
    assert negative.lower().count("jumping") == 1
    assert "feet leaving the floor" in negative
    assert "whole-body bouncing" in negative


def test_apply_tap_sync_preserves_timing_and_applies_localized_profile():
    plan = {
        "results": [
            {
                "clip_index": 1,
                "scene": {"start": 4.0, "end": 8.0, "duration": 4.0},
                "seed_image_used": (
                    "inputs/ltx_seed_images/"
                    "scene_01_sunlit_cathedral_gospel_twerk_duet_woman_deep_"
                    "squat_hip_glute_reversals_on_clap_snare_hi_hat.png"
                ),
                "seed_filename_prompt_hint": (
                    "sunlit cathedral gospel twerk duet woman deep squat hip "
                    "glute reversals on clap snare hi hat"
                ),
                "prompt_text": (
                    "[AUDIO_TIMING]\nTiming.\n\n"
                    "[MOTION_PROMPT]\nMove.\n\n"
                    "[NEGATIVE_PROMPT]\nNo drift.\n"
                ),
            }
        ]
    }
    markers = {
        "tap_accent_candidate_count": 2,
        "scenes": [
            {
                "clip_index": 1,
                "primary_sync_targets_seconds": [4.5, 5.5],
                "primary_sync_targets_relative_seconds": [0.5, 1.5],
                "primary_sync_source": "high_frequency_percussive_onsets",
                "sync_target_policy": "tap_not_boom",
            }
        ],
    }

    patched = apply_tap_sync_to_plan_data(
        plan,
        audio_path="unused.wav",
        markers=markers,
    )

    item = patched["results"][0]
    prompt = item["prompt_text"]
    assert "[AUDIO_TIMING]" in prompt
    assert "[TAP_SYNC]" in prompt
    assert "[MOTION_PROMPT]" in prompt
    assert "[NEGATIVE_PROMPT]" in prompt
    assert "0.500s, 1.500s" in prompt
    assert item["tap_sync"]["primary_sync_targets_seconds"] == [4.5, 5.5]
    assert item["tap_sync"]["primary_sync_targets_relative_seconds"] == [0.5, 1.5]
    assert item["tap_motion_profile"] == "localized_glute_pulse"
    assert "compact localized twerk pulse" in prompt
    assert "jumping" in prompt.split("[NEGATIVE_PROMPT]", 1)[1]
    assert "feet leaving the floor" in prompt.split("[NEGATIVE_PROMPT]", 1)[1]
    assert patched["tap_sync"]["policy"] == "tap_not_boom"
    assert patched["tap_sync"]["candidate_count"] == 2
    assert patched["tap_sync"]["motion_profile_counts"]["localized_glute_pulse"] == 1


def test_apply_tap_sync_keeps_generic_profile_for_non_dance_scene():
    plan = {
        "results": [
            {
                "clip_index": 1,
                "scene": {"start": 0.0, "end": 4.0, "duration": 4.0},
                "seed_filename_prompt_hint": "bird flies over ocean clouds",
                "prompt_text": (
                    "[AUDIO_TIMING]\nTiming.\n\n"
                    "[MOTION_PROMPT]\nMove.\n\n"
                    "[NEGATIVE_PROMPT]\nNo drift.\n"
                ),
            }
        ]
    }
    markers = {
        "tap_accent_candidate_count": 1,
        "scenes": [
            {
                "clip_index": 1,
                "primary_sync_targets_seconds": [1.0],
                "primary_sync_targets_relative_seconds": [1.0],
                "primary_sync_source": "high_frequency_percussive_onsets",
            }
        ],
    }

    patched = apply_tap_sync_to_plan_data(
        plan,
        audio_path="unused.wav",
        markers=markers,
    )

    item = patched["results"][0]
    assert item["tap_motion_profile"] == "generic_tap_action"
    assert "compact localized twerk pulse" not in item["prompt_text"]
