"""Synthetic static preflight regression tests: no rendering and no leaked widget literals."""
import importlib.util
import json
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "gtrg_native_preflight.py"
# The entry script imports its sibling gtrg_workflow_wiring module.
sys.path.insert(0, str(SOURCE.parent))
spec = importlib.util.spec_from_file_location("gtrg_native_preflight", SOURCE)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def fixture():
    classes = [
        "AAOSceneRenderInputs", "LTXVPreprocess", "LTXVConditioning",
        "EmptyLTXVLatentVideo", "AAOFinishScene", "CreateVideo",
    ]
    outputs = {
        1: ["seed_image", "fps", "render_frames"],
        2: [], 3: [], 4: [],
        5: ["trimmed_frames", "fps", "original_soundtrack"],
        6: [],
    }
    inputs = {
        2: ["image"], 3: ["frame_rate"], 4: ["length"],
        6: ["images", "fps", "audio"],
    }
    nodes = []
    for index, cls in enumerate(classes, 1):
        nodes.append({
            "id": index, "type": cls,
            "outputs": [{"name": p, "links": []} for p in outputs[index]],
            "inputs": [{"name": p, "link": None} for p in inputs.get(index, [])],
            "widgets_values": [
                "SECRET_BEARER_API_KEY",
                "C:/confidential/music/song.mp3",
            ],
        })
    links = []
    for source, source_slot, target, target_slot in [
        (1, 0, 2, 0), (1, 1, 3, 0), (1, 2, 4, 0),
        (5, 0, 6, 0), (5, 1, 6, 1), (5, 2, 6, 2),
    ]:
        link_id = 100 + len(links)
        links.append([link_id, source, source_slot, target, target_slot, "*"])
        nodes[target - 1]["inputs"][target_slot]["link"] = link_id
    return {
        "nodes": nodes, "links": links,
        "extra": {"token": "SECRET_IN_METADATA"},
    }


def mock_object_info(doc):
    return {
        node["type"]: {
            "input": {
                "required": {
                    port["name"]: ["IMAGE", {}]
                    for port in node["inputs"]
                },
            },
            "output": [],
        }
        for node in doc["nodes"]
    }


def test_complete_wiring_detected_without_leaking_inputs():
    doc = fixture()
    report = m.preflight_ui_document(doc, mock_object_info(doc), m.DEFAULT_WORKFLOW)
    assert report["status"] == "READY_FOR_API_GRAPH_VALIDATION", report["definite_blockers"]
    assert report["handoff_checks"]["original_audio_to_video"]
    text = json.dumps(report)
    for secret in (
        "SECRET_BEARER_API_KEY", "C:/confidential",
        "SECRET_IN_METADATA",
    ):
        assert secret not in text
    assert not report["did_execute_graph"]
    assert not report["did_call_modal_or_paid_apis"]


def test_missing_original_audio_handoff_fails_closed():
    doc = fixture()
    doc["links"] = doc["links"][:-1]
    doc["nodes"][-1]["inputs"][-1]["link"] = None
    report = m.preflight_ui_document(doc, mock_object_info(doc), m.DEFAULT_WORKFLOW)
    assert report["status"] == "BLOCKED_STATIC"
    assert not report["handoff_checks"]["original_audio_to_video"]
    assert any(
        issue["kind"] == "unconnected_required_socket"
        for issue in report["definite_blockers"]
    )


def test_missing_registered_node_is_a_blocker():
    doc = fixture()
    classes = mock_object_info(doc)
    classes.pop("EmptyLTXVLatentVideo")
    report = m.preflight_ui_document(doc, classes, m.DEFAULT_WORKFLOW)
    assert report["registered_node_classes_missing"] == 1
    assert report["status"] == "BLOCKED_STATIC"


def test_external_api_node_is_flagged_without_executing_it():
    doc = fixture()
    doc["nodes"].append({
        "id": 77, "type": "LTXDirectImageToVideo",
        "inputs": [], "outputs": [],
    })
    report = m.preflight_ui_document(doc, mock_object_info(doc), m.DEFAULT_WORKFLOW)
    assert "LTXDirectImageToVideo" in report["external_api_node_classes"]
    assert report["did_call_modal_or_paid_apis"] is False


def test_scalar_widget_without_socket_does_not_false_fail():
    doc = fixture()
    classes = mock_object_info(doc)
    classes["AAOFinishScene"]["input"]["required"]["caption"] = [
        "STRING", {"default": "caption"},
    ]
    report = m.preflight_ui_document(doc, classes, m.DEFAULT_WORKFLOW)
    assert not [
        issue for issue in report["definite_blockers"]
        if issue.get("port") == "caption"
    ]


def test_cli_refuses_nonlocal_host(monkeypatch):
    import pytest
    monkeypatch.setattr(
        sys, "argv", ["preflight", "--server", "https://example.com"],
    )
    with pytest.raises(SystemExit) as error:
        m.main()
    assert error.value.code == 2


def test_connected_dropdown_widgets_are_not_required_cables():
    """These six inputs are selected in GUI widgets, then checked in API export."""
    doc = fixture()
    known = [
        ("KSamplerSelect", ["sampler_name"]),
        ("SaveVideo", ["format"]),
        ("LTXAVTextEncoderLoader", ["text_encoder", "ckpt_name", "device"]),
        ("LTXVAudioVAELoader", ["ckpt_name"]),
    ]
    next_id = 100
    definitions = mock_object_info(doc)
    for cls, names in known:
        doc["nodes"].append({
            "id": next_id,
            "type": cls,
            "inputs": [{"name": name, "link": None} for name in names],
            "outputs": [],
            "widgets_values": ["SECRET_SELECTED_VALUE" for _ in names],
        })
        definitions[cls] = {
            "input": {"required": {name: ["ANY", {}] for name in names}},
        }
        next_id += 1
    report = m.preflight_ui_document(doc, definitions, m.DEFAULT_WORKFLOW)
    assert report["status"] == "READY_FOR_API_GRAPH_VALIDATION", report["definite_blockers"]
    waivers = [
        item for item in report["warnings"]
        if item["kind"] == "widget_selection_requires_api_validation"
    ]
    assert len(waivers) == 6
    assert "SECRET_SELECTED_VALUE" not in json.dumps(report)
    assert report["is_full_video_render_verified"] is False


def test_unknown_required_socket_remains_hard_blocker():
    doc = fixture()
    doc["nodes"].append({
        "id": 300, "type": "UnknownNeedsImage",
        "inputs": [{"name": "source_image", "link": None}],
        "outputs": [],
    })
    definitions = mock_object_info(doc)
    definitions["UnknownNeedsImage"] = {
        "input": {"required": {"source_image": ["IMAGE", {}]}},
    }
    report = m.preflight_ui_document(doc, definitions, m.DEFAULT_WORKFLOW)
    assert report["status"] == "BLOCKED_STATIC"
    assert any(
        issue["kind"] == "unconnected_required_socket" and
        issue["class_type"] == "UnknownNeedsImage"
        for issue in report["definite_blockers"]
    )


def test_widget_metadata_can_show_custom_input_is_not_hard_blocker():
    doc = fixture()
    doc["nodes"].append({
        "id": 301, "type": "CustomComboAsSocket",
        "inputs": [{"name": "choice", "link": None, "widget": {"name": "choice"}}],
        "outputs": [], "widgets_values": ["SECRET_CUSTOM"],
    })
    definitions = mock_object_info(doc)
    definitions["CustomComboAsSocket"] = {
        "input": {"required": {"choice": ["CUSTOM_CHOICE_TYPE", {}]}},
    }
    report = m.preflight_ui_document(doc, definitions, m.DEFAULT_WORKFLOW)
    assert report["status"] == "READY_FOR_API_GRAPH_VALIDATION", report["definite_blockers"]
    assert any(
        warning["kind"] == "widget_selection_requires_api_validation" and
        warning["class_type"] == "CustomComboAsSocket"
        for warning in report["warnings"]
    )
    assert "SECRET_CUSTOM" not in json.dumps(report)
