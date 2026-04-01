from pathlib import Path
import argparse
import json
from datetime import datetime, timezone


def load_manifest(manifest_path):
    manifest_path = Path(manifest_path)
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _is_number(value):
    return isinstance(value, (int, float))


def _tempo_clause(value):
    if _is_number(value):
        return f"Build around roughly {value:.2f} BPM. "
    return ""


def _energy_phrase(profile):
    text = (profile or "").lower()
    if "high energy" in text:
        return "high-energy forward momentum"
    if "medium energy" in text:
        return "steady controlled energy"
    if "low energy" in text:
        return "restrained low-key energy"
    return "clear emotional movement"


def _tone_phrase(profile):
    text = (profile or "").lower()
    if "bright tone" in text:
        return "a vivid top end and sharp presence"
    if "balanced tone" in text:
        return "a balanced tonal character with controlled brightness"
    if "dark tone" in text:
        return "a darker tonal body with heavier weight"
    return "a defined tonal identity"


def _presence_phrase(profile):
    text = (profile or "").lower()
    if "strong vocal presence" in text:
        return "a vocal-dominant arrangement with a lead-performance focus"
    if "mixed instrumental and vocal presence" in text:
        return "a hybrid arrangement where instrumentation and vocal phrasing share the spotlight"
    if "mostly instrumental or sparse voicing" in text:
        return "an instrumental-forward arrangement with limited vocal weight"
    return "a clear performance center"


def compile_creative_music_prompt(file_entry):
    stem = file_entry.get("file_stem", "unknown")
    profile = file_entry.get("prompt_profile", "")
    tempo_clause = _tempo_clause(file_entry.get("tempo_bpm"))
    energy = _energy_phrase(profile)
    tone = _tone_phrase(profile)
    presence = _presence_phrase(profile)
    return (
        f"[{stem}] Studio-quality music prompt. {tempo_clause}"
        f"Build a track with {energy}, {tone}, and {presence}. "
        f"Keep the production modern, polished, mix-ready, and emotionally focused. "
        f"Avoid generic filler and preserve a strong sense of movement and identity."
    )


def compile_creative_video_prompt(file_entry):
    stem = file_entry.get("file_stem", "unknown")
    cue = file_entry.get("video_cue", "")
    profile = file_entry.get("prompt_profile", "")
    energy = _energy_phrase(profile)
    tone = _tone_phrase(profile)
    return (
        f"[{stem}] Music video prompt. Use {energy}, {tone}, and performance-centered framing. "
        f"Follow this cue as the base direction: {cue} "
        f"Emphasize edit rhythm, motion, lighting, and camera pacing that match the analyzed feel."
    )


def compile_creative_bundle(manifest_path, output_dir):
    manifest = load_manifest(manifest_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    files = manifest.get("files", [])
    if not files:
        raise ValueError("Manifest contains no file entries.")

    music_prompts = []
    video_prompts = []
    compiled_files = []

    for file_entry in files:
        music_prompt = compile_creative_music_prompt(file_entry)
        video_prompt = compile_creative_video_prompt(file_entry)
        music_prompts.append(music_prompt)
        video_prompts.append(video_prompt)
        compiled_files.append({
            "file_name": file_entry.get("file_name"),
            "file_stem": file_entry.get("file_stem"),
            "tempo_bpm": file_entry.get("tempo_bpm"),
            "creative_music_prompt": music_prompt,
            "creative_video_prompt": video_prompt,
        })

    music_path = output_dir / "creative_music_prompts.txt"
    video_path = output_dir / "creative_video_prompts.txt"
    bundle_path = output_dir / "creative_prompt_bundle.json"

    music_path.write_text("\n\n".join(music_prompts) + "\n", encoding="utf-8")
    video_path.write_text("\n\n".join(video_prompts) + "\n", encoding="utf-8")

    bundle = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_manifest": str(Path(manifest_path).resolve()),
        "files_compiled": len(compiled_files),
        "files": compiled_files,
        "outputs": {
            "creative_music_prompts_txt": str(music_path.resolve()),
            "creative_video_prompts_txt": str(video_path.resolve())
        }
    }
    bundle_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")

    return {
        "files_compiled": len(compiled_files),
        "output_dir": str(output_dir.resolve()),
        "creative_music_prompts_txt": str(music_path.resolve()),
        "creative_video_prompts_txt": str(video_path.resolve()),
        "creative_prompt_bundle_json": str(bundle_path.resolve())
    }


def parse_args():
    parser = argparse.ArgumentParser(description="Compile refined creative prompt files from a pipeline manifest.")
    parser.add_argument("--manifest", default="outputs\\pipeline_batch_run\\manifest.json", help="Path to manifest.json")
    parser.add_argument("--output-dir", default="outputs\\creative_prompt_bundle_run", help="Output directory for compiled prompt files")
    return parser.parse_args()


def main():
    args = parse_args()
    result = compile_creative_bundle(args.manifest, args.output_dir)
    print("Creative prompt compilation complete.")
    print(f"Files compiled          : {result['files_compiled']}")
    print(f"Output folder           : {result['output_dir']}")
    print(f"Creative music prompts  : {result['creative_music_prompts_txt']}")
    print(f"Creative video prompts  : {result['creative_video_prompts_txt']}")
    print(f"Creative bundle JSON    : {result['creative_prompt_bundle_json']}")


if __name__ == "__main__":
    main()
