from pathlib import Path
import argparse
import json
import sys

try:
    from .analyzer import analyze_audio_file
except ImportError:
    from analyzer import analyze_audio_file


def parse_args():
    parser = argparse.ArgumentParser(
        description="Analyze one audio file and export JSON metrics."
    )
    parser.add_argument("--input", required=True, help="Path to WAV or MP3 file")
    parser.add_argument(
        "--output",
        default=None,
        help="Optional output JSON path. Defaults to outputs/<file>_analysis.json"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    input_path = Path(args.input)

    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    if args.output:
        output_path = Path(args.output)
    else:
        output_path = Path("outputs") / f"{input_path.stem}_analysis.json"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    result = analyze_audio_file(input_path)

    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print("Audio analysis complete.")
    print(f"Input : {input_path.resolve()}")
    print(f"Output: {output_path.resolve()}")


if __name__ == "__main__":
    main()
