import sys
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from audio_analyze.runway_video_compiler import compile_runway_bundle


def test_compile_runway_bundle(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    output_dir = tmp_path / "out"

    manifest = {
        "files": [
            {
                "file_name": "song_a.wav",
                "file_stem": "song_a",
                "tempo_bpm": 160.0,
                "prompt_profile": "high energy, bright tone, strong vocal presence",
                "video_cue": "use medium-fast edit pacing and strong performance framing",
            }
        ]
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = compile_runway_bundle(manifest_path, output_dir, "gen4.5", "9:16")

    assert "created_at" in result
    assert "payloads" in result
    assert len(result["payloads"]) == 1
    assert result["payloads"][0]["model"] == "gen4.5"
    assert result["payloads"][0]["ratio"] == "9:16"
    assert result["payloads"][0]["file_stem"] == "song_a"
    assert (output_dir / "runway_payloads.json").exists()
