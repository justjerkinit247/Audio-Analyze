from pathlib import Path
import argparse
import csv
import json

try:
    from .analyzer import analyze_audio_file
except ImportError:
    from analyzer import analyze_audio_file

AUDIO_EXTENSIONS = {'.wav', '.mp3', '.flac', '.ogg', '.m4a'}


def iter_audio_files(input_dir):
    input_dir = Path(input_dir)
    for path in sorted(input_dir.rglob('*')):
        if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS:
            yield path


def build_prompt_profile(result):
    tempo = result.get('tempo_bpm')
    if isinstance(tempo, (int, float)):
        tempo_text = f'{tempo:.2f} BPM'
    else:
        tempo_text = 'unknown BPM'
    return f"{result.get('file_stem', 'unknown')}: estimated tempo {tempo_text}."


def analyze_folder(input_dir, output_dir):
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    json_dir = output_dir / 'json'
    json_dir.mkdir(parents=True, exist_ok=True)

    files = list(iter_audio_files(input_dir))
    if not files:
        raise FileNotFoundError(f'No supported audio files found in: {input_dir}')

    print(f'Found {len(files)} audio file(s).')
    results = []

    for index, audio_path in enumerate(files, start=1):
        print(f'[{index}/{len(files)}] Analyzing: {audio_path.name}')
        result = analyze_audio_file(audio_path)
        result['source_path'] = str(audio_path.resolve())
        result['prompt_profile'] = build_prompt_profile(result)
        json_path = json_dir / f'{audio_path.stem}_analysis.json'
        json_path.write_text(json.dumps(result, indent=2), encoding='utf-8')
        results.append(result)

    csv_path = output_dir / 'summary.csv'
    fieldnames = [
        'file_name', 'file_stem', 'source_path', 'sample_rate', 'duration_seconds',
        'tempo_bpm', 'beats_detected', 'pitch_estimate_hz', 'pitch_min_hz',
        'pitch_max_hz', 'voiced_frame_ratio', 'rms_mean', 'rms_max', 'zcr_mean',
        'spectral_centroid_mean_hz', 'spectral_rolloff_mean_hz', 'prompt_profile'
    ]

    with csv_path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            writer.writerow({key: row.get(key) for key in fieldnames})

    prompt_profiles_path = output_dir / 'prompt_profiles.txt'
    with prompt_profiles_path.open('w', encoding='utf-8') as f:
        for row in results:
            f.write(row['prompt_profile'] + '\n\n')

    return {
        'files_processed': len(results),
        'output_dir': str(output_dir.resolve()),
        'summary_csv': str(csv_path.resolve()),
        'prompt_profiles_txt': str(prompt_profiles_path.resolve()),
    }


def parse_args():
    parser = argparse.ArgumentParser(description='Analyze all audio files in a folder.')
    parser.add_argument('--input-dir', required=True, help='Folder containing audio files')
    parser.add_argument('--output-dir', default='outputs\\batch_run', help='Where results should be written')

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
