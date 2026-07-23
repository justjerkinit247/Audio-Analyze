from __future__ import annotations

import os
import re
from dataclasses import asdict
from typing import Any

try:
    from .local_ai_client import LocalAIClient, LocalAIConfig
except ImportError:
    from local_ai_client import LocalAIClient, LocalAIConfig


SUBJECT_LOCK_MARKER = "[SUBJECT_LOCK]"
SEED_IMAGE_DESCRIPTION_MARKER = "[SEED_IMAGE_DESCRIPTION]"
AUDIO_TIMING_MARKER = "[AUDIO_TIMING]"
TAP_SYNC_MARKER = "[TAP_SYNC]"
MOTION_MARKER = "[MOTION_PROMPT]"
NEGATIVE_MARKER = "[NEGATIVE_PROMPT]"
REQUIRED_MARKERS = (
    SUBJECT_LOCK_MARKER,
    SEED_IMAGE_DESCRIPTION_MARKER,
    AUDIO_TIMING_MARKER,
    TAP_SYNC_MARKER,
    MOTION_MARKER,
    NEGATIVE_MARKER,
)

DEFAULT_MAX_CHARS = 5000
DEFAULT_TARGET_MIN_CHARS = 4700
DEFAULT_TARGET_MAX_CHARS = 4980
DEFAULT_TIMEOUT_SECONDS = 600
DEFAULT_NUM_PREDICT = 2600
DEFAULT_TEMPERATURE = 0.2
DEFAULT_MAX_ATTEMPTS = 3


VISUAL_DESCRIPTION_SYSTEM = """You are Gemma's visual-description stage for an LTX image-to-video prompt.

Return ONLY the rich visual description that belongs inside [SEED_IMAGE_DESCRIPTION].
Do not return section markers, headings, bullets, code fences, character counts, notes, introductions, conclusions, or requests for feedback.

Your response will be inserted into the final LTX prompt VERBATIM. Python will not rewrite, summarize, truncate, or otherwise alter it after you return it.

HARD CHARACTER LIMIT: {description_max_chars} Unicode characters total, including spaces and line breaks.
TARGET: use approximately {description_target_min}-{description_target_max} characters when the source contains enough useful detail.

Condense the complete native image analysis while preserving its concrete visual substance: visible subject count and relationships, identities and appearance, wardrobe, pose, foreground/background layout, choir, cathedral architecture, stained glass, camera framing and angle, composition, depth, lighting, color, texture, atmosphere, photographic or cinematic style, and visible action cues. Remove only conversational filler, repeated wording, unsupported speculation, and generic recommendations. Do not invent anything that is not supported by the source analysis.
"""


LEGACY_FINAL_PROMPT_SYSTEM = """Return only the exact final LTX prompt. It must remain within {max_chars} Unicode characters and contain all required section markers exactly once in the required order."""


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


def _config(model: str) -> LocalAIConfig:
    return LocalAIConfig(
        provider="ollama",
        base_url=(
            os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip()
            or "http://127.0.0.1:11434"
        ).rstrip("/"),
        model=model,
        timeout_seconds=_int_env(
            "OLLAMA_FINAL_PROMPT_TIMEOUT_SECONDS",
            DEFAULT_TIMEOUT_SECONDS,
        ),
        temperature=_float_env(
            "OLLAMA_FINAL_PROMPT_TEMPERATURE",
            DEFAULT_TEMPERATURE,
        ),
        num_predict=_int_env(
            "OLLAMA_FINAL_PROMPT_NUM_PREDICT",
            DEFAULT_NUM_PREDICT,
        ),
    )


def _clean_response(text: str) -> str:
    value = str(text or "").strip()
    fence = re.fullmatch(r"```(?:text|markdown)?\s*(.*?)\s*```", value, re.DOTALL | re.I)
    if fence:
        value = fence.group(1).strip()
    return value


def _clean_inline(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _truncate_control(text: str, limit: int) -> str:
    value = _clean_inline(text)
    if len(value) <= limit:
        return value
    candidate = value[: max(1, limit - 1)].rstrip()
    boundary = max(candidate.rfind(". "), candidate.rfind("; "), candidate.rfind(", "))
    if boundary >= int(limit * 0.55):
        candidate = candidate[: boundary + 1].rstrip()
    else:
        word = candidate.rfind(" ")
        if word > 0:
            candidate = candidate[:word]
    return candidate.rstrip(" ,;:") + "."


def _section(prompt: str, marker: str, next_marker: str | None) -> str:
    if marker not in prompt:
        return ""
    tail = prompt.split(marker, 1)[1]
    if next_marker and next_marker in tail:
        tail = tail.split(next_marker, 1)[0]
    return tail.strip()


def _format_number(value: Any, digits: int = 2) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "unknown"


def _subject_lock(item: dict[str, Any]) -> str:
    policy = item.get("subject_count_policy") or {}
    parts = ["Preserve every visible subject and the seed image's body layout."]
    if policy.get("has_pair"):
        parts.append("Keep the foreground woman and man together and visible throughout.")
    if policy.get("has_choir"):
        parts.append("Keep the complete choir visible in the background.")
    elif policy.get("has_group"):
        parts.append("Keep all background performers visible in their original layout.")
    parts.append("Do not add, remove, merge, replace, hide, or duplicate people.")
    return " ".join(parts)


def _audio_timing(item: dict[str, Any]) -> str:
    timing = item.get("audio_timing") or {}
    scene_index = timing.get("scene_index") or item.get("clip_index") or 1
    start = _format_number(timing.get("start_seconds"), 2)
    end = _format_number(timing.get("end_seconds"), 2)
    duration = _format_number(timing.get("duration_seconds"), 2)
    tempo = _format_number(timing.get("tempo_bpm"), 2)
    alignment = "enabled" if timing.get("beat_alignment_enabled") else "disabled"
    return (
        f"Scene {scene_index}: {start}s-{end}s, duration {duration}s, {tempo} BPM, "
        f"beat alignment {alignment}. Keep visible motion synchronized to this audio window."
    )


def _target_text(item: dict[str, Any]) -> str:
    tap = item.get("tap_sync") or {}
    targets = tap.get("primary_sync_targets_relative_seconds") or []
    if not targets:
        return "no reliable tap accents detected"
    return ", ".join(f"{float(value):.3f}s" for value in targets)


def _tap_sync(item: dict[str, Any]) -> str:
    profile = item.get("tap_motion_profile") or (item.get("tap_sync") or {}).get(
        "motion_profile"
    )
    targets = _target_text(item)
    if profile == "localized_glute_pulse":
        return (
            f"Primary tap accents: {targets}. Begin visible foreground motion immediately at 0.00s. "
            "At each clap, snare, hi-hat, or sharp tap use one compact localized twerk pulse: "
            "a glute-cheek contraction, small backward pelvis pop, and controlled recoil. "
            "Both feet remain planted, heels down, knees bent, and body height stable. "
            "Maintain subtle pelvic micro-motion between taps. Do not convert the accents into jumping, "
            "hopping, standing up, repeated squats, whole-body bouncing, or feet leaving the floor. "
            "Ignore bass-only boom hits."
        )
    return (
        f"Primary tap accents: {targets}. Begin visible foreground motion immediately. "
        "Use sharp clap, snare, hi-hat, and high-frequency tap accents for controlled visible action changes. "
        "Maintain coherent motion between accents and ignore bass-only boom hits."
    )


def _motion(item: dict[str, Any]) -> str:
    expansion = item.get("filename_hint_expansion") or {}
    source = expansion.get("ltx_motion_prompt") or "Maintain continuous grounded motion and stable camera movement."
    return _truncate_control(str(source), 260)


def _negative(item: dict[str, Any]) -> str:
    expansion = item.get("filename_hint_expansion") or {}
    policy = item.get("choreography_policy") or {}
    subject = item.get("subject_count_policy") or {}
    terms: list[str] = []
    for source in (
        str(expansion.get("negative_prompt") or "").split(","),
        list(policy.get("negative_terms") or []),
        list(subject.get("negative_terms") or []),
        [
            "extra limbs",
            "distorted anatomy",
            "jumping",
            "feet leaving the floor",
            "missing male dancer",
            "missing female dancer",
            "missing choir",
            "changed subject count",
            "warped background",
            "flicker",
        ],
    ):
        for raw in source:
            value = _clean_inline(raw).strip(" ,")
            if value and value.lower() not in {item.lower() for item in terms}:
                terms.append(value)
    return _truncate_control(", ".join(terms), 380)


def _control_sections(item: dict[str, Any]) -> dict[str, str]:
    return {
        SUBJECT_LOCK_MARKER: _subject_lock(item),
        SEED_IMAGE_DESCRIPTION_MARKER: "",
        AUDIO_TIMING_MARKER: _audio_timing(item),
        TAP_SYNC_MARKER: _tap_sync(item),
        MOTION_MARKER: _motion(item),
        NEGATIVE_MARKER: _negative(item),
    }


def _render_sections(sections: dict[str, str]) -> str:
    blocks = [f"{marker}\n{sections.get(marker, '').strip()}" for marker in REQUIRED_MARKERS]
    return "\n\n".join(blocks).strip()


def _minimum_output_chars(native_chars: int, max_chars: int) -> int:
    if native_chars >= 4500:
        return min(max_chars - 250, 4550)
    if native_chars >= 3000:
        return min(max_chars - 400, max(3000, int(native_chars * 0.82)))
    return min(max_chars - 500, max(1200, int(native_chars * 0.72)))


def validate_final_prompt(
    prompt: str,
    *,
    native_chars: int,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> list[str]:
    problems: list[str] = []
    if not prompt:
        return ["Gemma returned an empty final prompt."]
    if len(prompt) > max_chars:
        problems.append(f"prompt is {len(prompt)} characters; hard limit is {max_chars}")
    positions: list[int] = []
    for marker in REQUIRED_MARKERS:
        count = prompt.count(marker)
        if count != 1:
            problems.append(f"{marker} appears {count} times instead of exactly once")
        positions.append(prompt.find(marker))
    if all(position >= 0 for position in positions) and positions != sorted(positions):
        problems.append("required markers are not in the required order")
    visual = _section(prompt, SEED_IMAGE_DESCRIPTION_MARKER, AUDIO_TIMING_MARKER)
    minimum_visual = min(3200, max(1000, int(native_chars * 0.58)))
    if len(visual) < minimum_visual:
        problems.append(
            f"seed-image description is only {len(visual)} characters; minimum target is {minimum_visual}"
        )
    return problems


def _legacy_full_prompt(value: str) -> bool:
    return all(marker in value for marker in REQUIRED_MARKERS)


def _visual_user_prompt(
    native: str,
    *,
    attempt: int,
    description_max_chars: int,
    description_target_min: int,
    description_target_max: int,
    previous_length: int | None = None,
) -> str:
    correction = ""
    if attempt > 1:
        correction = (
            f"\nYour previous response was {previous_length} characters. Rewrite it so it is no more than "
            f"{description_max_chars} characters while preserving more concrete visual detail than filler."
        )
    return (
        f"Create the final visual description from the complete native analysis below.\n"
        f"HARD MAXIMUM BEFORE YOU BEGIN: {description_max_chars} Unicode characters.\n"
        f"Preferred range: {description_target_min}-{description_target_max} characters."
        f"{correction}\n\nCOMPLETE NATIVE IMAGE ANALYSIS:\n{native}"
    )


def synthesize_final_ltx_prompt(
    item: dict[str, Any],
    *,
    client: LocalAIClient | None = None,
    model: str | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
    target_min: int = DEFAULT_TARGET_MIN_CHARS,
    target_max: int = DEFAULT_TARGET_MAX_CHARS,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> dict[str, Any]:
    analysis = item.get("seed_image_analysis") or {}
    native = str(analysis.get("description") or "").strip()
    if not native:
        raise ValueError("Cannot synthesize the final LTX prompt without Gemma's native analysis.")

    selected_model = (
        model
        or str(analysis.get("model") or "").strip()
        or os.environ.get("OLLAMA_VISION_MODEL", "gemma3:4b").strip()
        or "gemma3:4b"
    )
    local_client = client or LocalAIClient(_config(selected_model))

    sections = _control_sections(item)
    fixed_prompt = _render_sections(sections)
    description_max_chars = int(max_chars) - len(fixed_prompt)
    if description_max_chars < 1000:
        raise ValueError(
            "The required nonvisual LTX controls leave only "
            f"{description_max_chars} characters for Gemma's description."
        )
    description_target_max = max(1, description_max_chars - 20)
    description_target_min = min(
        description_target_max,
        max(1200, int(description_max_chars * 0.88)),
    )
    system = VISUAL_DESCRIPTION_SYSTEM.format(
        description_max_chars=description_max_chars,
        description_target_min=description_target_min,
        description_target_max=description_target_max,
    )

    attempts: list[dict[str, Any]] = []
    previous_length: int | None = None
    for attempt in range(1, max(1, int(max_attempts)) + 1):
        raw = local_client.chat_text(
            system,
            _visual_user_prompt(
                native,
                attempt=attempt,
                description_max_chars=description_max_chars,
                description_target_min=description_target_min,
                description_target_max=description_target_max,
                previous_length=previous_length,
            ),
        )
        value = _clean_response(raw)

        if _legacy_full_prompt(value):
            problems = validate_final_prompt(
                value,
                native_chars=len(native),
                max_chars=max_chars,
            )
            attempts.append(
                {
                    "attempt": attempt,
                    "response_mode": "legacy_full_prompt",
                    "raw_char_count": len(str(raw or "")),
                    "clean_prompt_char_count": len(value),
                    "problems": list(problems),
                }
            )
            if not problems:
                visual = _section(value, SEED_IMAGE_DESCRIPTION_MARKER, AUDIO_TIMING_MARKER)
                return {
                    "status": "complete",
                    "provider": "ollama",
                    "model": selected_model,
                    "mode": "legacy_full_prompt_compatibility",
                    "source_native_analysis_chars": len(native),
                    "final_prompt": value,
                    "final_prompt_char_count": len(value),
                    "seed_description": visual,
                    "seed_description_char_count": len(visual),
                    "description_char_limit_given_before_generation": description_max_chars,
                    "description_modified_after_generation": False,
                    "hard_limit_chars": int(max_chars),
                    "target_min_chars": int(target_min),
                    "target_max_chars": int(target_max),
                    "attempt_count": attempt,
                    "attempts": attempts,
                    "validation_passed": True,
                    "required_markers": list(REQUIRED_MARKERS),
                    "config": asdict(local_client.config),
                }
            previous_length = len(value)
            continue

        visual = value
        visual_problems: list[str] = []
        if not visual:
            visual_problems.append("Gemma returned an empty visual description")
        if len(visual) > description_max_chars:
            visual_problems.append(
                f"visual description is {len(visual)} characters; exact limit supplied beforehand was {description_max_chars}"
            )
        if len(visual) < min(2200, int(description_max_chars * 0.62)):
            visual_problems.append(
                f"visual description is only {len(visual)} characters and does not use enough of the available budget"
            )

        attempts.append(
            {
                "attempt": attempt,
                "response_mode": "bounded_visual_description",
                "raw_char_count": len(str(raw or "")),
                "visual_description_char_count": len(visual),
                "description_char_limit_given_before_generation": description_max_chars,
                "problems": list(visual_problems),
            }
        )
        if visual_problems:
            previous_length = len(visual)
            continue

        sections[SEED_IMAGE_DESCRIPTION_MARKER] = visual
        final_prompt = _render_sections(sections)
        problems = validate_final_prompt(
            final_prompt,
            native_chars=len(native),
            max_chars=max_chars,
        )
        if problems:
            attempts[-1]["problems"].extend(problems)
            previous_length = len(visual)
            continue

        return {
            "status": "complete",
            "provider": "ollama",
            "model": selected_model,
            "mode": "gemma_bounded_visual_description_python_envelope",
            "source_native_analysis_chars": len(native),
            "final_prompt": final_prompt,
            "final_prompt_char_count": len(final_prompt),
            "seed_description": visual,
            "seed_description_char_count": len(visual),
            "description_char_limit_given_before_generation": description_max_chars,
            "description_target_min_chars": description_target_min,
            "description_target_max_chars": description_target_max,
            "description_modified_after_generation": False,
            "hard_limit_chars": int(max_chars),
            "target_min_chars": int(target_min),
            "target_max_chars": int(target_max),
            "attempt_count": attempt,
            "attempts": attempts,
            "validation_passed": True,
            "required_markers": list(REQUIRED_MARKERS),
            "config": asdict(local_client.config),
        }

    last = attempts[-1]["problems"] if attempts else ["unknown validation failure"]
    raise ValueError(
        "Gemma could not produce a bounded visual description after "
        f"{len(attempts)} attempts: {'; '.join(str(problem) for problem in last)}"
    )
