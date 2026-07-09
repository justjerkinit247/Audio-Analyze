from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any
import json
import os
import re


AUTO_PROFILE = "auto"
PROFILE_ENV_VAR = "LTX_CHOREOGRAPHY_PROFILE"
DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "ltx_choreography_profiles.json"
)


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", str(value or "").lower()))


def _scene_direction(item: dict[str, Any]) -> str:
    expansion = item.get("filename_hint_expansion") or {}
    assignment = item.get("seed_assignment") or {}
    return " ".join(
        str(value or "")
        for value in (
            expansion.get("scene_hint"),
            item.get("seed_filename_prompt_hint"),
            assignment.get("filename_prompt_hint"),
            item.get("seed_filename_used_for_prompt_hint"),
            item.get("seed_image_used"),
        )
    )


def _validate_profile(profile_id: str, profile: dict[str, Any]) -> None:
    required = (
        "description",
        "activation",
        "target_selection",
        "prompt_template",
        "negative_terms",
        "required_prompt_phrases",
        "manifest",
    )
    missing = [name for name in required if name not in profile]
    if missing:
        raise ValueError(
            f"Choreography profile {profile_id!r} is missing: {', '.join(missing)}"
        )
    if "{target_text}" not in str(profile.get("prompt_template") or ""):
        raise ValueError(
            f"Choreography profile {profile_id!r} prompt_template must contain {{target_text}}."
        )


def _read_config(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    profiles = data.get("profiles") or {}
    default_profile = str(data.get("default_profile") or "").strip()
    if not profiles:
        raise ValueError("Choreography profile config contains no profiles.")
    if default_profile not in profiles:
        raise ValueError("Choreography profile config has an invalid default_profile.")
    for profile_id, profile in profiles.items():
        _validate_profile(str(profile_id), dict(profile or {}))
    return data


@lru_cache(maxsize=4)
def load_profile_config(config_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(config_path).resolve() if config_path else DEFAULT_CONFIG_PATH
    if not path.is_file():
        raise FileNotFoundError(f"Choreography profile config not found: {path}")
    return _read_config(path)


def available_profile_ids(config_path: str | Path | None = None) -> tuple[str, ...]:
    data = load_profile_config(config_path)
    return tuple(sorted(str(profile_id) for profile_id in data["profiles"]))


def normalize_requested_profile(
    requested: str | None,
    *,
    config_path: str | Path | None = None,
) -> str:
    value = str(requested or AUTO_PROFILE).strip().lower() or AUTO_PROFILE
    environment_override = os.environ.get(PROFILE_ENV_VAR, "").strip().lower()
    if value == AUTO_PROFILE and environment_override:
        value = environment_override

    valid = set(available_profile_ids(config_path)) | {AUTO_PROFILE}
    if value not in valid:
        raise ValueError(
            f"Unknown choreography profile {value!r}. Available: {', '.join(sorted(valid))}"
        )
    return value


def _activation_matches(profile: dict[str, Any], scene_tokens: set[str]) -> tuple[bool, list[str]]:
    activation = profile.get("activation") or {}
    mode = str(activation.get("mode") or "default")
    if mode == "default":
        return False, []

    any_tokens = {str(value).lower() for value in activation.get("any_tokens") or []}
    any_matches = sorted(scene_tokens & any_tokens)
    groups = [
        {str(value).lower() for value in group}
        for group in activation.get("all_token_groups") or []
    ]
    group_matches = [sorted(scene_tokens & group) for group in groups]
    all_groups_match = bool(groups) and all(bool(match) for match in group_matches)

    if mode == "any_token":
        matched = bool(any_matches)
    elif mode == "all_groups":
        matched = all_groups_match
    elif mode == "any_token_or_all_groups":
        matched = bool(any_matches) or all_groups_match
    else:
        raise ValueError(f"Unsupported choreography activation mode: {mode}")

    flattened = list(any_matches)
    for match in group_matches:
        flattened.extend(match)
    return matched, sorted(set(flattened))


def resolve_choreography_profile(
    item: dict[str, Any],
    *,
    requested_profile: str | None = AUTO_PROFILE,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    data = load_profile_config(config_path)
    profiles = data["profiles"]
    requested = normalize_requested_profile(requested_profile, config_path=config_path)

    if requested != AUTO_PROFILE:
        selected_id = requested
        selection_method = "explicit_per_run"
        matched_tokens: list[str] = []
    else:
        scene_tokens = _tokens(_scene_direction(item))
        candidates: list[tuple[int, str, list[str]]] = []
        for profile_id, raw_profile in profiles.items():
            profile = dict(raw_profile or {})
            matched, tokens = _activation_matches(profile, scene_tokens)
            if matched:
                candidates.append((int(profile.get("priority", 0)), str(profile_id), tokens))
        if candidates:
            _, selected_id, matched_tokens = sorted(candidates, reverse=True)[0]
            selection_method = "auto_seed_direction"
        else:
            selected_id = str(data["default_profile"])
            matched_tokens = []
            selection_method = "default_fallback"

    selected = deepcopy(dict(profiles[selected_id]))
    return {
        "profile_id": selected_id,
        "requested_profile": requested,
        "selection_method": selection_method,
        "matched_tokens": matched_tokens,
        "target_selection": deepcopy(selected.get("target_selection") or {}),
        "required_prompt_phrases": list(selected.get("required_prompt_phrases") or []),
        "negative_terms": list(selected.get("negative_terms") or []),
        "manifest": deepcopy(selected.get("manifest") or {}),
        "description": selected.get("description"),
        "prompt_template": selected.get("prompt_template"),
        "config_version": data.get("version"),
    }


def target_limit_for_policy(policy: dict[str, Any]) -> int | None:
    selection = policy.get("target_selection") or {}
    mode = str(selection.get("mode") or "all_reliable")
    if mode == "all_reliable":
        return None
    if mode == "strongest_limited":
        value = int(selection.get("max_targets") or 0)
        if value <= 0:
            raise ValueError("strongest_limited choreography policy requires max_targets > 0")
        return value
    raise ValueError(f"Unsupported choreography target-selection mode: {mode}")


def render_tap_sync_prompt(policy: dict[str, Any], target_text: str) -> str:
    template = str(policy.get("prompt_template") or "")
    return template.format(target_text=target_text)
