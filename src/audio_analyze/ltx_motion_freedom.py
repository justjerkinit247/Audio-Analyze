from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Sequence
import json


DEFAULT_LIVE_GUIDANCE_SCALE = 6.5
DEFAULT_MAX_PROMPTED_TAPS = 8


def _evenly_spaced_indices(length: int, limit: int) -> list[int]:
    if length <= 0 or limit <= 0:
        return []
    if length <= limit:
        return list(range(length))
    if limit == 1:
        return [0]

    raw = [round(index * (length - 1) / (limit - 1)) for index in range(limit)]
    indices: list[int] = []
    for value in raw:
        value = int(value)
        if value not in indices:
            indices.append(value)
    return indices


def select_evenly_spaced(values: Sequence[Any], limit: int) -> tuple[list[Any], list[int]]:
    items = list(values)
    indices = _evenly_spaced_indices(len(items), int(limit))
    return [items[index] for index in indices], indices


def _select_aligned(values: Sequence[Any] | None, indices: list[int]) -> list[Any]:
    items = list(values or [])
    return [items[index] for index in indices if index < len(items)]


def _format_targets(values: Sequence[Any]) -> str:
    return ", ".join(f"{float(value):.3f}s" for value in values)


def _subject_sentences(item: dict[str, Any]) -> tuple[str, str]:
    policy = item.get("subject_count_policy") or {}
    if policy.get("has_pair") and policy.get("has_choir"):
        return (
            "Preserve the woman, her male dance partner, the white-and-gold choir, their identities, costumes, cathedral setting, lighting, body layout, and framing from the seed image.",
            "The choir stays visible but secondary, adding only subtle sway after the lead pair is clearly moving.",
        )
    if policy.get("has_pair"):
        return (
            "Preserve both foreground dance partners, their identities, costumes, body layout, lighting, and framing from the seed image.",
            "Both partners remain visible together for the entire shot.",
        )
    if policy.get("has_group"):
        return (
            "Preserve every visible performer, identity, costume, body layout, lighting, and framing from the seed image.",
            "Background performers remain secondary to the main foreground action.",
        )
    return (
        "Preserve the main subject, identity, pose family, costume, lighting, background, and framing from the seed image.",
        "Background or environmental motion remains secondary to the main subject.",
    )


def build_motion_freedom_prompt(item: dict[str, Any]) -> str:
    tap_sync = item.get("tap_sync") or {}
    relative_targets = tap_sync.get("primary_sync_targets_relative_seconds") or []
    target_text = _format_targets(relative_targets) or "the strongest audible clap, snare, and hi-hat accents"
    subject_lock, background_rule = _subject_sentences(item)
    policy = item.get("subject_count_policy") or {}
    localized = item.get("tap_motion_profile") == "localized_glute_pulse"

    if localized:
        partner_motion = (
            "The male partner begins a restrained shoulder-and-chest groove beside her at the same moment. "
            if policy.get("has_pair")
            else ""
        )
        motion = (
            "From the first frame, the main foreground dancer is already moving: she maintains a small continuous pelvic groove and visibly departs the still seed pose immediately. "
            f"{partner_motion}"
            f"On the major tap accents at {target_text}, she adds one compact localized twerk pulse—a brief glute-cheek contraction, small backward pelvis pop, and controlled recoil—while continuing to move naturally between accents instead of waiting for the first one. "
            "Both feet remain planted, heels down, knees bent, and the low squat remains grounded, while natural breathing and small torso response keep the performance alive rather than rigid. "
            f"{background_rule} "
            "The camera is nearly locked with only a slow subtle push-in."
        )
        negatives = (
            "frozen foreground subjects, static lead pair, delayed foreground motion, background-only motion, "
            "moving choir hands while the lead pair remains frozen, jumping, hopping, standing up, repeated squats, "
            "whole-body bouncing, feet leaving the floor, missing partner, missing choir, changed subject count, camera orbit"
        )
    else:
        motion = (
            "From the first frame, the main foreground subject begins the core action immediately and continues with natural low-amplitude motion between major audio accents. "
            f"Use the major accents at {target_text} as emphasis points, not as a delayed start signal. "
            f"{background_rule} Keep the movement coherent, physically natural, and clearly readable throughout. "
            "The camera remains stable unless the filename direction explicitly requires movement."
        )
        negatives = (
            "frozen foreground subject, delayed motion onset, background-only motion, static opening, missing subject, "
            "changed subject count, duplicate subject, warped anatomy, chaotic camera movement"
        )

    return (
        "Audio-and-image-to-video continuation synchronized to the supplied audio.\n\n"
        f"[SUBJECT_LOCK]\n{subject_lock}\n\n"
        "[AUDIO_TIMING]\nUse the supplied audio as the timing source, but keep the core foreground action flowing naturally from the beginning to the end of the clip.\n\n"
        f"[TAP_SYNC]\n{motion}\n\n"
        "[MOTION_PROMPT]\nPrioritize natural continuous foreground performance over literal execution of every detected transient. Give the actors enough freedom to connect the emphasized accents with believable motion.\n\n"
        f"[NEGATIVE_PROMPT]\n{negatives}\n"
    )


def apply_motion_freedom_to_item(
    item: dict[str, Any],
    *,
    max_prompted_taps: int = DEFAULT_MAX_PROMPTED_TAPS,
) -> dict[str, Any]:
    patched = deepcopy(item)
    tap_sync = deepcopy(patched.get("tap_sync") or {})

    original_relative = list(tap_sync.get("primary_sync_targets_relative_seconds") or [])
    original_absolute = list(tap_sync.get("primary_sync_targets_seconds") or [])
    selected_relative, indices = select_evenly_spaced(original_relative, max_prompted_taps)

    tap_sync["all_detected_primary_sync_targets_relative_seconds"] = original_relative
    tap_sync["all_detected_primary_sync_targets_seconds"] = original_absolute
    tap_sync["primary_sync_targets_relative_seconds"] = selected_relative
    tap_sync["primary_sync_targets_seconds"] = _select_aligned(original_absolute, indices)
    tap_sync["tap_accent_times_seconds"] = _select_aligned(
        tap_sync.get("tap_accent_times_seconds"), indices
    )
    tap_sync["tap_accent_strengths"] = _select_aligned(
        tap_sync.get("tap_accent_strengths"), indices
    )
    tap_sync["tap_accent_high_frequency_ratios"] = _select_aligned(
        tap_sync.get("tap_accent_high_frequency_ratios"), indices
    )
    tap_sync["sync_density"] = len(selected_relative)
    tap_sync["prompt_target_policy"] = "eight_evenly_distributed_major_accents"
    patched["tap_sync"] = tap_sync

    original_prompt = str(patched.get("prompt_text") or "")
    prompt = build_motion_freedom_prompt(patched)
    patched["prompt_text_before_motion_freedom"] = original_prompt
    patched["prompt_text"] = prompt
    patched["motion_freedom_profile"] = {
        "status": "applied",
        "guidance_scale": DEFAULT_LIVE_GUIDANCE_SCALE,
        "original_prompt_chars": len(original_prompt),
        "api_prompt_chars": len(prompt),
        "detected_tap_count": len(original_relative),
        "prompted_tap_count": len(selected_relative),
        "selected_target_indices": indices,
        "prompt_style": "concise_continuous_motion_brief",
        "continuous_motion_priority": True,
        "first_tap_is_start_signal": False,
    }
    return patched


def apply_motion_freedom_to_plan(
    plan: dict[str, Any],
    *,
    max_prompted_taps: int = DEFAULT_MAX_PROMPTED_TAPS,
) -> dict[str, Any]:
    patched = deepcopy(plan)
    results = [
        apply_motion_freedom_to_item(item, max_prompted_taps=max_prompted_taps)
        for item in plan.get("results", []) or []
    ]
    patched["results"] = results
    patched["motion_freedom_profile"] = {
        "status": "applied",
        "scene_count": len(results),
        "guidance_scale": DEFAULT_LIVE_GUIDANCE_SCALE,
        "max_prompted_taps_per_scene": int(max_prompted_taps),
        "prompt_style": "concise_continuous_motion_brief",
    }
    return patched


def apply_motion_freedom_to_plan_file(
    plan_path: str | Path,
    *,
    max_prompted_taps: int = DEFAULT_MAX_PROMPTED_TAPS,
) -> dict[str, Any]:
    path = Path(plan_path).resolve()
    plan = json.loads(path.read_text(encoding="utf-8-sig"))
    patched = apply_motion_freedom_to_plan(
        plan,
        max_prompted_taps=max_prompted_taps,
    )
    path.write_text(json.dumps(patched, indent=2, ensure_ascii=False), encoding="utf-8")
    return patched
