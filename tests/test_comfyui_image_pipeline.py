from __future__ import annotations

import json

from audio_analyze.comfyui_image_pipeline import (
    DEFAULT_NEGATIVE_PROMPT,
    ComfyUIClient,
    compile_image_prompt,
    generate_image_jobs,
    load_api_workflow,
    prepare_api_workflow,
)


class FakeResponse:
    def __init__(self, payload=None, content=b""):
        self.payload = payload or {}
        self.content = content

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self):
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("get", url, kwargs))
        if url.endswith("/system_stats"):
            return FakeResponse({"system": {"comfyui_version": "test"}})
        if "/history/" in url:
            prompt_id = url.rsplit("/", 1)[-1]
            return FakeResponse({
                prompt_id: {
                    "status": {"status_str": "success", "completed": True},
                    "outputs": {
                        "9": {
                            "images": [
                                {
                                    "filename": "AudioAnalyze_00001_.png",
                                    "subfolder": "",
                                    "type": "output",
                                }
                            ]
                        }
                    },
                }
            })
        if url.endswith("/view"):
            return FakeResponse(content=b"test-png-bytes")
        raise AssertionError(f"Unexpected GET: {url}")

    def post(self, url, **kwargs):
        self.calls.append(("post", url, kwargs))
        if url.endswith("/prompt"):
            return FakeResponse({"prompt_id": "prompt-test-1", "number": 1})
        raise AssertionError(f"Unexpected POST: {url}")


def test_default_api_workflow_is_valid_and_uses_known_node_ids():
    workflow = load_api_workflow()
    assert workflow["3"]["class_type"] == "KSampler"
    assert workflow["4"]["class_type"] == "CheckpointLoaderSimple"
    assert workflow["6"]["class_type"] == "CLIPTextEncode"
    assert workflow["7"]["class_type"] == "CLIPTextEncode"
    assert workflow["9"]["class_type"] == "SaveImage"


def test_prepare_workflow_sets_prompts_seed_checkpoint_and_sdxl_dimensions():
    workflow = load_api_workflow()
    prepared = prepare_api_workflow(
        workflow,
        positive_prompt="Photorealistic gospel performance scene, dramatic church lighting.",
        negative_prompt="bad anatomy",
        checkpoint="RealVisXL_V5.0_fp16.safetensors",
        width=768,
        height=1024,
        steps=30,
        cfg=5.4,
        seed=42,
        filename_prefix="test_scene",
    )

    assert prepared["6"]["inputs"]["text"].startswith("Photorealistic")
    assert prepared["7"]["inputs"]["text"] == "bad anatomy"
    assert prepared["4"]["inputs"]["ckpt_name"] == "RealVisXL_V5.0_fp16.safetensors"
    assert prepared["3"]["inputs"]["seed"] == 42
    assert prepared["3"]["inputs"]["steps"] == 30
    assert prepared["3"]["inputs"]["cfg"] == 5.4
    assert prepared["5"]["inputs"]["width"] == 768
    assert prepared["5"]["inputs"]["height"] == 1024
    assert prepared["9"]["inputs"]["filename_prefix"] == "test_scene"
    assert workflow["6"]["inputs"]["text"] != prepared["6"]["inputs"]["text"]


def test_audio_context_is_secondary_and_preserves_visual_brief():
    prompt = compile_image_prompt(
        "A woman in a white suit dancing in a cathedral.",
        {"tempo_bpm": 142.0},
    )
    assert prompt.startswith("A woman in a white suit dancing in a cathedral.")
    assert "142.0 BPM" in prompt
    assert "fast, high-energy" in prompt
    assert "do not add literal musical symbols" in prompt


def test_comfyui_client_queues_waits_and_downloads_output(tmp_path):
    session = FakeSession()
    client = ComfyUIClient(session=session)
    workflow = load_api_workflow()
    result = client.generate(
        workflow,
        tmp_path,
        filename_stem="scene_01_cathedral",
        timeout_seconds=5,
        poll_interval_seconds=0.25,
    )
    assert result["status"] == "complete"
    assert result["prompt_id"] == "prompt-test-1"
    saved = tmp_path / "scene_01_cathedral.png"
    assert saved.read_bytes() == b"test-png-bytes"
    assert any(call[1].endswith("/prompt") for call in session.calls)
    assert any(call[1].endswith("/view") for call in session.calls)


def test_image_job_runner_writes_generation_report(tmp_path):
    session = FakeSession()
    client = ComfyUIClient(session=session)
    workflow_path = load_api_workflow_path_for_test()
    report = generate_image_jobs(
        [{"name": "scene_01_cathedral", "prompt": "Two adult dancers in a cathedral."}],
        workflow_path=workflow_path,
        output_dir=tmp_path / "run",
        client=client,
        timeout_seconds=5,
        poll_interval_seconds=0.25,
        global_seed=10,
    )
    assert report["status"] == "complete"
    assert report["images"][0]["seed"] == 10
    assert (tmp_path / "run" / "generation_report.json").is_file()
    assert report["images"][0]["images"]


def load_api_workflow_path_for_test():
    from pathlib import Path
    return Path(__file__).resolve().parents[1] / "workflows" / "comfyui_sdxl_api.json"
