import os
from pathlib import Path

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


def test_run_auto_audio_orchestrator_calls_existing_orchestrator(monkeypatch, tmp_path):
    audio = tmp_path / "test_audio.mp3"
    touch(audio, 100)
    calls = {}

    def fake_orchestrate(**kwargs):
        calls.update(kwargs)
        return {"status": "complete"}

    orchestrator_module = auto._load_orchestrator_module()
    monkeypatch.setattr(orchestrator_module, "orchestrate", fake_orchestrate)

    result = auto.run_auto_audio_orchestrator(
        audio_dir=tmp_path,
        seed_dir="inputs/ltx_seed_images",
        output_plan="outputs/test_plan.json",
        report_json="outputs/test_report.json",
        max_scenes=1,
        scene_seconds=4,
        allow_sorted_seed_fallback=True,
    )

    assert result["status"] == "complete"
    assert result["audio_selection_method"] == "newest_audio_in_folder"
    assert result["auto_selected_audio_resolved"] == str(audio.resolve())
    assert calls["audio"] == str(audio)
    assert calls["max_scenes"] == 1
    assert calls["scene_seconds"] == 4
    assert calls["allow_sorted_seed_fallback"] is True
