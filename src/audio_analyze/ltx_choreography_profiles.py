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

WATER_CONTEXT_TOKENS = {
    "water",
    "river",
    "lake",
    "ocean",
    "sea",
    "pool",
    "splash",
    "splashes",
    "splashing",
    "submerged",
    "immersed",
    "wade",
    "wading",
    "shallows",
    "shore",
    "shoreline",
    "wet",
}

WATER_DYNAMIC_VARIANT = "water_dynamic"
GROUND_CONTACT_VARIANT = "ground_contact"

_GROUND_CONTACT_NEGATIVE_TERMS = {
    "jumping",
    "hopping",
    "feet leaving the floor",
    "heels lifting",
    "standing up",
    "large vertical displacement",
}

_WATER_PROMPT_TEMPLATE = (
    "[TAP_SYNC]\n"
    "Primary tap-accent times inside this clip: {target_text}. Visible dance motion begins "
    "immediately at 0.00 seconds and continues throughout the entire clip; never hold the "
    "seed image as a static opening. At every listed clap, snare, hi-hat, or sharp tap "
    "accent, perform one compact localized twerk pulse: a brief glute-cheek contraction, "
    "a small backward pelvis pop, and a controlled recoil. Use the seed image's actual "
    "support and body contact as authoritative. If feet or heels are submerged, cropped, "
    "airborne, or not clearly visible, do not invent planted-foot or heel-down constraints. "
    "Preserve the existing pose and contact family while allowing natural water displacement, "
    "splash, wading, landing, or buoyant motion already supported by the visible scene. Keep "
    "the accent localized to the glutes and pelvis as much as physically natural without "
    "forcing repeated squats, artificial whole-body bouncing, or repeated vertical pumping. "
    "Between listed accents, maintain subtle continuous pelvic micro-motion and controlled hip "
    "sway so the image never freezes while waiting for the next tap. Do not use kick-drum or "
    "bass-only boom hits as major movement triggers. A prop may be animated only when the "
    "seed-image description confirms it is visibly present; otherwise ignore prop-like "
    "filename cue wording. This TAP_SYNC instruction overrides generic grounded-foot, jumping, "
    "bouncing, kick-driven, full-body, vertical, or unsupported-prop wording elsewhere in the prompt.\n"
)


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", str(value or "").lower()))


def _scene_direction(item: dict[str, Any]) -> str:
    expansion = item.get("filename_hint_expansion") or {}
    assignment = item.get("seed_assignment") or {}
    seed_analysis = item.get("seed_image_analysis") or {}
    return " ".join(
        str(value or "")
        for value in (
            expansion.get("scene_hint"),
            item.get("seed_filename_prompt_hint"),
            assignment.get("filename_prompt_hint"),
            item.get("seed_filename_used_for_prompt_hint"),
            item.get("seed_image_used"),
            seed_analysis.get("description"),
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


def _apply_context_variant(
    item: dict[str, Any],
    selected_id: str,
    selected: dict[str, Any],
) -> tuple[dict[str, Any], str, list[str]]:
    scene_tokens = _tokens(_scene_direction(item))
    water_matches = sorted(scene_tokens & WATER_CONTEXT_TOKENS)

    if selected_id != "localized_glute_pulse" or not water_matches:
        selected["context_variant"] = GROUND_CONTACT_VARIANT
        return selected, GROUND_CONTACT_VARIANT, []

    selected["context_variant"] = WATER_DYNAMIC_VARIANT
    selected["description"] = (
        f"{selected.get('description', '')} Context-adapted for water, submerged, wading, "
        "splashing, or otherwise uncertain foot-contact scenes."
    ).strip()
    selected["prompt_template"] = _WATER_PROMPT_TEMPLATE
    selected["negative_terms"] = [
        term
        for term in list(selected.get("negative_terms") or [])
        if str(term).strip().lower() not in _GROUND_CONTACT_NEGATIVE_TERMS
    ]
    selected["required_prompt_phrases"] = [
        "compact localized twerk pulse",
        "do not invent planted-foot or heel-down constraints",
        "seed-image description confirms it is visibly present",
    ]

    manifest = deepcopy(selected.get("manifest") or {})
    manifest["dance_direction_change_rule"] = (
        "Each listed tap triggers a compact localized glute/pelvis pulse while preserving "
        "the seed image's actual support/contact state; water, submerged, cropped, airborne, "
        "or landing poses must not be forced into planted-feet constraints."
    )
    manifest["negative_motion_rules"] = [
        rule
        for rule in list(manifest.get("negative_motion_rules") or [])
        if not any(
            phrase in str(rule).lower()
            for phrase in (
                "jumping or hopping",
                "feet leaving the floor",
                "standing up",
            )
        )
    ]
    manifest["negative_motion_rules"].extend(
        [
            "no invented ground contact when feet or heels are not visibly grounded",
            "no unsupported props from filename-only cue words",
            "no repeated artificial whole-body vertical pumping",
        ]
    )
    selected["manifest"] = manifest
    return selected, WATER_DYNAMIC_VARIANT, water_matches


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
    selected, context_variant, context_tokens = _apply_context_variant(
        item,
        selected_id,
        selected,
    )
    return {
        "profile_id": selected_id,
        "requested_profile": requested,
        "selection_method": selection_method,
        "matched_tokens": matched_tokens,
        "context_variant": context_variant,
        "context_tokens": context_tokens,
        "target_selection": deepcopy(selected.get("target_selection") or {}),
        "required_prompt_phrases": list(selected.get("required_prompt_phrases") or []),
        "negative_terms": list(selected.get("negative_terms") or []),
        "manifest": deepcopy(selected.get("manifest") or {}),
        "description": selected.get("description"),
        "prompt_template": selected.get("prompt_template"),
        "config_version": data.get("version"),
    }


def target_limit_for_policy(policy: dict[str,Any]) -> int | None:
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
