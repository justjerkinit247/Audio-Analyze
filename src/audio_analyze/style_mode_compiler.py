from pathlib import Path
import argparse
import json
from datetime import datetime, timezone


def load_manifest(manifest_path):
    manifest_path = Path(manifest_path)
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _style_instruction(mode):
    styles = {
        "suno": "Write a compact generation prompt focused on song production, arrangement, and sonic identity.",
        "cinematic": "Write a cinematic direction prompt focused on mood, visual scale, lighting, and emotional atmosphere.",
        "performance-video": "Write a music video prompt focused on artist performance, framing, edit rhythm, and stage presence.",
        "short-form-social": "Write a short-form social video prompt focused on immediate hook, fast pacing, visual punch, and scroll-stopping moments.",
    }
    return styles.get(mode, styles["performance-video"])


def compile_style_prompt(file_entry, mode):
    stem = file_entry.get("file_stem", "unknown")
    profile = file_entry.get("prompt_profile", "no prompt profile available")
    cue = file_entry.get("video_cue", "no video cue available")
    instruction = _style_instruction(mode)
    return (
        f"[{stem}] {instruction} "
        f"Primary profile: {profile} "
        f"Base cue: {cue}"
    )


def compile_style_mode_bundle(manifest_path, output_dir, mode):
    manifest = load_manifest(manifest_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    files = manifest.get("files", [])
    if not files:
        raise ValueError("Manifest contains no file entries.")

    prompts = []
    compiled_files = []

    for file_entry in files:
        prompt = compile_style_prompt(file_entry, mode)
        prompts.append(prompt)
        compiled_files.append({
            "file_name": file_entry.get("file_name"),
            "file_stem": file_entry.get("file_stem"),
            "mode": mode,
            "style_prompt": prompt,
        })

    prompts_path = output_dir / f"{mode}_prompts.txt"
    bundle_path = output_dir / f"{mode}_bundle.json"

    prompts_path.write_text("\n\n".join(prompts) + "\n", encoding="utf-8")

    bundle = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_manifest": str(Path(manifest_path).resolve()),
        "mode": mode,
        "files_compiled": len(compiled_files),
        "files": compiled_files,
        "outputs": {
            "style_prompts_txt": str(prompts_path.resolve()),
        },
    }
    bundle_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")

    return {
        "mode": mode,
        "files_compiled": len(compiled_files),
        "output_dir": str(output_dir.resolve()),
        "style_prompts_txt": str(prompts_path.resolve()),
        "style_bundle_json": str(bundle_path.resolve()),
    }


def parse_args():
    parser = argparse.ArgumentParser(description="Compile style-targeted prompt files from a pipeline manifest.")
    parser.add_argument("--manifest", default="outputs\\pipeline_batch_run\\manifest.json", help="Path to manifest.json")
    parser.add_argument("--output-dir", default="outputs\\style_mode_run", help="Output directory for compiled prompt files")
    parser.add_argument("--mode", default="performance-video", choices=["suno", "cinematic", "performance-video", "short-form-social"], help="Target style mode")
    return parser.parse_args()


def main():
    args = parse_args()
    result = compile_style_mode_bundle(args.manifest, args.output_dir, args.mode)
    print("Style mode compilation complete.")
    print(f"Mode              : {result['mode']}")
    print(f"Files compiled    : {result['files_compiled']}")
    print(f"Output folder     : {result['output_dir']}")
    print(f"Style prompts     : {result['style_prompts_txt']}")
    print(f"Style bundle JSON : {result['style_bundle_json']}")


if __name__ == "__main__":
    main()
