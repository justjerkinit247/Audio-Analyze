#!/usr/bin/env python3
"""Read-only, value-redacted structural inventory of saved ComfyUI GUI/API workflows.

Exports node types, port NAMES and graph edges. Never emits widget values, prompt
text, seed/audio paths, settings values, API tokens, or full workflow objects.
This script does not connect to ComfyUI or trigger execution.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DEFAULT_TARGETS = (
    "AudioAnalyze - LTX 2.3 Native (Carriage Preview).json",
    "AudioAnalyze - Ready to Run (Carriage Preview).json",
)


def category(class_type: str) -> str:
    value = class_type.lower()
    if value.startswith(("aao", "asmo")):
        return "asmo"
    if "gemma" in value:
        return "gemma"
    if "ltx" in value:
        return "ltx"
    if value.startswith(("vhs_", "save", "preview")) or "videocombine" in value:
        return "output"
    return "other"


def _port_name(ports: Any, slot: Any, prefix: str) -> str:
    if isinstance(ports, list) and isinstance(slot, int) and 0 <= slot < len(ports):
        port = ports[slot]
        if isinstance(port, dict) and isinstance(port.get("name"), str):
            return port["name"]
    return f"{prefix}_{slot}"


def _node_entry(node_id: str, class_type: str, inputs: Any, outputs: Any) -> dict:
    # Only structural metadata; never serialize arbitrary node properties.
    return {
        "id": str(node_id),
        "class_type": str(class_type),
        "category": category(str(class_type)),
        "input_ports": [
            str(p["name"]) for p in inputs
            if isinstance(p, dict) and isinstance(p.get("name"), str)
        ] if isinstance(inputs, list) else sorted(str(k) for k in inputs) if isinstance(inputs, dict) else [],
        "output_ports": [
            str(p["name"]) for p in outputs
            if isinstance(p, dict) and isinstance(p.get("name"), str)
        ] if isinstance(outputs, list) else [],
    }


def parse_gui_workflow(document: dict) -> tuple[list[dict], list[dict]]:
    raw_nodes = document.get("nodes", [])
    if not isinstance(raw_nodes, list):
        raise ValueError("ComfyUI UI workflow 'nodes' must be a list")
    nodes: dict[str, dict] = {}
    originals: dict[str, dict] = {}
    for source in raw_nodes:
        if not isinstance(source, dict) or "id" not in source:
            continue
        node_id = str(source["id"])
        class_type = str(source.get("type") or source.get("class_type") or "unknown")
        nodes[node_id] = _node_entry(
            node_id, class_type, source.get("inputs", []), source.get("outputs", [])
        )
        originals[node_id] = source

    edges: list[dict] = []
    links = document.get("links", [])
    if not isinstance(links, list):
        links = []
    for link in links:
        if isinstance(link, list) and len(link) >= 5:
            # Classic LiteGraph: [link_id, origin_id, origin_slot, target_id, target_slot, type]
            source_id, source_slot, target_id, target_slot = link[1:5]
        elif isinstance(link, dict):
            source_id = link.get("origin_id")
            source_slot = link.get("origin_slot")
            target_id = link.get("target_id")
            target_slot = link.get("target_slot")
        else:
            continue
        source_id, target_id = str(source_id), str(target_id)
        if source_id not in nodes or target_id not in nodes:
            continue
        src = originals[source_id]
        dst = originals[target_id]
        edges.append({
            "from_id": source_id,
            "from_type": nodes[source_id]["class_type"],
            "from_category": nodes[source_id]["category"],
            "output_port": _port_name(src.get("outputs"), source_slot, "slot"),
            "to_id": target_id,
            "to_type": nodes[target_id]["class_type"],
            "to_category": nodes[target_id]["category"],
            "input_port": _port_name(dst.get("inputs"), target_slot, "input"),
        })
    return list(nodes.values()), edges


def parse_api_workflow(document: dict) -> tuple[list[dict], list[dict]]:
    graph = document.get("prompt", document)
    if not isinstance(graph, dict):
        raise ValueError("API prompt must be a mapping")
    nodes: dict[str, dict] = {}
    for key, source in graph.items():
        if not isinstance(source, dict) or not isinstance(source.get("class_type"), str):
            continue
        nodes[str(key)] = _node_entry(
            str(key), source["class_type"], source.get("inputs", {}), []
        )
    edges = []
    for node_id, source in graph.items():
        if str(node_id) not in nodes:
            continue
        for input_name, value in (source.get("inputs") or {}).items():
            if (not isinstance(value, list) or len(value) != 2
                or not isinstance(value[1], int)):
                continue
            origin = str(value[0])
            if origin not in nodes:
                continue
            edges.append({
                "from_id": origin,
                "from_type": nodes[origin]["class_type"],
                "from_category": nodes[origin]["category"],
                "output_port": f"slot_{value[1]}",
                "to_id": str(node_id),
                "to_type": nodes[str(node_id)]["class_type"],
                "to_category": nodes[str(node_id)]["category"],
                "input_port": str(input_name),
            })
    return list(nodes.values()), edges


def summarize(document: dict, name: str) -> dict:
    if not isinstance(document, dict):
        raise ValueError("Workflow must be a JSON object")
    gui = isinstance(document.get("nodes"), list)
    nodes, edges = (parse_gui_workflow(document) if gui
                    else parse_api_workflow(document))
    if not nodes:
        raise ValueError("No ComfyUI node types found in workflow")
    cross = [
        edge for edge in edges
        if edge["from_category"] != edge["to_category"]
        and edge["from_category"] in {"asmo", "gemma", "ltx"}
    ]
    return {
        "file_name": name,
        "format": "comfy_ui_saved_gui" if gui else "comfy_ui_api",
        "node_count": len(nodes),
        "edge_count": len(edges),
        "asmo_node_count": sum(node["category"] == "asmo" for node in nodes),
        "ltx_node_count": sum(node["category"] == "ltx" for node in nodes),
        "nodes": sorted(nodes, key=lambda n: (
            0, int(n["id"])) if n["id"].isdigit() else (1, n["id"])),
        "edges": edges,
        "cross_category_edges": cross,
    }


def candidate_paths(comfy_root: Path, targets: tuple[str, ...] = DEFAULT_TARGETS) -> list[Path]:
    user_root = comfy_root / "user"
    if not user_root.is_dir():
        return []
    matches = []
    for target in targets:
        matches.extend(p for p in user_root.glob("*/workflows/**/" + target) if p.is_file())
    return sorted(set(matches), key=lambda p: str(p).lower())


def produce_report(comfy_root: Path, out_path: Path, targets: tuple[str, ...] = DEFAULT_TARGETS) -> dict:
    files = candidate_paths(comfy_root, targets)
    summaries: list[dict] = []
    warnings: list[str] = []
    for path in files:
        if path.stat().st_size > 15 * 1024 * 1024:
            warnings.append(f"File too large, skipped: {path.name}")
            continue
        try:
            document = json.loads(path.read_text(encoding="utf-8-sig"))
            summaries.append(summarize(document, path.name))
        except (ValueError, TypeError, UnicodeError, OSError) as exc:
            # Error type only; do not include exception text that could contain file content.
            warnings.append(f"Could not parse {path.name}: {type(exc).__name__}")
    found_names = {s["file_name"] for s in summaries}
    report = {
        "schema": "gtrg_comfyui_structural_wiring_v1",
        "read_only": True,
        "no_render_or_cloud_calls": True,
        "contains_literal_inputs_or_prompts": False,
        "target_workflows": list(targets),
        "matched_workflow_count": len(summaries),
        "missing_workflows": [name for name in targets if name not in found_names],
        "workflows": summaries,
        "warnings": warnings,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--comfy-root", type=Path,
        default=Path.home() / "Downloads" / "ComfyUI-Setup"
        / "ComfyUI_windows_portable" / "ComfyUI"
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path.home() / "Documents" / "Audio-Analyze" / "outputs"
        / "gtrg_local_smoke" / "gtrg_wiring_report.json"
    )
    parser.add_argument("--workflow", action="append", default=None,
                        help="Exact saved workflow JSON filename (repeatable)")
    args = parser.parse_args()
    names = tuple(args.workflow) if args.workflow else DEFAULT_TARGETS
    report = produce_report(args.comfy_root, args.output, names)
    print(f"GTRG wiring extraction: {report['matched_workflow_count']}/{len(names)} workflows")
    for wf in report["workflows"]:
        print(f"  {wf['file_name']}: {wf['node_count']} nodes, "
              f"{wf['edge_count']} links, {len(wf['cross_category_edges'])} cross-category handoffs")
        for edge in wf["cross_category_edges"]:
            print(f"    {edge['from_type']}.{edge['output_port']} -> "
                  f"{edge['to_type']}.{edge['input_port']}")
    for missing in report["missing_workflows"]:
        print(f"  NOT FOUND: {missing}")
    print(f"Report: {args.output}")
    print("No checkpoint loads, ComfyUI queue, Modal, or external API calls.")
    return 0 if report["matched_workflow_count"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
