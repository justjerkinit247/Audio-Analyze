from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Callable
import re

import librosa
import numpy as np

try:
    from .path_policy import resolve_runtime_path, serialize_path
    from .ltx_prompt_budget import compact_plan_prompts
    from .ltx_choreography_profiles import (
        AUTO_PROFILE,
        render_tap_sync_prompt,
        resolve_choreography_profile,
        target_limit_for_policy,
    )
except ImportError:
    from path_policy import resolve_runtime_path, serialize_path
    from ltx_prompt_budget import compact_plan_prompts
    from ltx_choreography_profiles import (
        AUTO_PROFILE,
        render_tap_sync_prompt,
        resolve_choreography_profile,
        target_limit_for_policy,
    )


TAP_SYNC_MARKER = "[TAP_SYNC]"
MOTION_MARKER = "[MOTION_PROMPT]"
NEGATIVE_MARKER = "[NEGATIVE_PROMPT]"
DEFAULT_HIGH_BAND_HZ = 1200.0
DEFAULT_MIN_HIGH_RATIO = 0.22
DEFAULT_MIN_SPACING_SECONDS = 0.08


def _scalar(value: Any) -> float:
    array = np.asarray(value)
    if array.size == 0:
        return 0.0
    return float(array.reshape(-1)[0])


def _scene_hint_for_item(item: dict[str, Any]) -> str:
    expansion = item.get("filename_hint_expansion") or {}
    assignment = item.get("seed_assignment") or {}
    return str(
        expansion.get("scene_hint")
        or item.get("seed_filename_prompt_hint")
        or assignment.get("filename_prompt_hint")
        or item.get("seed_image_used")
        or ""
    )


def is_localized_glute_scene(scene_hint: str) -> bool:
    """Backward-compatible helper backed by the structured policy resolver."""
    policy = resolve_choreography_profile(
        {"seed_filename_prompt_hint": scene_hint},
        requested_profile=AUTO_PROFILE,
    )
    return policy.get("profile_id") == "localized_glute_pulse"


def merge_negative_prompt_terms(prompt_text: str, extra_terms: list[str]) -> str:
    prompt_text = str(prompt_text or "")
    if NEGATIVE_MARKER not in prompt_text:
        return prompt_text

    before, current_negative = prompt_text.split(NEGATIVE_MARKER, 1)
    existing = [
        term.strip()
        for term in current_negative.replace("\n", " ").split(",")
        if term.strip()
    ]
    merged: list[str] = []
    seen: set[str] = set()
    for term in existing + list(extra_terms):
        cleaned = re.sub(r"\s+", " ", str(term or "")).strip().strip(",")
        key = cleaned.lower()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        merged.append(cleaned)
    return f"{before.rstrip()}\n\n{NEGATIVE_MARKER}\n{', '.join(merged)}\n"


def select_tap_accent_targets(
    candidates: list[dict[str, Any]],
    *,
    limit: int | None = None,
    min_spacing_seconds: float = DEFAULT_MIN_SPACING_SECONDS,
) -> list[dict[str, Any]]:
    """Select reliable sharp tap accents and return them in time order.

    When limit is None, every candidate surviving the analysis thresholds and
    minimum-spacing rule is retained. A numeric limit is used only when an
    explicitly selected choreography policy requests one.
    """
    active_limit = None if limit is None else max(0, int(limit))
    if active_limit == 0:
        return []

    ranked = sorted(
        candidates,
        key=lambda item: (
            float(item.get("tap_score", 0.0)),
            float(item.get("high_frequency_ratio", 0.0)),
            float(item.get("strength", 0.0)),
        ),
        reverse=True,
    )
    selected: list[dict[str, Any]] = []
    for candidate in ranked:
        time_value = float(candidate["time"])
        if any(
            abs(time_value - float(existing["time"])) < min_spacing_seconds
            for existing in selected
        ):
            continue
        selected.append(candidate)
        if active_limit is not None and len(selected) >= active_limit:
            break
    return sorted(selected, key=lambda item: float(item["time"]))


def choose_primary_sync_targets(
    tap_candidates: list[dict[str, Any]],
    beat_grid_items: list[dict[str, Any]],
    *,
    limit: int | None = None,
) -> tuple[list[float], str]:
    """Prefer actual sharp tap transients; use beat-grid hits only as fallback."""
    selected_taps = select_tap_accent_targets(tap_candidates, limit=limit)
    if selected_taps:
        return (
            [round(float(item["time"]), 3) for item in selected_taps],
            "high_frequency_percussive_onsets",
        )

    ranked_beats = sorted(
        beat_grid_items,
        key=lambda item: float(item.get("percussive_strength", 0.0)),
        reverse=True,
    )
    if limit is not None:
        ranked_beats = ranked_beats[: max(0, int(limit))]
    return (
        sorted(round(float(item["time"]), 3) for item in ranked_beats),
        "beat_grid_percussive_fallback",
    )


def _high_frequency_ratio(y_percussive: np.ndarray, sr: int) -> np.ndarray:
    magnitude = np.abs(librosa.stft(y_percussive))
    power = magnitude**2
    frequencies = librosa.fft_frequencies(sr=sr)
    high_mask = frequencies >= DEFAULT_HIGH_BAND_HZ
    total = power.sum(axis=0)
    high = power[high_mask].sum(axis=0)
    return np.divide(high, total + 1e-12)


def extract_tap_beat_markers(
    audio_path: str | Path,
    plan: dict[str, Any],
    *,
    choreography_profile: str = AUTO_PROFILE,
) -> dict[str, Any]:
    audio_path = resolve_runtime_path(audio_path)
    y, sr = librosa.load(str(audio_path), sr=None, mono=True)
    duration = float(librosa.get_duration(y=y, sr=sr))
    _, y_percussive = librosa.effects.hpss(y)

    percussive_env = librosa.onset.onset_strength(y=y_percussive, sr=sr)
    high_env = librosa.onset.onset_strength(
        y=y_percussive,
        sr=sr,
        feature=librosa.feature.melspectrogram,
        fmin=DEFAULT_HIGH_BAND_HZ,
        fmax=float(sr) / 2.0,
    )
    tempo_raw, beat_frames = librosa.beat.beat_track(
        y=y_percussive,
        sr=sr,
        onset_envelope=percussive_env,
    )
    tempo = _scalar(tempo_raw)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    ratios = _high_frequency_ratio(y_percussive, sr)

    onset_frames = librosa.onset.onset_detect(
        onset_envelope=high_env,
        sr=sr,
        backtrack=False,
        units="frames",
    )
    tap_candidates: list[dict[str, Any]] = []
    max_strength = float(np.max(high_env)) if len(high_env) else 1.0
    for frame in onset_frames:
        index = int(frame)
        time_value = float(librosa.frames_to_time(index, sr=sr))
        ratio = float(ratios[min(index, len(ratios) - 1)]) if len(ratios) else 0.0
        strength = float(high_env[index]) if 0 <= index < len(high_env) else 0.0
        if ratio < DEFAULT_MIN_HIGH_RATIO or strength <= 0.0:
            continue
        tap_candidates.append(
            {
                "time": round(time_value, 3),
                "strength": round(strength, 6),
                "high_frequency_ratio": round(ratio, 6),
                "tap_score": round((strength / max(max_strength, 1e-12)) * ratio, 6),
            }
        )

    beat_grid: list[dict[str, Any]] = []
    for frame, beat_time in zip(beat_frames, beat_times):
        index = int(frame)
        beat_grid.append(
            {
                "time": round(float(beat_time), 3),
                "percussive_strength": round(
                    float(percussive_env[index])
                    if 0 <= index < len(percussive_env)
                    else 0.0,
                    6,
                ),
            }
        )

    scenes: list[dict[str, Any]] = []
    profile_counts: dict[str, int] = {}
    for item in plan.get("results", []):
        clip_index = int(item.get("clip_index", 0))
        scene = item.get("scene") or {}
        start = float(scene.get("start", 0.0))
        end = float(scene.get("end", start))
        scene_duration = max(0.0, end - start)
        requested = (
            item.get("choreography_profile_requested")
            or plan.get("choreography_profile_requested")
            or choreography_profile
        )
        policy = resolve_choreography_profile(
            item,
            requested_profile=str(requested or AUTO_PROFILE),
        )
        profile_id = str(policy["profile_id"])
        profile_counts[profile_id] = profile_counts.get(profile_id, 0) + 1
        limit = target_limit_for_policy(policy)

        scene_taps = [
            row for row in tap_candidates if start <= float(row["time"]) <= end
        ]
        scene_beats = [
            row for row in beat_grid if start <= float(row["time"]) <= end
        ]
        targets, source = choose_primary_sync_targets(
            scene_taps,
            scene_beats,
            limit=limit,
        )
        selected_rows = [
            row for row in scene_taps if round(float(row["time"]), 3) in set(targets)
        ]
        selection_mode = str((policy.get("target_selection") or {}).get("mode") or "all_reliable")
        scenes.append(
            {
                "clip_index": clip_index,
                "start": round(start, 3),
                "end": round(end, 3),
                "duration": round(scene_duration, 3),
                "primary_sync_targets_seconds": targets,
                "primary_sync_targets_relative_seconds": [
                    round(float(value) - start, 3) for value in targets
                ],
                "primary_sync_source": source,
                "sync_target_policy": "tap_not_boom",
                "sync_target_count_policy": selection_mode,
                "choreography_policy": policy,
                "tap_accent_times_seconds": [
                    round(float(row["time"]), 3) for row in selected_rows
                ],
                "tap_accent_strengths": [
                    float(row["strength"]) for row in selected_rows
                ],
                "tap_accent_high_frequency_ratios": [
                    float(row["high_frequency_ratio"]) for row in selected_rows
                ],
                "sync_density": len(targets),
            }
        )

    return {
        "status": "analyzed",
        "audio_path": serialize_path(audio_path),
        "audio_resolved_path": str(audio_path.resolve()),
        "duration_seconds": round(duration, 3),
        "tempo_bpm": round(tempo, 3) if tempo else None,
        "tap_sync_policy": "tap_not_boom",
        "choreography_profile_requested": choreography_profile,
        "choreography_profile_counts": profile_counts,
        "tap_accent_candidate_count": len(tap_candidates),
        "tap_accent_candidates": tap_candidates,
        "beat_grid": beat_grid,
        "scenes": scenes,
    }


def build_tap_sync_prompt_block(
    scene_marker: dict[str, Any],
    *,
    scene_hint: str = "",
    choreography_profile: str = AUTO_PROFILE,
) -> str:
    targets = scene_marker.get("primary_sync_targets_relative_seconds") or []
    target_text = ", ".join(f"{float(value):.3f}s" for value in targets)
    if not target_text:
        target_text = "no reliable tap accents detected"

    policy = scene_marker.get("choreography_policy")
    if not policy:
        policy = resolve_choreography_profile(
            {"seed_filename_prompt_hint": scene_hint},
            requested_profile=choreography_profile,
        )
    return render_tap_sync_prompt(policy, target_text)


def insert_tap_sync_prompt(prompt_text: str, tap_sync_block: str) -> str:
    prompt_text = str(prompt_text or "")
    if TAP_SYNC_MARKER in prompt_text:
        before = prompt_text.split(TAP_SYNC_MARKER, 1)[0].rstrip()
        remainder = prompt_text.split(TAP_SYNC_MARKER, 1)[1]
        for marker in (MOTION_MARKER, NEGATIVE_MARKER):
            if marker in remainder:
                after = marker + remainder.split(marker, 1)[1]
                return f"{before}\n\n{tap_sync_block}\n{after.lstrip()}"
        return f"{before}\n\n{tap_sync_block}"

    if MOTION_MARKER in prompt_text:
        before, after = prompt_text.split(MOTION_MARKER, 1)
        return f"{before.rstrip()}\n\n{tap_sync_block}\n{MOTION_MARKER}{after}"
    return f"{prompt_text.rstrip()}\n\n{tap_sync_block}"


def apply_tap_sync_to_plan_data(
    plan: dict[str, Any],
    *,
    audio_path: str | Path,
    markers: dict[str, Any] | None = None,
    choreography_profile: str = AUTO_PROFILE,
) -> dict[str, Any]:
    markers = markers or extract_tap_beat_markers(
        audio_path,
        plan,
        choreography_profile=choreography_profile,
    )
    by_clip = {
        int(item.get("clip_index")): item
        for item in markers.get("scenes", [])
        if item.get("clip_index") is not None
    }
    patched = deepcopy(plan)
    results: list[dict[str, Any]] = []
    profile_counts: dict[str, int] = {}

    for raw_item in plan.get("results", []):
        item = deepcopy(raw_item)
        scene_marker = deepcopy(by_clip.get(int(item.get("clip_index", 0)), {}))
        scene_hint = _scene_hint_for_item(item)
        requested = (
            item.get("choreography_profile_requested")
            or plan.get("choreography_profile_requested")
            or choreography_profile
        )
        policy = scene_marker.get("choreography_policy") or resolve_choreography_profile(
            item,
            requested_profile=str(requested or AUTO_PROFILE),
        )
        profile_id = str(policy["profile_id"])
        profile_counts[profile_id] = profile_counts.get(profile_id, 0) + 1
        scene_marker["choreography_policy"] = policy
        scene_marker["motion_profile"] = profile_id
        scene_marker["scene_hint"] = scene_hint

        block = build_tap_sync_prompt_block(
            scene_marker,
            scene_hint=scene_hint,
            choreography_profile=str(requested or AUTO_PROFILE),
        )
        prompt_text = insert_tap_sync_prompt(item.get("prompt_text", ""), block)
        prompt_text = merge_negative_prompt_terms(
            prompt_text,
            list(policy.get("negative_terms") or []),
        )

        item["tap_sync"] = scene_marker
        item["tap_sync_prompt_block"] = block
        item["choreography_profile_requested"] = str(requested or AUTO_PROFILE)
        item["choreography_policy"] = policy
        item["tap_motion_profile"] = profile_id
        item["prompt_text"] = prompt_text
        results.append(item)

    patched["results"] = results
    patched["choreography_profile_requested"] = choreography_profile
    patched["choreography_policy"] = {
        "status": "applied",
        "selection_scope": "per_scene",
        "requested_profile": choreography_profile,
        "profile_counts": profile_counts,
    }
    patched["tap_sync"] = {
        "status": "applied",
        "policy": "tap_not_boom",
        "primary_source": "high_frequency_percussive_onsets",
        "candidate_count": markers.get("tap_accent_candidate_count", 0),
        "scene_count": len(results),
        "motion_profile_counts": profile_counts,
    }
    return compact_plan_prompts(patched)


def wrap_choreography_manifest(
    original_builder: Callable[..., dict[str, Any]],
) -> Callable[..., dict[str, Any]]:
    def wrapped(plan: dict[str, Any], beat_markers=None):
        manifest = original_builder(plan, beat_markers=beat_markers)
        manifest["sync_policy"] = "tap_not_boom"
        plan_items = {
            int(item.get("clip_index", 0)): item
            for item in plan.get("results", [])
        }
        for scene in manifest.get("scenes", []):
            clip_index = int(scene.get("clip_index", 0))
            plan_item = plan_items.get(clip_index, {})
            policy = plan_item.get("choreography_policy") or resolve_choreography_profile(
                plan_item,
                requested_profile=plan_item.get("choreography_profile_requested") or AUTO_PROFILE,
            )
            profile_id = str(policy.get("profile_id") or "generic_tap_action")
            policy_manifest = policy.get("manifest") or {}
            scene["motion_profile"] = profile_id
            scene["choreography_policy"] = {
                "profile_id": profile_id,
                "selection_method": policy.get("selection_method"),
                "target_selection": policy.get("target_selection"),
            }
            scene["beat_sync_rule"] = policy_manifest.get("beat_sync_rule")
            scene["dance_direction_change_rule"] = policy_manifest.get(
                "dance_direction_change_rule"
            )
            scene["negative_motion_rules"] = list(
                policy_manifest.get("negative_motion_rules") or []
            )
        return manifest

    return wrapped
