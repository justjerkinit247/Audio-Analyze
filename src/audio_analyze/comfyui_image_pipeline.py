from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
import argparse
import json
import os
import re
import secrets
import sys
import time

import requests


DEFAULT_COMFYUI_URL = "http://127.0.0.1:8188"
DEFAULT_CHECKPOINT = "RealVisXL_V5.0_fp16.safetensors"
DEFAULT_WIDTH = 768
DEFAULT_HEIGHT = 1024
DEFAULT_STEPS = 28
DEFAULT_CFG = 5.5
DEFAULT_SAMPLER = "dpmpp_2m"
DEFAULT_SCHEDULER = "karras"
DEFAULT_NEGATIVE_PROMPT = (
    "low quality, blurry, out of focus, bad anatomy, malformed hands, "
    "extra fingers, missing fingers, extra limbs, duplicated subjects, "
    "distorted face, deformed body, text, watermark, logo"
)
DEFAULT_TIMEOUT_SECONDS = 1800
DEFAULT_POLL_INTERVAL_SECONDS = 2.0
DEFAULT_WORKFLOW_PATH = (
    Path(__file__).resolve().parents[2] / "workflows" / "comfyui_sdxl_api.json"
)
DEFAULT_NODE_IDS = {
    "sampler": "3",
    "checkpoint": "4",
    "latent": "5",
    "positive": "6",
    "negative": "7",
    "save": "9",
}


class ComfyUIImageError(RuntimeError):
    """Raised when the local ComfyUI image-generation request cannot complete."""


def _read_json(path: str | Path) -> dict[str, Any]:
    file_path = Path(path).expanduser().resolve()
    if not file_path.is_file():
        raise FileNotFoundError(f"JSON file not found: {file_path}")
    data = json.loads(file_path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object in {file_path}")
    return data


def _write_json(path: str | Path, data: dict[str, Any]) -> Path:
    file_path = Path(path).expanduser().resolve()
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return file_path


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a positive integer.")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a positive integer.") from exc
    if parsed <= 0 or (isinstance(value, float) and not value.is_integer()):
        raise ValueError(f"{label} must be a positive integer.")
    return parsed


def _clean_prompt(value: Any, label: str) -> str:
    prompt = str(value or "").strip()
    if not prompt:
        raise ValueError(f"{label} cannot be empty.")
    if len(prompt) > 8000:
        raise ValueError(f"{label} is over the 8,000-character safety limit.")
    return prompt


def _safe_stem(value: str, fallback: str) -> str:
    candidate = Path(str(value or "")).stem
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", candidate).strip("._-")
    return cleaned[:96] or fallback


def load_api_workflow(path: str | Path = DEFAULT_WORKFLOW_PATH) -> dict[str, Any]:
    workflow = _read_json(path)
    if not workflow:
        raise ValueError("ComfyUI API workflow is empty.")
    invalid = [
        str(node_id)
        for node_id, node in workflow.items()
        if not isinstance(node, dict) or not isinstance(node.get("class_type"), str)
    ]
    if invalid:
        raise ValueError(
            "The workflow is not in ComfyUI API format. In ComfyUI, use "
            "Workflow > Export (API), not the regular UI workflow export. "
            f"Invalid node entries: {', '.join(invalid[:8])}"
        )
    return workflow


def _set_node_input(
    workflow: dict[str, Any],
    node_id: str,
    input_name: str,
    value: Any,
    expected_class: str,
) -> None:
    node = workflow.get(str(node_id))
    if not isinstance(node, dict):
        raise ComfyUIImageError(f"Workflow node {node_id!r} was not found.")
    actual_class = node.get("class_type")
    if actual_class != expected_class:
        raise ComfyUIImageError(
            f"Workflow node {node_id!r} should be {expected_class}, "
            f"but is {actual_class!r}. Update the node IDs for this workflow."
        )
    inputs = node.get("inputs")
    if not isinstance(inputs, dict) or input_name not in inputs:
        raise ComfyUIImageError(
            f"Workflow node {node_id!r} ({expected_class}) has no "
            f"{input_name!r} input."
        )
    inputs[input_name] = value


def prepare_api_workflow(
    workflow: dict[str, Any],
    *,
    positive_prompt: str,
    negative_prompt: str = DEFAULT_NEGATIVE_PROMPT,
    checkpoint: str = DEFAULT_CHECKPOINT,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    steps: int = DEFAULT_STEPS,
    cfg: float = DEFAULT_CFG,
    seed: int | None = None,
    sampler_name: str = DEFAULT_SAMPLER,
    scheduler: str = DEFAULT_SCHEDULER,
    filename_prefix: str = "AudioAnalyze",
    node_ids: dict[str, str] | None = None,
) -> dict[str, Any]:
    positive = _clean_prompt(positive_prompt, "Positive prompt")
    negative = str(negative_prompt or "").strip()
    if not str(checkpoint or "").strip():
        raise ValueError("Checkpoint filename cannot be empty.")

    width_value = _positive_int(width, "Width")
    height_value = _positive_int(height, "Height")
    if width_value % 8 or height_value % 8:
        raise ValueError("SDXL width and height must both be multiples of 8.")
    step_value = _positive_int(steps, "Steps")
    try:
        cfg_value = float(cfg)
    except (TypeError, ValueError) as exc:
        raise ValueError("CFG must be a number.") from exc
    if not 0.0 < cfg_value <= 30.0:
        raise ValueError("CFG must be greater than 0 and no more than 30.")

    actual_seed = int(seed) if seed is not None else secrets.randbelow(2**63 - 1)
    if actual_seed < 0 or actual_seed >= 2**64:
        raise ValueError("Seed must be between 0 and 2^64 - 1.")

    ids = {**DEFAULT_NODE_IDS, **(node_ids or {})}
    prepared = deepcopy(workflow)
    _set_node_input(
        prepared, ids["checkpoint"], "ckpt_name", str(checkpoint), "CheckpointLoaderSimple"
    )
    _set_node_input(
        prepared, ids["positive"], "text", positive, "CLIPTextEncode"
    )
    _set_node_input(
        prepared, ids["negative"], "text", negative, "CLIPTextEncode"
    )
    _set_node_input(
        prepared, ids["sampler"], "seed", actual_seed, "KSampler"
    )
    _set_node_input(
        prepared, ids["sampler"], "steps", step_value, "KSampler"
    )
    _set_node_input(
        prepared, ids["sampler"], "cfg", cfg_value, "KSampler"
    )
    _set_node_input(
        prepared, ids["sampler"], "sampler_name", str(sampler_name), "KSampler"
    )
    _set_node_input(
        prepared, ids["sampler"], "scheduler", str(scheduler), "KSampler"
    )
    _set_node_input(
        prepared, ids["latent"], "width", width_value, "EmptyLatentImage"
    )
    _set_node_input(
        prepared, ids["latent"], "height", height_value, "EmptyLatentImage"
    )
    _set_node_input(
        prepared, ids["latent"], "batch_size", 1, "EmptyLatentImage"
    )
    _set_node_input(
        prepared, ids["save"], "filename_prefix", str(filename_prefix), "SaveImage"
    )
    return prepared


def analyze_audio_for_image_context(audio_path: str | Path) -> dict[str, Any]:
    from .analyzer import analyze_audio_file

    path = Path(audio_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Audio file not found: {path}")
    return analyze_audio_file(path)


def compile_image_prompt(
    concept: str,
    audio_analysis: dict[str, Any] | None = None,
) -> str:
    """Keep the user's visual brief authoritative; use audio only as a secondary cue."""
    base = _clean_prompt(concept, "Visual concept")
    additions = [
        "Create one intentional still-image keyframe with a clear focal subject, "
        "coherent composition, physically plausible anatomy and perspective, "
        "consistent lighting, and readable separation between foreground and background."
    ]
    if audio_analysis:
        tempo = audio_analysis.get("tempo_bpm")
        if tempo is not None:
            try:
                tempo_value = float(tempo)
            except (TypeError, ValueError):
                tempo_value = None
            if tempo_value is not None and tempo_value > 0:
                if tempo_value >= 140:
                    pace = "fast, high-energy"
                elif tempo_value >= 110:
                    pace = "energetic, groove-led"
                elif tempo_value >= 85:
                    pace = "moderate, rhythmically steady"
                else:
                    pace = "slow, deliberate"
                additions.append(
                    f"Music alignment: the source track is approximately {tempo_value:.1f} BPM "
                    f"with a {pace} rhythmic feel. Let that influence pose energy and visual "
                    "intensity only; do not add literal musical symbols or objects unless the "
                    "visual brief asks for them."
                )
    return base + "\n\n" + " ".join(additions)


def refine_prompt_with_gemma(
    prompt: str,
    *,
    model: str = "gemma3:4b",
    client: Any = None,
) -> str:
    """Optionally polish the prompt with local Ollama/Gemma without changing its concept."""
    from .local_ai_client import LocalAIClient, LocalAIConfig

    active_client = client or LocalAIClient(LocalAIConfig.from_env(model=model))
    system = (
        "You are a precise SDXL prompt editor. Rewrite the user's visual brief as one "
        "high-information positive image-generation prompt. Preserve the exact requested "
        "subjects, subject count, identities or roles, wardrobe, action, setting, props, "
        "and style. Do not add people, props, text, logos, or story elements. Do not turn "
        "a still image into a video prompt. Do not output a heading, list, code fence, "
        "negative prompt, or explanation. Keep the result below 1,800 characters."
    )
    result = str(
        active_client.chat_text(
            system,
            "Polish this image prompt without changing its meaning:\n\n" + prompt,
        )
        or ""
    ).strip()
    result = re.sub(r"^\x60{3}(?:text|markdown)?\s*", "", result, flags=re.IGNORECASE)
    result = re.sub(r"\s*\x60{3}$", "", result).strip()
    if not result or len(result) > 1800:
        raise ComfyUIImageError(
            "Gemma prompt refinement returned empty text or exceeded 1,800 characters."
        )
    forbidden = (
        "[SUBJECT_LOCK]",
        "[SEED_IMAGE_DESCRIPTION]",
        "[AUDIO_TIMING]",
        "[TAP_SYNC]",
        "[MOTION_PROMPT]",
        "[NEGATIVE_PROMPT]",
    )
    if any(marker in result for marker in forbidden):
        raise ComfyUIImageError(
            "Gemma prompt refinement included an Audio-Analyze control marker; "
            "the image was not submitted."
        )
    return result


class ComfyUIClient:
    def __init__(
        self,
        base_url: str = DEFAULT_COMFYUI_URL,
        *,
        session: Any = None,
    ) -> None:
        self.base_url = str(base_url or DEFAULT_COMFYUI_URL).rstrip("/")
        self.session = session or requests

    def _request_json(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = self.base_url + path
        try:
            response = getattr(self.session, method)(url, **kwargs)
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise ComfyUIImageError(
                f"ComfyUI request failed at {url}: {exc}. Confirm that ComfyUI is "
                f"running and reachable at {self.base_url}."
            ) from exc
        except ValueError as exc:
            raise ComfyUIImageError(
                f"ComfyUI returned invalid JSON from {url}."
            ) from exc
        if not isinstance(payload, dict):
            raise ComfyUIImageError(f"ComfyUI returned an unexpected response from {url}.")
        return payload

    def health_check(self) -> dict[str, Any]:
        return self._request_json("get", "/system_stats", timeout=20)

    def queue_prompt(self, workflow: dict[str, Any]) -> str:
        payload = self._request_json(
            "post",
            "/prompt",
            json={"prompt": workflow, "client_id": "audio-analyze-local"},
            timeout=60,
        )
        node_errors = payload.get("node_errors") or {}
        if node_errors:
            raise ComfyUIImageError(
                "ComfyUI rejected the workflow before generation: "
                + json.dumps(node_errors, ensure_ascii=False)[:3000]
            )
        prompt_id = str(payload.get("prompt_id") or "").strip()
        if not prompt_id:
            raise ComfyUIImageError(
                "ComfyUI accepted no prompt ID. Response: "
                + json.dumps(payload, ensure_ascii=False)[:1500]
            )
        return prompt_id

    def wait_for_history(
        self,
        prompt_id: str,
        *,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    ) -> dict[str, Any]:
        timeout = _positive_int(timeout_seconds, "Timeout")
        interval = max(0.25, float(poll_interval_seconds))
        started = time.monotonic()
        while time.monotonic() - started < timeout:
            payload = self._request_json(
                "get", f"/history/{prompt_id}", timeout=30
            )
            record = payload.get(prompt_id)
            if isinstance(record, dict):
                status = record.get("status") or {}
                status_str = str(status.get("status_str") or "").lower()
                if status_str in {"error", "failed"}:
                    messages = status.get("messages") or []
                    raise ComfyUIImageError(
                        "ComfyUI generation failed: "
                        + json.dumps(messages, ensure_ascii=False)[:3000]
                    )
                if status.get("completed") is True or status_str == "success":
                    return record
            time.sleep(interval)
        raise TimeoutError(
            f"ComfyUI did not finish prompt {prompt_id} within {timeout} seconds."
        )

    @staticmethod
    def image_outputs(history_record: dict[str, Any]) -> list[dict[str, str]]:
        outputs = history_record.get("outputs") or {}
        images: list[dict[str, str]] = []
        for node_output in outputs.values():
            if not isinstance(node_output, dict):
                continue
            for image in node_output.get("images") or []:
                if not isinstance(image, dict):
                    continue
                filename = str(image.get("filename") or "").strip()
                if not filename:
                    continue
                images.append(
                    {
                        "filename": filename,
                        "subfolder": str(image.get("subfolder") or ""),
                        "type": str(image.get("type") or "output"),
                    }
                )
        return images

    def download_outputs(
        self,
        history_record: dict[str, Any],
        output_dir: str | Path,
        *,
        filename_stem: str,
    ) -> list[Path]:
        output_path = Path(output_dir).expanduser().resolve()
        output_path.mkdir(parents=True, exist_ok=True)
        image_records = self.image_outputs(history_record)
        if not image_records:
            raise ComfyUIImageError(
                "ComfyUI reported success but the workflow returned no saved images. "
                "Confirm that the API workflow ends in a SaveImage node."
            )

        saved: list[Path] = []
        for index, image in enumerate(image_records, start=1):
            source_name = Path(image["filename"]).name
            suffix = Path(source_name).suffix.lower()
            if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
                suffix = ".png"
            index_suffix = f"_{index:02d}" if len(image_records) > 1 else ""
            destination = output_path / f"{filename_stem}{index_suffix}{suffix}"
            if destination.exists():
                raise FileExistsError(
                    f"Refusing to overwrite an existing generated image: {destination}"
                )
            try:
                response = self.session.get(
                    self.base_url + "/view",
                    params={
                        "filename": image["filename"],
                        "subfolder": image["subfolder"],
                        "type": image["type"],
                    },
                    timeout=120,
                )
                response.raise_for_status()
            except requests.RequestException as exc:
                raise ComfyUIImageError(
                    f"Could not retrieve ComfyUI output {source_name}: {exc}"
                ) from exc
            content = getattr(response, "content", b"")
            if not content:
                raise ComfyUIImageError(
                    f"ComfyUI returned an empty image for {source_name}."
                )
            destination.write_bytes(content)
            saved.append(destination)
        return saved

    def generate(
        self,
        workflow: dict[str, Any],
        output_dir: str | Path,
        *,
        filename_stem: str,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    ) -> dict[str, Any]:
        prompt_id = self.queue_prompt(workflow)
        history = self.wait_for_history(
            prompt_id,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )
        paths = self.download_outputs(
            history,
            output_dir,
            filename_stem=filename_stem,
        )
        return {
            "prompt_id": prompt_id,
            "status": "complete",
            "images": [str(path) for path in paths],
        }


def load_image_jobs(
    *,
    prompt: str | None = None,
    negative_prompt: str = DEFAULT_NEGATIVE_PROMPT,
    manifest_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    if manifest_path:
        manifest = _read_json(manifest_path)
        items = manifest.get("images")
        if not isinstance(items, list) or not items:
            raise ValueError("Image manifest must contain a non-empty 'images' array.")
        jobs = []
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"Manifest image entry {index} must be a JSON object.")
            jobs.append(
                {
                    "name": str(item.get("name") or f"scene_{index:02d}"),
                    "prompt": _clean_prompt(
                        item.get("prompt") or item.get("positive_prompt"),
                        f"Manifest positive prompt {index}",
                    ),
                    "negative_prompt": str(
                        item.get("negative_prompt") or negative_prompt
                    ),
                    "seed": item.get("seed"),
                }
            )
        return jobs
    if prompt:
        return [
            {
                "name": "scene_01_generated",
                "prompt": _clean_prompt(prompt, "Positive prompt"),
                "negative_prompt": negative_prompt,
                "seed": None,
            }
        ]
    raise ValueError("Supply --prompt or --manifest.")


def generate_image_jobs(
    jobs: list[dict[str, Any]],
    *,
    workflow_path: str | Path = DEFAULT_WORKFLOW_PATH,
    checkpoint: str = DEFAULT_CHECKPOINT,
    output_dir: str | Path,
    base_url: str = DEFAULT_COMFYUI_URL,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    steps: int = DEFAULT_STEPS,
    cfg: float = DEFAULT_CFG,
    sampler_name: str = DEFAULT_SAMPLER,
    scheduler: str = DEFAULT_SCHEDULER,
    global_seed: int | None = None,
    audio_analysis: dict[str, Any] | None = None,
    gemma_refine: bool = False,
    gemma_model: str = "gemma3:4b",
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    client: ComfyUIClient | None = None,
    prompt_refiner: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    if not jobs:
        raise ValueError("No image-generation jobs were supplied.")
    workflow = load_api_workflow(workflow_path)
    active_client = client or ComfyUIClient(base_url)
    active_client.health_check()

    root = Path(output_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    images_dir = root / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    records = []
    for index, job in enumerate(jobs, start=1):
        source_prompt = _clean_prompt(job.get("prompt"), f"Image {index} prompt")
        compiled_prompt = compile_image_prompt(source_prompt, audio_analysis)
        if gemma_refine:
            if prompt_refiner is not None:
                compiled_prompt = _clean_prompt(
                    prompt_refiner(compiled_prompt), f"Gemma-refined prompt {index}"
                )
            else:
                compiled_prompt = refine_prompt_with_gemma(
                    compiled_prompt, model=gemma_model
                )

        selected_seed = job.get("seed")
        if selected_seed is None and global_seed is not None:
            selected_seed = int(global_seed) + index - 1
        if selected_seed is None:
            selected_seed = secrets.randbelow(2**63 - 1)
        selected_seed = int(selected_seed)

        name = _safe_stem(str(job.get("name") or ""), f"scene_{index:02d}")
        prepared = prepare_api_workflow(
            workflow,
            positive_prompt=compiled_prompt,
            negative_prompt=str(job.get("negative_prompt") or DEFAULT_NEGATIVE_PROMPT),
            checkpoint=checkpoint,
            width=width,
            height=height,
            steps=steps,
            cfg=cfg,
            seed=selected_seed,
            sampler_name=sampler_name,
            scheduler=scheduler,
            filename_prefix=f"AudioAnalyze_{index:02d}_{name}",
        )
        generation = active_client.generate(
            prepared,
            images_dir,
            filename_stem=f"scene_{index:02d}_{name}",
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )
        records.append(
            {
                "index": index,
                "name": name,
                "seed": selected_seed,
                "source_prompt": source_prompt,
                "compiled_prompt": compiled_prompt,
                "negative_prompt": str(
                    job.get("negative_prompt") or DEFAULT_NEGATIVE_PROMPT
                ),
                **generation,
            }
        )

    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "provider": "comfyui_local",
        "comfyui_url": str(base_url).rstrip("/"),
        "checkpoint": checkpoint,
        "workflow": str(Path(workflow_path).expanduser().resolve()),
        "settings": {
            "width": width,
            "height": height,
            "steps": steps,
            "cfg": cfg,
            "sampler_name": sampler_name,
            "scheduler": scheduler,
            "gemma_refine": gemma_refine,
            "gemma_model": gemma_model if gemma_refine else None,
        },
        "audio_analysis": audio_analysis,
        "images": records,
        "status": "complete",
    }
    _write_json(root / "generation_report.json", report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate local image seeds through ComfyUI using an SDXL API workflow. "
            "Optionally add Audio-Analyze audio context and Gemma prompt refinement."
        )
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--prompt", help="Visual concept for one generated image.")
    source.add_argument(
        "--manifest",
        help="JSON file with an 'images' array; each entry has name and prompt fields.",
    )
    parser.add_argument("--negative-prompt", default=DEFAULT_NEGATIVE_PROMPT)
    parser.add_argument("--audio", help="Optional WAV/MP3/etc. track to analyze for tempo context.")
    parser.add_argument("--workflow", default=str(DEFAULT_WORKFLOW_PATH))
    parser.add_argument("--comfyui-url", default=os.environ.get("COMFYUI_BASE_URL", DEFAULT_COMFYUI_URL))
    parser.add_argument("--checkpoint", default=DEFAULT_CHECKPOINT)
    parser.add_argument("--output-dir")
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    parser.add_argument("--steps", type=int, default=DEFAULT_STEPS)
    parser.add_argument("--cfg", type=float, default=DEFAULT_CFG)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--sampler", default=DEFAULT_SAMPLER)
    parser.add_argument("--scheduler", default=DEFAULT_SCHEDULER)
    parser.add_argument("--gemma-refine", action="store_true")
    parser.add_argument("--gemma-model", default="gemma3:4b")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--poll-interval-seconds", type=float, default=DEFAULT_POLL_INTERVAL_SECONDS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        jobs = load_image_jobs(
            prompt=args.prompt,
            negative_prompt=args.negative_prompt,
            manifest_path=args.manifest,
        )
        audio_analysis = (
            analyze_audio_for_image_context(args.audio) if args.audio else None
        )
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + secrets.token_hex(3)
        output_dir = (
            Path(args.output_dir).expanduser().resolve()
            if args.output_dir
            else Path("outputs") / "comfyui_image_run" / run_id
        )
        workflow_path = Path(args.workflow).expanduser().resolve()
        report = generate_image_jobs(
            jobs,
            workflow_path=workflow_path,
            checkpoint=args.checkpoint,
            output_dir=output_dir,
            base_url=args.comfyui_url,
            width=args.width,
            height=args.height,
            steps=args.steps,
            cfg=args.cfg,
            sampler_name=args.sampler,
            scheduler=args.scheduler,
            global_seed=args.seed,
            audio_analysis=audio_analysis,
            gemma_refine=args.gemma_refine,
            gemma_model=args.gemma_model,
            timeout_seconds=args.timeout_seconds,
            poll_interval_seconds=args.poll_interval_seconds,
        )
        print("ComfyUI image generation completed.")
        print(f"Generated images : {sum(len(item['images']) for item in report['images'])}")
        print(f"Output folder    : {Path(output_dir).resolve()}")
        print(f"Generation report: {(Path(output_dir) / 'generation_report.json').resolve()}")
        for item in report["images"]:
            for image_path in item["images"]:
                print(f"  {image_path}")
        return 0
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
