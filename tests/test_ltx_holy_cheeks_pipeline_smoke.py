import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from audio_analyze.ltx_holy_cheeks_pipeline import build_plan, run_preflight, submit_all, submit_one


def _make_test_inputs(tmp_path):
    audio_path = tmp_path / "holy_cheeks_test.wav"
    seed_dir = tmp_path / "ltx_seed_images"
    seed_dir.mkdir()
    seed_image = seed_dir / "seed.png"

    sample_rate = 22050
    duration_seconds = 4.0
    t = np.linspace(0, duration_seconds, int(sample_rate * duration_seconds), endpoint=False)
    y = 0.2 * np.sin(2 * np.pi * 440.0 * t)
    sf.write(str(audio_path), y, sample_rate)

    Image.new("RGB", (128, 128), color=(255, 255, 255)).save(seed_image)
    return audio_path, seed_dir, seed_image


def test_ltx_plan_preflight_and_dry_run_submit(tmp_path):
    audio_path, seed_dir, seed_image = _make_test_inputs(tmp_path)
    plan_path = tmp_path / "ltx_plan.json"
    preflight_path = tmp_path / "preflight.json"
    result_path = tmp_path / "scene_01_result.json"

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

    preflight = run_preflight(plan_path, preflight_path)
    assert preflight_path.exists()
    assert preflight["status"] == "PASSED"
    assert preflight["problems"] == []

    result = submit_one(
        plan_json=plan_path,
        output_json=result_path,
        clip_index=1,
        model="ltx-2-3-pro",
        guidance_scale=9.0,
    )

    assert result_path.exists()
    assert result["status"] == "dry_run"
    assert result["dry_run"] is True
    assert result["live"] is False
    assert Path(result["scene_audio_path"]).exists()
    assert result["ltx_result"]["endpoint"] == "/v1/audio-to-video"
    assert result["ltx_result"]["payload"]["model"] == "ltx-2-3-pro"
    assert result["ltx_result"]["payload"]["resolution"] == "1080x1920"


def test_ltx_submit_all_defaults_to_dry_run(tmp_path):
    audio_path, seed_dir, _ = _make_test_inputs(tmp_path)
    plan_path = tmp_path / "ltx_plan.json"
    output_dir = tmp_path / "submit_all"

    build_plan(
        audio_path=audio_path,
        seed_dir=seed_dir,
        output_json=plan_path,
        resolution="9:16",
        max_scenes=2,
        scene_seconds=4.0,
    )

    summary = submit_all(
        plan_json=plan_path,
        output_dir=output_dir,
        model="ltx-2-3-pro",
        guidance_scale=9.0,
    )

    assert summary["status"] == "complete"
    assert summary["dry_run"] is True
    assert summary["live"] is False
    assert len(summary["results"]) == 1
    assert (output_dir / "ltx_submit_all_summary.json").exists()
