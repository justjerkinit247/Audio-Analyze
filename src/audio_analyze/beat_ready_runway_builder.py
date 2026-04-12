from pathlib import Path
import argparse
import base64
import json
import mimetypes
import os
import re
import time
import traceback

import librosa
import numpy as np
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


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def append_log(log_path, text):
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(text.rstrip() + "\n")


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


def scalarize(value):
    if value is None:
        return None
    if np.isscalar(value):
        return float(value)
    arr = np.asarray(value)
    if arr.size == 0:
        return None
    return float(arr.reshape(-1)[0])


def analyze_music_for_video(audio_path):
    y, sr = librosa.load(audio_path, sr=None, mono=True)
    duration = float(librosa.get_duration(y=y, sr=sr))

    tempo_raw, beats = librosa.beat.beat_track(y=y, sr=sr)
    tempo = scalarize(tempo_raw)
    beat_times = librosa.frames_to_time(beats, sr=sr).tolist()

    rms = librosa.feature.rms(y=y)[0]
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)

    avg_rms = float(np.mean(rms)) if len(rms) else 0.0
    avg_centroid = float(np.mean(centroid)) if len(centroid) else 0.0
    onset_strength = float(np.mean(onset_env)) if len(onset_env) else 0.0

    if tempo is not None and tempo >= 140:
        energy = "very high"
        cut_speed = "fast"
        choreography = "sharp, punchy, aggressive body accents with strong downbeat hits"
        camera = "quick reframes, punch-in moves, hard motion accents"
    elif tempo is not None and tempo >= 110:
        energy = "high"
        cut_speed = "medium-fast"
        choreography = "confident rhythmic body movement, accenting the kick and snare with visible groove"
        camera = "push-ins, lateral slides, energized performance framing"
    elif tempo is not None and tempo >= 85:
        energy = "moderate"
        cut_speed = "medium"
        choreography = "groove-led movement, hip and shoulder phrasing, visible pulse with clean timing"
        camera = "controlled movement, readable framing, measured momentum"
    else:
        energy = "slow-burn"
        cut_speed = "slow"
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

    production_notes = {
        "tempo_bpm": round(tempo, 3) if tempo is not None else None,
        "duration_seconds": round(duration, 3),
        "energy_profile": energy,
        "edit_pacing": cut_speed,
        "choreography_notes": choreography,
        "camera_notes": camera,
        "lighting_notes": lighting,
        "style_notes": style,
        "scene_motion_notes": scene_motion,
        "mix_reactivity_notes": f"Average RMS {avg_rms:.4f}, spectral centroid {avg_centroid:.2f}, onset strength {onset_strength:.2f}",
    }

    return {
        "duration": duration,
        "tempo_bpm": round(tempo, 3) if tempo is not None else None,
        "beat_times": beat_times,
        "production_notes": production_notes,
    }


def build_scenes(analysis, beats_per_scene=4, min_scene_seconds=1.5, max_scene_seconds=5.0):
    beat_times = analysis["beat_times"]
    total_duration = analysis["duration"]

    if not beat_times:
        return [{
            "scene_index": 1,
            "start": 0.0,
            "end": round(total_duration, 3),
            "duration": round(total_duration, 3),
            "beat_group_size": beats_per_scene,
            "scene_type": "full-song fallback"
        }]

    points = [0.0] + beat_times + [total_duration]
    scenes = []
    i = 0
    scene_index = 1

    while i < len(points) - 1:
        j = min(i + beats_per_scene, len(points) - 1)
        start_t = points[i]
        end_t = points[j]
        duration = end_t - start_t

        while duration < min_scene_seconds and j < len(points) - 1:
            j += 1
            end_t = points[j]
            duration = end_t - start_t

        if duration > max_scene_seconds:
            end_t = start_t + max_scene_seconds
            duration = end_t - start_t

        if scene_index == 1:
            scene_type = "intro hook"
        elif end_t >= total_duration - max_scene_seconds:
            scene_type = "closing phrase"
        else:
            scene_type = "performance phrase"

        scenes.append({
            "scene_index": scene_index,
            "start": round(float(start_t), 3),
            "end": round(float(end_t), 3),
            "duration": round(float(duration), 3),
            "beat_group_size": beats_per_scene,
            "scene_type": scene_type
        })

        scene_index += 1
        i = j

    return scenes


def build_scene_prompt(file_stem, analysis, scene, total_scenes):
    notes = analysis["production_notes"]
    bpm = analysis["tempo_bpm"]
    bpm_text = f"{bpm:.2f} BPM" if bpm is not None else "the detected groove"

    return (
        f"Cinematic vertical music video for {file_stem}. "
        f"Scene {scene['scene_index']} of {total_scenes}. "
        f"This scene covers {scene['start']:.2f} seconds to {scene['end']:.2f} seconds of the song. "
        f"Movement, choreography, camera motion, and visual accents must feel locked to {bpm_text}. "
        f"Choreography direction: {notes['choreography_notes']}. "
        f"Style direction: {notes['style_notes']}. "
        f"Lighting direction: {notes['lighting_notes']}. "
        f"Scene note: {scene['scene_type']}. "
        f"Production note: edit pacing should feel {notes['edit_pacing']} with {notes['scene_motion_notes']}. "
        f"Camera direction: {notes['camera_notes']}. "
        f"Actors should visibly phrase movement to the beat and not drift randomly. "
        f"Short-form social framing, clean subject readability, polished realism, strong performance energy."
    )


def create_task(prompt_text, prompt_image, ratio, duration, model="gen4.5"):
    body = {
        "model": model,
        "promptImage": prompt_image,
        "promptText": prompt_text,
        "ratio": ratio,
        "duration": duration,
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


def poll_task(task_id, max_polls=120, sleep_seconds=5):
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


def save_snapshot(output_json, final):
    write_json(output_json, final)


def run(audio_path, seed_dir, output_json, ratio="9:16", beats_per_scene=4, submit=True, log_path=None):
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path.resolve()}")

    ratio = normalize_ratio(ratio)
    file_stem = audio_path.stem

    analysis = analyze_music_for_video(audio_path)
    scenes = build_scenes(analysis, beats_per_scene=beats_per_scene)
    images = list_seed_images(seed_dir)

    final = {
        "file_stem": file_stem,
        "tempo_bpm": analysis["tempo_bpm"],
        "total_duration": round(float(analysis["duration"]), 3),
        "beats_per_scene": beats_per_scene,
        "scene_count": len(scenes),
        "ratio": ratio,
        "production_notes": analysis["production_notes"],
        "results": [],
        "status": "running",
    }

    downloads_dir = Path("outputs/runway_video_run/downloads")
    downloads_dir.mkdir(parents=True, exist_ok=True)

    save_snapshot(output_json, final)

    for idx, scene in enumerate(scenes, start=1):
        chosen_image = images[(idx - 1) % len(images)]
        prompt_image = file_to_data_uri(chosen_image)
        prompt_text = build_scene_prompt(file_stem, analysis, scene, len(scenes))
        duration = max(5, min(10, int(round(scene["duration"]))))

        entry = {
            "clip_index": idx,
            "file_stem": file_stem,
            "scene": scene,
            "tempo_bpm": analysis["tempo_bpm"],
            "production_notes": analysis["production_notes"],
            "seed_image_used": str(chosen_image.resolve()),
            "prompt_text": prompt_text,
            "ratio": ratio,
            "duration": duration,
            "status": "prepared",
        }

        try:
            if submit:
                entry["status"] = "submitting"
                save_snapshot(output_json, final)

                task_created = create_task(
                    prompt_text=prompt_text,
                    prompt_image=prompt_image,
                    ratio=ratio,
                    duration=duration,
                    model="gen4.5",
                )
                entry["task_created"] = task_created
                entry["status"] = "polling"
                final["results"].append(entry)
                save_snapshot(output_json, final)

                task_result = poll_task(task_created["id"])
                entry["task_result"] = task_result
                entry["status"] = task_result.get("status", "unknown")

                downloaded_mp4 = None
                if task_result.get("status") == "SUCCEEDED":
                    downloaded_mp4 = download_first_output(
                        task_result,
                        downloads_dir / f"{sanitize_name(file_stem)}_beatclip_{idx:02d}.mp4"
                    )
                entry["downloaded_mp4"] = downloaded_mp4

                final["results"][-1] = entry
                save_snapshot(output_json, final)
            else:
                final["results"].append(entry)
                save_snapshot(output_json, final)

        except Exception as e:
            entry["status"] = "FAILED"
            entry["error"] = str(e)
            entry["traceback"] = traceback.format_exc()

            if final["results"] and final["results"][-1].get("clip_index") == idx:
                final["results"][-1] = entry
            else:
                final["results"].append(entry)

            final["status"] = "FAILED"
            save_snapshot(output_json, final)

            if log_path:
                append_log(log_path, f"FAILED SCENE {idx}")
                append_log(log_path, entry["error"])
                append_log(log_path, entry["traceback"])

            return final

    final["status"] = "SUCCEEDED"
    save_snapshot(output_json, final)
    return final


def parse_args():
    parser = argparse.ArgumentParser(description="Integrated beat-ready pre-Runway builder")
    parser.add_argument("--audio", required=True)
    parser.add_argument("--seed-dir", default="inputs\\runway_seed_images")
    parser.add_argument("--output", default="outputs\\runway_video_run\\holy_cheeks_beat_ready_result.json")
    parser.add_argument("--ratio", default="9:16")
    parser.add_argument("--beats-per-scene", type=int, default=4)
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--log-path", default="outputs\\runway_video_run\\holy_cheeks_beat_ready_log.txt")
    return parser.parse_args()


def main():
    args = parse_args()
    result = run(
        audio_path=args.audio,
        seed_dir=args.seed_dir,
        output_json=args.output,
        ratio=args.ratio,
        beats_per_scene=args.beats_per_scene,
        submit=args.submit,
        log_path=args.log_path,
    )

    print("Integrated beat-ready Runway builder complete.")
    print(f"File stem      : {result['file_stem']}")
    print(f"Tempo BPM      : {result['tempo_bpm']}")
    print(f"Scene count    : {result['scene_count']}")
    print(f"Status         : {result['status']}")
    print(f"Result JSON    : {Path(args.output).resolve()}")
    print(f"Log path       : {Path(args.log_path).resolve()}")

    for item in result["results"]:
        print(
            f"Scene {item['clip_index']:02d} | "
            f"{item['scene']['start']:.2f}s->{item['scene']['end']:.2f}s | "
            f"Dur: {item['duration']} | "
            f"Status: {item.get('status')} | "
            f"Image: {Path(item['seed_image_used']).name}"
        )
        if item.get("downloaded_mp4"):
            print(f"   MP4: {item['downloaded_mp4']}")
        if item.get("error"):
            print(f"   ERROR: {item['error']}")


if __name__ == "__main__":
    main()
