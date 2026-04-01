from pathlib import Path
import argparse

try:
    from .batch import analyze_folder
except ImportError:
    from batch import analyze_folder


def parse_args():
    parser = argparse.ArgumentParser(
        description="Analyze all supported audio files in a folder."
    )
    parser.add_argument("--input-dir", required=True, help="Folder containing audio files")
    parser.add_argument(
        "--output-dir",
        default="outputs/batch_run",
        help="Folder where JSON, CSV, plots, and prompt profiles will be written"
    )
    parser.add_argument(
        "--no-plots",
        action="store_true",
        help="Skip waveform and loudness plot generation"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    result = analyze_folder(
        input_dir=Path(args.input_dir),
        output_dir=Path(args.output_dir),
        write_plots=not args.no_plots,
    )

    print("Batch analysis complete.")
    print(f"Files processed: {result['files_processed']}")
    print(f"Output folder   : {result['output_dir']}")
    print(f"Summary CSV     : {result['summary_csv']}")
    print(f"Prompt profiles : {result['prompt_profiles_txt']}")


if __name__ == "__main__":
    main()
