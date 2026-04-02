from pathlib import Path
import argparse
import json
from datetime import datetime, timezone


def load_manifest(manifest_path):
    manifest_path = Path(manifest_path)
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _safe_tempo(file_entry):
    tempo = file_entry.get("tempo_bpm")
    try:
        if tempo is None:
            return None
        return float(tempo)
    except Exception:
        return None


def _duration_for_tempo(tempo_bpm):
    if tempo_bpm is None:
        return 8
    if tempo_bpm >= 150:
        return 6
    if tempo_bpm >= 120:
        return 8
    return 10


def _camera_phrase(tempo_bpm, profile, cue):
    text = f"{profile} {cue}".lower()
    if tempo_bpm is not None and tempo_bpm >= 150:
        return "The camera moves with aggressive, performance-led motion, quick reframing, and sharp energy matched to the beat."
    if "bright tone" in text or "high energy" in text:
        return "The camera uses confident push-ins, lateral movement, and energized framing that stays readable and polished."
    return "The camera uses deliberate performance framing with controlled movement and strong visual clarity."


def _lighting_phrase(profile):
    text = (profile or "").lower()
    if "bright tone" in text:
        return "Use crisp highlight detail, vivid practical lighting, and a bright, high-contrast concert atmosphere."
    if "dark tone" in text:
        return "Use moody contrast, shadow-heavy lighting, and dense cinematic atmosphere."
    return "Use balanced contrast, clean separation, and polished music-video lighting."


def _performance_phrase(profile):
    text = (profile or "").lower()
    if "strong vocal presence" in text:
        return "Keep the performer as the clear focal point with lead-artist presence, expressive face detail, and dominant stage energy."
    if "mixed instrumental and vocal presence" in text:
        return "Balance the performer with instrument-driven visual moments so the frame feels shared between voice and production."
    return "Keep the visual emphasis on rhythm, body movement, and the overall performance silhouette."


def build_runway_prompt(file_entry):
    stem = file_entry.get("file_stem", "unknown")
    profile = file_entry.get("prompt_profile", "no prompt profile available")
    cue = file_entry.get("video_cue", "no video cue available")
    tempo_bpm = _safe_tempo(file_entry)
    tempo_text = f"{tempo_bpm:.2f} BPM" if tempo_bpm is not None else "an unresolved tempo"
    return (
        f"Create a cinematic music video shot for {stem}. "
        f"Target the visual rhythm around {tempo_text}. "
        f"{_camera_phrase(tempo_bpm, profile, cue)} "
        f"{_lighting_phrase(profile)} "
        f"{_performance_phrase(profile)} "
        f"Base analysis profile: {profile} "
        f"Base cue: {cue} "
        f"Maintain strong temporal consistency, readable motion, and polished music-video realism."
    )


def compile_runway_bundle(manifest_path, output_dir, model="gen4.5", ratio="1280:720"):
    manifest = load_manifest(manifest_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    files = manifest.get("files", [])
    if not files:
        raise ValueError("Manifest contains no file entries.")

    prompts = []
    payloads = []

    for file_entry in files:
        tempo_bpm = _safe_tempo(file_entry)
        duration = _duration_for_tempo(tempo_bpm)
        prompt_text = build_runway_prompt(file_entry)
        prompts.append(f"[{file_entry.get('file_stem', 'unknown')}] {prompt_text}")
        payloads.append({
            "file_name": file_entry.get("file_name"),
            "file_stem": file_entry.get("file_stem"),
            "target_platform": "runway",
            "model": model,
            "generation_mode": "text-to-video",
            "duration": duration,
            "ratio": ratio,
            "promptText": prompt_text,
            "metadata": {
                "tempo_bpm": tempo_bpm,
                "prompt_profile": file_entry.get("prompt_profile"),
                "video_cue": file_entry.get("video_cue"),
            },
        })

    prompts_path = output_dir / "runway_prompts.txt"
    payloads_path = output_dir / "runway_payloads.json"

    prompts_path.write_text("\n\n".join(prompts) + "\n", encoding="utf-8")
    bundle = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_manifest": str(Path(manifest_path).resolve()),
        "target_platform": "runway",
        "model": model,
        "ratio": ratio,
        "files_compiled": len(payloads),
        "payloads": payloads,
        "outputs": {
            "runway_prompts_txt": str(prompts_path.resolve()),
        },
    }
    payloads_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")

    return {
        "target_platform": "runway",
        "model": model,
        "ratio": ratio,
        "files_compiled": len(payloads),
        "output_dir": str(output_dir.resolve()),
        "runway_prompts_txt": str(prompts_path.resolve()),
        "runway_payloads_json": str(payloads_path.resolve()),
    }


def parse_args():
    parser = argparse.ArgumentParser(description="Compile Runway-ready video payloads from a pipeline manifest.")
    parser.add_argument("--manifest", default="outputs\\pipeline_batch_run\\manifest.json", help="Path to manifest.json")
    parser.add_argument("--output-dir", default="outputs\\runway_video_run", help="Output directory for compiled Runway files")
    parser.add_argument("--model", default="gen4.5", help="Runway model target")
    parser.add_argument("--ratio", default="1280:720", help="Runway ratio setting")
    return parser.parse_args()


def main():
    args = parse_args()
    result = compile_runway_bundle(args.manifest, args.output_dir, args.model, args.ratio)
    print("Runway video compilation complete.")
    print(f"Target platform     : {result['target_platform']}")
    print(f"Model               : {result['model']}")
    print(f"Ratio               : {result['ratio']}")
    print(f"Files compiled      : {result['files_compiled']}")
    print(f"Output folder       : {result['output_dir']}")
    print(f"Runway prompts      : {result['runway_prompts_txt']}")
    print(f"Runway payload JSON : {result['runway_payloads_json']}")


if __name__ == "__main__":
    main()
