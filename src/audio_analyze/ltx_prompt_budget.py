from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any
import math
import re


SUBJECT_LOCK_MARKER = "[SUBJECT_LOCK]"
SEED_IMAGE_DESCRIPTION_MARKER = "[SEED_IMAGE_DESCRIPTION]"
AUDIO_TIMING_MARKER = "[AUDIO_TIMING]"
TAP_SYNC_MARKER = "[TAP_SYNC]"
MOTION_MARKER = "[MOTION_PROMPT]"
NEGATIVE_MARKER = "[NEGATIVE_PROMPT]"
MARKERS = [
    SUBJECT_LOCK_MARKER,
    SEED_IMAGE_DESCRIPTION_MARKER,
    AUDIO_TIMING_MARKER,
    TAP_SYNC_MARKER,
    MOTION_MARKER,
    NEGATIVE_MARKER,
]

DEFAULT_MAX_CHARS = 5000
DEFAULT_TARGET_CHARS = 5000
DEFAULT_SEED_ANALYSIS_RETENTION_TARGET = 0.90
FOREGROUND_ONSET_DEADLINE_SECONDS = 0.10
FOREGROUND_PRIORITY_WINDOW_SECONDS = 0.50

FOREGROUND_ONSET_NEGATIVE_TERMS = [
    "frozen foreground subjects",
    "static lead pair",
    "delayed foreground motion",
    "background-only motion",
]

CRITICAL_NEGATIVE_TERMS = [
    "missing male dancer",
    "missing female dancer",
    "missing choir",
    "jumping",
    "feet leaving the floor",
    "missing dance partner",
    "removed background performers",
    "changed subject count",
    "removed visible subject",
    "added unrelated subject",
    "merged people",
    "hopping",
    "heels lifting",
    "standing up",
    "repeated squats",
    "whole-body bouncing",
    "vertical pelvic bouncing",
    "full-body pumping",
    "extra limbs",
    "distorted anatomy",
    "duplicate subject",
    "warped background",
    "flicker",
    "jittery motion",
    *FOREGROUND_ONSET_NEGATIVE_TERMS,
    "static opening frame",
    "frozen first frames",
    "delayed motion onset",
]

NONVISUAL_SECTION_HEADINGS = (
    "Recommendations for Video Orchestration",
    "Recommendations for Video",
)


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
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[match.group(1)] = text[match.end():end].strip()
    return prefix, sections


def _render_prompt(prefix: str, sections: dict[str, str]) -> str:
    blocks = [prefix.strip()] if prefix and prefix.strip() else []
    blocks.extend(
        f"{marker}\n{sections.get(marker, '').strip()}"
        for marker in MARKERS
        if marker in sections
    )
    return "\n\n".join(blocks).strip() + "\n"


def _truncate(text: str, limit: int, *, fill: bool = False) -> str:
    cleaned = _clean_inline(text)
    if limit <= 0:
        return ""
    if len(cleaned) <= limit:
        return cleaned

    candidate = cleaned[:limit].rstrip()
    if fill:
        boundary = candidate.rfind(" ")
        if boundary >= int(limit * 0.96):
            candidate = candidate[:boundary]
    else:
        boundary = max(
            candidate.rfind(". "),
            candidate.rfind("! "),
            candidate.rfind("? "),
            candidate.rfind("; "),
            candidate.rfind(", "),
        )
        if boundary >= int(limit * 0.72):
            candidate = candidate[: boundary + 1]
        else:
            word_boundary = candidate.rfind(" ")
            if word_boundary > 0:
                candidate = candidate[:word_boundary]
    return candidate.rstrip(" ,;:")


def _remove_named_section(text: str, heading: str) -> tuple[str, bool]:
    pattern = re.compile(
        rf"(?is)\n\s*(?:\*\*)?{re.escape(heading)}:(?:\*\*)?.*?"
        rf"(?=\n\s*(?:\*\*)?[A-Z][^\n]{{2,100}}:(?:\*\*)?\s*\n|\Z)"
    )
    updated, count = pattern.subn("\n", text)
    return updated, bool(count)


def _native_visual_core(description: str) -> tuple[str, list[str]]:
    text = str(description or "").replace("\r\n", "\n").strip()
    removed: list[str] = []
    if not text:
        return "", removed

    paragraphs = re.split(r"\n\s*\n", text)
    if paragraphs and re.match(
        r"(?is)^(okay|here(?:'|’)s|here is|certainly|sure)[,!\s]",
        paragraphs[0].strip(),
    ):
        paragraphs = paragraphs[1:]
        removed.append("conversational_intro")

    text = "\n\n".join(paragraphs)
    for heading in NONVISUAL_SECTION_HEADINGS:
        text, did_remove = _remove_named_section(text, heading)
        if did_remove:
            removed.append(heading)

    paragraphs = re.split(r"\n\s*\n", text)
    while paragraphs and re.search(
        r"(?is)(let me know|do you want me|that(?:'|’)s my full|i(?:'|’)ve tried)",
        paragraphs[-1],
    ):
        paragraphs.pop()
        if "conversational_outro" not in removed:
            removed.append("conversational_outro")

    text = "\n\n".join(paragraphs)
    text = re.sub(r"(?m)^\s*---+\s*$", "", text)
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"(?m)^\s*[*+-]\s+", "", text)
    text = re.sub(r"(?m)^\s*#{1,6}\s*", "", text)
    return _clean_inline(text), removed


def _seed_filename(item: dict[str, Any]) -> str:
    value = (
        item.get("seed_filename_used_for_prompt_hint")
        or item.get("seed_image_used")
        or "seed_image.png"
    )
    return Path(str(value).replace("\\", "/")).name


def _compact_prefix(item: dict[str, Any]) -> str:
    return (
        "Audio-and-image-to-video continuation. "
        f"Seed image filename used as the Ollama prompt hint: {_seed_filename(item)}. "
        "Preserve identity, layout, framing, lighting, and setting."
    )


def _standard_subject_lock(item: dict[str, Any], existing: str) -> str:
    policy = item.get("subject_count_policy") or {}
    if not policy and existing:
        return _truncate(existing, 520)
    parts = [
        "The seed image is authoritative for subject count and body layout.",
        "Preserve every visible person; do not add, remove, merge, replace, or hide subjects.",
    ]
    if policy.get("has_pair"):
        parts.append(
            "Keep the female lead dancer and male dance partner visible together throughout."
        )
    if policy.get("has_choir"):
        parts.append("Keep the existing choir visible in the background throughout.")
    elif policy.get("has_group"):
        parts.append("Keep all existing background performers visible.")
    if policy.get("multiple_subjects"):
        parts.append("Do not render the scene as solitary or single-person.")
    return " ".join(parts)


def _priority_subject_lock(item: dict[str, Any]) -> str:
    policy = item.get("subject_count_policy") or {}
    if policy.get("has_pair") and policy.get("has_choir"):
        return (
            "Keep female lead, male partner, and choir; do not add, remove, or merge people."
        )
    if policy.get("has_pair"):
        return "Keep female lead and male partner; do not add, remove, or merge people."
    if policy.get("has_group") or policy.get("has_choir"):
        return "Keep every visible performer; do not add, remove, or merge people."
    return "Keep every visible subject; do not add, remove, or merge subjects."


def _standard_audio_timing(item: dict[str, Any], existing: str) -> str:
    timing = item.get("audio_timing") or {}
    if not timing:
        return _truncate(existing, 520)
    scene = timing.get("scene_index") or item.get("clip_index") or 1
    start = _format_float(timing.get("start_seconds"))
    end = _format_float(timing.get("end_seconds"))
    duration = _format_float(timing.get("duration_seconds"))
    tempo = _format_float(timing.get("tempo_bpm"))
    alignment = "enabled" if timing.get("beat_alignment_enabled") else "disabled"
    return (
        f"Scene {scene}: {start}s to {end}s, duration {duration}s, tempo {tempo} BPM, "
        f"beat alignment {alignment}. Synchronize visible motion and camera accents to audio."
    )


def _priority_audio_timing(item: dict[str, Any]) -> str:
    timing = item.get("audio_timing") or {}
    start = _format_float(timing.get("start_seconds"))
    end = _format_float(timing.get("end_seconds"))
    tempo = _format_float(timing.get("tempo_bpm"))
    return f"{start}-{end}s, {tempo} BPM; sync to audio."


def _target_text(item: dict[str, Any], existing: str) -> str:
    targets = (item.get("tap_sync") or {}).get(
        "primary_sync_targets_relative_seconds"
    ) or []
    if targets:
        return ",".join(f"{float(value):.3f}" for value in targets) + "s"
    match = re.search(
        r"Primary tap-accent times inside this clip:\s*([^.]*)",
        existing or "",
        flags=re.I,
    )
    return _clean_inline(match.group(1)) if match else "none"


def _standard_tap_sync(item: dict[str, Any], existing: str) -> str:
    targets = _target_text(item, existing)
    profile = item.get("tap_motion_profile") or (
        item.get("tap_sync") or {}
    ).get("motion_profile")
    if profile == "localized_glute_pulse":
        return (
            f"Primary tap-accent times inside this clip: {targets}. "
            "FOREGROUND MOTION ONSET: begin visible motion on frame 1; do not wait for "
            "the first tap. At each clap, snare, hi-hat, or sharp tap, perform one "
            "compact localized twerk pulse: glute-cheek contraction, small backward "
            "pelvis pop, and controlled recoil. Both feet remain planted; heels stay "
            "down, knees bent, and body height stable. Do not convert the accents into "
            "jumping, hopping, standing up, repeated squats, whole-body bouncing, "
            "vertical pumping, or feet leaving the floor. Ignore bass-only boom hits."
        )
    return (
        f"Primary tap-accent times inside this clip: {targets}. Begin visible motion "
        "on frame 1. Use clap, snare, hi-hat, and sharp high-frequency accents as "
        "controlled action triggers. Land controlled visible action changes on each "
        "tap and ignore bass-only boom hits."
    )


def _priority_tap_sync(item: dict[str, Any], existing: str) -> str:
    targets = _target_text(item, existing)
    profile = item.get("tap_motion_profile") or (
        item.get("tap_sync") or {}
    ).get("motion_profile")
    if profile == "localized_glute_pulse":
        return (
            f"Taps:{targets}. Start 0.00s; each clap/snare/hi-hat: compact localized "
            "twerk pulse and glute-cheek contraction. Both feet remain planted; heels "
            "down, knees bent. Do not convert the accents into jumping. Ignore "
            "bass-only hits."
        )
    return (
        f"Taps:{targets}. Start 0.00s; clap/snare/hi-hat triggers. Land controlled "
        "visible action changes; ignore bass-only hits."
    )


def _compact_motion(item: dict[str, Any], existing: str, limit: int) -> str:
    source = _clean_inline(
        (item.get("filename_hint_expansion") or {}).get("ltx_motion_prompt")
        or existing
    )
    fallback = "Maintain continuous grounded motion."
    return _truncate(source or fallback, max(1, limit)) or fallback


def _negative_terms(item: dict[str, Any], existing: str) -> list[str]:
    expansion = item.get("filename_hint_expansion") or {}
    sources = [str(expansion.get("negative_prompt") or ""), existing]
    terms = [
        part.strip()
        for source in sources
        for part in _clean_inline(source).split(",")
        if part.strip()
    ]
    terms.extend(FOREGROUND_ONSET_NEGATIVE_TERMS)

    seen: set[str] = set()
    unique: list[str] = []
    for term in terms:
        key = term.lower()
        if key not in seen:
            seen.add(key)
            unique.append(term)
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
        if len(candidate) <= max(0, limit):
            kept.append(term)
        else:
            removed.append(term)
    return ", ".join(kept), removed


def _visual_source(item: dict[str, Any], parsed: dict[str, str]) -> str:
    analysis = item.get("seed_image_analysis") or {}
    return str(
        analysis.get("description")
        or analysis.get("prompt_context")
        or parsed.get(SEED_IMAGE_DESCRIPTION_MARKER)
        or "Use the visible seed image as the visual authority."
    ).strip()


def _standard_fixed_sections(
    item: dict[str, Any],
    parsed: dict[str, str],
) -> tuple[str, dict[str, str], list[str]]:
    negative, removed_negative = _compact_negative(
        item, parsed.get(NEGATIVE_MARKER, ""), 1150
    )
    return (
        _compact_prefix(item),
        {
            SUBJECT_LOCK_MARKER: _standard_subject_lock(
                item, parsed.get(SUBJECT_LOCK_MARKER, "")
            ),
            SEED_IMAGE_DESCRIPTION_MARKER: "",
            AUDIO_TIMING_MARKER: _standard_audio_timing(
                item, parsed.get(AUDIO_TIMING_MARKER, "")
            ),
            TAP_SYNC_MARKER: _standard_tap_sync(
                item, parsed.get(TAP_SYNC_MARKER, "")
            ),
            MOTION_MARKER: _compact_motion(
                item, parsed.get(MOTION_MARKER, ""), 420
            ),
            NEGATIVE_MARKER: negative,
        },
        removed_negative,
    )


def _retention_priority_sections(
    item: dict[str, Any],
    parsed: dict[str, str],
) -> tuple[str, dict[str, str], list[str]]:
    negative, removed_negative = _compact_negative(
        item, parsed.get(NEGATIVE_MARKER, ""), 70
    )
    return (
        "",
        {
            SUBJECT_LOCK_MARKER: _priority_subject_lock(item),
            SEED_IMAGE_DESCRIPTION_MARKER: "",
            AUDIO_TIMING_MARKER: _priority_audio_timing(item),
            TAP_SYNC_MARKER: _priority_tap_sync(
                item, parsed.get(TAP_SYNC_MARKER, "")
            ),
            MOTION_MARKER: (
                "Grounded paired motion."
                if (item.get("subject_count_policy") or {}).get("has_pair")
                else "Grounded continuous motion."
            ),
            NEGATIVE_MARKER: negative,
        },
        removed_negative,
    )


def compact_item_prompt(
    item: dict[str, Any],
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    target_chars: int = DEFAULT_TARGET_CHARS,
) -> dict[str, Any]:
    patched = deepcopy(item)
    original = str(item.get("prompt_text") or "")
    _, parsed = _split_prompt(original)
    hard_limit = max(1, int(max_chars))
    target = min(hard_limit, max(1, int(target_chars)))

    native = _visual_source(item, parsed)
    visual_core, removed_sections = _native_visual_core(native)
    visual_core = visual_core or "Use the visible seed image as the visual authority."
    desired = min(
        len(visual_core),
        int(math.ceil(len(visual_core) * DEFAULT_SEED_ANALYSIS_RETENTION_TARGET)),
    )

    prefix, sections, removed_negative = _standard_fixed_sections(item, parsed)
    fixed = _render_prompt(prefix, sections)
    available = max(0, target - len(fixed))
    retention_priority_used = False

    if len(visual_core) >= 500 and available < desired:
        prefix, sections, priority_removed = _retention_priority_sections(
            item, parsed
        )
        removed_negative.extend(priority_removed)
        fixed = _render_prompt(prefix, sections)
        available = max(0, target - len(fixed))
        retention_priority_used = True

    visual_context = _truncate(visual_core, available, fill=True)
    sections[SEED_IMAGE_DESCRIPTION_MARKER] = visual_context
    compacted = _render_prompt(prefix, sections)

    if len(compacted) > target:
        overflow = len(compacted) - target
        visual_context = _truncate(
            visual_context,
            max(0, len(visual_context) - overflow),
            fill=True,
        )
        sections[SEED_IMAGE_DESCRIPTION_MARKER] = visual_context
        compacted = _render_prompt(prefix, sections)

    if len(compacted) > hard_limit:
        overflow = len(compacted) - hard_limit
        visual_context = _truncate(
            visual_context,
            max(0, len(visual_context) - overflow),
            fill=True,
        )
        sections[SEED_IMAGE_DESCRIPTION_MARKER] = visual_context
        compacted = _render_prompt(prefix, sections)

    if len(compacted) > hard_limit:
        raise ValueError(
            f"Unable to compact final LTX prompt below {hard_limit} characters; "
            f"got {len(compacted)}"
        )

    core_chars = len(visual_core)
    prompt_chars = len(visual_context)
    visual_ratio = prompt_chars / core_chars if core_chars else 1.0
    native_ratio = prompt_chars / len(native) if native else 1.0

    analysis = deepcopy(patched.get("seed_image_analysis") or {})
    if analysis:
        analysis.update(
            prompt_context=visual_context,
            prompt_context_char_count=prompt_chars,
            prompt_context_selection="native_visual_core_budget_fit",
            visual_core_char_count=core_chars,
            visual_core_removed_sections=removed_sections,
            visual_core_retention_ratio=round(visual_ratio, 6),
        )
        patched["seed_image_analysis"] = analysis

    patched["seed_image_description_prompt_block"] = (
        f"{SEED_IMAGE_DESCRIPTION_MARKER}\n{visual_context}\n"
    )
    patched["prompt_text_before_budget_compaction"] = original
    patched["prompt_text"] = compacted
    patched["foreground_motion_onset"] = {
        "required": True,
        "deadline_seconds": FOREGROUND_ONSET_DEADLINE_SECONDS,
        "priority_window_seconds": FOREGROUND_PRIORITY_WINDOW_SECONDS,
        "first_tap_is_start_signal": False,
        "background_only_motion_forbidden": True,
    }
    patched["prompt_budget"] = {
        "status": "compacted" if original != compacted else "within_budget",
        "before_chars": len(original),
        "after_chars": len(compacted),
        "target_chars": target,
        "hard_limit_chars": hard_limit,
        "removed_negative_terms": list(dict.fromkeys(removed_negative)),
        "preserved_markers": [marker for marker in MARKERS if marker in compacted],
        "policy": "compact_after_ollama_asmo_subject_lock_and_tap_sync",
        "policy_version": "gemma_native_analysis_first_v3",
        "foreground_motion_onset_enforced": True,
        "seed_analysis_native_chars": len(native),
        "seed_analysis_visual_core_chars": core_chars,
        "seed_analysis_prompt_chars": prompt_chars,
        "seed_analysis_visual_retention_ratio": round(visual_ratio, 6),
        "seed_analysis_native_retention_ratio": round(native_ratio, 6),
        "seed_analysis_retention_target": DEFAULT_SEED_ANALYSIS_RETENTION_TARGET,
        "seed_analysis_retention_target_met": (
            visual_ratio >= DEFAULT_SEED_ANALYSIS_RETENTION_TARGET
        ),
        "seed_analysis_removed_nonvisual_sections": removed_sections,
        "seed_analysis_summary_model_used": False,
        "seed_analysis_retention_priority_used": retention_priority_used,
    }

    expansion = patched.get("filename_hint_expansion")
    if isinstance(expansion, dict):
        expansion["negative_prompt_before_budget_compaction"] = expansion.get(
            "negative_prompt"
        )
        expansion["negative_prompt"] = sections[NEGATIVE_MARKER]

    return patched


def compact_plan_prompts(
    plan: dict[str, Any],
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    target_chars: int = DEFAULT_TARGET_CHARS,
) -> dict[str, Any]:
    patched = deepcopy(plan)
    results = [
        compact_item_prompt(
            item,
            max_chars=max_chars,
            target_chars=target_chars,
        )
        for item in plan.get("results", []) or []
    ]
    patched["results"] = results
    budgets = [item["prompt_budget"] for item in results]
    patched["prompt_budget"] = {
        "status": "applied",
        "scene_count": len(results),
        "target_chars": min(int(target_chars), int(max_chars)),
        "hard_limit_chars": int(max_chars),
        "max_before_chars": max(
            (budget["before_chars"] for budget in budgets),
            default=0,
        ),
        "max_after_chars": max(
            (budget["after_chars"] for budget in budgets),
            default=0,
        ),
        "min_seed_analysis_visual_retention_ratio": min(
            (
                budget["seed_analysis_visual_retention_ratio"]
                for budget in budgets
            ),
            default=1.0,
        ),
        "seed_analysis_retention_target": DEFAULT_SEED_ANALYSIS_RETENTION_TARGET,
        "policy": "compact_after_ollama_asmo_subject_lock_and_tap_sync",
        "policy_version": "gemma_native_analysis_first_v3",
        "foreground_motion_onset_enforced": True,
    }
    return patched
