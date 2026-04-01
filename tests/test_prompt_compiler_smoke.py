import sys
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / 'src' / 'audio_analyze'
sys.path.insert(0, str(SRC_DIR))

from prompt_compiler import compile_prompt_bundle


def test_compile_prompt_bundle(tmp_path):
    manifest_path = tmp_path / 'manifest.json'
    output_dir = tmp_path / 'out'

    manifest = {
        'files': [
            {
                'file_name': 'song_a.wav',
                'file_stem': 'song_a',
                'tempo_bpm': 100.0,
                'prompt_profile': 'mid tempo, medium energy, balanced tone, strong vocal presence',
                'video_cue': 'use medium edit pacing with balanced visuals and strong performance framing',
            },
            {
                'file_name': 'song_b.mp3',
                'file_stem': 'song_b',
                'tempo_bpm': 142.0,
                'prompt_profile': 'fast tempo, high energy, bright tone, mixed instrumental and vocal presence',
                'video_cue': 'use fast-cut edit pacing with high energy visuals',
            },
        ]
    }
    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')

    result = compile_prompt_bundle(manifest_path, output_dir)

    assert result['files_compiled'] == 2
    assert (output_dir / 'music_prompts.txt').exists()
    assert (output_dir / 'video_prompts.txt').exists()
    assert (output_dir / 'prompt_bundle.json').exists()
