import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from audio_analyze import ltx_filename_hint_expander as expander
from audio_analyze.local_ai_client import LocalAIError


class FakeOllamaClient:
    def __init__(self, payload=None, error=None):
        self.payload = payload or {}
        self.error = error
        self.calls = []

    def chat_json(self, system, user, schema_hint=None):
        self.calls.append({"system": system, "user": user, "schema_hint": schema_hint})
        if self.error:
            raise self.error
        return dict(self.payload)


def test_ollama_provider_accepts_ltx_motion_prompt():
    client = FakeOllamaClient(
        {
            "ltx_motion_prompt": "The duck lifts through the keyhole while the camera drifts toward ocean clouds.",
            "negative_prompt": "blurry motion, malformed wings",
            "motion_notes": ["local model response"],
        }
    )

    expansion = expander.expand_scene_hint(
        "duck flies off keyhole to ocean clouds",
        filename="scene_01_duck_flies_off_keyhole_to_ocean_clouds.png",
        provider="ollama",
        model="gemma3:4b",
        client=client,
    )

    assert expansion["provider"] == "ollama"
    assert expansion["model"] == "gemma3:4b"
    assert "duck lifts" in expansion["ltx_motion_prompt"]
    assert "[MOTION_PROMPT]" in expansion["combined_ltx_text"]
    assert "[NEGATIVE_PROMPT]" in expansion["combined_ltx_text"]
    assert client.calls


def test_ollama_provider_maps_common_prompt_key_variant():
    client = FakeOllamaClient({"prompt": "The camera follows the bird into clouds.", "motion_notes": []})

    expansion = expander.expand_scene_hint(
        "bird flies into clouds",
        filename="scene_02_bird_flies_into_clouds.png",
        provider="ollama",
        model="gemma3:4b",
        client=client,
    )

    assert expansion["ltx_motion_prompt"] == "The camera follows the bird into clouds."
    assert "malformed wings" in expansion["negative_prompt"]


def test_ollama_provider_uses_deterministic_fallback_for_missing_prompt():
    client = FakeOllamaClient({"negative_prompt": "blurry motion"})

    expansion = expander.expand_scene_hint(
        "shadow moves across empty room",
        filename="scene_03_shadow_moves_across_empty_room.png",
        provider="ollama",
        model="gemma3:4b",
        client=client,
    )

    assert "shadow moves across empty room" in expansion["ltx_motion_prompt"]
    assert "deterministic fallback" in " ".join(expansion["motion_notes"])


def test_ollama_provider_falls_back_when_request_fails():
    client = FakeOllamaClient(error=LocalAIError("ollama offline"))

    expansion = expander.expand_scene_hint(
        "duck flies toward ocean clouds",
        filename="scene_04_duck_flies_toward_ocean_clouds.png",
        provider="ollama",
        model="gemma3:4b",
        client=client,
    )

    assert expansion["provider"] == "ollama"
    assert "duck flies toward ocean clouds" in expansion["ltx_motion_prompt"]
    assert "ollama offline" in " ".join(expansion["motion_notes"])


def test_apply_expansions_to_plan_data_uses_ollama_client_factory():
    plan = {
        "results": [
            {
                "clip_index": 1,
                "seed_image_used": "inputs/ltx_seed_images/scene_01_duck_flies_to_ocean_clouds.png",
                "seed_filename_prompt_hint": "duck flies to ocean clouds",
                "prompt_text": "Base LTX prompt.",
            }
        ]
    }
    client = FakeOllamaClient({"motion_prompt": "The duck flies as the camera pushes toward ocean clouds."})

    updated = expander.apply_expansions_to_plan_data(
        plan,
        provider="ollama",
        model="gemma3:4b",
        client_factory=lambda: client,
    )

    item = updated["results"][0]
    assert updated["filename_hint_expander"]["provider"] == "ollama"
    assert item["filename_hint_expansion"]["provider"] == "ollama"
    assert "The duck flies" in item["prompt_text"]
    assert "[NEGATIVE_PROMPT]" in item["prompt_text"]
