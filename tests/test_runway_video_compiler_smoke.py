import sys
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / 'src' / 'audio_analyze'
sys.path.insert(0, str(SRC_DIR))

from runway_video_compiler import compile_runway_bundle


def test_compile_runway_bundle(tmp_path):
    manifest_path = tmp_path / 'manifest.json'
    output_dir = tmp_path / 'out'

    manifest = {
        'files': [
            {
                'file_name': 'song_a.wav',
                'file_stem': 'song_a',
                'tempo_bpm': 160.0,
                'prompt_profile': 'high energy, bright tone, strong vocal presence',
                'video_cue': 'use medium-fast edit pacing and strong performance framing',
            }
        ]
    }
    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')

    result = compile_runway_bundle(manifest_path, output_dir, 'gen4.5', '1280:720')

    assert result['target_platform'] == 'runway'
    assert result['model'] == 'gen4.5'
    assert result['files_compiled'] == 1
    assert (output_dir / 'runway_prompts.txt').exists()
    assert (output_dir / 'runway_payloads.json').exists()
