import audio_analyze.ltx_prompt_budget as prompt_budget
from audio_analyze.ltx_gemma_prompt_synthesizer import (
    AUDIO_TIMING_MARKER,
    MOTION_MARKER,
    NEGATIVE_MARKER,
    SEED_IMAGE_DESCRIPTION_MARKER,
    SUBJECT_LOCK_MARKER,
    TAP_SYNC_MARKER,
    synthesize_final_ltx_prompt,
)


class FakeClient:
    def __init__(self, responses):
        from audio_analyze.local_ai_client import LocalAIConfig

        self.responses = list(responses)
        self.calls = []
        self.config = LocalAIConfig(model="gemma3:4b")

    def chat_text(self, system, user):
        self.calls.append({"system": system, "user": user})
        return self.responses.pop(0)


def _native_analysis():
    return (
        "Detailed visual analysis of two foreground performers in an ornate Gothic "
        "cathedral, including their appearance, wardrobe, pose, relationship, choir "
        "placement, stained-glass architecture, camera framing, depth, golden light, "
        "color contrast, floor texture, composition, atmosphere, and photographic style. "
        * 35
    )


def _item(native):
    return {
        "clip_index": 1,
        "seed_image_used": "seed/scene_01_cathedral_duet_choir.png",
        "seed_filename_used_for_prompt_hint": "scene_01_cathedral_duet_choir.png",
        "subject_count_policy": {
            "has_pair": True,
            "has_choir": True,
            "has_group": True,
            "multiple_subjects": True,
            "requirements": [
                "Preserve the female lead dancer, male dance partner, and choir."
            ],
        },
        "audio_timing": {
            "scene_index": 1,
            "start_seconds": 0.0,
            "end_seconds": 8.0,
            "tempo_bpm": 140.62,
        },
        "tap_sync": {
            "primary_sync_targets_relative_seconds": [
                index * 0.251 for index in range(30)
            ],
            "motion_profile": "localized_glute_pulse",
        },
        "tap_motion_profile": "localized_glute_pulse",
        "filename_hint_expansion": {
            "ltx_motion_prompt": (
                "Maintain continuous grounded paired movement. Use compact localized "
                "twerk pulses on clap, snare, and hi-hat accents."
            ),
            "negative_prompt": (
                "extra limbs, distorted anatomy, jumping, feet leaving the floor, "
                "missing male dancer, missing female dancer, missing choir"
            ),
        },
        "seed_image_analysis": {
            "status": "complete",
            "provider": "ollama",
            "model": "gemma3:4b",
            "analysis_mode": "freeform_native",
            "description": native,
            "prompt_context": native,
        },
        "prompt_text": "pre-synthesis prompt",
    }


def _valid_final_prompt(native):
    visual = (
        "Two foreground performers remain fully described inside the cathedral. "
        + native
    )[:4020]
    prompt = (
        f"{SUBJECT_LOCK_MARKER}\n"
        "Preserve the female lead dancer, male dance partner, and complete choir.\n\n"
        f"{SEED_IMAGE_DESCRIPTION_MARKER}\n{visual}\n\n"
        f"{AUDIO_TIMING_MARKER}\n"
        "Scene 1 spans 0.00-8.00 seconds at 140.62 BPM; synchronize movement and camera.\n\n"
        f"{TAP_SYNC_MARKER}\n"
        "Use all thirty clap, snare, and hi-hat targets. Begin motion immediately. "
        "Use a compact localized twerk pulse with glute-cheek contraction. "
        "Both feet remain planted. Do not convert the accents into jumping.\n\n"
        f"{MOTION_MARKER}\n"
        "Maintain continuous grounded paired movement and restrained choir support.\n\n"
        f"{NEGATIVE_MARKER}\n"
        "missing male dancer, missing female dancer, missing choir, jumping, extra limbs"
    )
    if len(prompt) < 4550:
        addition = " Preserve all visible lighting, framing, architecture, wardrobe, and spatial detail."
        prompt = prompt.replace(
            f"\n\n{AUDIO_TIMING_MARKER}",
            addition * ((4550 - len(prompt)) // len(addition) + 1)
            + f"\n\n{AUDIO_TIMING_MARKER}",
        )
    return prompt[:4980]


def test_gemma_synthesizes_full_native_analysis_into_final_ltx_prompt():
    native = _native_analysis()
    expected = _valid_final_prompt(native)
    client = FakeClient([expected])

    result = synthesize_final_ltx_prompt(
        _item(native),
        client=client,
        max_chars=5000,
    )

    assert result["status"] == "complete"
    assert result["final_prompt"] == expected
    assert result["final_prompt_char_count"] <= 5000
    assert result["final_prompt_char_count"] >= 4550
    assert result["seed_description_char_count"] >= 3600
    assert result["attempt_count"] == 1
    assert "native_image_analysis" in client.calls[0]["user"]
    assert native in client.calls[0]["user"]


def test_synthesis_retries_when_first_draft_is_too_short():
    native = _native_analysis()
    expected = _valid_final_prompt(native)
    client = FakeClient(
        [
            (
                f"{SUBJECT_LOCK_MARKER}\nshort\n"
                f"{SEED_IMAGE_DESCRIPTION_MARKER}\nshort\n"
                f"{AUDIO_TIMING_MARKER}\nshort\n"
                f"{TAP_SYNC_MARKER}\nshort\n"
                f"{MOTION_MARKER}\nshort\n"
                f"{NEGATIVE_MARKER}\nshort"
            ),
            expected,
        ]
    )

    result = synthesize_final_ltx_prompt(
        _item(native),
        client=client,
        max_chars=5000,
    )

    assert result["attempt_count"] == 2
    assert result["final_prompt"] == expected
    assert result["attempts"][0]["problems"]


def test_compact_item_uses_gemma_synthesis_as_exact_ltx_payload(monkeypatch):
    native = _native_analysis()
    expected = _valid_final_prompt(native)

    def fake_synthesis(item, **kwargs):
        return {
            "status": "complete",
            "provider": "ollama",
            "model": "gemma3:4b",
            "mode": "gemma_full_native_analysis_to_final_ltx_prompt",
            "source_native_analysis_chars": len(native),
            "final_prompt": expected,
            "final_prompt_char_count": len(expected),
            "seed_description_char_count": 3900,
            "hard_limit_chars": 5000,
            "target_min_chars": 4700,
            "target_max_chars": 4980,
            "attempt_count": 1,
            "attempts": [],
            "validation_passed": True,
            "required_markers": [
                SUBJECT_LOCK_MARKER,
                SEED_IMAGE_DESCRIPTION_MARKER,
                AUDIO_TIMING_MARKER,
                TAP_SYNC_MARKER,
                MOTION_MARKER,
                NEGATIVE_MARKER,
            ],
            "config": {},
        }

    monkeypatch.setattr(
        prompt_budget,
        "synthesize_final_ltx_prompt",
        fake_synthesis,
    )

    compacted = prompt_budget.compact_item_prompt(_item(native))

    assert compacted["prompt_text"] == expected
    assert compacted["exact_prompt_sent_to_ltx"] == expected
    assert compacted["prompt_text_is_exact_ltx_payload"] is True
    assert compacted["prompt_text_chars"] == len(expected)
    assert compacted["seed_image_analysis"]["description"] == native
    assert compacted["gemma_final_prompt_synthesis"]["final_prompt"] == expected
    assert compacted["prompt_budget"]["status"] == "gemma_synthesized"
    assert compacted["prompt_budget"]["seed_analysis_summary_model_used"] is True
