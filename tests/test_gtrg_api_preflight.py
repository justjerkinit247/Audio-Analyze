"""Standard-library-only synthetic tests for ComfyUI API graph preflight."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "gtrg_api_preflight.py"
spec = importlib.util.spec_from_file_location("gtrg_api_preflight", SCRIPT)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def scenario():
    # Six known handoffs, plus an enum/model loader and a non-graph literal.
    graph = {
        "1": {"class_type": "AAOSceneRenderInputs", "inputs": {
            "song_path": "SECRET_SONG_PATH",
        }},
        "2": {"class_type": "LTXVPreprocess", "inputs": {"image": ["1", 0]}},
        "3": {"class_type": "LTXVConditioning", "inputs": {"frame_rate": ["1", 1]}},
        "4": {"class_type": "EmptyLTXVLatentVideo", "inputs": {"length": ["1", 2]}},
        "5": {"class_type": "AAOFinishScene", "inputs": {"scene": "PRIVATE_SCENE"}},
        "6": {"class_type": "CreateVideo", "inputs": {
            "images": ["5", 0],
            "fps": ["5", 1],
            "audio": ["5", 2],
            "format": "mp4",
        }},
        "7": {"class_type": "LTXAVTextEncoderLoader", "inputs": {
            "ckpt_name": "model-a.safetensors",
        }},
    }
    info = {
        "AAOSceneRenderInputs": {
            "input": {"required": {"song_path": ["STRING", {}]}},
            "output": ["IMAGE", "FLOAT", "INT"],
            "output_name": ["seed_image", "fps", "render_frames"],
        },
        "LTXVPreprocess": {
            "input": {"required": {"image": ["IMAGE", {}]}},
            "output": ["IMAGE"], "output_name": ["image"],
        },
        "LTXVConditioning": {
            "input": {"required": {"frame_rate": ["FLOAT", {}]}},
            "output": ["CONDITIONING"], "output_name": ["positive"],
        },
        "EmptyLTXVLatentVideo": {
            "input": {"required": {"length": ["INT", {}]}},
            "output": ["LATENT"], "output_name": ["latent"],
        },
        "AAOFinishScene": {
            "input": {"required": {"scene": ["STRING", {}]}},
            "output": ["IMAGE", "FLOAT", "AUDIO"],
            "output_name": ["trimmed_frames", "fps", "original_soundtrack"],
        },
        "CreateVideo": {
            "input": {"required": {
                "images": ["IMAGE", {}], "fps": ["FLOAT", {}],
                "audio": ["AUDIO", {}], "format": [["mp4", "webm"], {}],
            }},
            "output": ["VIDEO"], "output_name": ["video"],
        },
        "LTXAVTextEncoderLoader": {
            "input": {"required": {
                "ckpt_name": [["model-a.safetensors", "model-b.safetensors"], {}],
            }},
            "output": ["CLIP"], "output_name": ["CLIP"],
        },
    }
    return graph, info


def test_structural_validation_passes_and_does_not_leak_literals():
    graph, info = scenario()
    report = m.validate_graph(graph, info)
    assert report["status"] == "READY_FOR_CONTROLLED_LOCAL_TEST", report["definite_blockers"]
    assert report["checked_dropdown_count"] == 2
    assert report["validated_reference_count"] == 6
    assert all(x == "PASS" for x in report["required_handoffs"].values())
    assert not report["render_verified"]
    assert not report["node_execution_performed"]
    raw = json.dumps(report)
    assert "SECRET_SONG_PATH" not in raw
    assert "PRIVATE_SCENE" not in raw
    assert "model-a.safetensors" not in raw


def test_missing_api_required_input_is_blocker():
    graph, info = scenario()
    del graph["7"]["inputs"]["ckpt_name"]
    report = m.validate_graph(graph, info)
    assert report["status"] == "BLOCKED_API_STATIC"
    assert any(x["kind"] == "required_api_input_missing" for x in report["definite_blockers"])


def test_unavailable_dropdown_value_is_blocker_without_echoing_selected_filename():
    graph, info = scenario()
    graph["7"]["inputs"]["ckpt_name"] = "SUPER_SECRET_INVALID_MODEL_FILENAME"
    report = m.validate_graph(graph, info)
    assert any(x["kind"] == "dropdown_value_not_available" for x in report["definite_blockers"])
    assert "SUPER_SECRET_INVALID_MODEL_FILENAME" not in json.dumps(report)


def test_invalid_output_slot_is_blocker():
    graph, info = scenario()
    graph["2"]["inputs"]["image"] = ["1", 99]
    report = m.validate_graph(graph, info)
    assert any(x["kind"] == "link_output_slot_invalid" for x in report["definite_blockers"])
    assert report["status"] == "BLOCKED_API_STATIC"


def test_original_soundtrack_link_missing_fails_closed():
    graph, info = scenario()
    graph["6"]["inputs"]["audio"] = ["1", 0]
    report = m.validate_graph(graph, info)
    assert any(x["kind"] == "handoff_missing_or_wrong_source" and "audio" in x["handoff"]
               for x in report["definite_blockers"])
    assert report["status"] == "BLOCKED_API_STATIC"


def test_missing_output_names_does_not_make_unverified_link_pass():
    graph, info = scenario()
    del info["AAOFinishScene"]["output_name"]
    report = m.validate_graph(graph, info)
    assert report["status"] == "API_INPUTS_VALID_HANDOFF_UNVERIFIED"
    assert any(x == "UNVERIFIED" for x in report["required_handoffs"].values())


def test_api_node_can_never_invoke_paid_cloud_node_during_audit():
    graph, info = scenario()
    graph["8"] = {"class_type": "LTXDirectImageToVideo", "inputs": {}}
    info["LTXDirectImageToVideo"] = {"input": {"required": {}}, "output": ["VIDEO"]}
    report = m.validate_graph(graph, info)
    assert any(x["kind"] == "external_paid_or_cloud_api_class_present"
               for x in report["definite_blockers"])
    assert report["modal_or_paid_api_calls"] == 0


def test_reject_saved_ui_format():
    try:
        m.read_api_graph({"nodes": [{"id": 1}], "links": []})
    except ValueError as exc:
        assert "GUI-save" in str(exc)
    else:
        raise AssertionError("UI format passed incorrectly")


def test_read_api_wrapper_recognized_without_echoing_inputs():
    graph, info = scenario()
    loaded = m.read_api_graph({"prompt": graph, "extra_data": {
        "SECRET_TOKEN": "do_not_export",
    }})
    assert len(loaded) == len(graph)
    assert m.validate_graph(loaded, info)["status"] == "READY_FOR_CONTROLLED_LOCAL_TEST"


def test_only_loopback_endpoints_allowed():
    import pytest
    with pytest.raises(ValueError, match="Only loopback"):
        m.get_object_info("https://external.example.invalid")
