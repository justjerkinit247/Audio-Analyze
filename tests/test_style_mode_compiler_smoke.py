import sys
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / 'src' / 'audio_analyze'
sys.path.insert(0, str(SRC_DIR))

from style_mode_compiler import compile_style_mode_bundle


def test_compile_style_mode_bundle(tmp_path):
    manifest_path = tmp_path / 'manifest.json'
    output_dir = tmp_path / 'out'

    manifest = {
        'files': [
            {
                'file_name': 'song_a.wav',
                'file_stem': 'song_a',
                'prompt_profile': 'high energy, bright tone, strong vocal presence',
                'video_cue': 'use medium-fast edit pacing and strong performance framing',
            }
        ]
    }
    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')

    result = compile_style_mode_bundle(manifest_path, output_dir, 'cinematic')

    assert result['mode'] == 'cinematic'
    assert result['files_compiled'] == 1
    assert (output_dir / 'cinematic_prompts.txt').exists()
    assert (output_dir / 'cinematic_bundle.json').exists()
