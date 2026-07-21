from audio_analyze.ltx_prompt_budget import (
    AUDIO_TIMING_MARKER,
    MOTION_MARKER,
    NEGATIVE_MARKER,
    SCENE_DESCRIPTION_MARKER,
    SUBJECT_LOCK_MARKER,
    TAP_SYNC_MARKER,
    compact_item_prompt,
    compact_plan_prompts,
)


def long_duet_item():
    motion = (
        "The female lead dancer and male dance partner remain visible together throughout the shot; "
        "the man maintains a restrained grounded groove beside her. "
        "The existing choir remains visible in the background, clapping and swaying subtly without changing subject count. "
        + "Controlled cinematic performance motion continues naturally. " * 45
    )
    negative_terms = [
        "extra limbs",
        "distorted anatomy",
        "blurry background",
        "watermark",
        "text",
        "signature",
        "artifacts",
        "jpeg artifacts",
        "oversaturated",
        "unrealistic lighting",
        "blurry motion",
        "jittery motion",
        "chaotic camera movement",
        "warped background",
        "distorted subject",
        "duplicate subject",
        "low detail",
        "flicker",
        "static opening frame",
        "frozen first frames",
        "delayed motion onset",
        "motionless first half",
        "waiting before movement",
        "jumping",
        "hopping",
        "feet leaving the floor",
        "heels lifting",
        "standing up",
        "repeated squats",
        "whole-body bouncing",
        "vertical pelvic bouncing",
        "full-body pumping",
        "large vertical displacement",
        "missing dance partner",
        "missing male dancer",
        "missing female dancer",
        "missing choir",
        "removed background performers",
        "changed subject count",
        "removed visible subject",
        "added unrelated subject",
        "merged people",
    ] + [f"learned negative condition {index}" for index in range(80)]
    negative = ", ".join(negative_terms)
    timestamps = ", ".join(f"{index * 0.321:.3f}s" for index in range(25))
    scene_description = (
        "Two adult performers occupy the foreground in a full-body vertical composition. "
        "A choir remains visible behind them in a bright cathedral with warm white and gold lighting."
    )
    prompt = (
        "Audio-and-image-to-video continuation synchronized to the supplied audio for a very long mashup title. "
        "Use the supplied audio as the timing source and the seed image as the authoritative visual source.\n\n"
        f"[SCENE_DESCRIPTION]\nObservable opening-frame description: {scene_description}\n\n"
        "[SUBJECT_LOCK]\nThe seed image is authoritative for subject count and body layout. Preserve everybody.\n\n"
        "[AUDIO_TIMING]\n" + "Very verbose audio timing explanation. " * 35 + "\n\n"
        f"[TAP_SYNC]\nPrimary tap-accent times inside this clip: {timestamps}. "
        + "Very verbose tap behavior explanation. " * 35
        + "\n\n[MOTION_PROMPT]\n"
        + motion
        + "\n\n[NEGATIVE_PROMPT]\n"
        + negative
        + "\n"
    )
    return {
        "clip_index": 1,
        "seed_image_used": (
            "seed/scene_01_cathedral_gospel_twerk_duet_woman_man_partner_"
            "white_gold_choir_glute_cheek_pulses.png"
        ),
        "seed_filename_used_for_prompt_hint": (
            "scene_01_cathedral_gospel_twerk_duet_woman_man_partner_"
            "white_gold_choir_glute_cheek_pulses.png"
        ),
        "scene_description": scene_description,
        "subject_count_policy": {
            "has_pair": True,
            "has_choir": True,
            "has_group": True,
            "multiple_subjects": True,
        },
        "audio_timing": {
            "scene_index": 1,
            "start_seconds": 0.04,
            "end_seconds": 8.19,
            "duration_seconds": 8.15,
            "tempo_bpm": 140.62,
            "beat_alignment_enabled": True,
            "energy_profile": "very high",
            "edit_pacing": "fast",
        },
        "tap_sync": {
            "primary_sync_targets_relative_seconds": [index * 0.321 for index in range(25)],
            "motion_profile": "localized_glute_pulse",
        },
        "tap_motion_profile": "localized_glute_pulse",
        "filename_hint_expansion": {
            "ltx_motion_prompt": motion,
            "negative_prompt": negative,
        },
        "prompt_text": prompt,
    }


def test_compacts_long_prompt_under_safe_target_without_losing_contract():
    item = long_duet_item()
    assert len(item["prompt_text"]) > 5000

    compacted = compact_item_prompt(item, max_chars=5000, target_chars=4800)
    prompt = compacted["prompt_text"]

    assert len(prompt) <= 4800
    assert compacted["prompt_budget"]["before_chars"] > 5000
    assert compacted["prompt_budget"]["after_chars"] == len(prompt)
    for marker in (
        SCENE_DESCRIPTION_MARKER,
        SUBJECT_LOCK_MARKER,
        AUDIO_TIMING_MARKER,
        TAP_SYNC_MARKER,
        MOTION_MARKER,
        NEGATIVE_MARKER,
    ):
        assert marker in prompt
    assert "Audio-and-image-to-video continuation" in prompt
    assert "Seed image filename used as the Ollama prompt hint:" in prompt
    assert "Two adult performers occupy the foreground" in prompt
    assert compacted["prompt_budget"]["scene_description_preserved"] is True
    assert "female lead dancer and male dance partner" in prompt
    assert "choir" in prompt
    assert "compact localized twerk pulse" in prompt
    assert "glute-cheek contraction" in prompt
    assert "Both feet remain planted" in prompt
    assert "Do not convert the accents into jumping" in prompt
    assert "jumping" in prompt.split(NEGATIVE_MARKER, 1)[1]
    assert "missing male dancer" in prompt.split(NEGATIVE_MARKER, 1)[1]
    assert "missing choir" in prompt.split(NEGATIVE_MARKER, 1)[1]


def test_compact_plan_records_plan_level_budget_metadata():
    plan = {"results": [long_duet_item()]}

    compacted = compact_plan_prompts(plan, max_chars=5000, target_chars=4800)

    assert compacted["prompt_budget"]["status"] == "applied"
    assert compacted["prompt_budget"]["scene_count"] == 1
    assert compacted["prompt_budget"]["max_after_chars"] <= 4800
    assert compacted["prompt_budget"]["scene_description_preserved"] is True
    assert compacted["results"][0]["prompt_budget"]["policy"] == (
        "compact_after_ollama_vision_asmo_subject_lock_and_tap_sync"
    )
