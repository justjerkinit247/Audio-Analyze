"""Regression tests for 9-frame, two-step local-only ComfyUI LTX canary."""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "gtrg_tiny_ltx_local.py"
sys.path.insert(0, str(SCRIPT.parent))
spec = importlib.util.spec_from_file_location("gtrg_tiny_ltx_local", SCRIPT)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def fixture():
    graph = {
        "2": {"class_type": "AAOBuildPlan", "inputs": {"provider": "ollama"}},
        "4": {"class_type": "AAOSceneRenderInputs", "inputs": {}},
        "5": {"class_type": "LTXVPreprocess", "inputs": {"image": ["4", 0]}},
        "6": {"class_type": "LTXVConditioning", "inputs": {"frame_rate": ["4", 1]}},
        "7": {"class_type": "EmptyLTXVLatentVideo", "inputs": {
            "length": ["4", 2], "width": 1024, "height": 576,
        }},
        "8": {"class_type": "LTXVEmptyLatentAudio", "inputs": {
            "frames_number": ["4", 2],
        }},
        "9": {"class_type": "LTXVScheduler", "inputs": {"steps": 32}},
        "10": {"class_type": "AAOFinishScene", "inputs": {}},
        "11": {"class_type": "CreateVideo", "inputs": {
            "images": ["10", 0], "fps": ["10", 1], "audio": ["10", 2],
        }},
        "12": {"class_type": "SaveVideo", "inputs": {
            "video": ["11", 0], "filename_prefix": "ORIGINAL_PREFIX",
        }},
    }
    info = {
        "AAOBuildPlan": {
            "input": {"required": {"provider": [["ollama"], {}]}},
            "output": [],
            "output_name": [],
        },
        "AAOSceneRenderInputs": {
            "input": {"required": {}},
            "output": ["IMAGE", "FLOAT", "INT"],
            "output_name": ["seed_image", "fps", "render_frames"],
        },
        "LTXVPreprocess": {
            "input": {"required": {"image": ["IMAGE", {}]}},
            "output": [],
            "output_name": [],
        },
        "LTXVConditioning": {
            "input": {"required": {"frame_rate": ["FLOAT", {}]}},
            "output": [],
            "output_name": [],
        },
        "EmptyLTXVLatentVideo": {
            "input": {"required": {
                "length": ["INT", {"min": 1, "step": 8}],
                "width": ["INT", {"min": 64, "step": 32}],
                "height": ["INT", {"min": 64, "step": 32}],
            }},
            "output": [], "output_name": [],
        },
        "LTXVEmptyLatentAudio": {
            "input": {"required": {"frames_number": ["INT", {"min": 1}]}},
            "output": [], "output_name": [],
        },
        "LTXVScheduler": {
            "input": {"required": {"steps": ["INT", {"min": 1, "max": 80}]}},
            "output": [], "output_name": [],
        },
        "AAOFinishScene": {
            "input": {"required": {}},
            "output": ["IMAGE", "FLOAT", "AUDIO"],
            "output_name": ["trimmed_frames", "fps", "original_soundtrack"],
        },
        "CreateVideo": {
            "input": {"required": {
                "images": ["IMAGE", {}], "fps": ["FLOAT", {}],
                "audio": ["AUDIO", {}],
            }},
            "output": ["VIDEO"], "output_name": ["VIDEO"],
        },
        "SaveVideo": {
            "input": {"required": {
                "video": ["VIDEO", {}],
                "filename_prefix": ["STRING", {"default": "original"}],
            }},
            "output": [],
            "output_name": [],
        },
    }
    return graph, info


def test_local_tiny_video_patch_keeps_original_graph_and_audio_path():
    graph, info = fixture()
    old = copy.deepcopy(graph)
    clone, report = m.build_tiny(graph, info, "GTRG_Tiny_9f_test")
    assert graph == old
    assert clone["7"]["inputs"] == {"length": 9, "width": 288, "height": 512}
    assert clone["8"]["inputs"]["frames_number"] == 9
    assert clone["9"]["inputs"]["steps"] == 2
    assert clone["12"]["inputs"]["filename_prefix"] == "GTRG_Tiny_9f_test"
    assert clone["11"]["inputs"]["audio"] == ["10", 2]
    assert report["original_graph_handoffs_preserved_in_source"]
    assert report["video_frames"] == 9
    assert report["steps"] == 2


def test_reject_missing_sampler_reduction():
    graph, info = fixture()
    del graph["9"]
    try:
        m.build_tiny(graph, info, "GTRG_Tiny_9f_test")
    except ValueError as exc:
        assert "9-frame and 2-step" in str(exc)
    else:
        raise AssertionError("Should not queue unreduced GPU generation")


def test_reject_external_cloud_api_node():
    graph, info = fixture()
    graph["13"] = {"class_type": "LTXDirectImageToVideo", "inputs": {}}
    info["LTXDirectImageToVideo"] = {"input": {"required": {}}, "output": []}
    try:
        m.build_tiny(graph, info, "GTRG_Tiny_9f_test")
    except ValueError as exc:
        assert "preflight" in str(exc) or "cloud/API" in str(exc)
    else:
        raise AssertionError("Should reject cloud API node")


def test_reject_unset_ollama_provider():
    graph, info = fixture()
    graph["2"]["inputs"]["provider"] = "template"
    try:
        m.build_tiny(graph, info, "GTRG_Tiny_9f_test")
    except ValueError:
        pass
    else:
        raise AssertionError("Should refuse old invalid provider")


def test_minimum_model_contract_is_hard_stop():
    graph, info = fixture()
    info["EmptyLTXVLatentVideo"]["input"]["required"]["width"][1]["min"] = 512
    try:
        m.build_tiny(graph, info, "GTRG_Tiny_9f_test")
    except ValueError as exc:
        assert "disallows tiny" in str(exc)
    else:
        raise AssertionError("Should refuse unsupported dimensions")


def test_extra_upscaler_is_blocked_for_low_resource_test():
    graph, info = fixture()
    graph["13"] = {"class_type": "LTXVLatentUpsampler", "inputs": {}}
    info["LTXVLatentUpsampler"] = {"input": {"required": {}}, "output": []}
    try:
        m.build_tiny(graph, info, "GTRG_Tiny_9f_test")
    except ValueError as exc:
        assert "Refine/upscale" in str(exc)
    else:
        raise AssertionError("Should refuse extra expensive pass")


def test_only_targeted_id_cancelled(monkeypatch):
    calls = []
    monkeypatch.setattr(m, "_owned_job_in_queue", lambda id: (True, False))
    monkeypatch.setattr(m, "http_json", lambda route, data=None, **kw:
                        calls.append((route, data)) or {})
    result = m.cancel_own("my-id-9")
    assert result.get("targeted_interrupt_requested")
    assert calls == [("/interrupt", {"prompt_id": "my-id-9"})]


def test_queue_busy_does_not_submit_anything(monkeypatch):
    monkeypatch.setattr(m, "queue_empty", lambda: False)
    def never_submit(*args, **kwargs):
        raise AssertionError("Should not contact ComfyUI for render")
    monkeypatch.setattr(m, "http_json", never_submit)
    try:
        m.run_job({}, seconds=60, comfy_output=Path("not-used"), prefix="test")
    except RuntimeError as exc:
        assert "busy" in str(exc)
    else:
        raise AssertionError("Should refuse busy queue")


def test_report_does_not_contain_source_widget_values():
    graph, info = fixture()
    graph["2"]["inputs"]["SECRET_AUDIO_PATH"] = "C:/private/music/123.wav"
    clone, audit = m.build_tiny(graph, info, "GTRG_Tiny_9f_test")
    assert "C:/private/music" not in json.dumps(audit)


def test_custom_scheduler_can_be_limited_to_two_steps():
    graph, info = fixture()
    graph["9"]["class_type"] = "BetaSamplingScheduler"
    info["BetaSamplingScheduler"] = info.pop("LTXVScheduler")
    tiny, report = m.build_tiny(graph, info, "GTRG_Tiny_9f_test")
    assert tiny["9"]["inputs"]["steps"] == 2
    assert any(
        c["class_type"] == "BetaSamplingScheduler" and c["input_name"] == "steps"
        for c in report["changed_inputs"]
    )


def test_batch_size_forced_to_one_when_latent_nodes_support_it():
    graph, info = fixture()
    graph["7"]["inputs"]["batch_size"] = 4
    graph["8"]["inputs"]["batch_size"] = 2
    info["EmptyLTXVLatentVideo"]["input"]["required"]["batch_size"] = [
        "INT", {"min": 1, "max": 64}
    ]
    info["LTXVEmptyLatentAudio"]["input"]["required"]["batch_size"] = [
        "INT", {"min": 1, "max": 64}
    ]
    tiny, _ = m.build_tiny(graph, info, "GTRG_Tiny_9f_test")
    assert tiny["7"]["inputs"]["batch_size"] == 1
    assert tiny["8"]["inputs"]["batch_size"] == 1
    assert graph["7"]["inputs"]["batch_size"] == 4
    assert graph["8"]["inputs"]["batch_size"] == 2
