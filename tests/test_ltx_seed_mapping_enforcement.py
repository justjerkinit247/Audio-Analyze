import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from audio_analyze import ltx_holy_cheeks_pipeline as ltx
from audio_analyze.ltx_seed_mapper import validate_seed_mapping


MODEL = "ltx-2-3-pro"
GUIDANCE_SCALE = 9.0


def make_audio(tmp_path):
    audio = tmp_path / "song.mp3"
    audio.write_bytes(b"audio bytes")
    return audio


def make_seed(seed_dir, name, content=b"image bytes"):
    seed = seed_dir / name
    seed.write_bytes(content)
    return seed


def make_item(index, audio, seed, method="scene_label"):
    return {
        "clip_index": index,
        "file_stem": "song",
        "source_audio_path": str(audio),
        "seed_image_used": str(seed),
        "seed_assignment": {
            "method": method,
            "seed_file": Path(seed).name,
            "seed_image_path": str(seed),
            "scene_label_expected": f"scene_{index:02d}",
        },
        "scene": {"scene_index": index, "start": 0.0, "end": 8.0, "duration": 8.0},
        "resolution": "1080x1920",
        "prompt_text": "Valid prompt",
    }


def make_plan(*items, seed_dir=None):
    plan = {"results": list(items)}
    if seed_dir is not None:
        plan["seed_mapping"] = {"seed_dir": str(seed_dir)}
    return plan


def stub_plan_analysis(monkeypatch, scene_count):
    monkeypatch.setattr(
        ltx,
        "analyze_audio",
        lambda _audio: {
            "tempo_bpm": 120.0,
            "camera_notes": "controlled tracking",
            "movement_notes": "beat-synced movement",
            "lighting_notes": "studio lighting",
        },
    )
    monkeypatch.setattr(ltx, "detect_beats", lambda _audio: (16.0, 120.0, []))
    monkeypatch.setattr(
        ltx,
        "build_scenes",
        lambda *args, **kwargs: [
            {
                "scene_index": index,
                "start": float((index - 1) * 8),
                "end": float(index * 8),
                "duration": 8.0,
                "scene_type": "performance phrase",
                "sync_start_rule": "fixed scene grid",
                "sync_end_rule": "fixed scene grid",
            }
            for index in range(1, scene_count + 1)
        ],
    )


def test_build_plan_prefers_explicit_scene_labels_over_sort_order(tmp_path, monkeypatch):
    seed_dir = tmp_path / "seeds"
    seed_dir.mkdir()
    audio = make_audio(tmp_path)
    scene_2 = make_seed(seed_dir, "clip_02_aaa.png")
    scene_1 = make_seed(seed_dir, "scene_01_zzz.png")
    stub_plan_analysis(monkeypatch, scene_count=2)

    plan = ltx.build_plan(audio, seed_dir, tmp_path / "plan.json")

    assert plan["seed_mapping"]["status"] == "PASSED"
    assert plan["results"][0]["seed_image_used"] == str(scene_1.resolve())
    assert plan["results"][1]["seed_image_used"] == str(scene_2.resolve())
    assert [item["seed_assignment"]["method"] for item in plan["results"]] == ["scene_label", "scene_label"]


def test_build_plan_marks_sorted_fallback_unsafe_unless_allowed(tmp_path, monkeypatch):
    seed_dir = tmp_path / "seeds"
    seed_dir.mkdir()
    audio = make_audio(tmp_path)
    make_seed(seed_dir, "unlabeled.png")
    stub_plan_analysis(monkeypatch, scene_count=1)

    rejected = ltx.build_plan(audio, seed_dir, tmp_path / "rejected.json")
    allowed = ltx.build_plan(
        audio,
        seed_dir,
        tmp_path / "allowed.json",
        allow_sorted_seed_fallback=True,
    )

    assert rejected["seed_mapping"]["status"] == "FAILED"
    assert rejected["results"][0]["seed_assignment"]["method"] == "sorted_seed_fallback"
    assert allowed["seed_mapping"]["status"] == "PASSED"
    assert allowed["seed_mapping"]["fallback_mode_used"] is True


def test_explicit_complete_mapping_passes(tmp_path):
    seed_dir = tmp_path / "seeds"
    seed_dir.mkdir()
    audio = make_audio(tmp_path)
    seed_1 = make_seed(seed_dir, "scene_01_intro.png")
    seed_2 = make_seed(seed_dir, "scene_02_close.png")
    plan = make_plan(
        make_item(1, audio, seed_1),
        make_item(2, audio, seed_2),
        seed_dir=seed_dir,
    )

    report = validate_seed_mapping(plan)
    problems = ltx.validate_plan(
        plan,
        model=MODEL,
        guidance_scale=GUIDANCE_SCALE,
        require_seed_mapping=True,
    )

    assert report["status"] == "PASSED"
    assert report["mapped_scene_count"] == 2
    assert report["missing_mappings"] == []
    assert report["duplicate_seed_usage"] == []
    assert report["fallback_mode_used"] is False
    assert problems == []


def test_missing_seed_mapping_fails(tmp_path):
    seed_dir = tmp_path / "seeds"
    seed_dir.mkdir()
    audio = make_audio(tmp_path)
    seed = make_seed(seed_dir, "scene_01_intro.png")
    item = make_item(1, audio, seed)
    item.pop("seed_assignment")

    report = validate_seed_mapping(make_plan(item, seed_dir=seed_dir))

    assert report["status"] == "FAILED"
    assert report["missing_mappings"][0]["clip_index"] == 1
    assert report["missing_mappings"][0]["expected_key"] == "scene_01"
    assert str(seed) in report["problems"][0]


def test_mapped_seed_file_missing_fails(tmp_path):
    seed_dir = tmp_path / "seeds"
    seed_dir.mkdir()
    audio = make_audio(tmp_path)
    missing_seed = seed_dir / "scene_01_missing.png"

    report = validate_seed_mapping(make_plan(make_item(1, audio, missing_seed), seed_dir=seed_dir))

    assert report["status"] == "FAILED"
    assert any("Scene 1" in problem and "mapped seed image file missing" in problem for problem in report["problems"])
    assert any(str(missing_seed) in problem for problem in report["problems"])


def test_mapped_seed_file_empty_fails(tmp_path):
    seed_dir = tmp_path / "seeds"
    seed_dir.mkdir()
    audio = make_audio(tmp_path)
    seed = make_seed(seed_dir, "scene_01_empty.png", content=b"")

    report = validate_seed_mapping(make_plan(make_item(1, audio, seed), seed_dir=seed_dir))

    assert report["status"] == "FAILED"
    assert any("Scene 1" in problem and "mapped seed image file is empty" in problem for problem in report["problems"])


def test_invalid_image_extension_fails(tmp_path):
    seed_dir = tmp_path / "seeds"
    seed_dir.mkdir()
    audio = make_audio(tmp_path)
    seed = make_seed(seed_dir, "scene_01_seed.bmp")

    report = validate_seed_mapping(make_plan(make_item(1, audio, seed), seed_dir=seed_dir))

    assert report["status"] == "FAILED"
    assert any("unsupported image extension '.bmp'" in problem for problem in report["problems"])


def test_accidental_duplicate_seed_usage_is_detected(tmp_path):
    seed_dir = tmp_path / "seeds"
    seed_dir.mkdir()
    audio = make_audio(tmp_path)
    seed = make_seed(seed_dir, "scene_01_shared.png")
    plan = make_plan(
        make_item(1, audio, seed, method="manifest_seed_file"),
        make_item(2, audio, seed, method="manifest_seed_file"),
        seed_dir=seed_dir,
    )

    report = validate_seed_mapping(plan)
    allowed = validate_seed_mapping(plan, allow_duplicate_seed_reuse=True)

    assert report["status"] == "FAILED"
    assert report["duplicate_seed_usage"][0]["clip_indexes"] == [1, 2]
    assert report["duplicate_seed_usage"][0]["seed_image_path"] == str(seed.resolve())
    assert allowed["status"] == "PASSED"
    assert allowed["allow_duplicate_seed_reuse"] is True


def test_sorted_order_fallback_is_rejected_before_live_submit(tmp_path, monkeypatch):
    seed_dir = tmp_path / "seeds"
    seed_dir.mkdir()
    audio = make_audio(tmp_path)
    seed = make_seed(seed_dir, "unlabeled_seed.png")
    plan_path = tmp_path / "plan.json"
    output_path = tmp_path / "scene_01_result.json"
    plan_path.write_text(
        json.dumps(make_plan(make_item(1, audio, seed, method="sorted_seed_fallback"), seed_dir=seed_dir)),
        encoding="utf-8",
    )
    constructed_clients = []

    class FailIfConstructedClient:
        def __init__(self, *args, **kwargs):
            constructed_clients.append((args, kwargs))
            raise AssertionError("LTXClient should not be constructed when seed mapping validation fails")

    monkeypatch.setenv("LTXV_API_KEY", "test-key")
    monkeypatch.setattr(ltx, "LTXClient", FailIfConstructedClient)

    with pytest.raises(RuntimeError) as exc_info:
        ltx.submit_one(
            plan_json=plan_path,
            output_json=output_path,
            clip_index=1,
            model=MODEL,
            guidance_scale=GUIDANCE_SCALE,
            dry_run=False,
            live=True,
        )

    assert constructed_clients == []
    assert "Scene 1" in str(exc_info.value)
    assert "expected_key=scene_01" in str(exc_info.value)
    assert "sorted-order seed fallback is unsafe unless explicitly allowed" in str(exc_info.value)
    assert str(seed) in str(exc_info.value)


def test_invalid_mapping_in_later_scene_blocks_partial_live_submit(tmp_path, monkeypatch):
    seed_dir = tmp_path / "seeds"
    seed_dir.mkdir()
    audio = make_audio(tmp_path)
    seed_1 = make_seed(seed_dir, "scene_01_intro.png")
    seed_2 = make_seed(seed_dir, "scene_02_close.png")
    scene_2 = make_item(2, audio, seed_2)
    scene_2.pop("seed_assignment")
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        json.dumps(make_plan(make_item(1, audio, seed_1), scene_2, seed_dir=seed_dir)),
        encoding="utf-8",
    )
    constructed_clients = []

    class FailIfConstructedClient:
        def __init__(self, *args, **kwargs):
            constructed_clients.append((args, kwargs))
            raise AssertionError("LTXClient should not be constructed when any planned mapping fails")

    monkeypatch.setenv("LTXV_API_KEY", "test-key")
    monkeypatch.setattr(ltx, "LTXClient", FailIfConstructedClient)

    with pytest.raises(RuntimeError) as exc_info:
        ltx.submit_one(
            plan_json=plan_path,
            output_json=tmp_path / "scene_01_result.json",
            clip_index=1,
            model=MODEL,
            guidance_scale=GUIDANCE_SCALE,
            dry_run=False,
            live=True,
        )

    assert constructed_clients == []
    assert "Scene 2" in str(exc_info.value)
    assert "expected_key=scene_02" in str(exc_info.value)
    assert "missing explicit seed_assignment" in str(exc_info.value)


def test_sorted_order_fallback_only_passes_when_explicitly_allowed(tmp_path):
    seed_dir = tmp_path / "seeds"
    seed_dir.mkdir()
    audio = make_audio(tmp_path)
    seed = make_seed(seed_dir, "unlabeled_seed.png")
    plan = make_plan(make_item(1, audio, seed, method="sorted_seed_fallback"), seed_dir=seed_dir)

    rejected = validate_seed_mapping(plan)
    allowed = validate_seed_mapping(plan, allow_sorted_seed_fallback=True)

    assert rejected["status"] == "FAILED"
    assert allowed["status"] == "PASSED"
    assert allowed["fallback_mode_used"] is True
    assert allowed["fallback_mappings"][0]["clip_index"] == 1


def test_extra_unmapped_seed_images_are_reported_as_warnings(tmp_path):
    seed_dir = tmp_path / "seeds"
    seed_dir.mkdir()
    audio = make_audio(tmp_path)
    mapped = make_seed(seed_dir, "scene_01_intro.png")
    extra = make_seed(seed_dir, "scene_02_extra.png")

    report = validate_seed_mapping(make_plan(make_item(1, audio, mapped), seed_dir=seed_dir))

    assert report["status"] == "PASSED"
    assert report["extra_seed_files"] == [str(extra.resolve())]
    assert any(str(extra.resolve()) in warning for warning in report["warnings"])
