import pytest

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
        (
            "Detailed visual analysis of two foreground performers in an ornate Gothic "
            "cathedral, including their appearance, wardrobe, pose, relationship, choir "
            "placement, stained-glass architecture, camera framing, depth, golden light, "
            "color contrast, floor texture, composition, atmosphere, and photographic style. "
        )
        * 35
    ).strip()


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
                "Preserve every visible person from the seed image.",
                "Keep both visible foreground subjects together throughout.",
                "Keep the existing choir visible in the background.",
            ],
            "negative_terms": [
                "missing foreground partner",
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
                "missing foreground partner, missing choir"
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


def _bounded_visual(limit):
    sentence = (
        "Two foreground performers remain visible in the grand Gothic cathedral, with "
        "detailed wardrobe, grounded pose, layered choir placement, stained-glass "
        "architecture, golden volumetric light, deep perspective, reflective flooring, "
        "balanced framing, rich color contrast, texture, atmosphere, and cinematic style. "
    )
    minimum = max(2200, int(limit * 0.70))
    return (sentence * ((minimum // len(sentence)) + 2))[:minimum]


def _valid_authoritative_final_prompt(native):
    visual = (
        "Two foreground performers remain fully described inside the cathedral. "
        + native
    )[:3800]
    prompt = (
        f"{SUBJECT_LOCK_MARKER}\n"
        "Preserve every visible subject, both foreground partners, and the complete choir.\n\n"
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
        "missing foreground partner, missing choir, jumping, extra limbs"
    )
    return prompt[:4980]


def test_gemma_receives_exact_description_budget_before_generation():
    native = _native_analysis()
    probe = FakeClient([""])

    try:
        synthesize_final_ltx_prompt(_item(native), client=probe, max_attempts=1)
    except ValueError:
        pass

    assert len(probe.calls) == 1
    system = probe.calls[0]["system"]
    user = probe.calls[0]["user"]
    match = __import__("re").search(r"HARD CHARACTER LIMIT: (\d+)", system)
    assert match
    exact_limit = int(match.group(1))
    assert exact_limit > 1000
    assert f"HARD MAXIMUM BEFORE YOU BEGIN: {exact_limit}" in user
    assert native in user


def test_bounded_gemma_description_is_inserted_verbatim():
    native = _native_analysis()
    probe = FakeClient([""])
    try:
        synthesize_final_ltx_prompt(_item(native), client=probe, max_attempts=1)
    except ValueError:
        pass
    exact_limit = int(
        __import__("re").search(
            r"HARD CHARACTER LIMIT: (\d+)", probe.calls[0]["system"]
        ).group(1)
    )

    visual = _bounded_visual(exact_limit)
    client = FakeClient([visual])
    result = synthesize_final_ltx_prompt(_item(native), client=client, max_chars=5000)

    assert result["status"] == "complete"
    assert result["mode"] == "gemma_bounded_visual_description_python_envelope"
    assert result["seed_description"] == visual
    assert result["seed_description_char_count"] == len(visual)
    assert result["description_char_limit_given_before_generation"] == exact_limit
    assert result["description_modified_after_generation"] is False
    assert result["final_prompt_char_count"] <= 5000
    assert result["final_prompt"].startswith(SUBJECT_LOCK_MARKER)
    assert f"{SEED_IMAGE_DESCRIPTION_MARKER}\n{visual}\n\n{AUDIO_TIMING_MARKER}" in result[
        "final_prompt"
    ]
    for marker in (
        SUBJECT_LOCK_MARKER,
        SEED_IMAGE_DESCRIPTION_MARKER,
        AUDIO_TIMING_MARKER,
        TAP_SYNC_MARKER,
        MOTION_MARKER,
        NEGATIVE_MARKER,
    ):
        assert result["final_prompt"].count(marker) == 1


def test_over_limit_visual_response_retries_with_same_predeclared_limit():
    native = _native_analysis()
    probe = FakeClient([""])
    try:
        synthesize_final_ltx_prompt(_item(native), client=probe, max_attempts=1)
    except ValueError:
        pass
    exact_limit = int(
        __import__("re").search(
            r"HARD CHARACTER LIMIT: (\d+)", probe.calls[0]["system"]
        ).group(1)
    )
    valid = _bounded_visual(exact_limit)
    client = FakeClient(["x" * (exact_limit + 100), valid])

    result = synthesize_final_ltx_prompt(_item(native), client=client, max_attempts=2)

    assert result["attempt_count"] == 2
    assert result["seed_description"] == valid
    assert result["attempts"][0]["description_char_limit_given_before_generation"] == exact_limit
    assert f"no more than {exact_limit} characters" in client.calls[1]["user"]


def test_full_prompt_response_is_rejected_instead_of_accepted_as_legacy():
    native = _native_analysis()
    full_prompt = _valid_authoritative_final_prompt(native)
    client = FakeClient([full_prompt])

    with pytest.raises(ValueError, match="forbidden control marker"):
        synthesize_final_ltx_prompt(
            _item(native),
            client=client,
            max_chars=5000,
            max_attempts=1,
        )


def test_compact_item_uses_gemma_synthesis_as_exact_ltx_payload(monkeypatch):
    native = _native_analysis()
    expected = _valid_authoritative_final_prompt(native)
    visual = "Detailed synthesized visual description. " * 100

    def fake_synthesis(item, **kwargs):
        return {
            "status": "complete",
            "provider": "ollama",
            "model": "gemma3:4b",
            "mode": "gemma_bounded_visual_description_python_envelope",
            "source_native_analysis_chars": len(native),
            "final_prompt": expected,
            "final_prompt_char_count": len(expected),
            "seed_description": visual,
            "seed_description_char_count": len(visual),
            "description_char_limit_given_before_generation": len(visual) + 200,
            "description_modified_after_generation": False,
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
    assert compacted["gemma_final_prompt_synthesis"]["seed_description"] == visual
    assert compacted["prompt_budget"]["status"] == "gemma_synthesized"
    assert compacted["prompt_budget"]["seed_analysis_summary_model_used"] is True
