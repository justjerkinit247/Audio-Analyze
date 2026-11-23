#!/usr/bin/env python3
"""Validate a ComfyUI *API-format* graph using local /object_info, without submitting it.

Never calls /prompt, loads models, contacts Modal, or runs a renderer. Report omits
all input values, prompts, media paths, secrets, and model filenames. API export
itself CAN contain secrets: share only the generated report after review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

REMOTE_CLASSES = frozenset({
    "LtxApi25AudioToVideo", "LtxApi25ImageToVideo",
    "LtxApi25TextToVideo", "LTXDirectImageToVideo",
})
REQUIRED_CLASSES = (
    "AAOSceneRenderInputs", "AAOFinishScene", "CreateVideo",
    "LTXVPreprocess", "LTXVConditioning", "EmptyLTXVLatentVideo",
)
HANDOFFS = (
    ("AAOSceneRenderInputs", "seed_image", "LTXVPreprocess", "image"),
    ("AAOSceneRenderInputs", "fps", "LTXVConditioning", "frame_rate"),
    ("AAOSceneRenderInputs", "render_frames", "EmptyLTXVLatentVideo", "length"),
    ("AAOFinishScene", "trimmed_frames", "CreateVideo", "images"),
    ("AAOFinishScene", "fps", "CreateVideo", "fps"),
    ("AAOFinishScene", "original_soundtrack", "CreateVideo", "audio"),
)


def read_api_graph(source: Any) -> dict[str, dict]:
    if not isinstance(source, dict):
        raise ValueError("API graph must be a JSON object")
    if isinstance(source.get("nodes"), list):
        raise ValueError("This is GUI-save format; export the workflow using File > Export Workflow (API)")
    graph = source.get("prompt", source)
    if not isinstance(graph, dict) or not graph:
        raise ValueError("API graph must be nonempty")
    nodes = {
        str(key): val for key, val in graph.items()
        if isinstance(val, dict) and isinstance(val.get("class_type"), str)
        and isinstance(val.get("inputs"), dict)
    }
    if len(nodes) < 2:
        raise ValueError("Too few valid API nodes; select the correct exported workflow")
    return nodes


def get_object_info(server: str = "http://127.0.0.1:8188") -> dict:
    if server.rstrip("/") not in {"http://127.0.0.1:8188", "http://localhost:8188"}:
        raise ValueError("Only loopback ComfyUI on port 8188 is allowed")
    with urlopen(f"{server.rstrip('/')}/object_info", timeout=90) as response:
        result = json.load(response)
    if not isinstance(result, dict):
        raise ValueError("Invalid object_info payload")
    return result


def get_link(value: Any, graph: dict[str, dict]) -> tuple[str, int] | None:
    if (
        isinstance(value, list)
        and len(value) == 2
        and isinstance(value[0], (str, int))
        and isinstance(value[1], int)
        and not isinstance(value[1], bool)
        and str(value[0]) in graph
    ):
        return str(value[0]), value[1]
    return None


def input_definition(info: dict, input_name: str) -> Any:
    source = info.get("input") or {}
    if not isinstance(source, dict):
        return None
    for key in ("required", "optional"):
        section = source.get(key)
        if isinstance(section, dict) and input_name in section:
            return section[input_name]
    return None


def connection_check(
    graph: dict[str, dict],
    object_info: dict,
    from_class: str,
    output_name: str,
    to_class: str,
    input_name: str,
) -> str:
    """Return PASS, FAIL, or UNVERIFIED; never assume output slot identity."""
    targets = [
        node for node in graph.values()
        if node["class_type"] == to_class and input_name in node["inputs"]
    ]
    uncertain = False
    for dest in targets:
        link = get_link(dest["inputs"][input_name], graph)
        if link is None:
            continue
        origin_id, slot = link
        origin_class = graph[origin_id]["class_type"]
        if origin_class != from_class:
            continue
        output_names = object_info.get(from_class, {}).get("output_name")
        if not isinstance(output_names, list) or slot >= len(output_names):
            uncertain = True
            continue
        if output_names[slot] == output_name:
            return "PASS"
    return "UNVERIFIED" if uncertain else "FAIL"


def validate_graph(graph: dict[str, dict], object_info: dict) -> dict:
    blockers: list[dict] = []
    warnings: list[dict] = []
    class_ids = sorted(set(node["class_type"] for node in graph.values()))
    class_set = set(class_ids)
    missing_classes = sorted(class_set - set(object_info))
    for cls in missing_classes:
        blockers.append({"kind": "unregistered_class", "class_type": cls})
    for cls in REQUIRED_CLASSES:
        if cls not in class_set:
            blockers.append({"kind": "required_class_absent", "class_type": cls})
    for cls in sorted(class_set & REMOTE_CLASSES):
        blockers.append({
            "kind": "external_paid_or_cloud_api_class_present",
            "class_type": cls,
        })

    checked_inputs = 0
    checked_dropdowns = 0
    validated_links = 0
    for node_id, node in graph.items():
        cls = node["class_type"]
        info = object_info.get(cls)
        if not isinstance(info, dict):
            continue
        provided = node.get("inputs", {})
        spec = info.get("input") or {}
        required = spec.get("required") if isinstance(spec, dict) else {}
        if not isinstance(required, dict):
            required = {}
        for name in required:
            if name not in provided:
                blockers.append({
                    "kind": "required_api_input_missing",
                    "node_id": node_id,
                    "class_type": cls,
                    "input_name": name,
                })
        for name, value in provided.items():
            checked_inputs += 1
            definition = input_definition(info, name)
            if definition is None:
                warnings.append({
                    "kind": "api_input_not_declared_in_current_node",
                    "node_id": node_id, "class_type": cls, "input_name": name,
                })
                continue
            link = get_link(value, graph)
            if link is not None:
                from_id, outslot = link
                origin_class = graph[from_id]["class_type"]
                out_spec = object_info.get(origin_class, {}).get("output") or []
                if not isinstance(out_spec, list) or outslot < 0 or outslot >= len(out_spec):
                    blockers.append({
                        "kind": "link_output_slot_invalid",
                        "node_id": node_id,
                        "class_type": cls, "input_name": name,
                        "origin_class": origin_class,
                    })
                else:
                    validated_links += 1
                continue
            # ComfyUI option/enum values are a list in object_info input metadata.
            allowed = definition[0] if isinstance(definition, (list, tuple)) and definition else None
            if isinstance(allowed, list):
                checked_dropdowns += 1
                if value not in allowed:
                    blockers.append({
                        "kind": "dropdown_value_not_available",
                        "node_id": node_id, "class_type": cls,
                        "input_name": name,
                    })
                continue
            if isinstance(value, list) and len(value) == 2 and isinstance(value[1], int):
                warnings.append({
                    "kind": "ambiguous_two_item_literal_or_invalid_link",
                    "node_id": node_id, "class_type": cls,
                    "input_name": name,
                })
            if value is None:
                blockers.append({
                    "kind": "null_input_value",
                    "node_id": node_id, "class_type": cls,
                    "input_name": name,
                })

    handoffs: dict[str, str] = {}
    for source_cls, output_name, dest_cls, input_name in HANDOFFS:
        key = f"{source_cls}.{output_name} -> {dest_cls}.{input_name}"
        status = connection_check(
            graph, object_info, source_cls, output_name, dest_cls, input_name
        )
        handoffs[key] = status
        if status == "FAIL":
            blockers.append({
                "kind": "handoff_missing_or_wrong_source",
                "handoff": key,
            })
        elif status == "UNVERIFIED":
            warnings.append({"kind": "handoff_output_name_unavailable", "handoff": key})

    handoff_verified = all(status == "PASS" for status in handoffs.values())
    status = (
        "BLOCKED_API_STATIC" if blockers
        else "READY_FOR_CONTROLLED_LOCAL_TEST" if handoff_verified
        else "API_INPUTS_VALID_HANDOFF_UNVERIFIED"
    )
    return {
        "schema": "gtrg_local_api_preflight_v1",
        "status": status,
        "api_node_count": len(graph),
        "registered_class_count": len(class_set),
        "checked_input_count": checked_inputs,
        "validated_reference_count": validated_links,
        "checked_dropdown_count": checked_dropdowns,
        "required_handoffs": handoffs,
        "definite_blockers": blockers,
        "warnings": warnings,
        "node_execution_performed": False,
        "model_weights_loaded": False,
        "render_verified": False,
        "modal_or_paid_api_calls": 0,
        "report_excludes_input_values": True,
        "next_step": (
            "Fix listed blockers or verify handoffs; then run a separately "
            "authorized low-resolution local render. Never submit automatically."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", required=True, type=Path,
                        help="Local ComfyUI File > Export Workflow (API) JSON")
    parser.add_argument(
        "--report", type=Path,
        default=Path.home() / "Documents" / "Audio-Analyze"
        / "outputs" / "gtrg_local_smoke" / "gtrg_api_preflight.json",
    )
    parser.add_argument("--server", default="http://127.0.0.1:8188")
    args = parser.parse_args()
    try:
        if args.api.stat().st_size > 15 * 1024 * 1024:
            raise ValueError("API graph exceeds 15 MB")
        raw = args.api.read_bytes()
        graph = read_api_graph(json.loads(raw.decode("utf-8-sig")))
        info = get_object_info(args.server)
        report = validate_graph(graph, info)
        # A hash references source graph without exposing its sensitive literals.
        report["api_file_sha256"] = hashlib.sha256(raw).hexdigest()
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    except (OSError, HTTPError, URLError, ValueError, TypeError) as exc:
        print(f"API preflight could not run: {type(exc).__name__}. No job submitted.")
        return 2

    print("=== GTRG NATIVE LTX 2.3 API PREFLIGHT (READ ONLY) ===")
    print(f"Status: {report['status']}")
    print(f"Nodes: {report['api_node_count']}")
    print(f"Inputs checked: {report['checked_input_count']}")
    print(f"Links validated: {report['validated_reference_count']}")
    print(f"Dropdown selections checked: {report['checked_dropdown_count']}")
    print(f"Blockers: {len(report['definite_blockers'])}")
    for item in report["definite_blockers"]:
        print("  BLOCKER: " + json.dumps(item, sort_keys=True))
    print(f"Warnings: {len(report['warnings'])}")
    for item in report["warnings"][:20]:
        print("  WARNING: " + json.dumps(item, sort_keys=True))
    print(f"Report: {args.report}")
    print("No prompt submission, checkpoint load, render, Modal, or paid API call.")
    return 0 if not report["definite_blockers"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
