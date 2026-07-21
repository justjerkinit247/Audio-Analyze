from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .local_ai_client import LocalAIClient, LocalAIConfig, LocalAIError
    from .path_policy import resolve_runtime_path, serialize_path
except ImportError:
    from local_ai_client import LocalAIClient, LocalAIConfig, LocalAIError
    from path_policy import resolve_runtime_path, serialize_path


DEFAULT_OLLAMA_VISION_MODEL = "gemma3:4b"
DEFAULT_OLLAMA_VISION_NUM_PREDICT = 2048
DEFAULT_OLLAMA_VISION_TIMEOUT_SECONDS = 600
DEFAULT_OLLAMA_VISION_PROMPT_CONTEXT_CHARS = 1400
SEED_IMAGE_DESCRIPTION_MARKER = "[SEED_IMAGE_DESCRIPTION]"
VISION_ANALYSIS_MODE = "freeform_native"
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

VISION_SYSTEM_PROMPT = (
    "You are an expert visual analyst. Your complete response will be preserved and supplied "
    "to a downstream image-to-video orchestrator. Analyze the supplied image independently, "
    "freely, thoroughly, and naturally. Use your own judgment about what is visually important. "
    "There is no required checklist, schema, response format, or word limit. Return the full "
    "analysis you would ordinarily provide when asked to analyze an image."
)

VISION_USER_PROMPT = (
    "Analyze this seed image thoroughly for an image-to-video project. Return your complete "
    "native analysis. Include anything you judge visually meaningful or useful, and do not "
    "shorten, summarize, or force the response into a predefined structure. The downstream "
    "orchestrator will decide what to use."
)

PROMPT_CONTEXT_SYSTEM_PROMPT = (
    "You are the downstream image-to-video orchestrator selecting visual context from a complete "
    "native image analysis. Preserve the most useful current-frame facts for generation: visible "
    "subjects and relationships, pose and body layout, framing and camera perspective, environment, "
    "lighting, composition, style, atmosphere, textures, props, and unusual constraints. Do not "
    "invent details. Return only the selected visual context as natural-language prose."
)


def _env_positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default)).strip() or str(default)
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _vision_config(model: str) -> LocalAIConfig:
    base = LocalAIConfig.from_env(model=model)
    return LocalAIConfig(
        provider=base.provider,
        base_url=base.base_url,
        model=base.model,
        timeout_seconds=_env_positive_int(
            "OLLAMA_VISION_TIMEOUT_SECONDS",
            max(base.timeout_seconds, DEFAULT_OLLAMA_VISION_TIMEOUT_SECONDS),
        ),
        temperature=base.temperature,
        num_predict=_env_positive_int(
            "OLLAMA_VISION_NUM_PREDICT",
            DEFAULT_OLLAMA_VISION_NUM_PREDICT,
        ),
    )


def _clean_description(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise LocalAIError("Ollama returned an empty seed-image description.")
    return text


def _fallback_prompt_context(description: str, max_chars: int) -> str:
    if len(description) <= max_chars:
        return description

    candidate = description[:max_chars].rstrip()
    sentence_end = max(candidate.rfind("."), candidate.rfind("!"), candidate.rfind("?"))
    if sentence_end >= max_chars // 2:
        candidate = candidate[: sentence_end + 1]
    return candidate.rstrip()


def _select_prompt_context(
    description: str,
    *,
    client: Any,
    max_chars: int,
) -> tuple[str, str]:
    if len(description) <= max_chars:
        return description, "full_native_analysis"

    user_prompt = (
        f"Select the most useful visual context from the complete analysis below. "
        f"Keep the result at or below {max_chars} characters so it can fit inside the final "
        "LTX prompt. The complete analysis remains preserved separately.\n\n"
        f"COMPLETE NATIVE ANALYSIS:\n{description}"
    )

    try:
        selected = _clean_description(
            client.chat_text(
                PROMPT_CONTEXT_SYSTEM_PROMPT,
                user_prompt,
            )
        )
    except Exception:
        return _fallback_prompt_context(description, max_chars), "deterministic_fallback"

    if len(selected) > max_chars:
        selected = _fallback_prompt_context(selected, max_chars)
        return selected, "ollama_selection_trimmed"

    return selected, "ollama_orchestrator_selection"


def analyze_seed_image(
    image_path: str | Path,
    *,
    model: str | None = None,
    client: Any = None,
) -> dict[str, Any]:
    path = resolve_runtime_path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"Seed image not found: {path.resolve()}")
    if path.suffix.lower() not in ALLOWED_IMAGE_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_IMAGE_EXTENSIONS))
        raise ValueError(f"Unsupported seed image type {path.suffix!r}; expected one of: {allowed}")

    active_model = (
        model
        or os.environ.get("OLLAMA_VISION_MODEL")
        or os.environ.get("OLLAMA_MODEL")
        or DEFAULT_OLLAMA_VISION_MODEL
    )
    active_client = client or LocalAIClient(_vision_config(active_model))
    description = _clean_description(
        active_client.chat_text_with_images(
            VISION_SYSTEM_PROMPT,
            VISION_USER_PROMPT,
            [path],
        )
    )
    prompt_context_limit = _env_positive_int(
        "OLLAMA_VISION_PROMPT_CONTEXT_CHARS",
        DEFAULT_OLLAMA_VISION_PROMPT_CONTEXT_CHARS,
    )
    prompt_context, prompt_context_selection = _select_prompt_context(
        description,
        client=active_client,
        max_chars=prompt_context_limit,
    )

    return {
        "status": "complete",
        "provider": "ollama",
        "model": active_model,
        "description_format": "natural_language",
        "analysis_mode": VISION_ANALYSIS_MODE,
        "description": description,
        "description_char_count": len(description),
        "description_line_count": len(description.splitlines()),
        "prompt_context": prompt_context,
        "prompt_context_char_count": len(prompt_context),
        "prompt_context_limit_chars": prompt_context_limit,
        "prompt_context_selection": prompt_context_selection,
        "image_path": serialize_path(path),
        "image_path_resolved": str(path.resolve()),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "observation_policy": "freeform_native_visual_analysis",
    }


def failed_seed_image_analysis(
    image_path: str | Path,
    error: Exception,
    *,
    model: str | None = None,
) -> dict[str, Any]:
    return {
        "status": "failed",
        "provider": "ollama",
        "model": (
            model
            or os.environ.get("OLLAMA_VISION_MODEL")
            or os.environ.get("OLLAMA_MODEL")
            or DEFAULT_OLLAMA_VISION_MODEL
        ),
        "description_format": "natural_language",
        "analysis_mode": VISION_ANALYSIS_MODE,
        "description": "",
        "prompt_context": "",
        "image_path": serialize_path(image_path),
        "error_type": type(error).__name__,
        "error": str(error),
        "observation_policy": "freeform_native_visual_analysis",
    }


def render_seed_image_description_block(analysis: dict[str, Any]) -> str:
    description = str(
        analysis.get("prompt_context")
        or analysis.get("description")
        or ""
    ).strip()
    if description:
        body = description
    else:
        error = str(analysis.get("error") or "analysis unavailable").strip()
        body = (
            f"Seed-image analysis unavailable: {error}. "
            "Use the visible seed image as the visual authority."
        )
    return f"{SEED_IMAGE_DESCRIPTION_MARKER}\n{body}\n"
