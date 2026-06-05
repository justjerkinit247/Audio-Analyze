import argparse
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_root_main():
    module_name = "audio_analyze_root_main_for_tests"
    spec = importlib.util.spec_from_file_location(module_name, ROOT / "main.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def make_args(audio, seed_dir):
    return argparse.Namespace(
        audio=str(audio),
        seed_dir=str(seed_dir),
        output_plan=None,
        resolution="9:16",
        max_scenes=None,
        scene_seconds=8.0,
        start_offset_seconds=0.0,
        beat_align=False,
        model="ltx-2-3-pro",
        guidance_scale=9.0,
        run_id="hard_stop_test",
        live=True,
        dry_run=False,
        assemble_after=True,
        assembly_dry_run=True,
        cleanup_json=False,
        cleanup_json_on_success=False,
        cleanup_after_dry_run=False,
        no_cleanup_json=True,
    )


def test_enforce_submit_hard_stop_return_contract():
    root_main = load_root_main()
    result = {"status": "complete", "summary": {"status": "complete_with_failures"}}

    reason = root_main.enforce_submit_hard_stop(result, render_output_expected=True)

    assert reason
    assert result["status"] == "failed_submit"
    assert result["hard_stop_reason"] == reason


def test_enforce_submit_hard_stop_returns_none_on_success():
    root_main = load_root_main()
    result = {"status": "complete", "summary": {"status": "complete"}}

    reason = root_main.enforce_submit_hard_stop(result, render_output_expected=True)

    assert reason is None
    assert result["status"] == "complete"
    assert "hard_stop_reason" not in result


def test_enforce_submit_hard_stop_ignores_planning_only_without_render_expectation():
    root_main = load_root_main()
    result = {"status": "complete"}

    reason = root_main.enforce_submit_hard_stop(result)

    assert reason is None
    assert result["status"] == "complete"
    assert "hard_stop_reason" not in result


def test_complete_with_failures_does_not_allow_root_success(tmp_path, monkeypatch):
    root_main = load_root_main()

    audio = tmp_path / "song.mp3"
    audio.write_bytes(b"fake audio")
    seed_dir = tmp_path / "seeds"
    seed_dir.mkdir()
    run_dir = tmp_path / "run"

    def fake_build_run_paths(run_id):
        return root_main.RunPaths(
            run_id=run_id,
            run_dir=run_dir,
            plan_json=run_dir / "holy_cheeks_ltx_plan.json",
            preflight_json=run_dir / "preflight_report.json",
            submissions_dir=run_dir / "submissions",
            orchestration_dir=run_dir / "orchestration",
            stitching_manifest=run_dir / "orchestration" / "stitching_manifest.json",
            assembled_dir=run_dir / "assembled",
            assembly_output=run_dir / "assembled" / "final_music_video.mp4",
            assembly_report=run_dir / "assembled" / "assembly_report.json",
            run_orchestrator_report=run_dir / "orchestrator_report.json",
        )

    result = {
        "status": "complete",
        "summary": {
            "status": "complete_with_failures",
            "failed_count": 1,
            "results": [{"clip_index": 2, "status": "failed"}],
        },
    }

    class FakeOrchestrator:
        def orchestrate(self, **kwargs):
            return result

    monkeypatch.setattr(root_main, "FINALS_DIR", tmp_path / "final_videos")
    monkeypatch.setattr(root_main, "build_run_paths", fake_build_run_paths)
    monkeypatch.setattr(root_main, "configure_orchestrator", lambda paths: FakeOrchestrator())
    monkeypatch.setattr(
        root_main,
        "assert_no_root_leaks",
        lambda run_id: {"run_id": run_id, "root_leak_count": 0, "root_leaks": []},
    )

    exit_code = root_main.run_pipeline(make_args(audio, seed_dir))

    assert exit_code == 1
    assert result["status"] == "failed_submit"
    assert "hard_stop_reason" in result
    assert not (run_dir / "assembled" / "assembly_report.json").exists()
