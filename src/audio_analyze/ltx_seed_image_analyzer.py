from __future__ import annotations

import os
import re
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
SEED_IMAGE_DESCRIPTION_MARKER = "[SEED_IMAGE_DESCRIPTION]"
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

VISION_SYSTEM_PROMPT = (
    "You are the visual-observation stage of an LTX image-to-video pipeline. "
    "Describe only what is visibly present in the supplied seed image. "
    "Return concise natural-language prose, not JSON, markdown, headings, bullets, or an animation prompt. "
    "Do not invent movement, future actions, hidden objects, backstory, emotions, names, ethnicity, or events. "
    "Do not give choreography instructions."
)

VISION_USER_PROMPT = (
    "Describe this seed image for a downstream animation prompt builder. Include the visible subject count, "
    "subject type, pose, orientation, camera framing, camera angle, visible body parts, clothing, environment, "
    "lighting, composition, art or photographic style, and important props. State uncertainty plainly when a "
    "detail is not clear. Keep the description between 60 and 140 words."
)


def _clean_description(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(r"^(?:description|scene description)\s*:\s*", "", text, flags=re.IGNORECASE)
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
    active_client = client or LocalAIClient(LocalAIConfig.from_env(model=active_model))
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
        "description": description,
        "image_path": serialize_path(path),
        "image_path_resolved": str(path.resolve()),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "observation_policy": "visible_details_only_no_motion_invention",
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
        "description": "",
        "image_path": serialize_path(image_path),
        "error_type": type(error).__name__,
        "error": str(error),
        "observation_policy": "visible_details_only_no_motion_invention",
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
