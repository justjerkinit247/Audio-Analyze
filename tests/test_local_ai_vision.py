import base64

from audio_analyze.local_ai_client import LocalAIClient, LocalAIConfig
from audio_analyze.ltx_plan_prompt_expander import expand_plan_data
from audio_analyze.ltx_seed_image_analyzer import SEED_IMAGE_DESCRIPTION_MARKER


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


def test_ollama_vision_request_includes_encoded_image(tmp_path):
    image = tmp_path / "seed.png"
    image.write_bytes(b"image-bytes")
    session = FakeSession({"message": {"content": "One subject in a studio."}})
    client = LocalAIClient(LocalAIConfig(model="gemma3:4b"), session=session)

    assert client.chat_text_with_images("system", "describe", [image]) == "One subject in a studio."
    sent = session.posts[0]["json"]["messages"][1]
    assert sent["images"] == [base64.b64encode(b"image-bytes").decode("ascii")]


def test_plan_prompt_contains_natural_language_seed_description():
    plan = {
        "file_stem": "song",
        "analysis": {"tempo_bpm": 120.0},
        "results": [{
            "clip_index": 1,
            "file_stem": "song",
            "seed_image_used": "inputs/ltx_seed_images/scene_01_subject.png",
            "scene": {"scene_index": 1, "start": 0.0, "end": 4.0, "duration": 4.0},
            "prompt_text": "old",
        }],
    }

    def fake_expander(scene_hint, filename, provider, model):
        return {
            "filename": filename,
            "scene_hint": scene_hint,
            "provider": provider,
            "model": model,
            "ltx_motion_prompt": "The subject moves with controlled rhythm.",
            "negative_prompt": "blur, drift",
            "motion_notes": [],
        }

    def fake_analyzer(image_path, model):
        return {
            "status": "complete",
            "provider": "ollama",
            "model": model,
            "description_format": "natural_language",
            "description": "One subject is visible from head to toe in a softly lit studio.",
        }

    patched = expand_plan_data(
        plan,
        provider="ollama",
        model="gemma3:4b",
        expander=fake_expander,
        image_analyzer=fake_analyzer,
    )
    prompt = patched["results"][0]["prompt_text"]
    assert SEED_IMAGE_DESCRIPTION_MARKER in prompt
    assert "One subject is visible from head to toe" in prompt
    assert prompt.index(SEED_IMAGE_DESCRIPTION_MARKER) < prompt.index("[AUDIO_TIMING]")
