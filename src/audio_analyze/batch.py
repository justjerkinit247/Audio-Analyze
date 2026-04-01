from pathlib import Path
import csv
import json

import librosa

try:
    from .analyzer import analyze_audio_file
    from .plotting import save_waveform_plot, save_loudness_envelope_plot
except ImportError:
    from analyzer import analyze_audio_file
    from plotting import save_waveform_plot, save_loudness_envelope_plot


AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}
DEFAULT_HOP_LENGTH = 512


def iter_audio_files(input_dir):
    input_dir = Path(input_dir)
    for path in sorted(input_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS:
            yield path


def classify_energy(rms_mean):
    if rms_mean is None:
        return "unknown energy"
    if rms_mean < 0.03:
        return "low energy"
    if rms_mean < 0.08:
        return "medium energy"
    return "high energy"


def classify_brightness(centroid_hz):
    if centroid_hz is None:
        return "unknown brightness"
    if centroid_hz < 1200:
        return "dark tone"
    if centroid_hz < 2500:
        return "balanced tone"
    return "bright tone"


def classify_tempo(tempo_bpm):
    if tempo_bpm is None:
        return "unknown tempo"
    if tempo_bpm < 85:
        return "slow tempo"
    if tempo_bpm < 120:
        return "mid tempo"
    if tempo_bpm < 150:
        return "upbeat tempo"
    return "fast tempo"


def classify_voicing(voiced_ratio):
    if voiced_ratio is None:
        return "unknown vocal presence"
    if voiced_ratio < 0.15:
        return "mostly instrumental or sparse voicing"
    if voiced_ratio < 0.45:
        return "mixed instrumental and vocal presence"
    return "strong vocal presence"


def build_prompt_profile(result):
    tempo_text = classify_tempo(result.get("tempo_bpm"))
    energy_text = classify_energy(result.get("rms_mean"))
    brightness_text = classify_brightness(result.get("spectral_centroid_mean_hz"))
    voicing_text = classify_voicing(result.get("voiced_frame_ratio"))

    tempo_value = result.get("tempo_bpm")
    tempo_value_text = f"{tempo_value:.2f} BPM" if isinstance(tempo_value, (int, float)) else "unknown BPM"

    return (
        f"{result.get('file_stem', 'unknown')}: "
        f"{tempo_text}, {energy_text}, {brightness_text}, {voicing_text}, "
        f"estimated at {tempo_value_text}. "
        f"Use this as a rough creative profile, not a final genre verdict."
    )


def analyze_folder(input_dir, output_dir, write_plots=True):
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)

    json_dir = output_dir / "json"
    plots_wave_dir = output_dir / "plots" / "waveforms"
    plots_rms_dir = output_dir / "plots" / "loudness"
    json_dir.mkdir(parents=True, exist_ok=True)

    files = list(iter_audio_files(input_dir))
    if not files:
        raise FileNotFoundError(f"No supported audio files found in: {input_dir}")

    results = []

    for audio_path in files:
        result = analyze_audio_file(audio_path)
        result["source_path"] = str(audio_path.resolve())

        json_path = json_dir / f"{audio_path.stem}_analysis.json"
        json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

        if write_plots:
            y, sr = librosa.load(str(audio_path), sr=None, mono=True)
            rms = librosa.feature.rms(y=y, hop_length=DEFAULT_HOP_LENGTH)[0]

            save_waveform_plot(
                y=y,
                sr=sr,
                output_path=plots_wave_dir / f"{audio_path.stem}_waveform.png",
                title=f"{audio_path.stem} - Waveform"
            )

            save_loudness_envelope_plot(
                rms=rms,
                sr=sr,
                hop_length=DEFAULT_HOP_LENGTH,
                output_path=plots_rms_dir / f"{audio_path.stem}_loudness.png",
                title=f"{audio_path.stem} - Loudness Envelope"
            )

        result["prompt_profile"] = build_prompt_profile(result)
        results.append(result)

    csv_path = output_dir / "summary.csv"
    fieldnames = [
        "file_name",
        "file_stem",
        "source_path",
        "sample_rate",
        "duration_seconds",
        "tempo_bpm",
        "beats_detected",
        "pitch_estimate_hz",
        "pitch_min_hz",
        "pitch_max_hz",
        "voiced_frame_ratio",
        "rms_mean",
        "rms_max",
        "zcr_mean",
        "spectral_centroid_mean_hz",
        "spectral_rolloff_mean_hz",
        "prompt_profile",
    ]

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            writer.writerow({key: row.get(key) for key in fieldnames})

    prompt_profiles_path = output_dir / "prompt_profiles.txt"
    with prompt_profiles_path.open("w", encoding="utf-8") as f:
        for row in results:
            f.write(row["prompt_profile"] + "\n\n")

    return {
        "files_processed": len(results),
        "output_dir": str(output_dir.resolve()),
        "summary_csv": str(csv_path.resolve()),
        "prompt_profiles_txt": str(prompt_profiles_path.resolve()),
    }
