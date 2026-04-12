from pathlib import Path
import argparse
import json
from datetime import datetime, timezone

from .image_integration import inject_image
from .multi_clip_generator import generate_multi_clip_payloads


def load_manifest(manifest_path):
    manifest_path = Path(manifest_path)
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _safe_tempo(file_entry):
    tempo = file_entry.get("tempo_bpm")
    try:
        return float(tempo) if tempo is not None else None
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


def build_runway_prompt(file_entry):
    stem = file_entry.get("file_stem", "unknown")
    profile = file_entry.get("prompt_profile", "")
    cue = file_entry.get("video_cue", "")
    tempo = _safe_tempo(file_entry)

    tempo_text = f"{tempo:.2f} BPM" if tempo else "dynamic rhythm"

    return (
        f"Cinematic music video for {stem}. "
        f"Sync motion to {tempo_text}. "
        f"{profile} {cue} "
        f"High energy, music-video realism, clean motion, strong subject focus."
    )


def compile_runway_bundle(manifest_path, output_dir, model="gen4.5", ratio="9:16"):
    manifest = load_manifest(manifest_path)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    files = manifest.get("files", [])
    if not files:
        raise ValueError("No files in manifest.")

    payloads = []

    for file_entry in files:
        tempo = _safe_tempo(file_entry)
        duration = _duration_for_tempo(tempo)

        prompt = build_runway_prompt(file_entry)

        payload = {
            "file_name": file_entry.get("file_name"),
            "file_stem": file_entry.get("file_stem"),
            "model": model,
            "duration": duration,
            "ratio": ratio,
            "promptText": prompt,
        }

        # 🔥 TEXT + IMAGE
        payload = inject_image(payload)

        payloads.append(payload)

    # 🔥 MULTI-CLIP SEQUENCING
    payloads = generate_multi_clip_payloads(payloads)

    out_json = output_dir / "runway_payloads.json"

    bundle = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "payloads": payloads
    }

    out_json.write_text(json.dumps(bundle, indent=2), encoding="utf-8")

    return bundle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="outputs/pipeline_batch_run/manifest.json")
    parser.add_argument("--output-dir", default="outputs/runway_video_run")

    args = parser.parse_args()

    result = compile_runway_bundle(args.manifest, args.output_dir)

    print("✅ FULL PIPELINE COMPLETE")
    print(f"Payloads generated: {len(result['payloads'])}")


if __name__ == "__main__":
    main()