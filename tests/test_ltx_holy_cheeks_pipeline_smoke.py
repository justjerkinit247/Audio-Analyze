import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from audio_analyze.ltx_holy_cheeks_pipeline import build_plan, submit_one


def test_ltx_plan_and_dry_run_submit(tmp_path):
    audio_path = tmp_path / "holy_cheeks_test.wav"
    seed_dir = tmp_path / "ltx_seed_images"
    seed_dir.mkdir()
    seed_image = seed_dir / "seed.png"
    plan_path = tmp_path / "ltx_plan.json"
    result_path = tmp_path / "scene_01_result.json"

    sample_rate = 22050
    duration_seconds = 4.0
    t = np.linspace(0, duration_seconds, int(sample_rate * duration_seconds), endpoint=False)
    y = 0.2 * np.sin(2 * np.pi * 440.0 * t)
    sf.write(str(audio_path), y, sample_rate)

    Image.new("RGB", (128, 128), color=(255, 255, 255)).save(seed_image)

    plan = build_plan(
        audio_path=audio_path,
        seed_dir=seed_dir,
        output_json=plan_path,
        resolution="9:16",
        max_scenes=2,
        scene_seconds=4.0,
    )

    assert plan_path.exists()
    assert plan["scene_count"] == 1
    assert plan["resolution"] == "1080x1920"
    assert plan["results"][0]["source_audio_path"] == str(audio_path.resolve())
    assert plan["results"][0]["seed_image_used"] == str(seed_image.resolve())

    result = submit_one(
        plan_json=plan_path,
        output_json=result_path,
        clip_index=1,
        model="ltx-2-3-pro",
        guidance_scale=9.0,
        dry_run=True,
    )

    assert result_path.exists()
    assert result["status"] == "dry_run"
    assert Path(result["scene_audio_path"]).exists()
    assert result["ltx_result"]["endpoint"] == "/v1/audio-to-video"
    assert result["ltx_result"]["payload"]["model"] == "ltx-2-3-pro"
    assert result["ltx_result"]["payload"]["resolution"] == "1080x1920"
