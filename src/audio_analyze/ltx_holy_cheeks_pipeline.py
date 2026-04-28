from pathlib import Path
import argparse
import json
import re

import librosa
import numpy as np

try:
    from .ltx_client import LTXClient
except ImportError:
    from ltx_client import LTXClient


ALLOWED_IMAGES = {".jpg", ".jpeg", ".png", ".webp"}
RESOLUTION_MAP = {
    "9:16": "1080x1920",
    "16:9": "1920x1080",
    "1:1": "1080x1080",
}


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def scalarize(value):
    arr = np.asarray(value)
    if arr.size == 0:
        return None
    return float(arr.reshape(-1)[0])


def safe_name(name):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._-")
    return cleaned or "ltx_output"


def normalize_resolution(value):
    return RESOLUTION_MAP.get(value, value)


def list_seed_images(seed_dir):
    seed_dir = Path(seed_dir)
    if not seed_dir.exists():
        raise FileNotFoundError(f"Seed image folder not found: {seed_dir.resolve()}")
    images = sorted(p for p in seed_dir.iterdir() if p.is_file() and p.suffix.lower() in ALLOWED_IMAGES)
    if not images:
        raise FileNotFoundError(f"No seed images found in {seed_dir.resolve()}")
    return images


def analyze_audio(audio_path):
    y, sr = librosa.load(str(audio_path), sr=None, mono=True)
    duration = float(librosa.get_duration(y=y, sr=sr))
    tempo_raw, beats = librosa.beat.beat_track(y=y, sr=sr)
    tempo = scalarize(tempo_raw)
    rms = librosa.feature.rms(y=y)[0]
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)

    avg_rms = float(np.mean(rms)) if len(rms) else 0.0
    avg_centroid = float(np.mean(centroid)) if len(centroid) else 0.0
    onset_strength = float(np.mean(onset_env)) if len(onset_env) else 0.0

    if tempo and tempo >= 140:
        energy = "very high"
        pacing = "fast"
        movement = "sharp downbeat hits, punchy footwork, confident hip and shoulder accents"
        camera = "quick push-ins, lateral tracking, clean punch-in accents"
    elif tempo and tempo >= 110:
        energy = "high"
        pacing = "medium-fast"
        movement = "locked rhythmic walking, visible groove, confident body accents on kick and snare"
        camera = "smooth tracking, energized reframes, steady forward motion"
    elif tempo and tempo >= 85:
        energy = "moderate-high"
        pacing = "medium"
        movement = "groove-led movement, readable choreography, controlled rhythmic phrasing"
        camera = "controlled tracking, readable framing, cinematic drift"
    else:
        energy = "slow-burn"
        pacing = "slow"
        movement = "deliberate pose transitions, restrained performance movement, slow groove"
        camera = "slow push-ins, held compositions, gradual cinematic movement"

    if avg_centroid >= 3000:
        lighting = "bright crisp high-contrast stage lighting"
    elif avg_centroid >= 1800:
        lighting = "balanced polished music-video lighting"
    else:
        lighting = "moody contrast with selective highlights"

    return {
        "tempo_bpm": round(tempo, 3) if tempo is not None else None,
        "duration_seconds": round(duration, 3),
        "energy_profile": energy,
        "edit_pacing": pacing,
        "movement_notes": movement,
        "camera_notes": camera,
        "lighting_notes": lighting,
        "mix_reactivity_notes": f"Average RMS {avg_rms:.4f}, spectral centroid {avg_centroid:.2f}, onset strength {onset_strength:.2f}",
    }


def build_scenes(duration_seconds, max_scenes=6):
    scene_count = max(1, min(max_scenes, int(np.ceil(duration_seconds / 8.0))))
    scene_len = duration_seconds / scene_count
    scenes = []
    for i in range(scene_count):
        start = i * scene_len
        end = min(duration_seconds, (i + 1) * scene_len)
        scenes.append({
            "scene_index": i + 1,
            "start": round(start, 3),
            "end": round(end, 3),
            "duration": round(end - start, 3),
            "scene_type": "intro hook" if i == 0 else "closing phrase" if i == scene_count - 1 else "performance phrase",
        })
    return scenes


def build_prompt(file_stem, analysis, scene):
    bpm = analysis.get("tempo_bpm")
    bpm_text = f"{bpm:.2f} BPM" if bpm else "the song rhythm"
    return (
        f"Vertical short-form music video for {file_stem}. "
        f"Scene {scene['scene_index']} covers {scene['start']:.2f}s to {scene['end']:.2f}s. "
        f"Motion must feel locked to {bpm_text}. "
        f"Three gospel-performance characters continue walking forward in synchronized rhythm. "
        f"The camera tracks backward smoothly and slightly arcs to the side. "
        f"Performers glance back over their shoulders with confident playful stage presence. "
        f"Two female performers add brief rhythmic hip and lower-body dance accents synced to the beat, "
        f"styled as polished gospel-club choreography and not explicit. "
        f"Movement direction: {analysis['movement_notes']}. "
        f"Camera direction: {analysis['camera_notes']}. "
        f"Lighting direction: {analysis['lighting_notes']}. "
        f"White robe-inspired wardrobe, sacred-meets-club energy, clean facial consistency, no extra limbs, "
        f"no random costume changes, no chaotic warping, no random scene change."
    )


def build_plan(audio_path, seed_dir, output_json, resolution="9:16", max_scenes=6):
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path.resolve()}")
    images = list_seed_images(seed_dir)
    analysis = analyze_audio(audio_path)
    scenes = build_scenes(analysis["duration_seconds"], max_scenes=max_scenes)
    resolution = normalize_resolution(resolution)

    results = []
    for idx, scene in enumerate(scenes, start=1):
        image = images[(idx - 1) % len(images)]
        results.append({
            "clip_index": idx,
            "file_stem": audio_path.stem,
            "audio_path": str(audio_path.resolve()),
            "seed_image_used": str(image.resolve()),
            "scene": scene,
            "resolution": resolution,
            "prompt_text": build_prompt(audio_path.stem, analysis, scene),
            "status": "planned",
        })

    plan = {
        "file_stem": audio_path.stem,
        "analysis": analysis,
        "scene_count": len(results),
        "resolution": resolution,
        "results": results,
        "status": "planned",
    }
    write_json(output_json, plan)
    return plan


def submit_one(plan_json, output_json, clip_index, model="ltx-2-3-pro", guidance_scale=9.0):
    plan = json.loads(Path(plan_json).read_text(encoding="utf-8-sig"))
    match = None
    for item in plan["results"]:
        if int(item["clip_index"]) == int(clip_index):
            match = item
            break
    if match is None:
        raise ValueError(f"Clip index {clip_index} not found")

    output_dir = Path(output_json).parent / "downloads"
    output_dir.mkdir(parents=True, exist_ok=True)
    mp4_path = output_dir / f"{safe_name(match['file_stem'])}_ltx_scene_{int(clip_index):02d}.mp4"

    client = LTXClient()
    result = {
        "clip_index": int(clip_index),
        "file_stem": match["file_stem"],
        "scene": match["scene"],
        "seed_image_used": match["seed_image_used"],
        "audio_path": match["audio_path"],
        "prompt_text": match["prompt_text"],
        "resolution": match["resolution"],
        "model": model,
        "guidance_scale": guidance_scale,
        "status": "submitting",
    }
    write_json(output_json, result)

    ltx_result = client.audio_to_video(
        audio_uri=match["audio_path"],
        image_uri=match["seed_image_used"],
        prompt=match["prompt_text"],
        output_path=str(mp4_path),
        model=model,
        resolution=match["resolution"],
        guidance_scale=guidance_scale,
    )

    result["ltx_result"] = ltx_result
    result["status"] = ltx_result.get("status", "complete")
    result["downloaded_mp4"] = ltx_result.get("downloaded_mp4")
    write_json(output_json, result)
    return result


def main():
    parser = argparse.ArgumentParser(description="LTX Studio Holy Cheeks video pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    p1 = sub.add_parser("plan")
    p1.add_argument("--audio", required=True)
    p1.add_argument("--seed-dir", default="inputs\\ltx_seed_images")
    p1.add_argument("--output", required=True)
    p1.add_argument("--resolution", default="9:16")
    p1.add_argument("--max-scenes", type=int, default=6)

    p2 = sub.add_parser("submit-one")
    p2.add_argument("--plan-json", required=True)
    p2.add_argument("--output", required=True)
    p2.add_argument("--clip-index", type=int, default=1)
    p2.add_argument("--model", default="ltx-2-3-pro")
    p2.add_argument("--guidance-scale", type=float, default=9.0)

    args = parser.parse_args()

    if args.command == "plan":
        plan = build_plan(args.audio, args.seed_dir, args.output, args.resolution, args.max_scenes)
        print("LTX scene plan created.")
        print(Path(args.output).resolve())
        print(f"Scene count: {plan['scene_count']}")
        print(json.dumps(plan["analysis"], indent=2))
    elif args.command == "submit-one":
        result = submit_one(args.plan_json, args.output, args.clip_index, args.model, args.guidance_scale)
        print("LTX scene submit complete.")
        print(Path(args.output).resolve())
        print(f"Status: {result.get('status')}")
        print(f"Downloaded MP4: {result.get('downloaded_mp4')}")


if __name__ == "__main__":
    main()
