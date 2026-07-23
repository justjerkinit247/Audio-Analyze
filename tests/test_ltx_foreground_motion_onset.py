from audio_analyze.ltx_prompt_budget import compact_item_prompt


def _item(*, pair=True, choir=True, localized=True):
    filename = "scene_01_duet_choir_glute_cheek_twerk.png"
    prompt = (
        "Audio-and-image-to-video continuation synchronized to the supplied audio.\n\n"
        "[SUBJECT_LOCK]\nPreserve everyone.\n\n"
        "[AUDIO_TIMING]\nScene timing.\n\n"
        "[TAP_SYNC]\nPrimary tap-accent times inside this clip: 1.500s, 2.500s.\n\n"
        "[MOTION_PROMPT]\nThe pair performs while choir hands clap in the background.\n\n"
        "[NEGATIVE_PROMPT]\nblurry motion, jumping, missing partner, missing choir\n"
    )
    return {
        "clip_index": 1,
        "seed_image_used": f"seed/{filename}",
        "seed_filename_used_for_prompt_hint": filename,
        "subject_count_policy": {
            "has_pair": pair,
            "has_choir": choir,
            "has_group": choir,
            "multiple_subjects": pair or choir,
        },
        "audio_timing": {
            "scene_index": 1,
            "start_seconds": 0.0,
            "end_seconds": 8.0,
            "duration_seconds": 8.0,
            "tempo_bpm": 120.0,
            "beat_alignment_enabled": True,
        },
        "tap_sync": {
            "primary_sync_targets_relative_seconds": [1.5, 2.5],
            "motion_profile": "localized_glute_pulse" if localized else "generic_tap_action",
        },
        "tap_motion_profile": "localized_glute_pulse" if localized else "generic_tap_action",
        "filename_hint_expansion": {
            "ltx_motion_prompt": "The pair performs while choir hands clap in the background.",
            "negative_prompt": "blurry motion, jumping, missing partner, missing choir",
        },
        "prompt_text": prompt,
    }


def test_localized_pair_moves_before_first_tap_with_grounded_continuity():
    compacted = compact_item_prompt(_item())
    prompt = compacted["prompt_text"]

    assert "begin visible motion on frame 1" in prompt
    assert "depart the seed pose by 0.10 seconds" in prompt
    assert "first tap is an accent, not the start signal" in prompt
    assert "compact localized twerk pulse" in prompt
    assert "glute-cheek contraction" in prompt
    assert "Both feet remain planted" in prompt
    assert "pelvic micro-motion between taps" in prompt
    assert "Do not convert the accents into jumping" in prompt
    assert compacted["foreground_motion_onset"]["deadline_seconds"] == 0.10
    assert compacted["foreground_motion_onset"]["first_tap_is_start_signal"] is False
    assert compacted["foreground_motion_onset"]["background_only_motion_forbidden"] is True


def test_critical_negative_terms_block_static_foreground_with_moving_hands():
    compacted = compact_item_prompt(_item())
    negative = compacted["prompt_text"].split("[NEGATIVE_PROMPT]", 1)[1]

    assert "frozen foreground subjects" in negative
    assert "static lead pair" in negative
    assert "background-only motion" in negative
    assert "moving background hands while foreground remains frozen" in negative
    assert "animated background with static main characters" in negative


def test_generic_solo_gets_immediate_primary_subject_motion():
    compacted = compact_item_prompt(
        _item(pair=False, choir=False, localized=False)
    )
    prompt = compacted["prompt_text"]

    assert "the main foreground subject begin visible motion on frame 1" in prompt
    assert "depart the seed pose by 0.10 seconds" in prompt
    assert "first tap is an accent, not the start signal" in prompt
    assert "maintain coherent foreground motion between accents" in prompt
    assert len(prompt) <= 4800
