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

Return ONLY the rich visual description that belongs inside the final [SEED_IMAGE_DESCRIPTION] section.
Do not return any section label, heading, bullet list, code fence, character count, note, introduction, conclusion, or request for feedback.
Never output any of these reserved strings: [SUBJECT_LOCK], [SEED_IMAGE_DESCRIPTION], [AUDIO_TIMING], [TAP_SYNC], [MOTION_PROMPT], [NEGATIVE_PROMPT].

Your response will be inserted into a Python-owned final LTX prompt envelope VERBATIM. Python will not rewrite, summarize, truncate, or otherwise alter your descriptive wording after you return it.

HARD CHARACTER LIMIT: {description_max_chars} Unicode characters total, including spaces and line breaks.
TARGET: use as much of the available allowance as naturally useful, but never exceed {description_max_chars} characters.

Condense the complete native image analysis while preserving concrete visible substance: subject count and relationships, appearance, wardrobe, pose, foreground/background layout, environment, architecture, props, camera framing and angle, composition, depth, lighting, color, texture, atmosphere, photographic or cinematic style, and visible action cues. Remove only conversational filler, repeated wording, unsupported speculation, and generic recommendations. Do not invent anything unsupported by the source analysis.
"""


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
    fence = re.fullmatch(
        r"```(?:text|markdown)?\s*(.*?)\s*```",
        value,
        re.DOTALL | re.I,
    )
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
    boundary = max(
        candidate.rfind(". "),
        candidate.rfind("; "),
        candidate.rfind(", "),
    )
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
    requirements = [
        _clean_inline(value)
        for value in list(policy.get("requirements") or [])
        if _clean_inline(value)
    ]
    if requirements:
        return _truncate_control(" ".join(requirements), 720)

    parts = [
        "Preserve every visible subject and the seed image's exact body layout.",
        "Do not add, remove, merge, replace, hide, or duplicate any visible subject.",
    ]
    if policy.get("has_pair"):
        parts.append(
            "Keep both visible foreground subjects together and visible throughout."
        )
    if policy.get("has_choir"):
        parts.append("Keep the complete existing choir visible in the background.")
    elif policy.get("has_group"):
        parts.append(
            "Keep every existing background performer visible in the original layout."
        )
    if policy.get("multiple_subjects"):
        parts.append("Do not render the scene as solitary, solo, lone, or single-person.")
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
        f"Scene {scene_index}: {start}s-{end}s, duration {duration}s, "
        f"{tempo} BPM, beat alignment {alignment}. Keep visible motion "
        "synchronized to this supplied-audio window."
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
            f"Primary tap accents: {targets}. Begin visible foreground motion "
            "immediately at 0.00s. At each clap, snare, hi-hat, or sharp tap use "
            "one compact localized twerk pulse: a glute-cheek contraction, small "
            "backward pelvis pop, and controlled recoil. Both feet remain planted, "
            "heels down, knees bent, and body height stable. Maintain subtle pelvic "
            "micro-motion between taps. Do not convert the accents into jumping, "
            "hopping, standing up, repeated squats, whole-body bouncing, or feet "
            "leaving the floor. Do not use kick-drum or bass-only boom hits as major "
            "movement triggers."
        )
    return (
        f"Primary tap accents: {targets}. Begin visible foreground motion immediately. "
        "Use sharp clap, snare, hi-hat, and similar high-frequency tap transients as "
        "visible motion triggers. Land controlled visible action changes on each listed "
        "primary tap accent. Maintain coherent foreground motion between accents. Do not "
        "use kick-drum or bass-only boom hits as major movement triggers."
    )


def _motion(item: dict[str, Any]) -> str:
    expansion = item.get("filename_hint_expansion") or {}
    source = expansion.get("ltx_motion_prompt") or (
        "Maintain continuous grounded motion and stable camera movement."
    )
    return _truncate_control(str(source), 300)


def _negative(item: dict[str, Any]) -> str:
    expansion = item.get("filename_hint_expansion") or {}
    choreography = item.get("choreography_policy") or {}
    subject = item.get("subject_count_policy") or {}
    defaults = [
        "extra limbs",
        "distorted anatomy",
        "jumping",
        "feet leaving the floor",
        "missing visible foreground subject",
        "changed subject count",
        "warped background",
        "flicker",
    ]
    if subject.get("has_pair"):
        defaults.append("missing foreground partner")
    if subject.get("has_choir"):
        defaults.append("missing choir")
    elif subject.get("has_group"):
        defaults.append("missing background performers")

    terms: list[str] = []
    seen: set[str] = set()
    for source in (
        str(expansion.get("negative_prompt") or "").split(","),
        list(choreography.get("negative_terms") or []),
        list(subject.get("negative_terms") or []),
        defaults,
    ):
        for raw in source:
            value = _clean_inline(raw).strip(" ,")
            key = value.lower()
            if value and key not in seen:
                seen.add(key)
                terms.append(value)
    return _truncate_control(", ".join(terms), 430)


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
    return "\n\n".join(
        f"{marker}\n{str(sections.get(marker, '')).strip()}"
        for marker in REQUIRED_MARKERS
    ).strip()


def validate_final_prompt(
    prompt: str,
    *,
    native_chars: int,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> list[str]:
    del native_chars  # Retained in the public signature for compatibility.
    problems: list[str] = []
    if not prompt:
        return ["Gemma returned an empty final prompt."]
    if len(prompt) > max_chars:
        problems.append(
            f"prompt is {len(prompt)} characters; hard limit is {max_chars}"
        )
    if not prompt.lstrip().startswith(SUBJECT_LOCK_MARKER):
        problems.append("final prompt does not begin with [SUBJECT_LOCK]")

    positions: list[int] = []
    for marker in REQUIRED_MARKERS:
        count = prompt.count(marker)
        if count != 1:
            problems.append(
                f"{marker} appears {count} times instead of exactly once"
            )
        positions.append(prompt.find(marker))
    if all(position >= 0 for position in positions) and positions != sorted(positions):
        problems.append("required markers are not in the required order")
    visual = _section(
        prompt,
        SEED_IMAGE_DESCRIPTION_MARKER,
        AUDIO_TIMING_MARKER,
    )
    if not visual.strip():
        problems.append("seed-image description is empty")
    return problems


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
            f"\nYour previous response was {previous_length} characters. "
            f"Rewrite it so it is no more than {description_max_chars} characters. "
            "Do not include any section label or reserved marker."
        )
    return (
        "Create the final visual description from the complete native analysis below.\n"
        f"HARD MAXIMUM BEFORE YOU BEGIN: {description_max_chars} Unicode characters.\n"
        f"Preferred range: {description_target_min}-{description_target_max} characters, "
        "but a shorter complete response is acceptable."
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
        raise ValueError(
            "Cannot synthesize the final LTX prompt without Gemma's native analysis."
        )

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
        max(800, int(description_max_chars * 0.75)),
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
        visual = _clean_response(raw)
        visual_problems: list[str] = []
        if not visual:
            visual_problems.append("Gemma returned an empty visual description")
        if len(visual) > description_max_chars:
            visual_problems.append(
                f"visual description is {len(visual)} characters; exact limit supplied "
                f"beforehand was {description_max_chars}"
            )
        for forbidden_marker in REQUIRED_MARKERS:
            if forbidden_marker in visual:
                visual_problems.append(
                    f"Gemma included forbidden control marker {forbidden_marker}"
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
        f"{len(attempts)} attempts: "
        + "; ".join(str(problem) for problem in last)
    )
