from pathlib import Path
import json

import numpy as np
import soundfile as sf

from src.audio_analyze.audio_analysis_upgrade import analyze_beat_grid, classify_audio_source, score_scene_boundaries


def test_audio_analysis_upgrade_smoke(tmp_path):
    sr = 22050
    duration = 4.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    y = 0.1 * np.sin(2 * np.pi * 220 * t)
    for beat in np.arange(0, duration, 0.5):
        idx = int(beat * sr)
        y[idx:idx + 300] += np.hanning(300) * 0.8

    audio = tmp_path / "test.wav"
    sf.write(str(audio), y, sr)

    report = analyze_beat_grid(audio)
    assert report["audio_source"]["quality_class"] == "lossless_preferred"
    assert report["beat_count"] > 0
    assert report["beat_confidence"] >= 0

    plan = {
        "results": [
            {"clip_index": 1, "scene": {"start": 0.0, "end": 2.0}},
            {"clip_index": 2, "scene": {"start": 2.0, "end": 4.0}},
        ]
    }
    boundary = score_scene_boundaries(plan, report)
    assert boundary["scenes"]
    assert boundary["average_boundary_confidence"] is not None

    mp3_meta = classify_audio_source(Path("song.mp3"))
    assert mp3_meta["quality_class"] == "compressed_usable"
