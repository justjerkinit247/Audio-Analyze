import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from audio_analyze import ltx_submit_resilient as resilient


MODEL = "ltx-2-3-pro"
GUIDANCE_SCALE = 9.0


def plan_item(prompt_text="Base prompt", seed_image="C:/seeds/scene_01.png"):
    return {
        "clip_index": 1,
        "file_stem": "song",
        "prompt_text": prompt_text,
        "seed_image_used": seed_image,
        "source_audio_path": "C:/audio/song.mp3",
        "scene": {"scene_index": 1, "start": 0.0, "end": 8.0, "duration": 8.0},
        "resolution": "1080x1920",
        "audio_to_video_confirmed": True,
        "beat_alignment_enabled": False,
    }


def write_plan(path, item):
    path.write_text(json.dumps({"results": [item]}), encoding="utf-8")


def write_result_metadata(result_path, item, fingerprint=None):
    fingerprint = fingerprint or resilient.clip_fingerprint(item, model=MODEL, guidance_scale=GUIDANCE_SCALE)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps({"clip_fingerprint": fingerprint}), encoding="utf-8")


def prepare_existing_mp4(output_dir, item, content=b"fake mp4"):
    mp4_path = resilient.expected_mp4_path(output_dir, item)
    mp4_path.parent.mkdir(parents=True, exist_ok=True)
    mp4_path.write_bytes(content)
    return mp4_path


def fail_submit_one(*args, **kwargs):
    raise AssertionError("submit_one should not be called for this dry-run reuse validation")


def run_one(tmp_path, item, monkeypatch, live=False):
    plan_path = tmp_path / "plan.json"
    output_dir = tmp_path / "out"
    write_plan(plan_path, item)
    monkeypatch.setattr(resilient, "submit_one", fail_submit_one)
    return resilient.submit_resilient(
        plan_json=plan_path,
        output_dir=output_dir,
        model=MODEL,
        guidance_scale=GUIDANCE_SCALE,
        live=live,
        retries=0,
        retry_sleep_seconds=0,
        only_missing=True,
    )


def test_existing_mp4_with_matching_fingerprint_is_skipped(tmp_path, monkeypatch):
    item = plan_item()
    output_dir = tmp_path / "out"
    prepare_existing_mp4(output_dir, item)
    write_result_metadata(output_dir / "scene_01_result.json", item)
    plan_path = tmp_path / "plan.json"
    write_plan(plan_path, item)
    monkeypatch.setattr(resilient, "submit_one", fail_submit_one)

    summary = resilient.submit_resilient(
        plan_json=plan_path,
        output_dir=output_dir,
        model=MODEL,
        guidance_scale=GUIDANCE_SCALE,
        live=False,
        retries=0,
        retry_sleep_seconds=0,
        only_missing=True,
    )

    assert summary["skipped_existing_scenes"] == [1]
    assert summary["completed_scenes"] == []
    assert summary["stale_existing_scenes"] == []
    assert summary["results"][0]["status"] == "skipped_existing"
    assert summary["results"][0]["fingerprint_validation"]["status"] == "matched"


def test_existing_mp4_with_missing_metadata_is_stale(tmp_path, monkeypatch):
    item = plan_item()
    output_dir = tmp_path / "out"
    prepare_existing_mp4(output_dir, item)

    summary = run_one(tmp_path, item, monkeypatch)

    assert summary["stale_existing_scenes"] == [1]
    assert summary["skipped_existing_scenes"] == []
    assert summary["completed_scenes"] == []
    assert summary["results"][0]["status"] == "would_resubmit_stale"
    assert summary["results"][0]["fingerprint_validation"]["status"] == "metadata_missing_or_unreadable"


def test_existing_mp4_with_mismatched_fingerprint_is_stale(tmp_path, monkeypatch):
    item = plan_item()
    output_dir = tmp_path / "out"
    prepare_existing_mp4(output_dir, item)
    write_result_metadata(output_dir / "scene_01_result.json", item, fingerprint="not-current")

    summary = run_one(tmp_path, item, monkeypatch)

    assert summary["stale_existing_scenes"] == [1]
    assert summary["skipped_existing_scenes"] == []
    assert summary["completed_scenes"] == []
    assert summary["results"][0]["status"] == "would_resubmit_stale"
    assert summary["results"][0]["fingerprint_validation"]["status"] == "fingerprint_mismatch"


def test_empty_existing_mp4_is_stale_even_with_matching_metadata(tmp_path, monkeypatch):
    item = plan_item()
    output_dir = tmp_path / "out"
    prepare_existing_mp4(output_dir, item, content=b"")
    write_result_metadata(output_dir / "scene_01_result.json", item)

    summary = run_one(tmp_path, item, monkeypatch)

    assert summary["stale_existing_scenes"] == [1]
    assert summary["skipped_existing_scenes"] == []
    assert summary["completed_scenes"] == []
    assert summary["results"][0]["status"] == "would_resubmit_stale"
    assert summary["results"][0]["fingerprint_validation"]["status"] == "mp4_empty"


def test_stale_existing_clip_is_not_counted_as_valid_skip_or_completion(tmp_path, monkeypatch):
    item = plan_item()
    output_dir = tmp_path / "out"
    prepare_existing_mp4(output_dir, item)

    summary = run_one(tmp_path, item, monkeypatch)

    assert 1 in summary["stale_existing_scenes"]
    assert 1 not in summary["skipped_existing_scenes"]
    assert 1 not in summary["completed_scenes"]


def test_dry_run_reports_would_resubmit_for_stale_existing_clip(tmp_path, monkeypatch):
    item = plan_item(prompt_text="Current prompt")
    output_dir = tmp_path / "out"
    prepare_existing_mp4(output_dir, item)
    stale_item = plan_item(prompt_text="Old prompt")
    write_result_metadata(output_dir / "scene_01_result.json", stale_item)

    summary = run_one(tmp_path, item, monkeypatch)

    row = summary["results"][0]
    assert row["status"] == "would_resubmit_stale"
    assert row["stale_existing"] is True
    assert row["reason"] == "dry-run would resubmit stale existing MP4"


def test_live_stale_existing_clip_is_resubmitted(tmp_path, monkeypatch):
    item = plan_item()
    output_dir = tmp_path / "out"
    mp4_path = prepare_existing_mp4(output_dir, item)
    write_result_metadata(output_dir / "scene_01_result.json", item, fingerprint="old")
    plan_path = tmp_path / "plan.json"
    write_plan(plan_path, item)
    calls = []

    def fake_submit_one(*args, **kwargs):
        calls.append(kwargs)
        return {
            "status": "complete",
            "downloaded_mp4": str(mp4_path.resolve()),
            "scene_audio_path": "C:/audio/scene_01.mp3",
            "scene_audio_format": "MP3",
        }

    monkeypatch.setattr(resilient, "submit_one", fake_submit_one)

    summary = resilient.submit_resilient(
        plan_json=plan_path,
        output_dir=output_dir,
        model=MODEL,
        guidance_scale=GUIDANCE_SCALE,
        live=True,
        retries=0,
        retry_sleep_seconds=0,
        only_missing=True,
    )

    assert len(calls) == 1
    assert summary["stale_existing_scenes"] == [1]
    assert summary["completed_scenes"] == [1]
    assert summary["skipped_existing_scenes"] == []
    assert (output_dir / "downloads" / "song_ltx_scene_01.metadata.json").exists()
