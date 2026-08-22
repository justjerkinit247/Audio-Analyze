from audio_analyze.ltx_choreography_profiles import (
    AUTO_PROFILE,
    render_tap_sync_prompt,
    resolve_choreography_profile,
)
from audio_analyze.ltx_gemma_prompt_synthesizer import _motion, _negative, _tap_sync


def _water_item() -> dict:
    return {
        "seed_filename_used_for_prompt_hint": "scene_01_praise_twerk_water_slap_violin_hit.png",
        "filename_hint_expansion": {
            "filename": "scene_01_praise_twerk_water_slap_violin_hit.png",
            "scene_hint": "praise twerk water slap violin hit",
            "ltx_motion_prompt": (
                "A young woman performs a joyous twerk, splashing water with energetic "
                "movements, while simultaneously striking a violin with rhythmic precision. "
                "The camera orbits her slowly as water droplets shimmer in the light. "
                "The violin's notes cascade and swell with the movement."
            ),
            "negative_prompt": (
                "frozen foreground subjects, jumping, hopping, feet leaving the floor, "
                "heels lifting, standing up, large vertical displacement, distorted anatomy"
            ),
        },
        "seed_image_analysis": {
            "description": (
                "A woman is immersed in turquoise water with a large dynamic splash. "
                "Her arms are outstretched and her feet are submerged and not clearly visible. "
                "No handheld object is visible."
            )
        },
        "asmo_motion_prompt_block": (
            "TIMED ASMO MOTION DIRECTIVES: - +1.000s: maintain rhythmic full-body groove "
            "synchronized to beat; camera=steady_tracking; lyric='test'"
        ),
        "tap_sync": {"primary_sync_targets_relative_seconds": [0.405, 1.226]},
        "tap_motion_profile": "localized_glute_pulse",
        "subject_count_policy": {},
    }


def test_water_scene_uses_water_dynamic_glute_variant():
    item = _water_item()
    policy = resolve_choreography_profile(item, requested_profile=AUTO_PROFILE)

    assert policy["profile_id"] == "localized_glute_pulse"
    assert policy["context_variant"] == "water_dynamic"
    prompt = render_tap_sync_prompt(policy, "0.405s, 1.226s")
    assert "do not invent planted-foot or heel-down constraints" in prompt
    assert "Both feet remain planted" not in prompt
    negatives = {str(value).lower() for value in policy["negative_terms"]}
    assert "jumping" not in negatives
    assert "feet leaving the floor" not in negatives


def test_dry_scene_preserves_ground_contact_variant():
    item = {
        "filename_hint_expansion": {"scene_hint": "praise twerk hip pulse"},
        "seed_image_analysis": {
            "description": (
                "A woman stands on a dry cathedral floor with both shoes fully visible "
                "and stable contact with the floor."
            )
        },
    }
    policy = resolve_choreography_profile(item, requested_profile=AUTO_PROFILE)

    assert policy["profile_id"] == "localized_glute_pulse"
    assert policy["context_variant"] == "ground_contact"
    prompt = render_tap_sync_prompt(policy, "0.500s")
    assert "Both feet remain planted" in prompt
    assert "jumping" in {str(value).lower() for value in policy["negative_terms"]}


def test_gemma_motion_removes_filename_only_violin_and_keeps_asmo():
    item = _water_item()
    item["choreography_policy"] = resolve_choreography_profile(
        item, requested_profile=AUTO_PROFILE
    )

    motion = _motion(item)
    negative = _negative(item)

    assert "violin" not in motion.lower()
    assert "TIMED ASMO MOTION DIRECTIVES:" in motion
    assert "+1.000s" in motion
    assert "invented violin" in negative.lower()


def test_gemma_motion_keeps_visually_confirmed_violin():
    item = _water_item()
    item["seed_image_analysis"]["description"] += (
        " She visibly holds a violin against her shoulder."
    )
    item["choreography_policy"] = resolve_choreography_profile(
        item, requested_profile=AUTO_PROFILE
    )

    assert "violin" in _motion(item).lower()
    assert "invented violin" not in _negative(item).lower()


def test_gemma_water_tap_sync_does_not_reintroduce_ground_constraints():
    item = _water_item()
    policy = resolve_choreography_profile(item, requested_profile=AUTO_PROFILE)
    item["choreography_policy"] = policy

    tap = _tap_sync(item)
    lowered = tap.lower()
    assert "feet remain planted" not in lowered
    assert "heels down" not in lowered
    assert "do not invent planted-foot or heel-down constraints" in lowered
    assert "natural splash, wading, landing, or buoyant motion" in lowered
    assert "seed-image description confirms it is visibly present" in lowered

    negative = _negative(item).lower()
    assert "jumping" not in {part.strip() for part in negative.split(",")}
    assert "feet leaving the floor" not in negative


def test_water_required_phrases_match_final_python_owned_tap_section():
    item = _water_item()
    policy = resolve_choreography_profile(item, requested_profile=AUTO_PROFILE)
    item["choreography_policy"] = policy
    tap = _tap_sync(item)

    for phrase in policy["required_prompt_phrases"]:
        assert phrase in tap
