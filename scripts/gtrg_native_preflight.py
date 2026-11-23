#!/usr/bin/env python3
"""Read-only local ComfyUI native ASMO/LTX preflight.

Only HTTP GET to localhost. No prompt queueing, rendering, model loading, cloud
calls, paid API calls, or edits to BeatSync/ASMO. Exports structural metadata only,
never widget values, paths from the workflow, audio, prompts, or API tokens.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from gtrg_workflow_wiring import candidate_paths, summarize

DEFAULT_WORKFLOW = "AudioAnalyze - LTX 2.3 Native (Carriage Preview).json"
MODEL_FOLDERS = ("checkpoints", "diffusion_models", "text_encoders", "vae", "loras")
WIDGET_TYPES = {"STRING", "INT", "FLOAT", "BOOLEAN"}
REMOTE_API_CLASSES = {
    "LtxApi25AudioToVideo", "LtxApi25ImageToVideo",
    "LtxApi25TextToVideo", "LTXDirectImageToVideo",
}

# In ComfyUI's saved GUI JSON these are widget/dropdown selections, not
# mandatory graph cables. The selected values still require API-format
# validation; this static pass deliberately does not read or print them.
KNOWN_WIDGET_PORTS = {
    ("KSamplerSelect", "sampler_name"),
    ("SaveVideo", "format"),
    ("LTXAVTextEncoderLoader", "text_encoder"),
    ("LTXAVTextEncoderLoader", "ckpt_name"),
    ("LTXAVTextEncoderLoader", "device"),
    ("LTXVAudioVAELoader", "ckpt_name"),
}


def local_get(url: str, *, timeout: int = 25) -> Any:
    with urlopen(url, timeout=timeout) as response:
        return json.load(response)


def _link_info(item: Any) -> tuple[Any, Any, Any, Any, Any] | None:
    if isinstance(item, list) and len(item) >= 5:
        return item[0], item[1], item[2], item[3], item[4]
    if isinstance(item, dict):
        return (
            item.get("id"), item.get("origin_id"), item.get("origin_slot"),
            item.get("target_id"), item.get("target_slot"),
        )
    return None


def _has_edge(edges: list[dict], from_class: str, output: str,
              to_class: str, target: str) -> bool:
    return any(
        edge["from_type"] == from_class
        and edge["output_port"] == output
        and edge["to_type"] == to_class
        and edge["input_port"] == target
        for edge in edges
    )


def _is_socket(type_def: Any) -> bool:
    if not isinstance(type_def, list) or not type_def:
        return False
    kind = type_def[0]
    flags = type_def[1] if len(type_def) > 1 and isinstance(type_def[1], dict) else {}
    if flags.get("forceInput"):
        return True
    return isinstance(kind, str) and kind.upper() not in WIDGET_TYPES


def _node_inputs(source: dict) -> dict[str, dict]:
    ports = source.get("inputs", [])
    if not isinstance(ports, list):
        return {}
    return {
        port["name"]: port for port in ports
        if isinstance(port, dict) and isinstance(port.get("name"), str)
    }


def preflight_ui_document(
    document: dict,
    object_info: dict,
    workflow_name: str,
    model_folder_counts: dict[str, Any] | None = None,
) -> dict:
    if not isinstance(document.get("nodes"), list):
        raise ValueError("Expected saved ComfyUI GUI workflow JSON")
    inventory = summarize(document, workflow_name)
    raw_nodes = document["nodes"]
    node_by_id = {
        str(node["id"]): node for node in raw_nodes
        if isinstance(node, dict) and "id" in node
    }
    counts = Counter(
        str(node.get("type") or node.get("class_type") or "unknown")
        for node in raw_nodes if isinstance(node, dict)
    )
    problems: list[dict] = []
    cautions: list[dict] = []
    checks: dict[str, bool] = {}

    for node_id, node in node_by_id.items():
        cls = str(node.get("type") or node.get("class_type") or "unknown")
        if cls not in object_info:
            problems.append({
                "kind": "missing_registered_node",
                "node_id": node_id, "class_type": cls,
            })
            continue
        info = object_info[cls]
        required = info.get("input", {}).get("required", {})
        if not isinstance(required, dict):
            required = {}
        ports = _node_inputs(node)
        for input_name, input_def in required.items():
            if not _is_socket(input_def):
                continue  # A scalar/enum GUI widget need not have a cable.
            socket = ports.get(input_name)
            if socket and socket.get("link") is not None:
                continue
            # Some core nodes advertise connectable dropdowns as typed inputs.
            # No wire is needed if the GUI widget supplies the value, but
            # we cannot infer whether its saved selection is usable here.
            has_gui_widget = bool(socket and socket.get("widget") is not None)
            if has_gui_widget or (cls, input_name) in KNOWN_WIDGET_PORTS:
                cautions.append({
                    "kind": "widget_selection_requires_api_validation",
                    "node_id": node_id, "class_type": cls, "port": input_name,
                })
                continue
            problems.append({
                "kind": "unconnected_required_socket",
                "node_id": node_id, "class_type": cls, "port": input_name,
            })

    link_ids: set[str] = set()
    links = document.get("links", [])
    if not isinstance(links, list):
        links = []
        problems.append({"kind": "invalid_links_collection"})
    for raw_link in links:
        parsed = _link_info(raw_link)
        if not parsed:
            problems.append({"kind": "malformed_graph_link"})
            continue
        link_id, origin_id, origin_slot, dest_id, dest_slot = parsed
        if str(link_id) in link_ids:
            problems.append({"kind": "duplicate_link_id", "link_id": str(link_id)})
        link_ids.add(str(link_id))
        origin = node_by_id.get(str(origin_id))
        dest = node_by_id.get(str(dest_id))
        if origin is None or dest is None:
            problems.append({"kind": "link_endpoint_missing", "link_id": str(link_id)})
            continue
        for side, node, slot, field in (
            ("origin", origin, origin_slot, "outputs"),
            ("destination", dest, dest_slot, "inputs"),
        ):
            slots = node.get(field, [])
            if (not isinstance(slot, int) or not isinstance(slots, list)
                    or slot < 0 or slot >= len(slots)):
                problems.append({
                    "kind": "link_slot_out_of_range",
                    "link_id": str(link_id), "side": side,
                })
        ports = dest.get("inputs", [])
        if (isinstance(dest_slot, int) and isinstance(ports, list)
                and 0 <= dest_slot < len(ports)):
            target = ports[dest_slot]
            if (isinstance(target, dict) and target.get("link") is not None
                    and str(target["link"]) != str(link_id)):
                cautions.append({
                    "kind": "destination_link_mismatch", "link_id": str(link_id),
                })

    edges = inventory["edges"]
    checks["scene_renderer_node"] = counts["AAOSceneRenderInputs"] >= 1
    checks["finalizer_node"] = counts["AAOFinishScene"] >= 1
    checks["video_output_node"] = counts["CreateVideo"] >= 1
    checks["scene_to_seed_preprocess"] = _has_edge(
        edges, "AAOSceneRenderInputs", "seed_image", "LTXVPreprocess", "image",
    )
    checks["scene_to_ltx_fps"] = _has_edge(
        edges, "AAOSceneRenderInputs", "fps", "LTXVConditioning", "frame_rate",
    )
    checks["scene_to_native_frame_count"] = _has_edge(
        edges, "AAOSceneRenderInputs", "render_frames",
        "EmptyLTXVLatentVideo", "length",
    )
    checks["final_frames_to_video"] = _has_edge(
        edges, "AAOFinishScene", "trimmed_frames", "CreateVideo", "images",
    )
    checks["final_fps_to_video"] = _has_edge(
        edges, "AAOFinishScene", "fps", "CreateVideo", "fps",
    )
    checks["original_audio_to_video"] = _has_edge(
        edges, "AAOFinishScene", "original_soundtrack", "CreateVideo", "audio",
    )
    for key, good in checks.items():
        if not good:
            problems.append({
                "kind": "required_workflow_handoff_missing", "check": key,
            })
    remote = sorted(set(counts) & REMOTE_API_CLASSES)
    if remote:
        cautions.append({
            "kind": "external_api_node_present", "class_types": remote,
        })
    for kind in MODEL_FOLDERS:
        if model_folder_counts is not None and model_folder_counts.get(kind) == 0:
            cautions.append({
                "kind": "model_category_empty", "category": kind,
            })

    # Widget values may contain complete audio paths, prompts and credentials.
    # Never serialize or print any widget literal, even when model selection fails.
    return {
        "schema": "gtrg_native_static_preflight_v1",
        "workflow": workflow_name,
        "status": "BLOCKED_STATIC" if problems else "READY_FOR_API_GRAPH_VALIDATION",
        "is_full_video_render_verified": False,
        "did_execute_graph": False,
        "did_trigger_model_load": False,
        "did_call_modal_or_paid_apis": False,
        "node_count": inventory["node_count"],
        "link_count": len(links),
        "registered_node_classes_checked": len(set(counts)),
        "registered_node_classes_missing": sum(
            p["kind"] == "missing_registered_node" for p in problems
        ),
        "handoff_checks": checks,
        "external_api_node_classes": remote,
        "model_category_file_counts": model_folder_counts,
        "definite_blockers": problems,
        "warnings": cautions,
        "next_step": "Export the same saved workflow in ComfyUI API format and validate it without queuing.",
    }


def perform(comfy_root: Path, workflow_name: str, server: str,
            out_path: Path) -> dict:
    matches = candidate_paths(comfy_root, (workflow_name,))
    if len(matches) != 1:
        raise RuntimeError(f"Expected one matching saved workflow; found {len(matches)}")
    path = matches[0]
    if path.stat().st_size > 15 * 1024 * 1024:
        raise RuntimeError("Workflow JSON exceeds 15MB")
    document = json.loads(path.read_text(encoding="utf-8-sig"))
    system = local_get(f"{server}/system_stats", timeout=5)
    info = local_get(f"{server}/object_info", timeout=90)
    model_counts: dict[str, Any] = {}
    for category in MODEL_FOLDERS:
        try:
            files = local_get(f"{server}/models/{category}", timeout=12)
            model_counts[category] = len(files) if isinstance(files, list) else None
        except (HTTPError, URLError, OSError, ValueError):
            model_counts[category] = None
    report = preflight_ui_document(document, info, workflow_name, model_counts)
    report["local_server_responded"] = True
    report["cuda_device_reported"] = any(
        "cuda" in str(device.get("type", "")).lower()
        or "cuda" in str(device.get("name", "")).lower()
        for device in system.get("devices", [])
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--comfy-root", type=Path,
        default=Path.home() / "Downloads" / "ComfyUI-Setup"
        / "ComfyUI_windows_portable" / "ComfyUI",
    )
    parser.add_argument("--workflow", default=DEFAULT_WORKFLOW)
    parser.add_argument("--server", default="http://127.0.0.1:8188")
    parser.add_argument(
        "--output", type=Path,
        default=Path.home() / "Documents" / "Audio-Analyze" / "outputs"
        / "gtrg_local_smoke" / "gtrg_native_preflight.json",
    )
    args = parser.parse_args()
    if args.server.rstrip("/") not in (
        "http://127.0.0.1:8188", "http://localhost:8188",
    ):
        parser.error("Only local ComfyUI on port 8188 is permitted")
    try:
        result = perform(
            args.comfy_root, args.workflow, args.server.rstrip("/"), args.output,
        )
    except (ValueError, TypeError, OSError, RuntimeError, HTTPError, URLError) as exc:
        print(
            f"Preflight could not complete: {type(exc).__name__} "
            "(no cloud jobs started)"
        )
        return 2
    print("=== GTRG NATIVE LTX 2.3 READ-ONLY PREFLIGHT ===")
    print(f"Nodes: {result['node_count']} | Links: {result['link_count']}")
    print(f"Missing registered classes: {result['registered_node_classes_missing']}")
    for key, good in result["handoff_checks"].items():
        print(f"  {'OK' if good else 'FAIL'}: {key}")
    print(f"Status: {result['status']}")
    print(
        f"Definite blockers: {len(result['definite_blockers'])} | "
        f"Warnings: {len(result['warnings'])}"
    )
    print(f"Report saved: {args.output}")
    print("No prompt submitted, model loaded, or cloud service contacted.")
    return 0 if not result["definite_blockers"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
