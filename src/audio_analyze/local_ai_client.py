from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

import requests


class LocalAIError(RuntimeError):
    """Raised when the local AI provider cannot complete a request."""


@dataclass(frozen=True)
class LocalAIConfig:
    provider: str = "ollama"
    base_url: str = "http://127.0.0.1:11434"
    model: str = "gemma3:4b"
    timeout_seconds: int = 240
    temperature: float = 0.25
    num_predict: int = 700

    @classmethod
    def from_env(cls, model: str | None = None) -> "LocalAIConfig":
        timeout_raw = os.environ.get("LOCAL_AI_TIMEOUT_SECONDS", "240").strip() or "240"
        try:
            timeout_seconds = int(timeout_raw)
        except ValueError:
            timeout_seconds = 240

        return cls(
            provider=os.environ.get("LOCAL_AI_PROVIDER", "ollama").strip() or "ollama",
            base_url=(os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip() or "http://127.0.0.1:11434").rstrip("/"),
            model=model or os.environ.get("OLLAMA_MODEL", "gemma3:4b").strip() or "gemma3:4b",
            timeout_seconds=timeout_seconds,
        )


def extract_json_object(text: str) -> dict[str, Any]:
    """Parse a JSON object from local model output.

    Local models sometimes return strict JSON, sometimes wrap JSON in prose or
    markdown. This helper accepts a single object and extracts the first object
    block when needed.
    """

    content = str(text or "").strip()
    if not content:
        raise LocalAIError("Local AI returned empty content.")

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, flags=re.DOTALL)
        if not match:
            raise LocalAIError("Local AI did not return a JSON object.")
        data = json.loads(match.group(0))

    if not isinstance(data, dict):
        raise LocalAIError("Local AI JSON response was not an object.")
    return data


class LocalAIClient:
    def __init__(self, config: LocalAIConfig | None = None, session: Any = None) -> None:
        self.config = config or LocalAIConfig.from_env()
        if self.config.provider != "ollama":
            raise LocalAIError(f"Unsupported local AI provider: {self.config.provider}")
        self.session = session or requests

    def _chat_payload(self, system: str, user: str, json_mode: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.config.model,
            "stream": False,
            "options": {
                "temperature": self.config.temperature,
                "num_predict": self.config.num_predict,
            },
            "messages": [
                {"role": "system", "content": str(system or "")},
                {"role": "user", "content": str(user or "")},
            ],
        }
        if json_mode:
            payload["format"] = "json"
        return payload

    def _post_chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.config.base_url}/api/chat"
        try:
            response = self.session.post(url, json=payload, timeout=self.config.timeout_seconds)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise LocalAIError(f"Ollama request failed at {url}: {exc}") from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise LocalAIError("Ollama response was not valid JSON.") from exc

        if not isinstance(data, dict):
            raise LocalAIError("Ollama response was not a JSON object.")
        return data

    def chat_text(self, system: str, user: str) -> str:
        data = self._post_chat(self._chat_payload(system, user, json_mode=False))
        message = data.get("message", {})
        content = message.get("content", "") if isinstance(message, dict) else ""
        content = str(content).strip()
        if not content:
            raise LocalAIError("Ollama returned no message content.")
        return content

    def chat_json(self, system: str, user: str, schema_hint: str | None = None) -> dict[str, Any]:
        prompt = str(user or "")
        if schema_hint:
            prompt = f"{prompt}\n\nJSON schema/context hint:\n{schema_hint}"
        data = self._post_chat(self._chat_payload(system, prompt, json_mode=True))
        message = data.get("message", {})
        content = message.get("content", "") if isinstance(message, dict) else ""
        return extract_json_object(str(content))

    def health_check(self) -> dict[str, Any]:
        url = f"{self.config.base_url}/api/tags"
        try:
            response = self.session.get(url, timeout=min(self.config.timeout_seconds, 30))
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            return {
                "ok": False,
                "provider": self.config.provider,
                "model": self.config.model,
                "base_url": self.config.base_url,
                "error": str(exc),
            }
        except ValueError as exc:
            return {
                "ok": False,
                "provider": self.config.provider,
                "model": self.config.model,
                "base_url": self.config.base_url,
                "error": f"Invalid JSON from Ollama tags endpoint: {exc}",
            }

        return {
            "ok": True,
            "provider": self.config.provider,
            "model": self.config.model,
            "base_url": self.config.base_url,
            "models": data.get("models", []) if isinstance(data, dict) else [],
        }
