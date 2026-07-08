import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from audio_analyze import ltx_auto_audio_orchestrator as auto


def touch(path, when):
    path.write_bytes(b"audio")
    os.utime(path, (when, when))


def test_find_newest_audio_selects_most_recent_supported_file(tmp_path):
    older = tmp_path / "older_track.mp3"
    newer = tmp_path / "newer_track.wav"
    ignored = tmp_path / "notes.txt"

    touch(older, 100)
    touch(newer, 200)
    ignored.write_text("ignore", encoding="utf-8")

    assert auto.find_newest_audio(tmp_path) == newer


def test_find_newest_audio_rejects_empty_audio_folder(tmp_path):
    with pytest.raises(FileNotFoundError, match="No supported audio files"):
        auto.find_newest_audio(tmp_path)


def test_resolve_audio_argument_prefers_explicit_path(tmp_path):
    explicit = tmp_path / "explicit.mp3"
    auto_candidate = tmp_path / "newest.wav"
    touch(explicit, 100)
    touch(auto_candidate, 300)

    selected, method = auto.resolve_audio_argument(explicit, audio_dir=tmp_path)

    assert selected == explicit
    assert method == "explicit_audio"


def test_archive_existing_plan_removes_it_from_active_path(tmp_path):
    plan_path = tmp_path / "validated_plan.json"
    plan_path.write_text('{"old": true}', encoding="utf-8")

    archived = auto.archive_existing_plan(plan_path, "ltx_test_run")

    assert archived is not None
    assert not plan_path.exists()
    archived_path = Path(archived["archived_resolved_path"])
    assert archived_path.is_file()
    assert json.loads(archived_path.read_text(encoding="utf-8")) == {"old": True}
    assert archived_path.parent.name == "_archive"


def test_validate_fresh_run_plan_rejects_wrong_run_id(tmp_path):
    plan_path = tmp_path / "run" / "validated_plan.json"
    plan_path.parent.mkdir(parents=True)
    plan = {
        "run_id": "ltx_current",
        "plan_reuse_allowed": False,
        "fresh_run": {
            "run_id": "ltx_current",
            "plan_json_resolved": str(plan_path.resolve()),
            "run_root_resolved": str(plan_path.parent.resolve()),
        },
        "results": [{"clip_index": 1}],
    }
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    problems = auto.validate_fresh_run_plan(
        plan,
        plan_json=plan_path,
        expected_run_id="ltx_wrong",
        output_json=plan_path.parent / "live_result.json",
    )

    assert any("run_id mismatch" in problem for problem in problems)


def test_submit_fresh_run_plan_verifies_id_before_calling_pipeline(monkeypatch, tmp_path):
    plan_path = tmp_path / "run" / "validated_plan.json"
    output_path = plan_path.parent / "live_result.json"
    plan_path.parent.mkdir(parents=True)
    plan = {
        "run_id": "ltx_current",
        "plan_reuse_allowed": False,
        "fresh_run": {
            "run_id": "ltx_current",
            "plan_json_resolved": str(plan_path.resolve()),
            "run_root_resolved": str(plan_path.parent.resolve()),
        },
        "results": [{"clip_index": 1}],
    }
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    calls = {}

    def fake_submit_one(**kwargs):
        calls.update(kwargs)
        return {"status": "dry_run"}

    fake_pipeline = SimpleNamespace(
        DEFAULT_MODEL="ltx-2-3-pro",
        DEFAULT_GUIDANCE_SCALE=9.0,
        read_json=lambda path: json.loads(Path(path).read_text(encoding="utf-8")),
        submit_one=fake_submit_one,
    )
    monkeypatch.setattr(auto, "_load_pipeline_module", lambda: fake_pipeline)

    result = auto.submit_fresh_run_plan(
        plan_json=plan_path,
        output_json=output_path,
        expected_run_id="ltx_current",
        clip_index=1,
        live=False,
    )

    assert result["fresh_run_verified"] is True
    assert result["verified_run_id"] == "ltx_current"
    assert calls["plan_json"] == plan_path
    assert calls["output_json"] == output_path
    assert calls["dry_run"] is True
    assert calls["live"] is False


def test_run_auto_audio_orchestrator_calls_existing_orchestrator(monkeypatch, tmp_path):
    audio = tmp_path / "test_audio.mp3"
    touch(audio, 100)
    calls = {}

    def fake_orchestrate(**kwargs):
        calls.update(kwargs)
        calls["scoped_preflight"] = orchestrator_module.DEFAULT_PREFLIGHT_JSON
        calls["scoped_submit_dir"] = orchestrator_module.DEFAULT_SUBMIT_DIR
        calls["scoped_orchestration_dir"] = orchestrator_module.DEFAULT_ORCHESTRATION_DIR
        return {"status": "complete"}

    orchestrator_module = auto._load_orchestrator_module()
    original_preflight = orchestrator_module.DEFAULT_PREFLIGHT_JSON
    original_submit = orchestrator_module.DEFAULT_SUBMIT_DIR
    original_orchestration = orchestrator_module.DEFAULT_ORCHESTRATION_DIR
    monkeypatch.setattr(orchestrator_module, "orchestrate", fake_orchestrate)

    run_root = tmp_path / "run_001"
    output_plan = run_root / "validated_plan.json"
    report_json = run_root / "report.json"
    result = auto.run_auto_audio_orchestrator(
        audio_dir=tmp_path,
        seed_dir="inputs/ltx_seed_images",
        output_plan=output_plan,
        report_json=report_json,
        run_id="ltx_run_001",
        max_scenes=1,
        scene_seconds=4,
        allow_sorted_seed_fallback=True,
    )

    assert result["status"] == "complete"
    assert result["run_id"] == "ltx_run_001"
    assert result["fresh_run"] is True
    assert result["plan_reuse_allowed"] is False
    assert result["audio_selection_method"] == "newest_audio_in_folder"
    assert result["auto_selected_audio_resolved"] == str(audio.resolve())
    assert calls["audio"] == str(audio)
    assert calls["max_scenes"] == 1
    assert calls["scene_seconds"] == 4
    assert calls["allow_sorted_seed_fallback"] is True
    assert Path(calls["scoped_preflight"]).resolve() == (run_root / "preflight_report.json").resolve()
    assert Path(calls["scoped_submit_dir"]).resolve() == (run_root / "submissions").resolve()
    assert Path(calls["scoped_orchestration_dir"]).resolve() == (run_root / "orchestration").resolve()
    assert orchestrator_module.DEFAULT_PREFLIGHT_JSON == original_preflight
    assert orchestrator_module.DEFAULT_SUBMIT_DIR == original_submit
    assert orchestrator_module.DEFAULT_ORCHESTRATION_DIR == original_orchestration
