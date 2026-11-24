from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_gtrg_local_output.py"
spec = importlib.util.spec_from_file_location("verify_gtrg_local_output", SCRIPT)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _source_report(path: Path, *, resolution="288x512", frames=51):
    video = path.parent / "sample.mp4"
    video.write_bytes(b"local test fixture")
    path.write_text(json.dumps({
        "mode": "LOCAL_RENDER",
        "tiny_settings": {
            "resolution": resolution,
            "video_frames": 57,
            "genuine_frames_for_output": frames,
            "expected_finish_frames": frames,
            "preview_uses_repeated_motion": False,
        },
        "result": {
            "status": "PLAYABLE_FILE_NOT_YET_VERIFIED",
            "output_videos": [str(video)],
        },
    }), encoding="utf-8")
    return video


def _ffprobe_json(*, width=288, height=512, frames=51, audio=True):
    streams = [{
        "codec_type": "video", "codec_name": "h264", "width": width,
        "height": height, "nb_read_frames": str(frames),
    }]
    if audio:
        streams.append({"codec_type": "audio", "codec_name": "aac"})
    return json.dumps({"streams": streams, "format": {"duration": "2.125"}})


def test_verifies_expected_video_frames_dimensions_and_audio(monkeypatch, tmp_path):
    report = tmp_path / "canary.json"
    video = _source_report(report)
    commands = []

    class Completed:
        returncode = 0
        stdout = _ffprobe_json()

    def fake_run(command, **kwargs):
        commands.append((command, kwargs))
        return Completed()

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    result = module.verify_report(report, ffprobe="ffprobe")

    assert result["status"] == "VERIFIED_STREAMS_AND_FRAME_COUNT"
    assert result["files"][0]["actual"]["video_frames"] == 51
    assert result["files"][0]["checks"]["audio_stream_present"]
    assert video.as_posix() in commands[0][0]
    assert commands[0][1]["timeout"] == 90
    saved = json.loads((tmp_path / "canary.verification.json").read_text())
    assert saved["status"] == "VERIFIED_STREAMS_AND_FRAME_COUNT"


@pytest.mark.parametrize("probe_json", [
    _ffprobe_json(frames=50),
    _ffprobe_json(width=512, height=288),
    _ffprobe_json(audio=False),
])
def test_rejects_wrong_frame_count_dimensions_or_missing_audio(monkeypatch, tmp_path, probe_json):
    report = tmp_path / "canary.json"
    _source_report(report)

    class Completed:
        returncode = 0
        stdout = probe_json

    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: Completed())
    result = module.verify_report(report, ffprobe="ffprobe")
    assert result["status"] == "VERIFICATION_FAILED"


def test_nonzero_ffprobe_exit_is_recorded_as_failure(monkeypatch, tmp_path):
    report = tmp_path / "canary.json"
    _source_report(report)

    class Completed:
        returncode = 1
        stdout = ""

    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: Completed())
    result = module.verify_report(report, ffprobe="ffprobe")
    assert result["status"] == "VERIFICATION_FAILED"
    assert result["files"][0]["error"] == "ffprobe rejected the output file"


def test_missing_report_video_paths_fail_closed(tmp_path):
    report = tmp_path / "canary.json"
    report.write_text(json.dumps({
        "tiny_settings": {
            "resolution": "288x512", "video_frames": 57,
            "genuine_frames_for_output": 51,
            "expected_finish_frames": 51, "preview_uses_repeated_motion": False,
        },
        "mode": "LOCAL_RENDER",
        "result": {"status": "PLAYABLE_FILE_NOT_YET_VERIFIED", "output_videos": []},
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="no output_videos"):
        module.verify_report(report, ffprobe="ffprobe")


def test_missing_video_file_is_recorded_as_failure(tmp_path):
    report = tmp_path / "canary.json"
    missing = tmp_path / "missing.mp4"
    report.write_text(json.dumps({
        "tiny_settings": {
            "resolution": "288x512", "video_frames": 57,
            "genuine_frames_for_output": 51,
            "expected_finish_frames": 51, "preview_uses_repeated_motion": False,
        },
        "mode": "LOCAL_RENDER",
        "result": {
            "status": "PLAYABLE_FILE_NOT_YET_VERIFIED",
            "output_videos": [str(missing)],
        },
    }), encoding="utf-8")
    result = module.verify_report(report, ffprobe="ffprobe")
    assert result["status"] == "VERIFICATION_FAILED"
    assert result["files"][0]["error"] == "Output file does not exist"


def test_repeated_preview_is_rejected_as_nonproduction(tmp_path):
    report = tmp_path / "preview.json"
    _source_report(report)
    source = json.loads(report.read_text())
    source["tiny_settings"]["preview_uses_repeated_motion"] = True
    report.write_text(json.dumps(source), encoding="utf-8")
    with pytest.raises(ValueError, match="repeated preview motion"):
        module.verify_report(report, ffprobe="ffprobe")


def test_dry_run_report_is_rejected(tmp_path):
    report = tmp_path / "dry-run.json"
    _source_report(report)
    source = json.loads(report.read_text())
    source["mode"] = "DRY_RUN_NO_GPU"
    report.write_text(json.dumps(source), encoding="utf-8")
    with pytest.raises(ValueError, match="not from an explicitly run local render"):
        module.verify_report(report, ffprobe="ffprobe")
