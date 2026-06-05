import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from audio_analyze import ltx_holy_cheeks_pipeline as ltx


MODEL = "ltx-2-3-pro"
GUIDANCE_SCALE = 9.0


def make_media(tmp_path):
    audio = tmp_path / "song.mp3"
    image = tmp_path / "seed.png"
    audio.write_bytes(b"audio bytes")
    image.write_bytes(b"image bytes")
    return audio, image


def make_item(audio, image, **overrides):
    item = {
        "clip_index": 1,
        "file_stem": "song",
        "source_audio_path": str(audio),
        "seed_image_used": str(image),
        "scene": {"scene_index": 1, "start": 0.0, "end": 8.0, "duration": 8.0},
        "resolution": "1080x1920",
        "prompt_text": "Valid prompt",
        "status": "planned",
        "audio_to_video_confirmed": True,
    }
    item.update(overrides)
    return item


def make_plan(item):
    return {"results": [item]}


def assert_problem_contains(problems, *parts):
    joined = "\n".join(problems)
    for part in parts:
        assert part in joined


def test_valid_plan_and_settings_pass(tmp_path):
    audio, image = make_media(tmp_path)
    problems = ltx.validate_plan(
        make_plan(make_item(audio, image)),
        model=MODEL,
        guidance_scale=GUIDANCE_SCALE,
        clip_index=1,
    )

    assert problems == []


def test_invalid_model_fails(tmp_path):
    audio, image = make_media(tmp_path)
    problems = ltx.validate_plan(make_plan(make_item(audio, image)), model="bad-model", guidance_scale=GUIDANCE_SCALE)

    assert_problem_contains(problems, "Scene 1", "model", "unsupported model 'bad-model'")


def test_invalid_guidance_scale_type_fails(tmp_path):
    audio, image = make_media(tmp_path)
    problems = ltx.validate_plan(make_plan(make_item(audio, image)), model=MODEL, guidance_scale="strong")

    assert_problem_contains(problems, "Scene 1", "guidance_scale", "must be numeric")


def test_out_of_range_guidance_scale_fails(tmp_path):
    audio, image = make_media(tmp_path)
    problems = ltx.validate_plan(make_plan(make_item(audio, image)), model=MODEL, guidance_scale=100)

    assert_problem_contains(problems, "Scene 1", "guidance_scale", "must be between")


def test_invalid_resolution_fails(tmp_path):
    audio, image = make_media(tmp_path)
    problems = ltx.validate_plan(make_plan(make_item(audio, image, resolution="9:16")), model=MODEL, guidance_scale=GUIDANCE_SCALE)

    assert_problem_contains(problems, "Scene 1", "resolution", "unsupported or unnormalized value")


def test_empty_prompt_fails(tmp_path):
    audio, image = make_media(tmp_path)
    problems = ltx.validate_plan(make_plan(make_item(audio, image, prompt_text="   ")), model=MODEL, guidance_scale=GUIDANCE_SCALE)

    assert_problem_contains(problems, "Scene 1", "prompt_text", "prompt is empty")


def test_overlong_prompt_fails(tmp_path):
    audio, image = make_media(tmp_path)
    problems = ltx.validate_plan(
        make_plan(make_item(audio, image, prompt_text="x" * (ltx.PROMPT_MAX_CHARS + 1))),
        model=MODEL,
        guidance_scale=GUIDANCE_SCALE,
    )

    assert_problem_contains(problems, "Scene 1", "prompt_text", f"over {ltx.PROMPT_MAX_CHARS} characters")


def test_missing_audio_path_fails(tmp_path):
    _, image = make_media(tmp_path)
    missing_audio = tmp_path / "missing.mp3"
    problems = ltx.validate_plan(make_plan(make_item(missing_audio, image)), model=MODEL, guidance_scale=GUIDANCE_SCALE)

    assert_problem_contains(problems, "Scene 1", "source_audio_path", "file missing", str(missing_audio))


def test_missing_seed_image_path_fails(tmp_path):
    audio, _ = make_media(tmp_path)
    missing_image = tmp_path / "missing.png"
    problems = ltx.validate_plan(make_plan(make_item(audio, missing_image)), model=MODEL, guidance_scale=GUIDANCE_SCALE)

    assert_problem_contains(problems, "Scene 1", "seed_image_used", "file missing", str(missing_image))


def test_empty_media_file_fails(tmp_path):
    audio, image = make_media(tmp_path)
    audio.write_bytes(b"")
    problems = ltx.validate_plan(make_plan(make_item(audio, image)), model=MODEL, guidance_scale=GUIDANCE_SCALE)

    assert_problem_contains(problems, "Scene 1", "source_audio_path", "file is empty", str(audio))


def test_invalid_media_extension_fails(tmp_path):
    audio = tmp_path / "song.txt"
    image = tmp_path / "seed.bmp"
    audio.write_bytes(b"audio bytes")
    image.write_bytes(b"image bytes")
    problems = ltx.validate_plan(make_plan(make_item(audio, image)), model=MODEL, guidance_scale=GUIDANCE_SCALE)

    assert_problem_contains(problems, "source_audio_path", "unsupported extension '.txt'")
    assert_problem_contains(problems, "seed_image_used", "unsupported extension '.bmp'")


def test_invalid_clip_index_fails(tmp_path):
    audio, image = make_media(tmp_path)
    problems = ltx.validate_plan(make_plan(make_item(audio, image, clip_index=0)), model=MODEL, guidance_scale=GUIDANCE_SCALE)

    assert_problem_contains(problems, "clip_index", "must be a positive integer")


def test_live_submit_refuses_before_ltx_client_on_validation_failure(tmp_path, monkeypatch):
    audio, image = make_media(tmp_path)
    plan_path = tmp_path / "plan.json"
    output_path = tmp_path / "scene_01_result.json"
    plan_path.write_text(json.dumps(make_plan(make_item(audio, image))), encoding="utf-8")
    constructed_clients = []

    class FailIfConstructedClient:
        def __init__(self, *args, **kwargs):
            constructed_clients.append((args, kwargs))
            raise AssertionError("LTXClient should not be constructed when validation fails")

    monkeypatch.setenv("LTXV_API_KEY", "test-key")
    monkeypatch.setattr(ltx, "LTXClient", FailIfConstructedClient)

    with pytest.raises(RuntimeError) as exc_info:
        ltx.submit_one(
            plan_json=plan_path,
            output_json=output_path,
            clip_index=1,
            model="bad-model",
            guidance_scale=GUIDANCE_SCALE,
            dry_run=False,
            live=True,
        )

    assert constructed_clients == []
    assert "Preflight failed" in str(exc_info.value)
    assert "Scene 1: model: unsupported model 'bad-model'" in str(exc_info.value)
