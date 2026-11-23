#!/usr/bin/env python3
"""One low-cost *local* ASMO/LTX 2.3 video canary, defaulting to DRY-RUN.

Never touches the original API export, BeatSync source, or any cloud provider.
An explicit --run is necessary to send a single temporary tiny graph to the
local ComfyUI API. Any active queue causes a hard stop. Timed-out jobs are
interrupted/deleted by their OWN prompt_id, never globally.
"""
from __future__ import annotations

import argparse
import copy
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from gtrg_api_preflight import get_object_info, read_api_graph, validate_graph

BASE = "http://127.0.0.1:8188"
WIDTH, HEIGHT, FRAMES, STEPS = 288, 512, 9, 2
LATENT_VIDEO = {"EmptyLTXVLatentVideo", "LTXV23ImgToVideo", "LTXVImgToVideo"}
IMAGE_PREPROCESS = {"LTXVPreprocess"}
LATENT_AUDIO = {"LTXVEmptyLatentAudio"}
SAMPLERS = {
    "LTXVScheduler", "BasicScheduler", "KSampler", "KSamplerAdvanced",
    "LTXV23KSampler", "LTXV23RefineSampler", "LTXV25KSampler",
    "KarrasScheduler", "AlignYourStepsScheduler",
}
EXPENSIVE_EXTRA = {
    "LTXVLatentUpsampler", "LTXV23LatentUpscale",
    "LTXV25LatentUpscale", "LTXV23RefineSampler",
}


def http_json(route: str, data: dict | None = None, *, timeout: int = 20) -> Any:
    if not route.startswith("/") or "://" in route:
        raise ValueError("Only local relative API routes are permitted")
    payload = json.dumps(data).encode("utf-8") if data is not None else None
    request = Request(
        BASE + route, data=payload,
        headers={"Content-Type": "application/json"} if data is not None else {},
        method="POST" if data is not None else "GET",
    )
    with urlopen(request, timeout=timeout) as response:
        return json.load(response) if response.status != 204 and response.length != 0 else {}


def _within_range(spec: Any, proposed: int) -> bool:
    """Honor current ComfyUI min/max/step metadata; don't guess if incompatible."""
    if not isinstance(spec, list) or not spec:
        return False
    kind = spec[0]
    if kind not in ("INT", "FLOAT"):
        return False
    opts = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
    low, high = opts.get("min"), opts.get("max")
    if isinstance(low, (int, float)) and proposed < low:
        return False
    if isinstance(high, (int, float)) and proposed > high:
        return False
    if isinstance(low, int) and isinstance(opts.get("step"), int):
        step = opts["step"]
        if step > 1 and (proposed - low) % step != 0:
            return False
    return True


def _input_spec(info: dict, cls: str, key: str) -> Any:
    definition = info.get(cls, {}).get("input", {})
    if not isinstance(definition, dict):
        return None
    for role in ("required", "optional"):
        ports = definition.get(role, {})
        if isinstance(ports, dict) and key in ports:
            return ports[key]
    return None


def build_tiny(graph: dict[str, dict], info: dict, prefix: str) -> tuple[dict, dict]:
    """Patch a disconnected low-resource render *copy*; no original edits."""
    approved = validate_graph(graph, info)
    if approved["status"] != "READY_FOR_CONTROLLED_LOCAL_TEST":
        raise ValueError("Original API graph must pass strict GTRG API preflight first")
    if graph.get("2", {}).get("class_type") != "AAOBuildPlan":
        raise ValueError("Missing expected AAOBuildPlan node 2")
    if graph["2"]["inputs"].get("provider") != "ollama":
        raise ValueError("AAOBuildPlan must use the locally verified ollama provider")
    classes = {node["class_type"] for node in graph.values()}
    if classes & EXPENSIVE_EXTRA:
        raise ValueError("Refine/upscale node present; refusing this minimum-resource test")
    if not {"SaveVideo", "CreateVideo", "EmptyLTXVLatentVideo"} <= classes:
        raise ValueError("Required native LTX video/output classes are absent")
    if any(
        "modal" in cls.lower() or "api" in cls.lower() or "runway" in cls.lower()
        for cls in classes
    ):
        raise ValueError("Potential cloud/API node present; local-only test refused")

    clone = copy.deepcopy(graph)
    changes: list[dict] = []
    reduced_video = 0
    reduced_steps = 0
    audio_frames = 0
    saved_prefix = 0
    for node_id, node in clone.items():
        cls, inputs = node["class_type"], node["inputs"]
        targets: dict[str, int] = {}
        if cls in LATENT_VIDEO:
            targets.update({"width": WIDTH, "height": HEIGHT, "length": FRAMES})
        if cls in IMAGE_PREPROCESS:
            targets.update({"width": WIDTH, "height": HEIGHT})
        if cls in LATENT_AUDIO:
            targets.update({"frames_number": FRAMES})
        if cls in SAMPLERS:
            targets.update({"steps": STEPS, "num_steps": STEPS})
        for key, target in targets.items():
            if key not in inputs:
                continue
            field = _input_spec(info, cls, key)
            if not _within_range(field, target):
                raise ValueError(
                    f"Current node minimum/maximum disallows tiny {cls}.{key}"
                )
            old = inputs[key]
            if old != target:
                inputs[key] = target
                changes.append({
                    "node_id": node_id, "class_type": cls, "input_name": key,
                    "new_value": target, "was_graph_link": isinstance(old, list),
                })
            if cls in LATENT_VIDEO and key == "length":
                reduced_video += 1
            if cls in LATENT_AUDIO and key == "frames_number":
                audio_frames += 1
            if cls in SAMPLERS and key in {"steps", "num_steps"}:
                reduced_steps += 1

        if cls == "SaveVideo":
            if "filename_prefix" not in inputs or isinstance(
                inputs["filename_prefix"], list
            ):
                raise ValueError("SaveVideo lacks an editable filename_prefix")
            inputs["filename_prefix"] = prefix
            saved_prefix += 1

    if reduced_video < 1 or reduced_steps < 1 or saved_prefix < 1:
        raise ValueError("Could not verify 9-frame and 2-step rendering controls")
    if "LTXVEmptyLatentAudio" in classes and audio_frames < 1:
        raise ValueError("Audio latent length could not be constrained")
    return clone, {
        "nodes": len(clone),
        "video_frames": FRAMES,
        "steps": STEPS,
        "resolution": f"{WIDTH}x{HEIGHT}",
        "audio_frames_constrained": audio_frames,
        "new_prefix": prefix,
        "changed_inputs": changes,
        "original_graph_handoffs_preserved_in_source": True,
        "test_copy_may_override_frame_links": True,
    }


def queue_empty() -> bool:
    q = http_json("/queue", timeout=12)
    return not q.get("queue_running") and not q.get("queue_pending")


def _owned_job_in_queue(prompt_id: str) -> tuple[bool, bool]:
    q = http_json("/queue", timeout=12)
    def contains(items: Any) -> bool:
        for item in items or []:
            if isinstance(item, (list, tuple)) and len(item) > 1 and item[1] == prompt_id:
                return True
            if isinstance(item, dict) and (
                item.get("prompt_id") == prompt_id or item.get("id") == prompt_id
            ):
                return True
        return False
    return contains(q.get("queue_running")), contains(q.get("queue_pending"))


def cancel_own(prompt_id: str) -> dict:
    outcome: dict[str, Any] = {"attempted": True, "prompt_id": prompt_id}
    try:
        running, pending = _owned_job_in_queue(prompt_id)
        if running:
            http_json("/interrupt", {"prompt_id": prompt_id}, timeout=10)
            outcome["targeted_interrupt_requested"] = True
        if pending:
            http_json("/queue", {"delete": [prompt_id]}, timeout=10)
            outcome["targeted_queue_delete_requested"] = True
        if not running and not pending:
            outcome["already_not_queued"] = True
    except (OSError, HTTPError, URLError, ValueError):
        outcome["cleanup_error"] = "Local server did not acknowledge target cancellation"
    return outcome


def _find_video_from_history(history: dict, comfy_output: Path, prefix: str) -> list[Path]:
    found: list[Path] = []
    def scan(obj: Any) -> None:
        if isinstance(obj, dict):
            filename = obj.get("filename")
            subfolder = obj.get("subfolder", "")
            if isinstance(filename, str) and filename.startswith(prefix) and (
                filename.lower().endswith((".mp4", ".webm", ".mov", ".mkv"))
            ):
                # Restrict paths to local ComfyUI output directory.
                candidate = (comfy_output / str(subfolder) / filename).resolve()
                if candidate.is_relative_to(comfy_output.resolve()) and candidate.is_file():
                    found.append(candidate)
            for item in obj.values():
                scan(item)
        elif isinstance(obj, list):
            for item in obj:
                scan(item)
    scan(history.get("outputs", {}))
    return found


def run_job(graph: dict, *, seconds: int, comfy_output: Path, prefix: str) -> dict:
    if not queue_empty():
        raise RuntimeError("ComfyUI queue is busy; no job was submitted")
    response = http_json(
        "/prompt", {
            "prompt": graph, "client_id": str(uuid.uuid4()),
        }, timeout=40,
    )
    prompt_id = response.get("prompt_id")
    if not isinstance(prompt_id, str) or not prompt_id:
        raise RuntimeError("ComfyUI rejected the tiny workflow (no prompt ID)")
    started = time.monotonic()
    result: dict[str, Any] = {
        "prompt_id": prompt_id, "status": "TIMEOUT",
        "output_videos": [], "elapsed_seconds": 0,
        "cancellation": None,
    }
    try:
        deadline = started + seconds
        while time.monotonic() < deadline:
            time.sleep(3)
            h = http_json("/history/" + quote(prompt_id, safe=""), timeout=20)
            record = h.get(prompt_id)
            if not isinstance(record, dict):
                continue
            status = record.get("status") or {}
            if status.get("status_str") in {"error", "failed", "cancelled"}:
                result["status"] = "RENDER_FAILED"
                return result
            if status.get("completed") is True:
                videos = _find_video_from_history(
                    record, comfy_output, prefix
                )
                if not videos:
                    # Native SaveVideo implementations may not include file
                    # metadata; only a uniquely prefixed, real local file counts.
                    videos = [
                        p.resolve() for p in comfy_output.rglob(prefix + "*")
                        if p.is_file() and p.suffix.lower() in (
                            ".mp4", ".webm", ".mov", ".mkv"
                        ) and p.stat().st_size > 1024
                    ]
                result["output_videos"] = [str(p) for p in videos]
                result["status"] = (
                    "PLAYABLE_FILE_NOT_YET_VERIFIED" if videos
                    else "FINISHED_WITHOUT_VERIFIED_VIDEO_FILE"
                )
                return result
        return result
    finally:
        result["elapsed_seconds"] = round(time.monotonic() - started, 1)
        if result["status"] in {"TIMEOUT", "RENDER_FAILED"}:
            result["cancellation"] = cancel_own(prompt_id)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--api", type=Path, required=True,
        help="Previously validated, corrected local API workflow JSON",
    )
    p.add_argument(
        "--comfy-root", type=Path,
        default=Path.home() / "Downloads" / "ComfyUI-Setup"
        / "ComfyUI_windows_portable" / "ComfyUI",
    )
    p.add_argument(
        "--report", type=Path,
        default=Path.home() / "Documents" / "Audio-Analyze"
        / "outputs" / "gtrg_local_smoke" / "gtrg_tiny_video_result.json",
    )
    p.add_argument("--max-runtime-seconds", type=int, default=600)
    p.add_argument("--run", action="store_true",
                   help="Explicitly authorize one small local GPU generation")
    args = p.parse_args()
    if not 60 <= args.max_runtime_seconds <= 3600:
        p.error("Runtime limit must be 60-3600 seconds")
    if not args.api.is_file():
        p.error("Corrected local API graph not found")
    if args.api.stat().st_size > 15 * 1024 * 1024:
        p.error("API graph exceeds 15MB")
    if not (args.comfy_root / "output").is_dir():
        p.error("Existing ComfyUI output directory not found")
    try:
        info = get_object_info(BASE)
        raw = json.loads(args.api.read_text(encoding="utf-8-sig"))
        graph = read_api_graph(raw)
        prefix = "GTRG_Tiny_9f_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        tiny, summary = build_tiny(graph, info, prefix)
        if not queue_empty():
            raise RuntimeError("ComfyUI is busy; no test started")
        args.report.parent.mkdir(parents=True, exist_ok=True)
        report: dict[str, Any] = {
            "schema": "gtrg_native_9frame_local_test_v1",
            "mode": "LOCAL_RENDER" if args.run else "DRY_RUN_NO_GPU",
            "source_file_changed": False,
            "cloud_calls": 0,
            "max_runtime_seconds": args.max_runtime_seconds,
            "tiny_settings": summary,
            "result": {"status": "DRY_RUN_ONLY"},
        }
        if args.run:
            report["result"] = run_job(
                tiny, seconds=args.max_runtime_seconds,
                comfy_output=args.comfy_root / "output", prefix=prefix,
            )
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    except HTTPError as exc:
        # Never echo server validation body: it may contain input values/secrets.
        print(f"Local ComfyUI request rejected (HTTP {exc.code}); "
              "inspect local ComfyUI console. No cloud service was called.")
        return 3
    except (OSError, URLError, ValueError, RuntimeError, TypeError) as exc:
        print(f"Test stopped safely: {type(exc).__name__}: {exc}")
        return 3
    print("=== GTRG TINY LOCAL LTX 2.3 VIDEO CANARY ===")
    print(f"Mode: {report['mode']}")
    print(f"Resolution: {WIDTH}x{HEIGHT}, frames: {FRAMES}, sampler steps: {STEPS}")
    print(f"Changed numeric inputs: {len(summary['changed_inputs'])}")
    for changed in summary["changed_inputs"]:
        print(
            "  " + changed["class_type"] + "." + changed["input_name"]
            + " = " + str(changed["new_value"])
        )
    r = report["result"]
    print("Result: " + r["status"])
    for video in r.get("output_videos", []):
        print("Video file (check playback): " + video)
    if r.get("cancellation"):
        print("Timed out or failed; targeted cancellation attempted.")
    print("Report: " + str(args.report))
    print("No Modal or paid API calls. Original workflow untouched.")
    return 0 if not args.run or r["status"] == "PLAYABLE_FILE_NOT_YET_VERIFIED" else 4


if __name__ == "__main__":
    raise SystemExit(main())
