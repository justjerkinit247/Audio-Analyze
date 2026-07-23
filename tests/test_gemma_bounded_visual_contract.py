from audio_analyze.local_ai_client import LocalAIConfig
from audio_analyze.ltx_gemma_prompt_synthesizer import (
    AUDIO_TIMING_MARKER,
    SEED_IMAGE_DESCRIPTION_MARKER,
    synthesize_final_ltx_prompt,
)


class FakeClient:
    def __init__(self, response: str):
        self.response = response
        self.calls = []
        self.config = LocalAIConfig(model="gemma3:4b")

    def chat_text(self, system: str, user: str) -> str:
        self.calls.append({"system": system, "user": user})
        return self.response


def _item() -> dict:
    native = (
        "A detailed native visual analysis of two foreground performers in a grand "
        "Gothic cathedral with a complete choir, stained glass, golden light, deep "
        "perspective, reflective floor tiles, formal and shimmering wardrobe, dynamic "
        "pose relationships, cinematic framing, rich contrast, texture, atmosphere, "
        "and photographic style. "
        * 18
    )
    return {
        "clip_index": 1,
        "seed_image_used": "seed/scene_01_cathedral_duet_choir.png",
        "subject_count_policy": {
            "has_pair": True,
            "has_choir": True,
            "has_group": True,
            "multiple_subjects": True,
            "negative_terms": [
                "missing male dancer",
                "missing female dancer",
                "missing choir",
            ],
        },
        "audio_timing": {
            "scene_index": 1,
            "start_seconds": 0.0,
            "end_seconds": 8.0,
            "duration_seconds": 8.0,
            "tempo_bpm": 140.62,
            "beat_alignment_enabled": True,
        },
        "tap_sync": {
            "primary_sync_targets_relative_seconds": [0.25, 0.50, 0.75],
            "motion_profile": "localized_glute_pulse",
        },
        "tap_motion_profile": "localized_glute_pulse",
        "filename_hint_expansion": {
            "ltx_motion_prompt": "Maintain grounded paired movement and subtle choir support.",
            "negative_prompt": "extra limbs, jumping, missing choir",
        },
        "seed_image_analysis": {
            "status": "complete",
            "provider": "ollama",
            "model": "gemma3:4b",
            "analysis_mode": "freeform_native",
            "description": native,
        },
        "prompt_text": "before synthesis",
    }


def test_short_under_budget_description_is_accepted_unchanged():
    visual = (
        "Two foreground performers remain together inside the vast cathedral while the "
        "white-robed choir stays layered behind them. Golden stained-glass light shapes "
        "the deep architectural perspective, shimmering wardrobe, reflective floor, and "
        "cinematic composition."
    )
    result = synthesize_final_ltx_prompt(
        _item(),
        client=FakeClient(visual),
        max_attempts=1,
    )

    assert result["seed_description"] == visual
    assert result["description_modified_after_generation"] is False
    assert result["final_prompt_char_count"] <= 5000
    assert result["final_prompt"].count(SEED_IMAGE_DESCRIPTION_MARKER) == 1


def test_single_echoed_visual_marker_is_not_duplicated_or_removed():
    visual = (
        f"{SEED_IMAGE_DESCRIPTION_MARKER}\n"
        "Two foreground performers remain together inside the cathedral, with the choir "
        "visible behind them under dramatic golden stained-glass illumination."
    )
    result = synthesize_final_ltx_prompt(
        _item(),
        client=FakeClient(visual),
        max_attempts=1,
    )

    assert result["seed_description"] == visual
    assert result["final_prompt"].count(SEED_IMAGE_DESCRIPTION_MARKER) == 1
    assert result["final_prompt"].index(SEED_IMAGE_DESCRIPTION_MARKER) < result[
        "final_prompt"
    ].index(AUDIO_TIMING_MARKER)
