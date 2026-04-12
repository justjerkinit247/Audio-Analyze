from pathlib import Path
import argparse
import base64
import json
import mimetypes
import os
import re
import time

import requests

API_BASE = "https://api.dev.runwayml.com"
API_VERSION = "2024-11-06"
ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

RATIO_MAP = {
    "9:16": "720:1280",
    "16:9": "1280:720",
    "1:1": "960:960",
}
VALID_RATIOS = {
    "1280:720",
    "720:1280",
    "1104:832",
    "960:960",
    "832:1104",
    "1584:672",
}

def load_payload_bundle(payload_path):
    payload_path = Path(payload_path)
    if not payload_path.exists():
        raise FileNotFoundError(f"Payload file not found: {payload_path}")
    return json.loads(payload_path.read_text(encoding="utf-8"))

def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")

def runway_headers():
    api_key = os.environ.get("RUNWAYML_API_SECRET")
    if not api_key:
        raise RuntimeError("RUNWAYML_API_SECRET is not set in this PowerShell window.")
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-Runway-Version": API_VERSION,
    }

def normalize_ratio(value):
    ratio = RATIO_MAP.get(value, value)
    if ratio not in VALID_RATIOS:
        raise ValueError(f"Unsupported ratio '{value}'. Use one of: {sorted(VALID_RATIOS)} or aliases {sorted(RATIO_MAP)}")
    return ratio

def sanitize_name(name):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._-")
    return cleaned or "runway_output"

def list_seed_images(seed_dir):
    seed_dir = Path(seed_dir)
    if not seed_dir.exists():
        raise FileNotFoundError(f"Seed image folder not found: {seed_dir.resolve()}")
    files = sorted([p for p in seed_dir.iterdir() if p.is_file() and p.suffix.lower() in ALLOWED_EXTS])
    if not files:
        raise FileNotFoundError(f"No supported image files found in {seed_dir.resolve()}")
    return files

def file_to_data_uri(path):
    mime_type, _ = mimetypes.guess_type(str(path))
    if not mime_type:
        raise RuntimeError(f"Could not detect MIME type for {path}")
    raw = path.read_bytes()
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"

def choose_payloads(bundle, file_stem=None):
    payloads = bundle.get("payloads", [])
    if not payloads:
        raise ValueError("No payloads found in bundle.")

    if not file_stem:
        return payloads

    target = file_stem.strip().lower()
    matched = []
    for payload in payloads:
        stem = str(payload.get("file_stem", "")).strip().lower()
        if stem == target or target in stem or stem in target:
            matched.append(payload)

    if not matched:
        available = [p.get("file_stem") for p in payloads]
        raise ValueError(f"Could not find payloads for '{file_stem}'. Available: {available}")

    return matched

def create_task(payload, prompt_image, ratio_override=None):
    ratio = normalize_ratio(ratio_override or payload.get("ratio", "1280:720"))

    body = {
        "model": payload["model"],
        "promptImage": prompt_image,
        "promptText": payload["promptText"],
        "ratio": ratio,
        "duration": payload["duration"],
    }

    response = requests.post(
        f"{API_BASE}/v1/image_to_video",
        headers=runway_headers(),
        json=body,
        timeout=120,
    )

    if not response.ok:
        raise RuntimeError(
            f"Runway create_task failed: HTTP {response.status_code}\n"
            f"{response.text}\n\nSubmitted body:\n{json.dumps(body, indent=2)}"
        )

    data = response.json()
    if "id" not in data:
        raise RuntimeError(f"Runway create_task returned no task id:\n{json.dumps(data, indent=2)}")
    data["submitted_body"] = body
    return data

def poll_task(task_id, max_polls=72, sleep_seconds=5):
    for _ in range(max_polls):
        response = requests.get(
            f"{API_BASE}/v1/tasks/{task_id}",
            headers=runway_headers(),
            timeout=120,
        )

        if not response.ok:
            raise RuntimeError(f"Runway poll_task failed: HTTP {response.status_code}\n{response.text}")

        data = response.json()
        status = data.get("status")

        if status in {"SUCCEEDED", "FAILED", "CANCELED"}:
            return data

        time.sleep(sleep_seconds)

    raise TimeoutError(f"Task {task_id} did not finish within the polling window.")

def download_first_output(task_result, destination):
    output = task_result.get("output") or []
    if not output:
        return None

    url = output[0]
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    response = requests.get(url, timeout=180)
    response.raise_for_status()
    destination.write_bytes(response.content)
    return str(destination.resolve())

def run_multi_clip(payload_path, output_path, file_stem=None, seed_dir="inputs/runway_seed_images", ratio=None):
    bundle = load_payload_bundle(payload_path)
    selected_payloads = choose_payloads(bundle, file_stem=file_stem)
    seed_images = list_seed_images(seed_dir)

    results = []
    downloads_dir = Path("outputs/runway_video_run/downloads")
    downloads_dir.mkdir(parents=True, exist_ok=True)

    for i, payload in enumerate(selected_payloads, start=1):
        payload = payload.copy()
        chosen_seed = seed_images[(i - 1) % len(seed_images)]
        prompt_image = file_to_data_uri(chosen_seed)

        task_created = create_task(payload, prompt_image, ratio_override=ratio)
        task_result = poll_task(task_created["id"])

        downloaded_mp4 = None
        if task_result.get("status") == "SUCCEEDED":
            stem = sanitize_name(payload.get("file_stem", "runway_output"))
            downloaded_mp4 = download_first_output(
                task_result,
                downloads_dir / f"{stem}_clip_{i:02d}.mp4"
            )

        result = {
            "clip_index": i,
            "file_stem": payload.get("file_stem"),
            "seed_image_used": str(chosen_seed.resolve()),
            "submitted_payload": payload,
            "task_created": task_created,
            "task_result": task_result,
            "downloaded_mp4": downloaded_mp4,
        }
        results.append(result)

    final = {
        "payload_count": len(selected_payloads),
        "results": results,
    }

    write_json(output_path, final)
    return final

def parse_args():
    parser = argparse.ArgumentParser(description="Runway multi-clip runner")
    parser.add_argument("--payloads", default="outputs\\runway_video_run\\runway_payloads.json")
    parser.add_argument("--output", default="outputs\\runway_video_run\\runway_multi_clip_result.json")
    parser.add_argument("--file-stem", required=True)
    parser.add_argument("--seed-dir", default="inputs\\runway_seed_images")
    parser.add_argument("--ratio", default="9:16")
    return parser.parse_args()

def main():
    args = parse_args()
    result = run_multi_clip(
        args.payloads,
        args.output,
        file_stem=args.file_stem,
        seed_dir=args.seed_dir,
        ratio=args.ratio,
    )

    print("Runway multi-clip runner complete.")
    print(f"Payload count   : {result['payload_count']}")
    print(f"Result JSON     : {Path(args.output).resolve()}")

    for item in result["results"]:
        print(
            f"Clip {item['clip_index']:02d} | "
            f"Stem: {item['file_stem']} | "
            f"Status: {item['task_result'].get('status')} | "
            f"Image: {item['seed_image_used']} | "
            f"MP4: {item.get('downloaded_mp4')}"
        )

if __name__ == "__main__":
    main()
