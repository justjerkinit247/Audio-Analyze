from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any
import os
import re

try:
    from .ltx_gemma_prompt_synthesizer import (
        AUDIO_TIMING_MARKER,
        MOTION_MARKER,
        NEGATIVE_MARKER,
        SEED_IMAGE_DESCRIPTION_MARKER,
        SUBJECT_LOCK_MARKER,
        TAP_SYNC_MARKER,
        REQUIRED_MARKERS,
        synthesize_final_ltx_prompt,
    )
except ImportError:
    from ltx_gemma_prompt_synthesizer import (
        AUDIO_TIMING_MARKER,
        MOTION_MARKER,
        NEGATIVE_MARKER,
        SEED_IMAGE_DESCRIPTION_MARKER,
        SUBJECT_LOCK_MARKER,
        TAP_SYNC_MARKER,
        REQUIRED_MARKERS,
        synthesize_final_ltx_prompt,
    )


MARKERS = list(REQUIRED_MARKERS)
DEFAULT_MAX_CHARS = 5000
DEFAULT_TARGET_CHARS = 4800
FOREGROUND_ONSET_DEADLINE_SECONDS = 0.10
FOREGROUND_PRIORITY_WINDOW_SECONDS = 0.50

FOREGROUND_ONSET_NEGATIVE_TERMS = [
    "frozen foreground subjects",
    "static lead pair",
    "delayed foreground motion",
    "background-only motion",
    "moving background hands while foreground remains frozen",
    "animated background with static main characters",
    "foreground motion starting after the first tap",
]

CRITICAL_NEGATIVE_TERMS = [
    *FOREGROUND_ONSET_NEGATIVE_TERMS,
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
    "missing dance partner",
    "missing male dancer",
    "missing female dancer",
    "missing choir",
    "removed background performers",
    "changed subject count",
    "removed visible subject",
    "added unrelated subject",
    "merged people",
    "extra limbs",
    "distorted anatomy",
    "duplicate subject",
    "warped background",
    "flicker",
    "jittery motion",
    "chaotic camera movement",
]


def _clean_inline(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _format_float(value: Any, digits: int = 2) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "unknown"


def _split_prompt(prompt_text: str) -> tuple[str, dict[str, str]]:
    text = str(prompt_text or "")
    pattern = re.compile(
        rf"(?m)^\s*({'|'.join(re.escape(marker) for marker in MARKERS)})\s*$"
    )
    matches = list(pattern.finditer(text))
    if not matches:
        return _clean_inline(text), {}

    prefix = _clean_inline(text[: matches[0].start()])
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[match.group(1)] = _clean_inline(text[start:end])
    return prefix, sections


def _render_prompt(prefix: str, sections: dict[str, str]) -> str:
    blocks: list[str] = []
    if prefix:
        blocks.append(prefix.strip())
    for marker in MARKERS:
        if marker in sections:
            blocks.append(f"{marker}\n{sections[marker].strip()}")
    return "\n\n".join(blocks).strip() + "\n"


def _truncate_at_boundary(text: str, limit: int) -> str:
    cleaned = _clean_inline(text)
    if limit <= 0:
        return ""
    if len(cleaned) <= limit:
        return cleaned
    candidate = cleaned[: max(1, limit - 1)].rstrip()
    boundary = max(
        candidate.rfind(". "),
        candidate.rfind("; "),
        candidate.rfind(", "),
    )
    if boundary >= int(limit * 0.55):
        candidate = candidate[: boundary + 1].rstrip()
    else:
        word_boundary = candidate.rfind(" ")
        if word_boundary > 0:
            candidate = candidate[:word_boundary]
    return candidate.rstrip(" ,;:") + "."


def _compact_prefix(item: dict[str, Any]) -> str:
    filename = (
        item.get("seed_filename_used_for_prompt_hint")
        or Path(str(item.get("seed_image_used") or "seed_image.png")).name
    )
    return (
        "Audio-and-image-to-video continuation synchronized to the supplied audio. "
        "Use audio as the timing source and the seed image as authoritative for subject "
        "count, identity, pose family, body layout, framing, lighting, and background. "
        f"Seed image filename used as the Ollama prompt hint: {filename}."
    )


def _compact_subject_lock(item: dict[str, Any], existing: str) -> str:
    policy = item.get("subject_count_policy") or {}
    parts = [
        "The seed image is authoritative for subject count and body layout.",
        "Preserve every visible person; do not add, remove, merge, replace, or hide subjects.",
    ]
    if policy.get("has_pair"):
        parts.append(
            "Keep the female lead dancer and male dance partner visible together throughout the complete clip."
        )
    if policy.get("has_choir"):
        parts.append("Keep the existing choir visible in the background throughout.")
    elif policy.get("has_group"):
        parts.append("Keep all existing background performers visible in their original layout.")
    if policy.get("multiple_subjects"):
        parts.append("Do not render the scene as solitary, solo, lone, or single-person.")
    if not policy and existing:
        return _truncate_at_boundary(existing, 520)
    return " ".join(parts)


def _compact_audio_timing(item: dict[str, Any], existing: str) -> str:
    timing = item.get("audio_timing") or {}
    if not timing:
        return _truncate_at_boundary(existing, 520)

    scene_index = timing.get("scene_index") or item.get("clip_index") or 1
    start = _format_float(timing.get("start_seconds"), 2)
    end = _format_float(timing.get("end_seconds"), 2)
    duration = _format_float(timing.get("duration_seconds"), 2)
    tempo = _format_float(timing.get("tempo_bpm"), 2)
    alignment = "enabled" if timing.get("beat_alignment_enabled") else "disabled"
    energy = _clean_inline(timing.get("energy_profile") or "rhythm-aware")
    pacing = _clean_inline(timing.get("edit_pacing") or "controlled")
    return (
        f"Scene {scene_index}: {start}s to {end}s, duration {duration}s, tempo "
        f"{tempo} BPM, beat alignment {alignment}. Keep visible movement and major "
        "action changes synchronized to this audio window. "
        f"Energy/pacing: {energy}, {pacing}."
    )


def _target_text(item: dict[str, Any], existing: str) -> str:
    tap = item.get("tap_sync") or {}
    targets = tap.get("primary_sync_targets_relative_seconds") or []
    if targets:
        return ", ".join(f"{float(value):.3f}s" for value in targets)
    match = re.search(
        r"Primary tap-accent times inside this clip:\s*([^.]*)",
        existing or "",
        flags=re.I,
    )
    return _clean_inline(match.group(1)) if match else "no reliable tap accents detected"


def _foreground_scope(item: dict[str, Any]) -> str:
    policy = item.get("subject_count_policy") or {}
    if policy.get("has_pair"):
        return "both main foreground partners"
    if policy.get("has_group") and not policy.get("has_choir"):
        return "the main foreground performers"
    return "the main foreground subject"


def _compact_tap_sync(item: dict[str, Any], existing: str) -> str:
    targets = _target_text(item, existing)
    profile = item.get("tap_motion_profile") or (item.get("tap_sync") or {}).get(
        "motion_profile"
    )
    scope = _foreground_scope(item)

    onset = (
        f"{scope} begin visible motion on frame 1 and depart the seed pose by 0.10 "
        "seconds. The first tap is an accent, not the start signal. "
    )

    if profile == "localized_glute_pulse":
        return (
            f"Primary tap-accent times inside this clip: {targets}. {onset}"
            "At each clap, snare, hi-hat, or sharp tap accent, perform one compact "
            "localized twerk pulse: a brief glute-cheek contraction, small backward "
            "pelvis pop, and controlled recoil. Both feet remain planted; heels stay "
            "down, knees bent, and body height remains nearly constant. Maintain "
            "pelvic micro-motion between taps. Do not convert the accents into jumping, "
            "hopping, standing up, repeated squats, whole-body bouncing, vertical "
            "pumping, or feet leaving the floor. Ignore bass-only boom hits."
        )

    return (
        f"Primary tap-accent times inside this clip: {targets}. {onset}"
        "Use clap, snare, hi-hat, and sharp high-frequency accents as controlled "
        "visible action triggers. Ignore bass-only boom hits and maintain coherent "
        "foreground motion between accents."
    )


def _compact_motion(item: dict[str, Any], existing: str, limit: int) -> str:
    expansion = item.get("filename_hint_expansion") or {}
    source = _clean_inline(expansion.get("ltx_motion_prompt") or existing)
    fallback = "Maintain continuous grounded motion and stable camera movement."
    return _truncate_at_boundary(source or fallback, max(240, limit))


def _split_negative_terms(text: str) -> list[str]:
    return [term.strip() for term in _clean_inline(text).split(",") if term.strip()]


def _negative_terms(item: dict[str, Any], existing: str) -> list[str]:
    expansion = item.get("filename_hint_expansion") or {}
    raw_terms = _split_negative_terms(str(expansion.get("negative_prompt") or ""))
    raw_terms.extend(_split_negative_terms(existing))
    raw_terms.extend(FOREGROUND_ONSET_NEGATIVE_TERMS)

    seen: set[str] = set()
    unique: list[str] = []
    for term in raw_terms:
        cleaned = _clean_inline(term).strip(" ,")
        key = cleaned.lower()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        unique.append(cleaned)
    return unique


def _compact_negative(
    item: dict[str, Any],
    existing: str,
    limit: int,
) -> tuple[str, list[str]]:
    terms = _negative_terms(item, existing)
    by_key = {term.lower(): term for term in terms}
    prioritized: list[str] = []
    used: set[str] = set()

    for critical in CRITICAL_NEGATIVE_TERMS:
        key = critical.lower()
        if key in by_key and key not in used:
            prioritized.append(by_key[key])
            used.add(key)
    for term in terms:
        key = term.lower()
        if key not in used:
            prioritized.append(term)
            used.add(key)

    kept: list[str] = []
    removed: list[str] = []
    for term in prioritized:
        candidate = ", ".join(kept + [term])
        if len(candidate) <= limit:
            kept.append(term)
        else:
            removed.append(term)
    return ", ".join(kept), removed


def _freeform_gemma_analysis(item: dict[str, Any]) -> bool:
    analysis = item.get("seed_image_analysis") or {}
    if os.environ.get("OLLAMA_FINAL_PROMPT_SYNTHESIS", "1").strip().lower() in {
        "0",
        "false",
        "no",
        "off",
    }:
        return False
    return (
        analysis.get("status") == "complete"
        and bool(str(analysis.get("description") or "").strip())
        and analysis.get("analysis_mode") == "freeform_native"
    )


def _apply_gemma_synthesis(
    item: dict[str, Any],
    *,
    max_chars: int,
) -> dict[str, Any]:
    patched = deepcopy(item)
    synthesis = synthesize_final_ltx_prompt(
        patched,
        max_chars=max_chars,
        target_min=min(4700, max_chars - 250),
        target_max=min(4980, max_chars),
    )
    final_prompt = synthesis["final_prompt"]
    analysis = deepcopy(patched.get("seed_image_analysis") or {})
    analysis["prompt_context"] = final_prompt
    analysis["prompt_context_char_count"] = len(final_prompt)
    analysis["prompt_context_selection"] = (
        "gemma_full_native_analysis_to_final_ltx_prompt"
    )
    patched["seed_image_analysis"] = analysis
    patched["gemma_final_prompt_synthesis"] = synthesis
    patched["prompt_text_before_gemma_final_synthesis"] = str(
        item.get("prompt_text") or ""
    )
    patched["prompt_text"] = final_prompt
    patched["exact_prompt_sent_to_ltx"] = final_prompt
    patched["prompt_text_is_exact_ltx_payload"] = True
    patched["prompt_text_chars"] = len(final_prompt)
    patched["prompt_budget"] = {
        "status": "gemma_synthesized",
        "before_chars": len(str(item.get("prompt_text") or "")),
        "after_chars": len(final_prompt),
        "target_chars": min(4980, max_chars),
        "hard_limit_chars": max_chars,
        "preserved_markers": [
            marker for marker in REQUIRED_MARKERS if marker in final_prompt
        ],
        "policy": "gemma_full_native_analysis_final_prompt_synthesis",
        "policy_version": "gemma_final_ltx_prompt_v1",
        "seed_analysis_native_chars": synthesis["source_native_analysis_chars"],
        "seed_analysis_prompt_chars": synthesis["seed_description_char_count"],
        "seed_analysis_summary_model_used": True,
        "final_prompt_synthesis_model": synthesis["model"],
        "final_prompt_synthesis_attempts": synthesis["attempt_count"],
        "final_prompt_validation_passed": synthesis["validation_passed"],
        "prompt_text_is_exact_ltx_payload": True,
    }
    return patched


def _deterministic_compact_item(
    item: dict[str, Any],
    *,
    max_chars: int,
    target_chars: int,
) -> dict[str, Any]:
    patched = deepcopy(item)
    original = str(item.get("prompt_text") or "")
    _, parsed = _split_prompt(original)

    sections = {
        SUBJECT_LOCK_MARKER: _compact_subject_lock(
            item,
            parsed.get(SUBJECT_LOCK_MARKER, ""),
        ),
        AUDIO_TIMING_MARKER: _compact_audio_timing(
            item,
            parsed.get(AUDIO_TIMING_MARKER, ""),
        ),
        TAP_SYNC_MARKER: _compact_tap_sync(
            item,
            parsed.get(TAP_SYNC_MARKER, ""),
        ),
        MOTION_MARKER: "",
        NEGATIVE_MARKER: "",
    }

    analysis = item.get("seed_image_analysis") or {}
    seed_description = _clean_inline(
        analysis.get("description")
        or analysis.get("prompt_context")
        or parsed.get(SEED_IMAGE_DESCRIPTION_MARKER)
        or ""
    )
    if seed_description:
        sections[SEED_IMAGE_DESCRIPTION_MARKER] = seed_description

    prefix = _compact_prefix(item)
    fixed_without_motion_negative = _render_prompt(prefix, sections)
    available = max(700, target_chars - len(fixed_without_motion_negative))
    negative_limit = min(1150, max(720, int(available * 0.46)))
    motion_limit = max(420, available - negative_limit)

    sections[MOTION_MARKER] = _compact_motion(
        item,
        parsed.get(MOTION_MARKER, ""),
        motion_limit,
    )
    negative, removed_terms = _compact_negative(
        item,
        parsed.get(NEGATIVE_MARKER, ""),
        negative_limit,
    )
    sections[NEGATIVE_MARKER] = negative
    compacted = _render_prompt(prefix, sections)

    if len(compacted) > target_chars:
        overflow = len(compacted) - target_chars
        if SEED_IMAGE_DESCRIPTION_MARKER in sections:
            sections[SEED_IMAGE_DESCRIPTION_MARKER] = _truncate_at_boundary(
                sections[SEED_IMAGE_DESCRIPTION_MARKER],
                max(
                    500,
                    len(sections[SEED_IMAGE_DESCRIPTION_MARKER]) - overflow - 60,
                ),
            )
        else:
            sections[MOTION_MARKER] = _truncate_at_boundary(
                sections[MOTION_MARKER],
                max(300, len(sections[MOTION_MARKER]) - overflow - 60),
            )
        compacted = _render_prompt(prefix, sections)

    if len(compacted) > max_chars:
        overflow = len(compacted) - max_chars
        sections[NEGATIVE_MARKER], additionally_removed = _compact_negative(
            item,
            sections[NEGATIVE_MARKER],
            max(500, len(sections[NEGATIVE_MARKER]) - overflow - 60),
        )
        removed_terms.extend(additionally_removed)
        compacted = _render_prompt(prefix, sections)

    if len(compacted) > max_chars:
        raise ValueError(
            f"Unable to compact final LTX prompt below {max_chars} characters; "
            f"got {len(compacted)}"
        )

    patched["prompt_text_before_budget_compaction"] = original
    patched["prompt_text"] = compacted
    patched["exact_prompt_sent_to_ltx"] = compacted
    patched["prompt_text_is_exact_ltx_payload"] = True
    patched["prompt_text_chars"] = len(compacted)
    patched["foreground_motion_onset"] = {
        "required": True,
        "deadline_seconds": FOREGROUND_ONSET_DEADLINE_SECONDS,
        "priority_window_seconds": FOREGROUND_PRIORITY_WINDOW_SECONDS,
        "first_tap_is_start_signal": False,
        "background_only_motion_forbidden": True,
        "subject_scope": _foreground_scope(item),
    }
    patched["prompt_budget"] = {
        "status": "compacted" if len(original) > len(compacted) else "within_budget",
        "before_chars": len(original),
        "after_chars": len(compacted),
        "target_chars": int(target_chars),
        "hard_limit_chars": int(max_chars),
        "removed_negative_terms": removed_terms,
        "preserved_markers": [
            marker for marker in MARKERS if marker in compacted
        ],
        "policy": "compact_after_ollama_asmo_subject_lock_and_tap_sync",
        "policy_version": "deterministic_fallback_v4",
        "foreground_motion_onset_enforced": True,
        "seed_analysis_summary_model_used": False,
        "prompt_text_is_exact_ltx_payload": True,
    }

    expansion = patched.get("filename_hint_expansion")
    if isinstance(expansion, dict):
        expansion["negative_prompt_before_budget_compaction"] = expansion.get(
            "negative_prompt"
        )
        expansion["negative_prompt"] = sections[NEGATIVE_MARKER]

    return patched


def compact_item_prompt(
    item: dict[str, Any],
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    target_chars: int = DEFAULT_TARGET_CHARS,
) -> dict[str, Any]:
    hard_limit = max(1, int(max_chars))
    target = min(hard_limit, max(1, int(target_chars)))

    if _freeform_gemma_analysis(item):
        return _apply_gemma_synthesis(item, max_chars=hard_limit)

    return _deterministic_compact_item(
        item,
        max_chars=hard_limit,
        target_chars=target,
    )


def compact_plan_prompts(
    plan: dict[str, Any],
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    target_chars: int = DEFAULT_TARGET_CHARS,
) -> dict[str, Any]:
    patched = deepcopy(plan)
    results: list[dict[str, Any]] = []
    before_lengths: list[int] = []
    after_lengths: list[int] = []
    synthesis_count = 0

    for item in plan.get("results", []) or []:
        compacted = compact_item_prompt(
            item,
            max_chars=max_chars,
            target_chars=target_chars,
        )
        budget = compacted["prompt_budget"]
        before_lengths.append(int(budget["before_chars"]))
        after_lengths.append(int(budget["after_chars"]))
        if budget.get("status") == "gemma_synthesized":
            synthesis_count += 1
        results.append(compacted)

    patched["results"] = results
    patched["prompt_budget"] = {
        "status": "applied",
        "scene_count": len(results),
        "target_chars": min(int(target_chars), int(max_chars)),
        "hard_limit_chars": int(max_chars),
        "max_before_chars": max(before_lengths) if before_lengths else 0,
        "max_after_chars": max(after_lengths) if after_lengths else 0,
        "gemma_final_prompt_synthesis_scene_count": synthesis_count,
        "policy": "gemma_synthesis_for_freeform_analysis_else_deterministic_compaction",
        "policy_version": "gemma_final_ltx_prompt_v1",
        "foreground_motion_onset_enforced": True,
    }
    return patched
