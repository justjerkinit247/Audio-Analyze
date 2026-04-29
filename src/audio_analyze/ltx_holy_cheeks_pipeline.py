from pathlib import Path
import argparse
import json
import os
import re

import librosa
import numpy as np
import soundfile as sf

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
MIN_LTX_AUDIO_SECONDS = 2.0
MAX_LTX_AUDIO_SECONDS = 20.0
DEFAULT_SCENE_SECONDS = 8.0
DEFAULT_MODEL = "ltx-2-3-pro"
DEFAULT_GUIDANCE_SCALE = 9.0

# LTX accepts audio/mpeg and audio/ogg. MP3 is preferred; OGG/Vorbis is fallback
# because local Windows/Python audio backends do not always expose MP3 encoding.
LTX_AUDIO_EXPORT_CANDIDATES = [
    {"format": "MP3", "extension": ".mp3", "subtype": None},
    {"format": "OGG", "extension": ".ogg", "subtype": "VORBIS"},
]


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


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


def build_scenes(duration_seconds, max_scenes=6, scene_seconds=DEFAULT_SCENE_SECONDS):
    scene_seconds = max(MIN_LTX_AUDIO_SECONDS, min(MAX_LTX_AUDIO_SECONDS, float(scene_seconds)))
    duration_seconds = float(duration_seconds)
    scene_count = max(1, min(max_scenes, int(np.ceil(duration_seconds / scene_seconds))))
    scenes = []

    for i in range(scene_count):
        start = i * scene_seconds
        end = min(duration_seconds, start + scene_seconds)
        if end - start < MIN_LTX_AUDIO_SECONDS and scenes:
            scenes[-1]["end"] = round(duration_seconds, 3)
            scenes[-1]["duration"] = round(duration_seconds - scenes[-1]["start"], 3)
            break
        scenes.append({
            "scene_index": len(scenes) + 1,
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


def build_plan(audio_path, seed_dir, output_json, resolution="9:16", max_scenes=6, scene_seconds=DEFAULT_SCENE_SECONDS):
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path.resolve()}")
    images = list_seed_images(seed_dir)
    analysis = analyze_audio(audio_path)
    scenes = build_scenes(analysis["duration_seconds"], max_scenes=max_scenes, scene_seconds=scene_seconds)
    resolution = normalize_resolution(resolution)

    results = []
    for idx, scene in enumerate(scenes, start=1):
        image = images[(idx - 1) % len(images)]
        results.append({
            "clip_index": idx,
            "file_stem": audio_path.stem,
            "source_audio_path": str(audio_path.resolve()),
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
        "scene_seconds": scene_seconds,
        "results": results,
        "status": "planned",
    }
    write_json(output_json, plan)
    return plan


def validate_plan(plan):
    problems = []
    if not plan.get("results"):
        problems.append("Plan has no scene results.")
    for item in plan.get("results", []):
        idx = item.get("clip_index", "unknown")
        audio_path = Path(item.get("source_audio_path", ""))
        image_path = Path(item.get("seed_image_used", ""))
        scene = item.get("scene", {})
        duration = float(scene.get("duration", 0))
        prompt = item.get("prompt_text", "")
        resolution = item.get("resolution", "")
        if not audio_path.exists():
            problems.append(f"Scene {idx}: source audio missing: {audio_path}")
        if not image_path.exists():
            problems.append(f"Scene {idx}: seed image missing: {image_path}")
        if duration < MIN_LTX_AUDIO_SECONDS or duration > MAX_LTX_AUDIO_SECONDS:
            problems.append(f"Scene {idx}: audio duration {duration:.2f}s is outside {MIN_LTX_AUDIO_SECONDS}-{MAX_LTX_AUDIO_SECONDS}s.")
        if not prompt.strip():
            problems.append(f"Scene {idx}: prompt is empty.")
        if len(prompt) > 5000:
            problems.append(f"Scene {idx}: prompt is over 5000 characters.")
        if resolution not in set(RESOLUTION_MAP.values()):
            problems.append(f"Scene {idx}: resolution looks unsupported or unnormalized: {resolution}")
    return problems


def run_preflight(plan_json, output_json=None):
    plan = read_json(plan_json)
    problems = validate_plan(plan)
    report = {
        "status": "FAILED" if problems else "PASSED",
        "scene_count": len(plan.get("results", [])),
        "problems": problems,
        "plan_json": str(Path(plan_json).resolve()),
    }
    if output_json:
        write_json(output_json, report)
    return report


def export_audio_candidate(path, y, sr, candidate):
    if candidate["subtype"]:
        sf.write(str(path), y, sr, format=candidate["format"], subtype=candidate["subtype"])
    else:
        sf.write(str(path), y, sr, format=candidate["format"])


def export_scene_audio(source_audio_path, scene, output_dir, file_stem, clip_index):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    source_audio_path = Path(source_audio_path)

    start = float(scene["start"])
    end = float(scene["end"])
    duration = max(MIN_LTX_AUDIO_SECONDS, min(MAX_LTX_AUDIO_SECONDS, end - start))

    y, sr = librosa.load(str(source_audio_path), sr=None, mono=False, offset=start, duration=duration)
    if y.size == 0:
        raise RuntimeError(f"Could not extract audio for scene {clip_index} from {source_audio_path}")

    if y.ndim == 2:
        y = y.T

    errors = []
    for candidate in LTX_AUDIO_EXPORT_CANDIDATES:
        scene_audio = output_dir / f"{safe_name(file_stem)}_ltx_scene_{int(clip_index):02d}{candidate['extension']}"
        try:
            export_audio_candidate(scene_audio, y, sr, candidate)
            return {
                "path": str(scene_audio.resolve()),
                "format": candidate["format"],
                "extension": candidate["extension"],
            }
        except Exception as exc:
            errors.append(f"{candidate['format']} failed: {exc}")
            try:
                if scene_audio.exists():
                    scene_audio.unlink()
            except Exception:
                pass

    raise RuntimeError("Could not export LTX-compatible scene audio. " + " | ".join(errors))


def _get_plan_item(plan, clip_index):
    for item in plan["results"]:
        if int(item["clip_index"]) == int(clip_index):
            return item
    raise ValueError(f"Clip index {clip_index} not found")


def submit_one(plan_json, output_json, clip_index, model=DEFAULT_MODEL, guidance_scale=DEFAULT_GUIDANCE_SCALE, dry_run=True, live=False):
    if live and dry_run:
        raise ValueError("Use either dry_run or live, not both.")
    if not dry_run and not live:
        raise RuntimeError("Live LTX calls require live=True. Default is dry-run to prevent accidental credit spending.")
    if live and not os.environ.get("LTXV_API_KEY"):
        raise RuntimeError("LTXV_API_KEY is not set. Refusing live LTX call.")

    plan = read_json(plan_json)
    problems = validate_plan(plan)
    if problems:
        raise RuntimeError("Preflight failed; refusing submit. Problems:\n" + "\n".join(problems))

    match = _get_plan_item(plan, clip_index)
    output_root = Path(output_json).parent
    downloads_dir = output_root / "downloads"
    scene_audio_dir = output_root / "scene_audio"
    downloads_dir.mkdir(parents=True, exist_ok=True)
    scene_audio_dir.mkdir(parents=True, exist_ok=True)

    scene_audio = export_scene_audio(
        source_audio_path=match["source_audio_path"],
        scene=match["scene"],
        output_dir=scene_audio_dir,
        file_stem=match["file_stem"],
        clip_index=clip_index,
    )
    scene_audio_path = scene_audio["path"]

    mp4_path = downloads_dir / f"{safe_name(match['file_stem'])}_ltx_scene_{int(clip_index):02d}.mp4"
    result = {
        "clip_index": int(clip_index),
        "file_stem": match["file_stem"],
        "scene": match["scene"],
        "seed_image_used": match["seed_image_used"],
        "source_audio_path": match["source_audio_path"],
        "scene_audio_path": scene_audio_path,
        "scene_audio_format": scene_audio["format"],
        "prompt_text": match["prompt_text"],
        "resolution": match["resolution"],
        "model": model,
        "guidance_scale": guidance_scale,
        "dry_run": dry_run,
        "live": live,
        "status": "submitting" if live else "dry_run",
    }
    write_json(output_json, result)

    client = LTXClient(api_key="dry-run-key" if dry_run else None)
    ltx_result = client.audio_to_video(
        audio_uri=scene_audio_path,
        image_uri=match["seed_image_used"],
        prompt=match["prompt_text"],
        output_path=str(mp4_path),
        model=model,
        resolution=match["resolution"],
        guidance_scale=guidance_scale,
        dry_run=dry_run,
    )

    result["ltx_result"] = ltx_result
    result["status"] = ltx_result.get("status", "complete")
    result["downloaded_mp4"] = ltx_result.get("downloaded_mp4")
    write_json(output_json, result)
    return result


def submit_all(plan_json, output_dir, model=DEFAULT_MODEL, guidance_scale=DEFAULT_GUIDANCE_SCALE, dry_run=True, live=False):
    plan = read_json(plan_json)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "status": "running",
        "dry_run": dry_run,
        "live": live,
        "plan_json": str(Path(plan_json).resolve()),
        "results": [],
    }
    summary_path = output_dir / "ltx_submit_all_summary.json"
    write_json(summary_path, summary)

    for item in plan.get("results", []):
        idx = int(item["clip_index"])
        result_path = output_dir / f"scene_{idx:02d}_result.json"
        result = submit_one(
            plan_json=plan_json,
            output_json=result_path,
            clip_index=idx,
            model=model,
            guidance_scale=guidance_scale,
            dry_run=dry_run,
            live=live,
        )
        summary["results"].append({
            "clip_index": idx,
            "status": result.get("status"),
            "scene_audio_path": result.get("scene_audio_path"),
            "scene_audio_format": result.get("scene_audio_format"),
            "downloaded_mp4": result.get("downloaded_mp4"),
            "result_json": str(result_path.resolve()),
        })
        write_json(summary_path, summary)

    summary["status"] = "complete"
    write_json(summary_path, summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description="LTX Studio Holy Cheeks video pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    p1 = sub.add_parser("plan")
    p1.add_argument("--audio", required=True)
    p1.add_argument("--seed-dir", default="inputs\\ltx_seed_images")
    p1.add_argument("--output", required=True)
    p1.add_argument("--resolution", default="9:16")
    p1.add_argument("--max-scenes", type=int, default=6)
    p1.add_argument("--scene-seconds", type=float, default=DEFAULT_SCENE_SECONDS)

    p_pre = sub.add_parser("preflight")
    p_pre.add_argument("--plan-json", required=True)
    p_pre.add_argument("--output", default=None)

    p2 = sub.add_parser("submit-one")
    p2.add_argument("--plan-json", required=True)
    p2.add_argument("--output", required=True)
    p2.add_argument("--clip-index", type=int, default=1)
    p2.add_argument("--model", default=DEFAULT_MODEL)
    p2.add_argument("--guidance-scale", type=float, default=DEFAULT_GUIDANCE_SCALE)
    p2.add_argument("--live", action="store_true", help="Actually call LTX and spend credits. Omit for dry-run.")

    p_all = sub.add_parser("submit-all")
    p_all.add_argument("--plan-json", required=True)
    p_all.add_argument("--output-dir", required=True)
    p_all.add_argument("--model", default=DEFAULT_MODEL)
    p_all.add_argument("--guidance-scale", type=float, default=DEFAULT_GUIDANCE_SCALE)
    p_all.add_argument("--live", action="store_true", help="Actually call LTX for all scenes and spend credits. Omit for dry-run.")

    args = parser.parse_args()

    if args.command == "plan":
        plan = build_plan(args.audio, args.seed_dir, args.output, args.resolution, args.max_scenes, args.scene_seconds)
        print("LTX scene plan created.")
        print(Path(args.output).resolve())
        print(f"Scene count: {plan['scene_count']}")
        print(json.dumps(plan["analysis"], indent=2))
    elif args.command == "preflight":
        report = run_preflight(args.plan_json, args.output)
        print(f"Preflight status: {report['status']}")
        print(f"Scene count: {report['scene_count']}")
        for problem in report["problems"]:
            print(f"PROBLEM: {problem}")
        if args.output:
            print(Path(args.output).resolve())
    elif args.command == "submit-one":
        result = submit_one(
            args.plan_json,
            args.output,
            args.clip_index,
            args.model,
            args.guidance_scale,
            dry_run=not args.live,
            live=args.live,
        )
        print("LTX scene submit complete.")
        print(Path(args.output).resolve())
        print(f"Status: {result.get('status')}")
        print(f"Scene audio: {result.get('scene_audio_path')}")
        print(f"Scene audio format: {result.get('scene_audio_format')}")
        print(f"Downloaded MP4: {result.get('downloaded_mp4')}")
    elif args.command == "submit-all":
        summary = submit_all(
            args.plan_json,
            args.output_dir,
            args.model,
            args.guidance_scale,
            dry_run=not args.live,
            live=args.live,
        )
        print("LTX submit-all complete.")
        print(f"Status: {summary['status']}")
        print(f"Scenes: {len(summary['results'])}")
        print(Path(args.output_dir).resolve())


if __name__ == "__main__":
    main()
