import sys
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src" / "audio_analyze"
sys.path.insert(0, str(SRC_DIR))

from analyzer import analyze_audio_file


def test_analyze_audio_file(tmp_path):
    sr = 22050
    t = np.linspace(0, 1.0, sr, endpoint=False)
    y = 0.2 * np.sin(2 * np.pi * 440 * t)

    sample_file = tmp_path / "sine.wav"
    sf.write(sample_file, y, sr)

    result = analyze_audio_file(sample_file)

    assert result["sample_rate"] == sr
    assert 0.95 <= result["duration_seconds"] <= 1.05
    assert "tempo_bpm" in result
    assert "pitch_estimate_hz" in result
    assert "rms_mean" in result
