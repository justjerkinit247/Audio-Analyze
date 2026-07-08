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
except ImportError:
    from path_policy import resolve_runtime_path, serialize_path
    from ltx_prompt_budget import compact_plan_prompts


TAP_SYNC_MARKER = "[TAP_SYNC]"
MOTION_MARKER = "[MOTION_PROMPT]"
NEGATIVE_MARKER = "[NEGATIVE_PROMPT]"
DEFAULT_HIGH_BAND_HZ = 1200.0
DEFAULT_MIN_HIGH_RATIO = 0.22
DEFAULT_MIN_SPACING_SECONDS = 0.08

LOCALIZED_GLUTE_TOKENS = {
    "twerk",
    "twerking",
    "glute",
    "glutes",
    "cheek",
    "cheeks",
    "booty",
    "rump",
}

LOCALIZED_GLUTE_NEGATIVE_TERMS = [
    "static opening frame",
    "frozen first frames",
    "delayed motion onset",
    "motionless first half",
    "waiting before movement",
    "jumping",
    "hopping",
    "feet leaving the floor",
    "heels lifting",
    "standing up",
    "repeated squats",
    "whole-body bouncing",
    "vertical pelvic bouncing",
    "full-body pumping",
    "large vertical displacement",
]


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
    tokens = set(re.findall(r"[a-z0-9]+", str(scene_hint or "").lower()))
    if tokens & LOCALIZED_GLUTE_TOKENS:
        return True
    has_hip_or_pelvis = bool(tokens & {"hip", "hips", "pelvis", "pelvic"})
    has_squat_or_lower_body = bool(tokens & {"squat", "squatting", "lower", "body"})
    return has_hip_or_pelvis and has_squat_or_lower_body


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
    limit: int,
    min_spacing_seconds: float = DEFAULT_MIN_SPACING_SECONDS,
) -> list[dict[str, Any]]:
    """Select the strongest sharp tap accents, then return them in time order."""
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
        if any(abs(time_value - float(existing["time"])) < min_spacing_seconds for existing in selected):
            continue
        selected.append(candidate)
        if len(selected) >= max(1, int(limit)):
            break
    return sorted(selected, key=lambda item: float(item["time"]))


def choose_primary_sync_targets(
    tap_candidates: list[dict[str, Any]],
    beat_grid_items: list[dict[str, Any]],
    *,
    limit: int,
) -> tuple[list[float], str]:
    """Prefer actual sharp tap transients; use percussive beat-grid hits only as fallback."""
    selected_taps = select_tap_accent_targets(tap_candidates, limit=limit)
    if selected_taps:
        return [round(float(item["time"]), 3) for item in selected_taps], "high_frequency_percussive_onsets"

    ranked_beats = sorted(
        beat_grid_items,
        key=lambda item: float(item.get("percussive_strength", 0.0)),
        reverse=True,
    )[:limit]
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


def extract_tap_beat_markers(audio_path: str | Path, plan: dict[str, Any]) -> dict[str, Any]:
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
                    float(percussive_env[index]) if 0 <= index < len(percussive_env) else 0.0,
                    6,
                ),
            }
        )

    scenes: list[dict[str, Any]] = []
    for item in plan.get("results", []):
        clip_index = int(item.get("clip_index", 0))
        scene = item.get("scene") or {}
        start = float(scene.get("start", 0.0))
        end = float(scene.get("end", start))
        scene_duration = max(0.0, end - start)
        limit = max(8, min(24, int(round(scene_duration * 4.0))))
        scene_taps = [item for item in tap_candidates if start <= float(item["time"]) <= end]
        scene_beats = [item for item in beat_grid if start <= float(item["time"]) <= end]
        targets, source = choose_primary_sync_targets(scene_taps, scene_beats, limit=limit)
        selected_rows = [
            item for item in scene_taps if round(float(item["time"]), 3) in set(targets)
        ]
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
                "tap_accent_times_seconds": [
                    round(float(item["time"]), 3) for item in selected_rows
                ],
                "tap_accent_strengths": [
                    float(item["strength"]) for item in selected_rows
                ],
                "tap_accent_high_frequency_ratios": [
                    float(item["high_frequency_ratio"]) for item in selected_rows
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
        "tap_accent_candidate_count": len(tap_candidates),
        "tap_accent_candidates": tap_candidates,
        "beat_grid": beat_grid,
        "scenes": scenes,
    }


def build_tap_sync_prompt_block(
    scene_marker: dict[str, Any],
    *,
    scene_hint: str = "",
) -> str:
    targets = scene_marker.get("primary_sync_targets_relative_seconds") or []
    target_text = ", ".join(f"{float(value):.3f}s" for value in targets)
    if not target_text:
        target_text = "no reliable tap accents detected"

    if is_localized_glute_scene(scene_hint):
        return (
            f"{TAP_SYNC_MARKER}\n"
            f"Primary tap-accent times inside this clip: {target_text}. "
            "Visible dance motion begins immediately at 0.00 seconds and continues throughout the entire clip; never hold the seed image as a static opening. "
            "At every listed clap, snare, hi-hat, or sharp tap accent, perform one compact localized twerk pulse: a brief glute-cheek contraction, a small backward pelvis pop, and a controlled recoil. "
            "Alternate left and right glute-cheek emphasis only when physically natural, while keeping the motion isolated below the waist. "
            "Both feet remain planted, heels remain down, knees stay bent, and the dancer remains in the same squat pose family. "
            "Keep head, shoulders, chest, torso, and overall body height nearly constant; the accent comes from the glutes and pelvis, not from moving the whole body upward. "
            "Between listed accents, maintain subtle continuous pelvic micro-motion and a small controlled hip sway so the image never freezes while waiting for the next tap. "
            "Do not convert the accents into jumping, hopping, standing up, repeated squats, whole-body bouncing, vertical pumping, or feet leaving the floor. "
            "Do not use kick-drum or bass-only boom hits as major movement triggers. "
            "This TAP_SYNC instruction overrides generic jumping, bouncing, kick-driven, full-body, or vertical direction-change wording elsewhere in the prompt.\n"
        )

    return (
        f"{TAP_SYNC_MARKER}\n"
        f"Primary tap-accent times inside this clip: {target_text}. "
        "Use sharp clap, snare, hi-hat, and similar high-frequency tap transients as visible motion triggers. "
        "Land controlled visible action changes on each listed primary tap accent. "
        "Do not trigger direction changes from kick-drum or bass-only boom hits; hold, travel, or prepare between tap accents. "
        "This TAP_SYNC rule overrides any generic kick or full-beat direction-change wording elsewhere in the prompt.\n"
    )


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
) -> dict[str, Any]:
    markers = markers or extract_tap_beat_markers(audio_path, plan)
    by_clip = {
        int(item.get("clip_index")): item
        for item in markers.get("scenes", [])
        if item.get("clip_index") is not None
    }
    patched = deepcopy(plan)
    results: list[dict[str, Any]] = []
    profile_counts = {"localized_glute_pulse": 0, "generic_tap_action": 0}

    for raw_item in plan.get("results", []):
        item = deepcopy(raw_item)
        scene_marker = deepcopy(by_clip.get(int(item.get("clip_index", 0)), {}))
        scene_hint = _scene_hint_for_item(item)
        localized_glute = is_localized_glute_scene(scene_hint)
        motion_profile = "localized_glute_pulse" if localized_glute else "generic_tap_action"
        profile_counts[motion_profile] += 1
        scene_marker["motion_profile"] = motion_profile
        scene_marker["scene_hint"] = scene_hint

        block = build_tap_sync_prompt_block(scene_marker, scene_hint=scene_hint)
        prompt_text = insert_tap_sync_prompt(item.get("prompt_text", ""), block)
        if localized_glute:
            prompt_text = merge_negative_prompt_terms(
                prompt_text,
                LOCALIZED_GLUTE_NEGATIVE_TERMS,
            )

        item["tap_sync"] = scene_marker
        item["tap_sync_prompt_block"] = block
        item["tap_motion_profile"] = motion_profile
        item["prompt_text"] = prompt_text
        results.append(item)

    patched["results"] = results
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
            motion_profile = plan_item.get("tap_motion_profile") or "generic_tap_action"
            scene["motion_profile"] = motion_profile
            scene["beat_sync_rule"] = (
                "Visible action accents land on sharp clap/snare/hi-hat-like tap accents, "
                "including off-grid accents; kick/bass-only boom hits do not trigger major direction changes."
            )
            if motion_profile == "localized_glute_pulse":
                scene["dance_direction_change_rule"] = (
                    "Each listed tap triggers a compact isolated glute-cheek contraction, "
                    "small backward pelvis pop, and controlled recoil while feet stay planted "
                    "and overall body height remains stable."
                )
                scene["negative_motion_rules"] = [
                    "no jumping or hopping",
                    "no feet leaving the floor or heels lifting",
                    "no standing up or repeated squats",
                    "no whole-body bouncing or vertical pumping",
                    "no frozen opening or delayed motion onset",
                    "no kick-drum or bass-only major movement triggers",
                    "no warped anatomy",
                    "no random background or body layout mutation",
                ]
            else:
                scene["dance_direction_change_rule"] = (
                    "Land controlled visible action changes on every listed primary tap accent."
                )
                scene["negative_motion_rules"] = [
                    "no kick-drum or bass-only direction changes",
                    "no drifting through a listed tap accent without a visible response",
                    "no random shaking between tap accents",
                    "no chaotic camera spin",
                    "no warped anatomy",
                    "no random background or body layout mutation",
                ]
        return manifest

    return wrapped
