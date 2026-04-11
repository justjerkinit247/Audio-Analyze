from pathlib import Path
import argparse
import base64
import json
import mimetypes
import os
import time

import requests

API_BASE = "https://api.dev.runwayml.com"
API_VERSION = "2024-11-06"
SEED_DIR = Path("inputs/runway_seed_images")
ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


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


def find_seed_image():
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


def create_task(payload, prompt_image):
    body = {
        "model": payload["model"],
        "promptImage": prompt_image,
        "promptText": payload["promptText"],
        "ratio": payload["ratio"],
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
            f"Runway create_task failed: HTTP {response.status_code}\n{response.text}"
        )

    data = response.json()
    if "id" not in data:
        raise RuntimeError(
            f"Runway create_task returned no task id:\n{json.dumps(data, indent=2)}"
        )
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


def run_first_payload(payload_path, output_path):
    bundle = load_payloads(payload_path)
    payloads = bundle.get("payloads", [])
    if not payloads:
        raise ValueError("No payloads found in bundle.")

    payload = payloads[0]
    seed_image = find_seed_image()
    prompt_image = file_to_data_uri(seed_image)

    task_created = create_task(payload, prompt_image)
    task_id = task_created["id"]
    task_result = poll_task(task_id)

    downloaded_mp4 = None
    if task_result.get("status") == "SUCCEEDED":
        downloaded_mp4 = download_first_output(
            task_result,
            Path("outputs/runway_video_run/downloads") / "benchmark_2_real_seed.mp4"
        )

    result = {
        "file_stem": payload.get("file_stem"),
        "seed_image_used": str(seed_image.resolve()),
        "submitted_payload": payload,
        "task_created": task_created,
        "task_result": task_result,
        "downloaded_mp4": downloaded_mp4,
    }

    write_json(output_path, result)
    return result


def parse_args():
    parser = argparse.ArgumentParser(description="Runway seed image test")
    parser.add_argument("--payloads", default="outputs\\runway_video_run\\runway_payloads.json")
    parser.add_argument("--output", default="outputs\\runway_video_run\\runway_live_test_result_seed_image.json")
    return parser.parse_args()


def main():
    args = parse_args()
    result = run_first_payload(args.payloads, args.output)
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
