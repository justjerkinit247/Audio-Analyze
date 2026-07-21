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

    return {
        "status": "complete",
        "provider": "ollama",
        "model": active_model,
        "description_format": "natural_language",
        "analysis_mode": VISION_ANALYSIS_MODE,
        "description": description,
        "description_char_count": len(description),
        "description_line_count": len(description.splitlines()),
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
        "image_path": serialize_path(image_path),
        "error_type": type(error).__name__,
        "error": str(error),
        "observation_policy": "freeform_native_visual_analysis",
    }


def render_seed_image_description_block(analysis: dict[str, Any]) -> str:
    description = str(analysis.get("description") or "").strip()
    if description:
        body = description
    else:
        error = str(analysis.get("error") or "analysis unavailable").strip()
        body = (
            f"Seed-image analysis unavailable: {error}. "
            "Use the visible seed image as the visual authority."
        )
    return f"{SEED_IMAGE_DESCRIPTION_MARKER}\n{body}\n"
