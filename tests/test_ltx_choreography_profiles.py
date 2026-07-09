import pytest

from audio_analyze.ltx_choreography_profiles import (
    AUTO_PROFILE,
    PROFILE_ENV_VAR,
    available_profile_ids,
    normalize_requested_profile,
    resolve_choreography_profile,
    target_limit_for_policy,
)


def test_profile_config_exposes_generic_and_specialized_policies():
    profiles = available_profile_ids()

    assert "generic_tap_action" in profiles
    assert "localized_glute_pulse" in profiles


def test_auto_profile_uses_generic_fallback_for_unrelated_scene(monkeypatch):
    monkeypatch.delenv(PROFILE_ENV_VAR, raising=False)

    policy = resolve_choreography_profile(
        {"seed_filename_prompt_hint": "bird glides over ocean clouds"},
        requested_profile=AUTO_PROFILE,
    )

    assert policy["profile_id"] == "generic_tap_action"
    assert policy["selection_method"] == "default_fallback"
    assert target_limit_for_policy(policy) is None


def test_auto_profile_selects_localized_policy_from_seed_direction(monkeypatch):
    monkeypatch.delenv(PROFILE_ENV_VAR, raising=False)

    policy = resolve_choreography_profile(
        {"seed_filename_prompt_hint": "deep squat hip glute twerk pulse"},
        requested_profile=AUTO_PROFILE,
    )

    assert policy["profile_id"] == "localized_glute_pulse"
    assert policy["selection_method"] == "auto_seed_direction"
    assert "twerk" in policy["matched_tokens"]
    assert target_limit_for_policy(policy) is None


def test_explicit_per_run_profile_overrides_auto_detection(monkeypatch):
    monkeypatch.delenv(PROFILE_ENV_VAR, raising=False)

    policy = resolve_choreography_profile(
        {"seed_filename_prompt_hint": "deep squat hip glute twerk pulse"},
        requested_profile="generic_tap_action",
    )

    assert policy["profile_id"] == "generic_tap_action"
    assert policy["selection_method"] == "explicit_per_run"


def test_environment_variable_is_a_scoped_per_run_override(monkeypatch):
    monkeypatch.setenv(PROFILE_ENV_VAR, "localized_glute_pulse")

    assert normalize_requested_profile(AUTO_PROFILE) == "localized_glute_pulse"
    policy = resolve_choreography_profile(
        {"seed_filename_prompt_hint": "bird glides over ocean clouds"},
        requested_profile=AUTO_PROFILE,
    )
    assert policy["profile_id"] == "localized_glute_pulse"
    assert policy["selection_method"] == "explicit_per_run"


def test_unknown_profile_is_rejected(monkeypatch):
    monkeypatch.delenv(PROFILE_ENV_VAR, raising=False)

    with pytest.raises(ValueError, match="Unknown choreography profile"):
        normalize_requested_profile("not-a-real-profile")
