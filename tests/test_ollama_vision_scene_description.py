from __future__ import annotations

import base64
from pathlib import Path

from audio_analyze.image_analyzer import analyze_seed_image
from audio_analyze.local_ai_client import LocalAIClient, LocalAIConfig
from audio_analyze.ltx_plan_prompt_expander import (
    SCENE_DESCRIPTION_MARKER,
    expand_plan_data,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.posts = []

    def post(self, url, json, timeout):
        self.posts.append({"url": url, "json": json, "timeout": timeout})
        return FakeResponse(self.payload)


class FakeVisionAnalyzer:
    def __call__(self, image_path, *, model, filename_hint):
        return {
            "status": "complete",
            "provider": "ollama",
            "model": model,
            "image_path": str(image_path),
            "output_format": "natural_language_scene_description",
            "describes_observable_pixels_only": True,
            "motion_generation_allowed": False,
            "description": (
                "Two adult performers stand together in a full-body vertical frame. "
                "A choir is visible behind them under warm cathedral lighting."
            ),
        }


def fake_motion_expander(scene_hint, filename, provider, model):
    return {
        "filename": filename,
        "scene_hint": scene_hint,
        "provider": provider,
        "model": model,
        "ltx_motion_prompt": "The foreground subjects begin coordinated grounded movement.",
        "negative_prompt": "blurry motion, scene drift",
        "combined_ltx_text": "unused",
        "motion_notes": ["fake motion expander"],
    }


def sample_plan():
    return {
        "file_stem": "vision_test",
        "analysis": {
            "tempo_bpm": 120.0,
            "beat_alignment_enabled": True,
        },
        "results": [
            {
                "clip_index": 1,
                "file_stem": "vision_test",
                "source_audio_path": "inputs/audio/test.mp3",
                "seed_image_used": "inputs/ltx_seed_images/scene_01_duet.png",
                "scene": {
                    "scene_index": 1,
                    "start": 0.0,
                    "end": 4.0,
                    "duration": 4.0,
                },
                "prompt_text": "old prompt",
                "beat_alignment_enabled": True,
            }
        ],
    }


def test_local_ai_client_places_base64_images_on_user_message():
    session = FakeSession({"message": {"content": "One adult subject fills the frame."}})
    client = LocalAIClient(
        LocalAIConfig(model="gemma3:4b", timeout_seconds=12),
        session=session,
    )

    result = client.chat_text("system", "user", images=["YWJj"])

    assert result == "One adult subject fills the frame."
    payload = session.posts[0]["json"]
    assert payload["messages"][1]["images"] == ["YWJj"]
    assert "format" not in payload


def test_analyze_seed_image_returns_plain_english_and_sends_pixels(tmp_path: Path):
    image_path = tmp_path / "seed.png"
    image_bytes = b"not-a-real-png-but-valid-test-bytes"
    image_path.write_bytes(image_bytes)

    session = FakeSession(
        {
            "message": {
                "content": (
                    "One adult woman is shown in a full-body view facing the camera. "
                    "Both feet are visible on a concrete floor under soft daylight."
                )
            }
        }
    )
    client = LocalAIClient(LocalAIConfig(model="gemma3:4b"), session=session)

    result = analyze_seed_image(image_path, client=client)

    assert result["status"] == "complete"
    assert result["output_format"] == "natural_language_scene_description"
    assert result["motion_generation_allowed"] is False
    assert result["description"].startswith("One adult woman")
    payload = session.posts[0]["json"]
    assert payload["messages"][1]["images"] == [
        base64.b64encode(image_bytes).decode("ascii")
    ]
    assert "Return one concise natural-language paragraph" in payload["messages"][0]["content"]


def test_plan_expander_injects_scene_description_without_replacing_motion_logic():
    patched = expand_plan_data(
        sample_plan(),
        provider="ollama",
        model="gemma3:4b",
        vision_model="gemma3:4b",
        expander=fake_motion_expander,
        image_analyzer=FakeVisionAnalyzer(),
    )

    item = patched["results"][0]
    prompt = item["prompt_text"]

    assert patched["seed_image_analysis"]["complete_count"] == 1
    assert patched["seed_image_analysis"]["fallback_count"] == 0
    assert item["image_analysis_method"] == "ollama_vision_natural_language_scene_description"
    assert item["scene_description"].startswith("Two adult performers")
    assert SCENE_DESCRIPTION_MARKER in prompt
    assert "Observable opening-frame description: Two adult performers" in prompt
    assert "does not override audio timing, choreography policy, tap synchronization" in prompt
    assert "The foreground subjects begin coordinated grounded movement." in prompt
    assert item["subject_count_policy"]["multiple_subjects"] is True
    assert item["subject_count_policy"]["has_choir"] is True
