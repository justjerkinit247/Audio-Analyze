import base64

from audio_analyze.local_ai_client import LocalAIClient, LocalAIConfig
from audio_analyze.ltx_plan_prompt_expander import (
    build_subject_count_policy,
    expand_plan_data,
)
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


def sample_plan():
    return {
        "file_stem": "song",
        "analysis": {"tempo_bpm": 120.0},
        "results": [
            {
                "clip_index": 1,
                "file_stem": "song",
                "seed_image_used": "inputs/ltx_seed_images/scene_01_subject.png",
                "scene": {
                    "scene_index": 1,
                    "start": 0.0,
                    "end": 4.0,
                    "duration": 4.0,
                },
                "prompt_text": "old",
            }
        ],
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


def test_ollama_vision_request_includes_encoded_image(tmp_path):
    image = tmp_path / "seed.png"
    image.write_bytes(b"image-bytes")
    session = FakeSession({"message": {"content": "One subject in a studio."}})
    client = LocalAIClient(LocalAIConfig(model="gemma3:4b"), session=session)

    assert client.chat_text_with_images("system", "describe", [image]) == "One subject in a studio."
    sent = session.posts[0]["json"]["messages"][1]
    assert sent["images"] == [base64.b64encode(b"image-bytes").decode("ascii")]


def test_plan_prompt_contains_natural_language_seed_description():
    def fake_analyzer(image_path, model):
        return {
            "status": "complete",
            "provider": "ollama",
            "model": model,
            "description_format": "natural_language",
            "description": "One subject is visible from head to toe in a softly lit studio.",
        }

    patched = expand_plan_data(
        sample_plan(),
        provider="ollama",
        model="gemma3:4b",
        expander=fake_expander,
        image_analyzer=fake_analyzer,
    )
    prompt = patched["results"][0]["prompt_text"]
    assert SEED_IMAGE_DESCRIPTION_MARKER in prompt
    assert "One subject is visible from head to toe" in prompt
    assert prompt.index(SEED_IMAGE_DESCRIPTION_MARKER) < prompt.index("[AUDIO_TIMING]")


def test_subject_count_does_not_treat_two_props_as_two_people():
    policy = build_subject_count_policy(
        "scene_01_woman_in_studio.png",
        "woman in studio",
        "One woman stands between two chairs with two windows behind her.",
    )

    assert policy["has_pair"] is False
    assert policy["multiple_subjects"] is False
    assert "missing foreground partner" not in policy["negative_terms"]


def test_subject_count_accepts_explicit_two_subject_description():
    policy = build_subject_count_policy(
        "scene_01_studio.png",
        "studio",
        "Two visible dancers stand together in the foreground.",
    )

    assert policy["has_pair"] is True
    assert policy["multiple_subjects"] is True


def test_template_provider_disables_vision_by_default():
    def forbidden_analyzer(image_path, model):
        raise AssertionError("template mode must not call Ollama vision by default")

    patched = expand_plan_data(
        sample_plan(),
        provider="template",
        model=None,
        expander=fake_expander,
        image_analyzer=forbidden_analyzer,
    )

    assert patched["seed_image_analysis"]["status"] == "disabled"
    assert patched["seed_image_analysis"]["enabled"] is False
    assert patched["results"][0]["seed_image_analysis"]["status"] == "disabled"


def test_template_provider_can_explicitly_force_vision_analysis():
    calls = []

    def recording_analyzer(image_path, model):
        calls.append((image_path, model))
        return {
            "status": "complete",
            "provider": "ollama",
            "model": model or "gemma3:4b",
            "description_format": "natural_language",
            "description": "One visible subject stands in a studio.",
        }

    patched = expand_plan_data(
        sample_plan(),
        provider="template",
        model=None,
        expander=fake_expander,
        image_analyzer=recording_analyzer,
        analyze_images=True,
        vision_model="gemma3:4b",
    )

    assert calls == [("inputs/ltx_seed_images/scene_01_subject.png", "gemma3:4b")]
    assert patched["seed_image_analysis"]["status"] == "applied"


def test_vision_model_is_separate_from_expansion_model():
    calls = {}

    def recording_analyzer(image_path, model):
        calls["image_path"] = image_path
        calls["model"] = model
        return {
            "status": "complete",
            "provider": "ollama",
            "model": model,
            "description_format": "natural_language",
            "description": "One visible subject stands in a studio.",
        }

    patched = expand_plan_data(
        sample_plan(),
        provider="openai",
        model="gpt-4o",
        vision_model="gemma3:4b",
        expander=fake_expander,
        image_analyzer=recording_analyzer,
    )

    assert calls["model"] == "gemma3:4b"
    assert patched["results"][0]["prompt_expansion_model"] == "gpt-4o"
    assert patched["results"][0]["seed_image_analysis"]["model"] == "gemma3:4b"
