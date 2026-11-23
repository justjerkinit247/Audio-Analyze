"""Pure-Python tests: workflow structure and no exported sensitive input values."""
import importlib.util
import json
import sys
from pathlib import Path

source = Path(__file__).resolve().parents[1] / "scripts" / "gtrg_workflow_wiring.py"
spec = importlib.util.spec_from_file_location("gtrg_workflow_wiring", source)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)

def sample():
    return {
        "nodes": [
            {"id": 1, "type": "AAOSceneRenderInputs",
             "outputs": [{"name": "render_payload"}], "inputs": [],
             "widgets_values": ["SECRET_PROMPT"]},
            {"id": 2, "type": "LTXV23ImgToVideo",
             "outputs": [{"name": "latent"}],
             "inputs": [{"name": "conditioning", "link": 50}],
             "widgets_values": ["SECRET_API_KEY"]},
            {"id": 3, "type": "VHS_VideoCombine",
             "inputs": [{"name": "images", "link": 51}], "outputs": []},
        ],
        "links": [[50, 1, 0, 2, 0, "CONDITIONING"],
                  [51, 2, 0, 3, 0, "LATENT"]],
        "metadata": {"secret": "HIDDEN_IN_METADATA"},
    }

def test_gui_wiring_and_redaction():
    data = m.summarize(sample(), "test-gui.json")
    assert data["format"] == "comfy_ui_saved_gui"
    assert data["node_count"] == 3
    assert data["edge_count"] == 2
    assert data["cross_category_edges"][0]["output_port"] == "render_payload"
    assert data["cross_category_edges"][0]["input_port"] == "conditioning"
    raw = json.dumps(data)
    for private in ("SECRET_PROMPT", "SECRET_API_KEY", "HIDDEN_IN_METADATA"):
        assert private not in raw

def test_object_links_and_unknown_slots():
    doc = sample()
    doc["links"] = [{"origin_id": 1, "origin_slot": 9,
                      "target_id": 2, "target_slot": 8}]
    edge = m.summarize(doc, "object-links.json")["edges"][0]
    assert edge["output_port"] == "slot_9"
    assert edge["input_port"] == "input_8"

def test_api_graph_and_redaction():
    data = {
        "1": {"class_type": "AAOBeatTimeline",
              "inputs": {"audio": "SECRET_SONG.wav"}},
        "2": {"class_type": "LTXV25ImgToVideo",
              "inputs": {"motion": ["1", 0], "prompt": "SECRET_TEXT"}},
    }
    report = m.summarize(data, "api.json")
    assert report["format"] == "comfy_ui_api"
    assert report["edge_count"] == 1
    assert report["cross_category_edges"][0]["input_port"] == "motion"
    assert "SECRET_SONG" not in json.dumps(report)
    assert "SECRET_TEXT" not in json.dumps(report)

def test_scan_named_workflows_only(tmp_path):
    root = tmp_path / "ComfyUI"
    folder = root / "user" / "default" / "workflows"
    folder.mkdir(parents=True)
    for target in m.DEFAULT_TARGETS:
        (folder / target).write_text(json.dumps(sample()), encoding="utf-8")
    (folder / "irrelevant.json").write_text("SECRET_UNRELATED", encoding="utf-8")
    destination = tmp_path / "report.json"
    result = m.produce_report(root, destination)
    assert result["matched_workflow_count"] == 2
    assert not result["missing_workflows"]
    assert "SECRET_" not in destination.read_text(encoding="utf-8")

def test_missing_workflows_fail_closed(tmp_path):
    root = tmp_path / "ComfyUI"
    (root / "user").mkdir(parents=True)
    report = m.produce_report(root, tmp_path / "report.json")
    assert report["matched_workflow_count"] == 0
    assert len(report["missing_workflows"]) == 2
