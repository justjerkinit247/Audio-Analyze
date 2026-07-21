from audio_analyze.ltx_prompt_budget import (
    SEED_IMAGE_DESCRIPTION_MARKER,
    compact_item_prompt,
)


def _native_analysis():
    visual_sentence = (
        "The two foreground performers remain clearly visible inside a vast Gothic cathedral, "
        "with warm stained-glass shafts, layered choir figures, gold wardrobe highlights, "
        "deep architectural perspective, textured floor reflections, and dramatic framing. "
    )
    return (
        "Okay, here is my complete analysis for the project.\n\n"
        "**Overall Impression:**\n\n"
        + visual_sentence * 22
        + "\n\n**Composition & Lighting:**\n\n"
        + visual_sentence * 3
        + "\n\n**Overall Tone & Potential Narrative:**\n\n"
        + "This could symbolize several abstract themes that are not current-frame facts. " * 5
        + "\n\n**Recommendations for Video Orchestration:**\n\n"
        + "Use quick cuts and a fast tempo. " * 20
        + "\n\nThat is my full analysis. Let me know if you want more."
    )


def _item(native):
    negative = (
        "extra limbs, distorted anatomy, jumping, feet leaving the floor, missing male dancer, "
        "missing female dancer, missing choir, changed subject count, warped background, flicker"
    )
    return {
        "clip_index": 1,
        "seed_image_used": "seed/scene_01_cathedral_duet_choir.png",
        "seed_filename_used_for_prompt_hint": "scene_01_cathedral_duet_choir.png",
        "subject_count_policy": {
            "has_pair": True,
            "has_choir": True,
            "has_group": True,
            "multiple_subjects": True,
        },
        "audio_timing": {
            "scene_index": 1,
            "start_seconds": 0.0,
            "end_seconds": 8.0,
            "tempo_bpm": 140.62,
        },
        "tap_sync": {
            "primary_sync_targets_relative_seconds": [index * 0.321 for index in range(25)],
            "motion_profile": "localized_glute_pulse",
        },
        "tap_motion_profile": "localized_glute_pulse",
        "filename_hint_expansion": {
            "ltx_motion_prompt": "Maintain continuous grounded paired motion and stable camera movement.",
            "negative_prompt": negative,
        },
        "seed_image_analysis": {
            "status": "complete",
            "description": native,
            "prompt_context": native,
        },
        "prompt_text": (
            "[SUBJECT_LOCK]\nold\n\n"
            f"{SEED_IMAGE_DESCRIPTION_MARKER}\n{native}\n\n"
            "[AUDIO_TIMING]\nold\n\n"
            "[MOTION_PROMPT]\nold\n\n"
            f"[NEGATIVE_PROMPT]\n{negative}\n"
        ),
    }


def test_prompt_budget_protects_gemma_marker_and_retains_visual_core():
    native = _native_analysis()
    compacted = compact_item_prompt(_item(native))
    prompt = compacted["prompt_text"]
    budget = compacted["prompt_budget"]

    assert len(prompt) <= 5000
    assert SEED_IMAGE_DESCRIPTION_MARKER in prompt
    assert compacted["seed_image_analysis"]["description"] == native
    assert budget["seed_analysis_summary_model_used"] is False
    assert budget["seed_analysis_retention_target_met"] is True
    assert budget["seed_analysis_visual_retention_ratio"] >= 0.90
    assert budget["seed_analysis_prompt_chars"] > 3000
    assert "Recommendations for Video Orchestration" not in prompt
    assert "Overall Tone & Potential Narrative" not in prompt
    assert "compact localized twerk pulse" in prompt
    assert "Both feet remain planted" in prompt
