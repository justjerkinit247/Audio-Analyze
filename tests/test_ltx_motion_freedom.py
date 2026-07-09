from audio_analyze.ltx_motion_freedom import (
    DEFAULT_LIVE_GUIDANCE_SCALE,
    apply_motion_freedom_to_item,
    select_evenly_spaced,
)


def _scene_item():
    relative = [round(index * 0.3, 3) for index in range(24)]
    absolute = [round(value + 12.0, 3) for value in relative]
    return {
        "clip_index": 1,
        "seed_image_used": "seed/scene_01_woman_man_duet_choir_glute_twerk.png",
        "seed_filename_used_for_prompt_hint": "scene_01_woman_man_duet_choir_glute_twerk.png",
        "subject_count_policy": {
            "has_pair": True,
            "has_choir": True,
            "has_group": True,
            "multiple_subjects": True,
        },
        "tap_motion_profile": "localized_glute_pulse",
        "tap_sync": {
            "primary_sync_targets_relative_seconds": relative,
            "primary_sync_targets_seconds": absolute,
            "tap_accent_times_seconds": absolute,
            "tap_accent_strengths": [float(index) for index in range(24)],
            "tap_accent_high_frequency_ratios": [0.5 for _ in range(24)],
            "sync_density": 24,
        },
        "prompt_text": "X" * 4763,
    }


def test_evenly_spaced_selection_preserves_start_middle_and_end_coverage():
    values = list(range(24))

    selected, indices = select_evenly_spaced(values, 8)

    assert len(selected) == 8
    assert selected[0] == 0
    assert selected[-1] == 23
    assert indices == sorted(indices)
    assert len(set(indices)) == 8


def test_motion_freedom_replaces_control_document_with_concise_motion_brief():
    patched = apply_motion_freedom_to_item(_scene_item(), max_prompted_taps=8)
    prompt = patched["prompt_text"]
    profile = patched["motion_freedom_profile"]

    assert patched["prompt_text_before_motion_freedom"] == "X" * 4763
    assert len(prompt) < 2400
    assert profile["guidance_scale"] == DEFAULT_LIVE_GUIDANCE_SCALE == 6.5
    assert profile["detected_tap_count"] == 24
    assert profile["prompted_tap_count"] == 8
    assert profile["first_tap_is_start_signal"] is False
    assert profile["continuous_motion_priority"] is True

    for marker in (
        "[SUBJECT_LOCK]",
        "[AUDIO_TIMING]",
        "[TAP_SYNC]",
        "[MOTION_PROMPT]",
        "[NEGATIVE_PROMPT]",
    ):
        assert marker in prompt

    assert "From the first frame" in prompt
    assert "instead of waiting for the first one" in prompt
    assert "compact localized twerk pulse" in prompt
    assert "glute-cheek contraction" in prompt
    assert "Both feet remain planted" in prompt
    assert "Do not convert the accents into jumping" in prompt
    assert "jumping" in prompt.split("[NEGATIVE_PROMPT]", 1)[1]
    assert "moving choir hands while the lead pair remains frozen" in prompt


def test_motion_freedom_reduces_active_tap_targets_but_retains_detected_evidence():
    original = _scene_item()
    patched = apply_motion_freedom_to_item(original, max_prompted_taps=8)
    tap_sync = patched["tap_sync"]

    assert len(tap_sync["primary_sync_targets_relative_seconds"]) == 8
    assert len(tap_sync["primary_sync_targets_seconds"]) == 8
    assert len(tap_sync["all_detected_primary_sync_targets_relative_seconds"]) == 24
    assert len(tap_sync["all_detected_primary_sync_targets_seconds"]) == 24
    assert tap_sync["sync_density"] == 8
    assert tap_sync["prompt_target_policy"] == "eight_evenly_distributed_major_accents"
