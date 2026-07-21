from __future__ import annotations

import base64
import re
from pathlib import Path
from typing import Any

try:
    from .local_ai_client import LocalAIClient, LocalAIConfig, LocalAIError
    from .path_policy import resolve_runtime_path, serialize_path
except ImportError:
    from local_ai_client import LocalAIClient, LocalAIConfig, LocalAIError
    from path_policy import resolve_runtime_path, serialize_path


DEFAULT_OLLAMA_VISION_MODEL = "gemma3:4b"
MAX_SCENE_DESCRIPTION_CHARS = 1400
ALLOWED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}

VISION_SYSTEM_PROMPT = (
    "You are the visual-observation stage of an image-to-video pipeline. "
    "Describe only what is visibly present in the supplied seed image. "
    "Return one concise natural-language paragraph, not JSON, not markdown, and not a list. "
    "Report subject count, subject type, pose, orientation, visible limbs, clothing, props, "
    "camera framing, camera angle, composition, environment, lighting, art or photographic style, "
    "and any spatial detail that matters for preserving the opening frame. "
    "Do not invent motion, choreography, events, dialogue, intentions, backstory, or unseen details. "
    "Do not write an animation prompt. Do not tell the downstream model what should happen next."
)

VISION_USER_PROMPT = (
    "Analyze this image as the opening frame of an LTX image-to-video shot. "
    "Describe the observable scene accurately in approximately 80 to 150 words. "
    "Use direct descriptive sentences. Preserve uncertainty when a detail is unclear."
)


def _collapse_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _truncate_description(value: str, max_chars: int = MAX_SCENE_DESCRIPTION_CHARS) -> str:
    text = _collapse_spaces(value)
    if len(text) <= max_chars:
        return text
    clipped = text[: max_chars + 1]
    sentence_end = max(clipped.rfind(". "), clipped.rfind("! "), clipped.rfind("? "))
    if sentence_end >= max_chars // 2:
        return clipped[: sentence_end + 1].strip()
    return clipped[:max_chars].rsplit(" ", 1)[0].rstrip(" ,;:") + "."


def _fallback_description(image_path: Path, filename_hint: str | None = None) -> str:
    hint = _collapse_spaces(filename_hint or image_path.stem.replace("_", " ").replace("-", " "))
    if hint:
        return (
            "The seed image could not be visually analyzed during this run. "
            f"The filename provides only this limited contextual hint: {hint}. "
            "The seed pixels remain authoritative for subject count, framing, pose, wardrobe, lighting, and environment."
        )
    return (
        "The seed image could not be visually analyzed during this run. "
        "The seed pixels remain authoritative for subject count, framing, pose, wardrobe, lighting, and environment."
    )


def _encode_image(image_path: Path) -> str:
    return base64.b64encode(image_path.read_bytes()).decode("ascii")


def analyze_seed_image(
    image_path: str | Path,
    *,
    model: str | None = DEFAULT_OLLAMA_VISION_MODEL,
    client: Any = None,
    filename_hint: str | None = None,
) -> dict[str, Any]:
    """Return a plain-English scene description from a local Ollama vision model.

    The model output is natural language. The surrounding dictionary is pipeline
    metadata so the description, provider status, and fallback reason can be
    audited in the run plan.
    """

    resolved = resolve_runtime_path(image_path)
    active_model = model or DEFAULT_OLLAMA_VISION_MODEL
    base_result: dict[str, Any] = {
        "provider": "ollama",
        "model": active_model,
        "image_path": serialize_path(resolved),
        "image_path_resolved": str(resolved.resolve()),
        "output_format": "natural_language_scene_description",
        "describes_observable_pixels_only": True,
        "motion_generation_allowed": False,
    }

    if not resolved.is_file():
        return {
            **base_result,
            "status": "fallback",
            "description": _fallback_description(resolved, filename_hint),
            "error": f"Seed image was not found: {resolved}",
        }

    if resolved.suffix.lower() not in ALLOWED_IMAGE_SUFFIXES:
        return {
            **base_result,
            "status": "fallback",
            "description": _fallback_description(resolved, filename_hint),
            "error": f"Unsupported seed image type: {resolved.suffix or '<none>'}",
        }

    if client is None:
        client = LocalAIClient(LocalAIConfig.from_env(model=active_model))

    try:
        description = client.chat_text(
            VISION_SYSTEM_PROMPT,
            VISION_USER_PROMPT,
            images=[_encode_image(resolved)],
        )
        description = _truncate_description(description)
        if not description:
            raise LocalAIError("Ollama vision analysis returned an empty scene description.")
    except (LocalAIError, OSError) as exc:
        return {
            **base_result,
            "status": "fallback",
            "description": _fallback_description(resolved, filename_hint),
            "error": str(exc),
        }

    return {
        **base_result,
        "status": "complete",
        "description": description,
        "character_count": len(description),
    }
