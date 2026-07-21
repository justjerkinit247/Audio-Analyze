from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any
import re


SCENE_DESCRIPTION_MARKER = "[SCENE_DESCRIPTION]"
SUBJECT_LOCK_MARKER = "[SUBJECT_LOCK]"
AUDIO_TIMING_MARKER = "[AUDIO_TIMING]"
TAP_SYNC_MARKER = "[TAP_SYNC]"
MOTION_MARKER = "[MOTION_PROMPT]"
NEGATIVE_MARKER = "[NEGATIVE_PROMPT]"
MARKERS = [
    SCENE_DESCRIPTION_MARKER,
    SUBJECT_LOCK_MARKER,
    AUDIO_TIMING_MARKER,
    TAP_SYNC_MARKER,
    MOTION_MARKER,
    NEGATIVE_MARKER,
]
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
        r"(?m)^\s*(\[SCENE_DESCRIPTION\]|\[SUBJECT_LOCK\]|\[AUDIO_TIMING\]|\[TAP_SYNC\]|\[MOTION_PROMPT\]|\[NEGATIVE_PROMPT\])\s*$"
    )
    matches = list(pattern.finditer(text))
    if not matches:
        return _clean_inline(text), {}

    prefix = _clean_inline(text[: matches[0].start()])
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        marker = match.group(1)
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[marker] = _clean_inline(text[start:end])
    return prefix, sections


def _render_prompt(prefix: str, sections: dict[str, str]) -> str:
    blocks: list[str] = []
    if prefix:
        blocks.append(prefix)
    for marker in MARKERS:
        if marker in sections:
            blocks.append(f"{marker}\n{sections[marker].strip()}")
    return "\n\n".join(blocks).strip() + "\n"


def _compact_prefix(item: dict[str, Any]) -> str:
    filename = (
        item.get("seed_filename_used_for_prompt_hint")
        or Path(str(item.get("seed_image_used") or "seed_image.png")).name
    )
    return (
        "Audio-and-image-to-video continuation synchronized to the supplied audio. "
        "Use audio as the timing source and the seed image pixels as authoritative for subject count, identity, pose family, body layout, framing, lighting, and background. "
        f"Seed image filename used as the Ollama prompt hint: {filename}. "
        "Use the natural-language pixel description as primary visual context and the filename as a secondary clue; do not import unrelated prior-project assumptions."
    )


def _truncate_at_boundary(text: str, limit: int) -> str:
    cleaned = _clean_inline(text)
    if len(cleaned) <= limit:
        return cleaned
    candidate = cleaned[: max(1, limit - 1)].rstrip()
    boundary = max(candidate.rfind(". "), candidate.rfind("; "), candidate.rfind(", "))
    if boundary >= int(limit * 0.55):
        candidate = candidate[: boundary + 1].rstrip()
    else:
        word_boundary = candidate.rfind(" ")
        if word_boundary > 0:
            candidate = candidate[:word_boundary]
    return candidate.rstrip(" ,;:") + "."


def _compact_scene_description(item: dict[str, Any], existing: str) -> str:
    description = _clean_inline(item.get("scene_description") or existing)
    if description.lower().startswith("observable opening-frame description:"):
        description = description.split(":", 1)[1].strip()
    policy_suffix = " This block describes the starting pixels only."
    if "this block describes the starting pixels only" in description.lower():
        description = re.split(
            r"this block describes the starting pixels only",
            description,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip()
    if not description:
        description = (
            "No natural-language pixel description was available; use the supplied seed image itself as the visual authority."
        )
    return (
        "Observable opening-frame description: "
        + _truncate_at_boundary(description, 850)
        + policy_suffix
        + " It does not override audio timing, choreography policy, tap synchronization, or subject locks."
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
        f"Scene {scene_index}: {start}s to {end}s, duration {duration}s, tempo {tempo} BPM, beat alignment {alignment}. "
        "Keep visible movement and major action changes synchronized to this audio window and its detected rhythmic feel. "
        f"Energy/pacing: {energy}, {pacing}. Keep camera movement stable and preserve the seed lighting."
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


def _background_priority_text(item: dict[str, Any]) -> str:
    policy = item.get("subject_count_policy") or {}
    if policy.get("has_choir"):
        return (
            "For the first 0.50 seconds, choir hands and other background motion remain subordinate and cannot be the only moving region. "
            "After foreground motion is clearly established, the choir may add only subtle claps and sway."
        )
    if policy.get("has_group"):
        return (
            "For the first 0.50 seconds, background performers remain subordinate and cannot be the only moving region. "
            "Background motion may increase only after the main foreground motion is clearly established."
        )
    return "Environmental or background motion cannot substitute for immediate motion by the main foreground subject."


def _compact_tap_sync(item: dict[str, Any], existing: str) -> str:
    targets = _target_text(item, existing)
    profile = item.get("tap_motion_profile") or (item.get("tap_sync") or {}).get("motion_profile")
    scope = _foreground_scope(item)
    background_rule = _background_priority_text(item)

    onset = (
        f"FOREGROUND MOTION ONSET: {scope} begin visible motion on frame 1 and visibly depart the seed pose by 0.10 seconds. "
        "The first listed tap is an accent target, not the start signal; do not wait for it. "
        "Maintain continuous low-amplitude foreground motion from 0.00 through 0.50 seconds and then throughout the clip. "
        f"{background_rule}"
    )

    if profile == "localized_glute_pulse":
        partner_rule = ""
        if (item.get("subject_count_policy") or {}).get("has_pair"):
            partner_rule = (
                "By 0.10 seconds, the lead dancer's pelvis and glutes are visibly displaced from the seed pose and the partner has already begun a restrained shoulder-and-chest groove. "
            )
        return (
            f"Primary tap-accent times inside this clip: {targets}. "
            f"{onset} {partner_rule}"
            "At each listed clap, snare, hi-hat, or sharp tap accent, perform one compact localized twerk pulse: a brief glute-cheek contraction, small backward pelvis pop, and controlled recoil. "
            "Alternate cheek emphasis only when physically natural. Both feet remain planted; heels stay down, knees bent, the same squat pose is maintained, and head, torso, and overall body height remain nearly constant. "
            "Maintain visible pelvic micro-motion between taps so the foreground never freezes. "
            "Do not convert the accents into jumping, hopping, standing up, repeated squats, whole-body bouncing, vertical pumping, or feet leaving the floor. "
            "Do not use kick-drum or bass-only hits as major movement triggers. This TAP_SYNC rule overrides any generic kick, full-beat, jumping, bouncing, full-body, vertical, delayed-start, or background-only motion wording elsewhere in the prompt."
        )

    return (
        f"Primary tap-accent times inside this clip: {targets}. "
        f"{onset} "
        "Use listed clap, snare, hi-hat, and sharp high-frequency accents as controlled visible action triggers. "
        "Do not use kick-drum or bass-only hits as major movement triggers; maintain coherent foreground motion between accents. "
        "This TAP_SYNC rule overrides any generic kick, full-beat, delayed-start, or background-only motion wording elsewhere in the prompt."
    )


def _compact_motion(item: dict[str, Any], existing: str, limit: int) -> str:
    expansion = item.get("filename_hint_expansion") or {}
    source = _clean_inline(expansion.get("ltx_motion_prompt") or existing)
    return _truncate_at_boundary(source, max(240, limit))


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


def _compact_negative(item: dict[str, Any], existing: str, limit: int) -> tuple[str, list[str]]:
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


def compact_item_prompt(
    item: dict[str, Any],
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    target_chars: int = DEFAULT_TARGET_CHARS,
) -> dict[str, Any]:
    patched = deepcopy(item)
    original = str(item.get("prompt_text") or "")
    _, parsed = _split_prompt(original)

    sections = {
        SCENE_DESCRIPTION_MARKER: _compact_scene_description(
            item,
            parsed.get(SCENE_DESCRIPTION_MARKER, ""),
        ),
        SUBJECT_LOCK_MARKER: _compact_subject_lock(item, parsed.get(SUBJECT_LOCK_MARKER, "")),
        AUDIO_TIMING_MARKER: _compact_audio_timing(item, parsed.get(AUDIO_TIMING_MARKER, "")),
        TAP_SYNC_MARKER: _compact_tap_sync(item, parsed.get(TAP_SYNC_MARKER, "")),
        MOTION_MARKER: "",
        NEGATIVE_MARKER: "",
    }
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
        sections[MOTION_MARKER] = _compact_motion(
            item,
            sections[MOTION_MARKER],
            max(300, len(sections[MOTION_MARKER]) - overflow - 80),
        )
        compacted = _render_prompt(prefix, sections)

    if len(compacted) > target_chars:
        overflow = len(compacted) - target_chars
        negative_budget = max(600, len(sections[NEGATIVE_MARKER]) - overflow - 80)
        sections[NEGATIVE_MARKER], additionally_removed = _compact_negative(
            item,
            sections[NEGATIVE_MARKER],
            negative_budget,
        )
        removed_terms.extend(additionally_removed)
        compacted = _render_prompt(prefix, sections)

    if len(compacted) > max_chars:
        overflow = len(compacted) - max_chars
        scene_budget = max(420, len(sections[SCENE_DESCRIPTION_MARKER]) - overflow - 80)
        sections[SCENE_DESCRIPTION_MARKER] = _truncate_at_boundary(
            sections[SCENE_DESCRIPTION_MARKER],
            scene_budget,
        )
        compacted = _render_prompt(prefix, sections)

    if len(compacted) > max_chars:
        raise ValueError(
            f"Unable to compact final LTX prompt below {max_chars} characters; got {len(compacted)}"
        )

    onset_metadata = {
        "required": True,
        "deadline_seconds": FOREGROUND_ONSET_DEADLINE_SECONDS,
        "priority_window_seconds": FOREGROUND_PRIORITY_WINDOW_SECONDS,
        "first_tap_is_start_signal": False,
        "background_only_motion_forbidden": True,
        "subject_scope": _foreground_scope(item),
    }

    patched["prompt_text_before_budget_compaction"] = original
    patched["prompt_text"] = compacted
    patched["foreground_motion_onset"] = onset_metadata
    patched["prompt_budget"] = {
        "status": "compacted" if len(original) > len(compacted) else "within_budget",
        "before_chars": len(original),
        "after_chars": len(compacted),
        "target_chars": int(target_chars),
        "hard_limit_chars": int(max_chars),
        "removed_negative_terms": removed_terms,
        "preserved_markers": [marker for marker in MARKERS if marker in compacted],
        "policy": "compact_after_ollama_vision_asmo_subject_lock_and_tap_sync",
        "foreground_motion_onset_enforced": True,
        "scene_description_preserved": SCENE_DESCRIPTION_MARKER in compacted,
    }

    expansion = patched.get("filename_hint_expansion")
    if isinstance(expansion, dict):
        expansion["negative_prompt_before_budget_compaction"] = expansion.get("negative_prompt")
        expansion["negative_prompt"] = sections[NEGATIVE_MARKER]

    return patched


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

    for item in plan.get("results", []) or []:
        compacted = compact_item_prompt(
            item,
            max_chars=max_chars,
            target_chars=target_chars,
        )
        before_lengths.append(int(compacted["prompt_budget"]["before_chars"]))
        after_lengths.append(int(compacted["prompt_budget"]["after_chars"]))
        results.append(compacted)

    patched["results"] = results
    patched["prompt_budget"] = {
        "status": "applied",
        "scene_count": len(results),
        "target_chars": int(target_chars),
        "hard_limit_chars": int(max_chars),
        "max_before_chars": max(before_lengths) if before_lengths else 0,
        "max_after_chars": max(after_lengths) if after_lengths else 0,
        "policy": "compact_after_all_prompt_layers_including_ollama_vision",
        "foreground_motion_onset_enforced": True,
        "scene_description_preserved": True,
    }
    return patched
