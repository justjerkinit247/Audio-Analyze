import sys
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / 'src' / 'audio_analyze'
sys.path.insert(0, str(SRC_DIR))

from creative_prompt_compiler import compile_creative_bundle


def test_compile_creative_bundle(tmp_path):
    manifest_path = tmp_path / 'manifest.json'
    output_dir = tmp_path / 'out'

    manifest = {
        'files': [
            {
                'file_name': 'song_a.wav',
                'file_stem': 'song_a',
                'tempo_bpm': None,
                'prompt_profile': 'unknown tempo, high energy, bright tone, strong vocal presence, estimated at unknown BPM.',
                'video_cue': 'use medium-fast edit pacing, high energy, bright tone visuals, with strong vocal presence.',
            },
            {
                'file_name': 'song_b.mp3',
                'file_stem': 'song_b',
                'tempo_bpm': 142.0,
                'prompt_profile': 'fast tempo, high energy, balanced tone, mixed instrumental and vocal presence, estimated at 142.00 BPM.',
                'video_cue': 'use fast-cut edit pacing, high energy, balanced tone visuals, with mixed instrumental and vocal presence.',
            },
        ]
    }
    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')

    result = compile_creative_bundle(manifest_path, output_dir)

    assert result['files_compiled'] == 2
    assert (output_dir / 'creative_music_prompts.txt').exists()
    assert (output_dir / 'creative_video_prompts.txt').exists()
    assert (output_dir / 'creative_prompt_bundle.json').exists()
