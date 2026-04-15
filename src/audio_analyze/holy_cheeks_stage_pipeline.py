from pathlib import Path
import argparse
import io
import base64
import json
import os
import re
import time

import librosa
import numpy as np
import requests
from PIL import Image
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def scalarize(value):
    if value is None:
        return None
    if np.isscalar(value):
        return float(value)
    arr = np.asarray(value)
    if arr.size == 0:
        return None
    return float(arr.reshape(-1)[0])


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


def list_seed_images(seed_dir):
    seed_dir = Path(seed_dir)
    if not seed_dir.exists():
        raise FileNotFoundError(f"Seed image folder not found: {seed_dir.resolve()}")
    files = sorted([p for p in seed_dir.iterdir() if p.is_file() and p.suffix.lower() in ALLOWED_EXTS])
    if not files:
        raise FileNotFoundError(f"No supported image files found in {seed_dir.resolve()}")
    return files


def tiny_jpeg_data_uri(path, max_dim=512, jpeg_quality=55):
    img = Image.open(path).convert("RGB")
    w, h = img.size
    scale = min(max_dim / max(w, h), 1.0)
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))

    if (new_w, new_h) != (w, h):
        img = img.resize((new_w, new_h), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=jpeg_quality, optimize=True)
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def analyze_music_for_video(audio_path):
    y, sr = librosa.load(audio_path, sr=None, mono=True)
    duration = float(librosa.get_duration(y=y, sr=sr))

    tempo_raw, beats = librosa.beat.beat_track(y=y, sr=sr)
    tempo = scalarize(tempo_raw)

    rms = librosa.feature.rms(y=y)[0]
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)

    avg_rms = float(np.mean(rms)) if len(rms) else 0.0
    avg_centroid = float(np.mean(centroid)) if len(centroid) else 0.0
    onset_strength = float(np.mean(onset_env)) if len(onset_env) else 0.0

    if tempo is not None and tempo >= 140:
        energy = "very high"
        edit_pacing = "fast"
        choreography = "sharp, punchy, aggressive body accents with strong downbeat hits"
        camera = "quick reframes, punch-in moves, hard motion accents"
    elif tempo is not None and tempo >= 110:
        energy = "high"
        edit_pacing = "medium-fast"
        choreography = "confident rhythmic body movement, accenting kick and snare with visible groove"
        camera = "push-ins, lateral slides, energized performance framing"
    elif tempo is not None and tempo >= 85:
        energy = "moderate-high"
        edit_pacing = "medium"
        choreography = "groove-led movement, hip and shoulder phrasing, visible pulse with clean timing"
        camera = "controlled movement, readable framing, measured momentum"
    else:
        energy = "slow-burn"
        edit_pacing = "slow"
        choreography = "restrained movement with deliberate pose transitions and emotional phrasing"
        camera = "slow push-ins, held compositions, deliberate pacing"

    if avg_centroid >= 3000:
        lighting = "bright, crisp, high-contrast concert lighting with vivid highlight separation"
        style = "clean, glossy, vivid, performance-forward"
    elif avg_centroid >= 1800:
        lighting = "balanced music-video lighting with polished skin tones and clear subject separation"
        style = "cinematic but bright, stylish, performance-led"
    else:
        lighting = "moody contrast, denser atmosphere, deeper shadows, selective highlight control"
        style = "atmospheric, dramatic, shadow-shaped"

    if onset_strength >= 8:
        scene_motion = "highly reactive scene motion with cuts and body accents landing hard on rhythmic events"
    elif onset_strength >= 4:
        scene_motion = "noticeable rhythmic reactivity with strong phrase transitions and visible musical phrasing"
    else:
        scene_motion = "lighter rhythmic emphasis with broader phrase-based movement"

    return {
        "tempo_bpm": round(tempo, 3) if tempo is not None else None,
        "duration_seconds": round(duration, 3),
        "energy_profile": energy,
        "edit_pacing": edit_pacing,
        "choreography_notes": choreography,
        "camera_notes": camera,
        "lighting_notes": lighting,
        "style_notes": style,
        "scene_motion_notes": scene_motion,
        "mix_reactivity_notes": f"Average RMS {avg_rms:.4f}, spectral centroid {avg_centroid:.2f}, onset strength {onset_strength:.2f}",
    }


def build_scenes(duration_seconds, max_scenes=6, min_scene_seconds=5.0, max_scene_seconds=8.0):
    total_duration = float(duration_seconds)
    target_scene_len = max(min_scene_seconds, min(max_scene_seconds, total_duration / max_scenes))
    scene_count = max(1, min(max_scenes, int(np.ceil(total_duration / target_scene_len))))
    scene_len = total_duration / scene_count

    scenes = []
    for i in range(scene_count):
        start_t = i * scene_len
        end_t = min(total_duration, (i + 1) * scene_len)
        duration = end_t - start_t

        if i == 0:
            scene_type = "intro hook"
        elif i == scene_count - 1:
            scene_type = "closing phrase"
        else:
            scene_type = "performance phrase"

        scenes.append({
            "scene_index": i + 1,
            "start": round(float(start_t), 3),
            "end": round(float(end_t), 3),
            "duration": round(float(duration), 3),
            "scene_type": scene_type
        })
    return scenes


def build_scene_prompt(file_stem, production_notes, scene, total_scenes, bpm):
    bpm_text = f"{bpm:.2f} BPM" if bpm is not None else "the detected groove"
    return (
        f"Cinematic vertical music video for {file_stem}. "
        f"Scene {scene['scene_index']} of {total_scenes}. "
        f"This scene covers {scene['start']:.2f}s to {scene['end']:.2f}s of the song. "
        f"Movement, choreography, camera motion, and visual accents must feel locked to {bpm_text}. "
        f"Choreography direction: {production_notes['choreography_notes']}. "
        f"Style direction: {production_notes['style_notes']}. "
        f"Lighting direction: {production_notes['lighting_notes']}. "
        f"Scene note: {scene['scene_type']}. "
        f"Production note: edit pacing should feel {production_notes['edit_pacing']} with {production_notes['scene_motion_notes']}. "
        f"Camera direction: {production_notes['camera_notes']}. "
        f"Actors should visibly phrase movement to the beat and not drift randomly. "
        f"Short-form social framing, clean subject readability, polished realism, strong performance energy."
    )


def build_scene_plan(audio_path, seed_dir, output_json, ratio="9:16", max_scenes=6):
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path.resolve()}")

    ratio = normalize_ratio(ratio)
    file_stem = audio_path.stem
    production_notes = analyze_music_for_video(audio_path)
    scenes = build_scenes(production_notes["duration_seconds"], max_scenes=max_scenes)
    images = list_seed_images(seed_dir)

    results = []
    for idx, scene in enumerate(scenes, start=1):
        chosen_image = images[(idx - 1) % len(images)]
        prompt_text = build_scene_prompt(
            file_stem=file_stem,
            production_notes=production_notes,
            scene=scene,
            total_scenes=len(scenes),
            bpm=production_notes["tempo_bpm"],
        )
        duration = max(5, min(8, int(round(scene["duration"]))))

        results.append({
            "clip_index": idx,
            "file_stem": file_stem,
            "scene": scene,
            "tempo_bpm": production_notes["tempo_bpm"],
            "production_notes": production_notes,
            "seed_image_used": str(chosen_image.resolve()),
            "prompt_text": prompt_text,
            "ratio": ratio,
            "duration": duration,
            "status": "planned",
        })

    final = {
        "file_stem": file_stem,
        "tempo_bpm": production_notes["tempo_bpm"],
        "scene_count": len(scenes),
        "ratio": ratio,
        "production_notes": production_notes,
        "results": results,
        "status": "planned",
    }
    write_json(output_json, final)
    return final


def make_session():
    session = requests.Session()
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=None,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=4)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


SESSION = make_session()


def runway_headers():
    api_key = os.environ.get("RUNWAYML_API_SECRET")
    if not api_key:
        raise RuntimeError("RUNWAYML_API_SECRET is not set in this PowerShell window.")
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-Runway-Version": API_VERSION,
        "Connection": "keep-alive",
    }


def create_task(prompt_text, prompt_image, ratio, duration, model="gen4_turbo"):
    body = {
        "model": model,
        "promptImage": prompt_image,
        "promptText": prompt_text,
        "ratio": ratio,
        "duration": duration,
    }

    response = SESSION.post(
        f"{API_BASE}/v1/image_to_video",
        headers=runway_headers(),
        json=body,
        timeout=(20, 120),
    )

    if not response.ok:
        raise RuntimeError(
            f"Runway create_task failed: HTTP {response.status_code}\n"
            f"{response.text}\n\nSubmitted body:\n{json.dumps(body, indent=2)[:4000]}"
        )

    data = response.json()
    if "id" not in data:
        raise RuntimeError(f"Runway create_task returned no task id:\n{json.dumps(data, indent=2)}")
    data["submitted_body"] = body
    return data


def poll_task(task_id, max_polls=90, sleep_seconds=5):
    for _ in range(max_polls):
        response = SESSION.get(
            f"{API_BASE}/v1/tasks/{task_id}",
            headers=runway_headers(),
            timeout=(20, 60),
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

    response = SESSION.get(url, timeout=(20, 180))
    response.raise_for_status()
    destination.write_bytes(response.content)
    return str(destination.resolve())


def submit_scene(plan_json, output_json, clip_index):
    plan = json.loads(Path(plan_json).read_text(encoding="utf-8-sig"))
    results = plan["results"]
    match = None
    for item in results:
        if int(item["clip_index"]) == int(clip_index):
            match = item
            break

    if match is None:
        raise ValueError(f"Clip index {clip_index} not found")

    result = {
        "clip_index": int(clip_index),
        "file_stem": match["file_stem"],
        "scene": match["scene"],
        "seed_image_used": match["seed_image_used"],
        "prompt_text": match["prompt_text"],
        "ratio": match["ratio"],
        "duration": match["duration"],
        "status": "preparing",
    }
    write_json(output_json, result)

    image_path = Path(match["seed_image_used"])
    prompt_image = tiny_jpeg_data_uri(image_path, max_dim=512, jpeg_quality=55)

    result["status"] = "submitting"
    write_json(output_json, result)

    task_created = create_task(
        prompt_text=match["prompt_text"],
        prompt_image=prompt_image,
        ratio=match["ratio"],
        duration=match["duration"],
        model="gen4_turbo",
    )
    result["task_created"] = task_created
    result["status"] = "polling"
    write_json(output_json, result)

    task_result = poll_task(task_created["id"])
    result["task_result"] = task_result
    result["status"] = task_result.get("status", "unknown")
    write_json(output_json, result)

    downloaded_mp4 = None
    if task_result.get("status") == "SUCCEEDED":
        downloads_dir = Path("outputs/runway_video_run/downloads")
        downloads_dir.mkdir(parents=True, exist_ok=True)
        downloaded_mp4 = download_first_output(
            task_result,
            downloads_dir / f"{sanitize_name(match['file_stem'])}_scene_{int(clip_index):02d}.mp4"
        )

    result["downloaded_mp4"] = downloaded_mp4
    write_json(output_json, result)
    return result


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    p1 = sub.add_parser("plan")
    p1.add_argument("--audio", required=True)
    p1.add_argument("--seed-dir", default="inputs\\runway_seed_images")
    p1.add_argument("--output", required=True)
    p1.add_argument("--ratio", default="9:16")
    p1.add_argument("--max-scenes", type=int, default=6)

    p2 = sub.add_parser("submit-one")
    p2.add_argument("--plan-json", required=True)
    p2.add_argument("--output", required=True)
    p2.add_argument("--clip-index", type=int, default=1)

    args = parser.parse_args()

    if args.command == "plan":
        result = build_scene_plan(
            audio_path=args.audio,
            seed_dir=args.seed_dir,
            output_json=args.output,
            ratio=args.ratio,
            max_scenes=args.max_scenes,
        )
        print("Scene plan created.")
        print(Path(args.output).resolve())
        print(f"Scene count: {result['scene_count']}")
        print(json.dumps(result["production_notes"], indent=2))

    elif args.command == "submit-one":
        result = submit_scene(
            plan_json=args.plan_json,
            output_json=args.output,
            clip_index=args.clip_index,
        )
        print("Single scene submit complete.")
        print(Path(args.output).resolve())
        print(f"Status: {result.get('status')}")
        print(f"Downloaded MP4: {result.get('downloaded_mp4')}")


if __name__ == "__main__":
    main()





