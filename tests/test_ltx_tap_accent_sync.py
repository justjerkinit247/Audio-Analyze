from audio_analyze.tap_accent_sync import (
    TAP_SYNC_MARKER,
    apply_tap_sync_to_plan_data,
    choose_primary_sync_targets,
    insert_tap_sync_prompt,
    select_tap_accent_targets,
)


def test_select_tap_accent_targets_keeps_off_grid_high_scores_in_time_order():
    candidates = [
        {"time": 1.00, "strength": 0.9, "high_frequency_ratio": 0.30, "tap_score": 0.27},
        {"time": 1.25, "strength": 0.8, "high_frequency_ratio": 0.80, "tap_score": 0.64},
        {"time": 1.50, "strength": 0.7, "high_frequency_ratio": 0.70, "tap_score": 0.49},
    ]

    selected = select_tap_accent_targets(candidates, limit=2)

    assert [row["time"] for row in selected] == [1.25, 1.50]


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
        "Reverse hips on clap and snare taps; not on bass-only boom hits.\n"
    )

    updated = insert_tap_sync_prompt(original, tap_block)

    assert updated.index("[AUDIO_TIMING]") < updated.index(TAP_SYNC_MARKER)
    assert updated.index(TAP_SYNC_MARKER) < updated.index("[MOTION_PROMPT]")
    assert "bass-only boom" in updated
    assert "[NEGATIVE_PROMPT]" in updated


def test_apply_tap_sync_preserves_existing_prompt_sections():
    plan = {
        "results": [
            {
                "clip_index": 1,
                "scene": {"start": 4.0, "end": 8.0, "duration": 4.0},
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

    prompt = patched["results"][0]["prompt_text"]
    assert "[AUDIO_TIMING]" in prompt
    assert "[TAP_SYNC]" in prompt
    assert "[MOTION_PROMPT]" in prompt
    assert "[NEGATIVE_PROMPT]" in prompt
    assert "0.500s, 1.500s" in prompt
    assert patched["tap_sync"]["policy"] == "tap_not_boom"
    assert patched["tap_sync"]["candidate_count"] == 2
