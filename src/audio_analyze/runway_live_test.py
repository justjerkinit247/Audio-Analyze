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
SEED_DIR = Path("inputs/runway_seed_images")
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


def load_payloads(payload_path):
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
        raise ValueError(
            f"Unsupported ratio '{value}'. Use one of: {sorted(VALID_RATIOS)} or aliases {sorted(RATIO_MAP)}"
        )
    return ratio


def sanitize_name(name):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._-")
    return cleaned or "runway_output"


def find_seed_image(seed_image=None):
    if seed_image:
        path = Path(seed_image)
        if not path.exists():
            raise FileNotFoundError(f"Seed image not found: {path.resolve()}")
        if path.suffix.lower() not in ALLOWED_EXTS:
            raise ValueError(f"Unsupported image type: {path.suffix}")
        return path

    if not SEED_DIR.exists():
        raise FileNotFoundError(f"Seed image folder not found: {SEED_DIR.resolve()}")

    files = sorted(
        [p for p in SEED_DIR.iterdir() if p.is_file() and p.suffix.lower() in ALLOWED_EXTS]
    )
    if not files:
        raise FileNotFoundError(
            f"No supported image files found in {SEED_DIR.resolve()}."
        )
    return files[0]


def file_to_data_uri(path):
    mime_type, _ = mimetypes.guess_type(str(path))
    if not mime_type:
        raise RuntimeError(f"Could not detect MIME type for {path}")
    raw = path.read_bytes()
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def choose_payload(bundle, file_stem=None):
    payloads = bundle.get("payloads", [])
    if not payloads:
        raise ValueError("No payloads found in bundle.")

    if not file_stem:
        return payloads[0]

    target = file_stem.strip().lower()
    for payload in payloads:
        stem = str(payload.get("file_stem", "")).strip().lower()
        if stem == target:
            return payload
        if target in stem or stem in target:
            return payload

    available = [p.get("file_stem") for p in payloads]
    raise ValueError(f"Could not find payload for '{file_stem}'. Available: {available}")


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
            f"{response.text}\n\n"
            f"Submitted body:\n{json.dumps(body, indent=2)}"
        )

    data = response.json()
    if "id" not in data:
        raise RuntimeError(
            f"Runway create_task returned no task id:\n{json.dumps(data, indent=2)}"
        )
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
            raise RuntimeError(
                f"Runway poll_task failed: HTTP {response.status_code}\n{response.text}"
            )

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


def run_selected_payload(payload_path, output_path, file_stem=None, seed_image=None, ratio=None):
    bundle = load_payloads(payload_path)
    payload = choose_payload(bundle, file_stem=file_stem).copy()

    chosen_seed = find_seed_image(seed_image=seed_image)
    prompt_image = file_to_data_uri(chosen_seed)

    task_created = create_task(payload, prompt_image, ratio_override=ratio)
    task_id = task_created["id"]
    task_result = poll_task(task_id)

    downloaded_mp4 = None
    if task_result.get("status") == "SUCCEEDED":
        stem = sanitize_name(payload.get("file_stem", "runway_output"))
        downloaded_mp4 = download_first_output(
            task_result,
            Path("outputs/runway_video_run/downloads") / f"{stem}.mp4"
        )

    result = {
        "file_stem": payload.get("file_stem"),
        "seed_image_used": str(chosen_seed.resolve()),
        "submitted_payload": payload,
        "task_created": task_created,
        "task_result": task_result,
        "downloaded_mp4": downloaded_mp4,
    }

    write_json(output_path, result)
    return result


def parse_args():
    parser = argparse.ArgumentParser(description="Runway explicit payload + seed image test")
    parser.add_argument("--payloads", default="outputs\\runway_video_run\\runway_payloads.json")
    parser.add_argument("--output", default="outputs\\runway_video_run\\runway_live_test_result_seed_image.json")
    parser.add_argument("--file-stem", help="Exact or partial file_stem to run")
    parser.add_argument("--seed-image", help="Exact image path to use")
    parser.add_argument("--ratio", default=None, help="Valid Runway ratio or alias like 9:16, 16:9, 1:1")
    return parser.parse_args()


def main():
    args = parse_args()
    result = run_selected_payload(
        args.payloads,
        args.output,
        file_stem=args.file_stem,
        seed_image=args.seed_image,
        ratio=args.ratio,
    )
    task_result = result["task_result"]

    print("Runway live seed-image test complete.")
    print(f"File stem      : {result['file_stem']}")
    print(f"Seed image     : {result['seed_image_used']}")
    print(f"Task id        : {task_result.get('id')}")
    print(f"Status         : {task_result.get('status')}")
    print(f"Result JSON    : {Path(args.output).resolve()}")
    print(f"Downloaded MP4 : {result.get('downloaded_mp4')}")
    print(f"Output         : {task_result.get('output')}")


if __name__ == "__main__":
    main()
