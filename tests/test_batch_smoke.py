import sys
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src" / "audio_analyze"
sys.path.insert(0, str(SRC_DIR))

from batch import analyze_folder


def test_analyze_folder(tmp_path):
    input_dir = tmp_path / "audio"
    output_dir = tmp_path / "out"
    input_dir.mkdir(parents=True, exist_ok=True)

    sr = 22050
    t = np.linspace(0, 1.0, sr, endpoint=False)

    y1 = 0.2 * np.sin(2 * np.pi * 220 * t)
    y2 = 0.2 * np.sin(2 * np.pi * 440 * t)

    sf.write(input_dir / "tone_a.wav", y1, sr)
    sf.write(input_dir / "tone_b.wav", y2, sr)

    result = analyze_folder(input_dir=input_dir, output_dir=output_dir, write_plots=False)

    assert result["files_processed"] == 2
    assert (output_dir / "summary.csv").exists()
    assert (output_dir / "prompt_profiles.txt").exists()
    assert (output_dir / "json" / "tone_a_analysis.json").exists()
    assert (output_dir / "json" / "tone_b_analysis.json").exists()
