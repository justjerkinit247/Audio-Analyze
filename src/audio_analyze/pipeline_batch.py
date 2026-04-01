from pathlib import Path
import argparse
import csv
import json
from datetime import datetime, timezone

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


def classify_tempo(tempo_bpm):
    if tempo_bpm is None:
        return 'unknown tempo'
    if tempo_bpm < 85:
        return 'slow tempo'
    if tempo_bpm < 120:
        return 'mid tempo'
    if tempo_bpm < 150:
        return 'upbeat tempo'
    return 'fast tempo'


def classify_energy(rms_mean):
    if rms_mean is None:
        return 'unknown energy'
    if rms_mean < 0.03:
        return 'low energy'
    if rms_mean < 0.08:
        return 'medium energy'
    return 'high energy'


def classify_brightness(centroid_hz):
    if centroid_hz is None:
        return 'unknown brightness'
    if centroid_hz < 1200:
        return 'dark tone'
    if centroid_hz < 2500:
        return 'balanced tone'
    return 'bright tone'


def classify_voicing(voiced_ratio):
    if voiced_ratio is None:
        return 'unknown vocal presence'
    if voiced_ratio < 0.15:
        return 'mostly instrumental or sparse voicing'
    if voiced_ratio < 0.45:
        return 'mixed instrumental and vocal presence'
    return 'strong vocal presence'


def estimate_cut_pacing(tempo_bpm, rms_mean):
    if isinstance(tempo_bpm, (int, float)) and tempo_bpm >= 140:
        return 'fast-cut edit pacing'
    if isinstance(rms_mean, (int, float)) and rms_mean >= 0.08:
        return 'medium-fast edit pacing'
    return 'medium edit pacing'


def build_prompt_profile(result):
    tempo_text = classify_tempo(result.get('tempo_bpm'))
    energy_text = classify_energy(result.get('rms_mean'))
    brightness_text = classify_brightness(result.get('spectral_centroid_mean_hz'))
    voicing_text = classify_voicing(result.get('voiced_frame_ratio'))

    tempo_value = result.get('tempo_bpm')
    if isinstance(tempo_value, (int, float)):
        tempo_value_text = f'{tempo_value:.2f} BPM'
    else:
        tempo_value_text = 'unknown BPM'

    return (
        f"{result.get('file_stem', 'unknown')}: {tempo_text}, {energy_text}, "
        f"{brightness_text}, {voicing_text}, estimated at {tempo_value_text}."
    )


def build_video_cue(result):
    energy_text = classify_energy(result.get('rms_mean'))
    brightness_text = classify_brightness(result.get('spectral_centroid_mean_hz'))
    voicing_text = classify_voicing(result.get('voiced_frame_ratio'))
    cut_pacing = estimate_cut_pacing(result.get('tempo_bpm'), result.get('rms_mean'))
    return (
        f"{result.get('file_stem', 'unknown')}: use {cut_pacing}, {energy_text}, "
        f"{brightness_text} visuals, with {voicing_text}."
    )


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
        result['video_cue'] = build_video_cue(result)

        json_path = json_dir / f'{audio_path.stem}_analysis.json'
        json_path.write_text(json.dumps(result, indent=2), encoding='utf-8')
        results.append(result)

    csv_path = output_dir / 'summary.csv'
    fieldnames = [
        'file_name', 'file_stem', 'source_path', 'sample_rate', 'duration_seconds',
        'tempo_bpm', 'beats_detected', 'pitch_estimate_hz', 'pitch_min_hz',
        'pitch_max_hz', 'voiced_frame_ratio', 'rms_mean', 'rms_max', 'zcr_mean',
        'spectral_centroid_mean_hz', 'spectral_rolloff_mean_hz', 'prompt_profile',
        'video_cue'
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

    video_cues_path = output_dir / 'video_cues.txt'
    with video_cues_path.open('w', encoding='utf-8') as f:
        for row in results:
            f.write(row['video_cue'] + '\n\n')

    manifest = {
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'input_dir': str(input_dir.resolve()),
        'output_dir': str(output_dir.resolve()),
        'files_processed': len(results),
        'outputs': {
            'summary_csv': str(csv_path.resolve()),
            'prompt_profiles_txt': str(prompt_profiles_path.resolve()),
            'video_cues_txt': str(video_cues_path.resolve()),
            'json_dir': str(json_dir.resolve()),
        },
        'files': [
            {
                'file_name': row.get('file_name'),
                'file_stem': row.get('file_stem'),
                'source_path': row.get('source_path'),
                'tempo_bpm': row.get('tempo_bpm'),
                'duration_seconds': row.get('duration_seconds'),
                'prompt_profile': row.get('prompt_profile'),
                'video_cue': row.get('video_cue'),
            }
            for row in results
        ],
    }

    manifest_path = output_dir / 'manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')

    return {
        'files_processed': len(results),
        'output_dir': str(output_dir.resolve()),
        'summary_csv': str(csv_path.resolve()),
        'prompt_profiles_txt': str(prompt_profiles_path.resolve()),
        'video_cues_txt': str(video_cues_path.resolve()),
        'manifest_json': str(manifest_path.resolve()),
    }


def parse_args():
    parser = argparse.ArgumentParser(description='Pipeline-oriented batch analysis for music and video prep.')
    parser.add_argument('--input-dir', required=True, help='Folder containing audio files')
    parser.add_argument('--output-dir', default='outputs\\pipeline_batch_run', help='Where results should be written')
    return parser.parse_args()


def main():
    args = parse_args()
    result = analyze_folder(input_dir=Path(args.input_dir), output_dir=Path(args.output_dir))
    print('Pipeline batch analysis complete.')
    print(f"Files processed: {result['files_processed']}")
    print(f"Output folder  : {result['output_dir']}")
    print(f"Summary CSV    : {result['summary_csv']}")
    print(f"Prompt profiles: {result['prompt_profiles_txt']}")
    print(f"Video cues     : {result['video_cues_txt']}")
    print(f"Manifest JSON  : {result['manifest_json']}")


if __name__ == '__main__':
    main()
