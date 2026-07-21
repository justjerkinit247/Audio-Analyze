from __future__ import annotations

import json
import os
import re
from dataclasses import asdict
from typing import Any

try:
    from .local_ai_client import LocalAIClient, LocalAIConfig, LocalAIError
except ImportError:
    from local_ai_client import LocalAIClient, LocalAIConfig, LocalAIError


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

FINAL_PROMPT_SYSTEM = """You are the final prompt composer for LTX audio-and-image-to-video generation.

Return ONLY the exact final prompt that will be sent to LTX. Do not add explanations, notes, code fences, character counts, or conversational text.

Hard requirements:
- The complete response must be no more than {max_chars} Unicode characters.
- Aim for {target_min}-{target_max} characters when the source material is long enough.
- Use these section markers exactly once and in this exact order:
  [SUBJECT_LOCK]
  [SEED_IMAGE_DESCRIPTION]
  [AUDIO_TIMING]
  [TAP_SYNC]
  [MOTION_PROMPT]
  [NEGATIVE_PROMPT]
- The [SEED_IMAGE_DESCRIPTION] section is the priority. Condense the ENTIRE native Gemma image analysis into a rich, comprehensive description. Preserve every concrete useful visual fact: subject count, identities and appearance, wardrobe, pose, relationship, foreground/background layout, camera framing and angle, composition, depth, architecture, environment, lighting, color, texture, atmosphere, style, and visible action cues.
- Remove only conversational introductions/outros, requests for feedback, repeated wording, unsupported speculation, and generic video recommendations.
- Integrate the supplied subject, audio, tap, motion, and negative controls accurately and concisely.
- The seed image remains the visual authority. Do not invent new subjects, props, wardrobe, architecture, or scene changes.
- Do not omit the choir, foreground pair, cathedral, lighting, framing, or other concrete details present in the native analysis.
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


def _clean_prompt(text: str) -> str:
    value = str(text or "").strip()
    fence = re.fullmatch(r"```(?:text|markdown)?\s*(.*?)\s*```", value, re.DOTALL | re.I)
    if fence:
        value = fence.group(1).strip()

    first_marker = value.find(SUBJECT_LOCK_MARKER)
    if first_marker > 0:
        value = value[first_marker:]

    return value.strip()


def _section(prompt: str, marker: str, next_marker: str | None) -> str:
    if marker not in prompt:
        return ""
    tail = prompt.split(marker, 1)[1]
    if next_marker and next_marker in tail:
        tail = tail.split(next_marker, 1)[0]
    return tail.strip()


def _minimum_output_chars(native_chars: int, max_chars: int) -> int:
    if native_chars >= 4500:
        return min(max_chars - 250, 4550)
    if native_chars >= 3000:
        return min(max_chars - 500, max(3000, int(native_chars * 0.88)))
    return min(max_chars - 700, max(1200, int(native_chars * 0.80)))


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
        problems.append(
            f"prompt is {len(prompt)} characters; hard limit is {max_chars}"
        )

    minimum_chars = _minimum_output_chars(native_chars, max_chars)
    if len(prompt) < minimum_chars:
        problems.append(
            f"prompt is only {len(prompt)} characters; minimum target is {minimum_chars}"
        )

    positions: list[int] = []
    for marker in REQUIRED_MARKERS:
        count = prompt.count(marker)
        if count != 1:
            problems.append(f"{marker} appears {count} times instead of exactly once")
        positions.append(prompt.find(marker))

    if all(position >= 0 for position in positions) and positions != sorted(positions):
        problems.append("required markers are not in the required order")

    visual = _section(
        prompt,
        SEED_IMAGE_DESCRIPTION_MARKER,
        AUDIO_TIMING_MARKER,
    )
    minimum_visual = min(3600, max(1200, int(native_chars * 0.68)))
    if len(visual) < minimum_visual:
        problems.append(
            f"seed-image description is only {len(visual)} characters; "
            f"minimum target is {minimum_visual}"
        )

    return problems


def _control_payload(item: dict[str, Any]) -> dict[str, Any]:
    expansion = item.get("filename_hint_expansion") or {}
    analysis = item.get("seed_image_analysis") or {}
    return {
        "seed_filename": (
            item.get("seed_filename_used_for_prompt_hint")
            or item.get("seed_image_used")
        ),
        "native_image_analysis": analysis.get("description") or "",
        "subject_count_policy": item.get("subject_count_policy") or {},
        "subject_lock": item.get("subject_lock_prompt_block") or "",
        "audio_timing": item.get("audio_timing") or {},
        "audio_timing_prompt": item.get("audio_timing_prompt_block") or "",
        "tap_sync": item.get("tap_sync") or {},
        "tap_sync_prompt": item.get("tap_sync_prompt_block") or "",
        "motion_prompt": expansion.get("ltx_motion_prompt") or "",
        "negative_prompt": expansion.get("negative_prompt") or "",
        "choreography_policy": item.get("choreography_policy") or {},
        "prompt_transport_mode": item.get("prompt_transport_mode"),
    }


def _user_prompt(
    item: dict[str, Any],
    *,
    attempt: int,
    previous_prompt: str = "",
    previous_problems: list[str] | None = None,
    max_chars: int,
    target_min: int,
    target_max: int,
) -> str:
    payload = _control_payload(item)
    correction = ""
    if attempt > 1:
        correction = (
            "\n\nThe previous draft failed validation.\n"
            f"Problems: {json.dumps(previous_problems or [], ensure_ascii=False)}\n"
            f"Previous draft character count: {len(previous_prompt)}\n"
            "Rewrite it from the complete source. Preserve more visual detail, obey the "
            "marker contract, and stay inside the hard character limit.\n"
        )

    return (
        "Compose the exact final LTX prompt from this complete source package."
        f"\nHard maximum: {max_chars} characters."
        f"\nTarget range: {target_min}-{target_max} characters."
        f"{correction}\n\nSOURCE PACKAGE:\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
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
    effective_target_max = min(int(max_chars), int(target_max))
    effective_target_min = min(
        effective_target_max,
        max(_minimum_output_chars(len(native), max_chars), int(target_min)),
    )
    local_client = client or LocalAIClient(_config(selected_model))
    system = FINAL_PROMPT_SYSTEM.format(
        max_chars=int(max_chars),
        target_min=effective_target_min,
        target_max=effective_target_max,
    )

    previous_prompt = ""
    previous_problems: list[str] = []
    attempts: list[dict[str, Any]] = []

    for attempt in range(1, max(1, int(max_attempts)) + 1):
        raw = local_client.chat_text(
            system,
            _user_prompt(
                item,
                attempt=attempt,
                previous_prompt=previous_prompt,
                previous_problems=previous_problems,
                max_chars=max_chars,
                target_min=effective_target_min,
                target_max=effective_target_max,
            ),
        )
        prompt = _clean_prompt(raw)
        problems = validate_final_prompt(
            prompt,
            native_chars=len(native),
            max_chars=max_chars,
        )
        attempts.append(
            {
                "attempt": attempt,
                "raw_char_count": len(str(raw or "")),
                "clean_prompt_char_count": len(prompt),
                "problems": list(problems),
            }
        )
        if not problems:
            visual = _section(
                prompt,
                SEED_IMAGE_DESCRIPTION_MARKER,
                AUDIO_TIMING_MARKER,
            )
            return {
                "status": "complete",
                "provider": "ollama",
                "model": selected_model,
                "mode": "gemma_full_native_analysis_to_final_ltx_prompt",
                "source_native_analysis_chars": len(native),
                "final_prompt": prompt,
                "final_prompt_char_count": len(prompt),
                "seed_description_char_count": len(visual),
                "hard_limit_chars": int(max_chars),
                "target_min_chars": effective_target_min,
                "target_max_chars": effective_target_max,
                "attempt_count": attempt,
                "attempts": attempts,
                "validation_passed": True,
                "required_markers": list(REQUIRED_MARKERS),
                "config": asdict(local_client.config),
            }

        previous_prompt = prompt
        previous_problems = problems

    detail = "; ".join(previous_problems) or "unknown validation failure"
    raise ValueError(
        "Gemma could not produce a valid final LTX prompt after "
        f"{len(attempts)} attempts: {detail}"
    )
