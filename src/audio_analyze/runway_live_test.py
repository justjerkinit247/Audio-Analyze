from pathlib import Path
import argparse
import json
import os
import time
import requests

API_BASE = "https://api.dev.runwayml.com"
API_VERSION = "2024-11-06"

TEST_PROMPT_IMAGE = "https://upload.wikimedia.org/wikipedia/commons/8/85/Tour_Eiffel_Wikimedia_Commons_%28cropped%29.jpg"

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

def create_task(payload):
    body = {
        "model": payload["model"],
        "promptImage": TEST_PROMPT_IMAGE,
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

def run_first_payload(payload_path, output_path):
    bundle = load_payloads(payload_path)
    payloads = bundle.get("payloads", [])
    if not payloads:
        raise ValueError("No payloads found in bundle.")

    payload = payloads[0]
    task_created = create_task(payload)
    task_id = task_created["id"]
    task_result = poll_task(task_id)

    result = {
        "file_stem": payload.get("file_stem"),
        "submitted_payload": payload,
        "promptImageUsed": TEST_PROMPT_IMAGE,
        "task_created": task_created,
        "task_result": task_result,
    }

    write_json(output_path, result)
    return result

def parse_args():
    parser = argparse.ArgumentParser(description="Run the first live Runway API test from a generated payload bundle.")
    parser.add_argument("--payloads", default="outputs\\runway_video_run\\runway_payloads.json", help="Path to runway_payloads.json")
    parser.add_argument("--output", default="outputs\\runway_video_run\\runway_live_test_result.json", help="Path for live test result output JSON")
    return parser.parse_args()

def main():
    args = parse_args()
    result = run_first_payload(args.payloads, args.output)
    task_result = result["task_result"]

    print("Runway live test complete.")
    print(f"File stem   : {result['file_stem']}")
    print(f"Task id     : {task_result.get('id')}")
    print(f"Status      : {task_result.get('status')}")
    print(f"Result JSON : {Path(args.output).resolve()}")
    print(f"Output      : {task_result.get('output')}")

if __name__ == "__main__":
    main()
