from pathlib import Path
import argparse
import json
from datetime import datetime, timezone


def load_manifest(manifest_path):
    manifest_path = Path(manifest_path)
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _tempo_text(value):
    if isinstance(value, (int, float)):
        return f"{value:.2f} BPM"
    return "unknown BPM"


def compile_music_prompt(file_entry):
    stem = file_entry.get("file_stem", "unknown")
    tempo = _tempo_text(file_entry.get("tempo_bpm"))
    profile = file_entry.get("prompt_profile", "no prompt profile available")
    return (
        f"[{stem}] Music prompt. Build around {tempo}. "
        f"Use this analyzed profile as the main guide: {profile} "
        f"Keep the structure cohesive, modern, and production-ready."
    )


def compile_video_prompt(file_entry):
    stem = file_entry.get("file_stem", "unknown")
    cue = file_entry.get("video_cue", "no video cue available")
    profile = file_entry.get("prompt_profile", "no prompt profile available")
    return (
        f"[{stem}] Video prompt. Use this direction: {cue} "
        f"Reference the analyzed audio profile: {profile} "
        f"Focus on pacing, visual rhythm, performance framing, and edit timing."
    )


def compile_prompt_bundle(manifest_path, output_dir):
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
        music_prompt = compile_music_prompt(file_entry)
        video_prompt = compile_video_prompt(file_entry)

        music_prompts.append(music_prompt)
        video_prompts.append(video_prompt)
        compiled_files.append({
            "file_name": file_entry.get("file_name"),
            "file_stem": file_entry.get("file_stem"),
            "tempo_bpm": file_entry.get("tempo_bpm"),
            "music_prompt": music_prompt,
            "video_prompt": video_prompt,
        })

    music_path = output_dir / "music_prompts.txt"
    video_path = output_dir / "video_prompts.txt"
    bundle_path = output_dir / "prompt_bundle.json"

    music_path.write_text("\n\n".join(music_prompts) + "\n", encoding="utf-8")
    video_path.write_text("\n\n".join(video_prompts) + "\n", encoding="utf-8")

    bundle = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_manifest": str(Path(manifest_path).resolve()),
        "files_compiled": len(compiled_files),
        "files": compiled_files,
        "outputs": {
            "music_prompts_txt": str(music_path.resolve()),
            "video_prompts_txt": str(video_path.resolve()),
        },
    }
    bundle_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")

    return {
        "files_compiled": len(compiled_files),
        "output_dir": str(output_dir.resolve()),
        "music_prompts_txt": str(music_path.resolve()),
        "video_prompts_txt": str(video_path.resolve()),
        "prompt_bundle_json": str(bundle_path.resolve()),
    }


def parse_args():
    parser = argparse.ArgumentParser(description="Compile prompt bundle files from a pipeline manifest.")
    parser.add_argument(
        "--manifest",
        default="outputs\\pipeline_batch_run\\manifest.json",
        help="Path to manifest.json",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs\\prompt_bundle_run",
        help="Output directory for compiled prompt files",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    result = compile_prompt_bundle(args.manifest, args.output_dir)
    print("Prompt compilation complete.")
    print(f"Files compiled : {result['files_compiled']}")
    print(f"Output folder  : {result['output_dir']}")
    print(f"Music prompts  : {result['music_prompts_txt']}")
    print(f"Video prompts  : {result['video_prompts_txt']}")
    print(f"Bundle JSON    : {result['prompt_bundle_json']}")


if __name__ == "__main__":
    main()
