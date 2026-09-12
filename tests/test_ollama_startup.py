from unittest.mock import Mock

import pytest

from audio_analyze import ollama_startup as startup

MODEL = "gemma3:4b"
URL = "http://127.0.0.1:11434"
READY = {"models": [{"name": MODEL}]}
EMPTY = {"models": []}


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(startup, "WINDOWS", True)
    monkeypatch.setattr(startup, "model_directory", lambda: tmp_path)
    monkeypatch.setattr(startup.time, "sleep", lambda _: None)
    start = Mock()
    restart = Mock()
    pull = Mock(return_value=Mock(returncode=0))
    monkeypatch.setattr(startup, "_start", start)
    monkeypatch.setattr(startup, "_restart_windows_listener", restart)
    monkeypatch.setattr(startup.subprocess, "run", pull)
    return tmp_path, start, restart, pull


def manifest(directory):
    path = directory / "manifests" / "registry.ollama.ai" / "library" / "gemma3" / "4b"
    path.parent.mkdir(parents=True)
    path.write_text('{}')


def test_healthy_server_is_left_running(runtime, monkeypatch):
    _, start, restart, pull = runtime
    monkeypatch.setattr(startup, "_read_tags", lambda _: READY)
    startup.ensure_ollama(URL, MODEL)
    start.assert_not_called()
    restart.assert_not_called()
    pull.assert_not_called()


def test_empty_server_with_existing_model_recovers_without_download(runtime, monkeypatch):
    directory, start, restart, pull = runtime
    manifest(directory)
    monkeypatch.setattr(startup, "_read_tags", Mock(side_effect=[EMPTY, EMPTY, READY]))
    startup.ensure_ollama(URL, MODEL)
    restart.assert_called_once_with(11434)
    assert start.call_args.args[0]["OLLAMA_MODELS"] == str(directory)
    assert start.call_args.args[0]["OLLAMA_HOST"] == URL
    pull.assert_not_called()


def test_stopped_server_starts_with_saved_folder(runtime, monkeypatch):
    directory, start, restart, pull = runtime
    manifest(directory)
    monkeypatch.setattr(startup, "_read_tags", Mock(side_effect=[None, READY]))
    startup.ensure_ollama(URL, MODEL)
    start.assert_called_once()
    restart.assert_not_called()
    pull.assert_not_called()


def test_existing_manifest_never_triggers_download_when_recovery_fails(runtime, monkeypatch):
    directory, _, _, pull = runtime
    manifest(directory)
    monkeypatch.setattr(startup, "_read_tags", lambda _: EMPTY)
    with pytest.raises(RuntimeError, match="No download attempted"):
        startup.ensure_ollama(URL, MODEL)
    pull.assert_not_called()


def test_missing_model_download_uses_requested_endpoint(runtime, monkeypatch):
    directory, _, restart, pull = runtime
    monkeypatch.setattr(startup, "_read_tags", Mock(side_effect=[EMPTY, READY]))
    startup.ensure_ollama(URL, MODEL)
    restart.assert_not_called()
    assert pull.call_args.args[0] == ["ollama", "pull", MODEL]
    assert pull.call_args.kwargs["env"]["OLLAMA_HOST"] == URL
    assert pull.call_args.kwargs["env"]["OLLAMA_MODELS"] == str(directory)


def test_remote_endpoint_never_restarts_local_server(runtime, monkeypatch):
    directory, start, restart, pull = runtime
    manifest(directory)
    monkeypatch.setattr(startup, "_read_tags", lambda _: EMPTY)
    with pytest.raises(RuntimeError, match="local recovery is not applicable"):
        startup.ensure_ollama("http://example.org:11434", MODEL)
    start.assert_not_called()
    restart.assert_not_called()
    pull.assert_not_called()


def test_manifest_path_and_implicit_latest(tmp_path):
    manifest(tmp_path)
    assert startup.has_manifest(tmp_path, MODEL)
    assert not startup.has_manifest(tmp_path, "../gemma3:4b")
    assert not startup.has_manifest(tmp_path, "gemma3:latest")
    assert startup._contains({"models": [{"name": "gemma3:latest"}]}, "gemma3")


def test_windows_saved_user_setting_overrides_stale_process_env(tmp_path, monkeypatch):
    import sys
    registry = Mock()
    registry.OpenKey.return_value.__enter__ = Mock(return_value="key")
    registry.OpenKey.return_value.__exit__ = Mock(return_value=False)
    registry.QueryValueEx.return_value = (str(tmp_path), 1)
    monkeypatch.setitem(sys.modules, "winreg", registry)
    monkeypatch.setattr(startup, "WINDOWS", True)
    monkeypatch.setenv("OLLAMA_MODELS", "stale-folder")
    assert startup.model_directory() == tmp_path


def test_restart_only_targets_verified_ollama_listener(monkeypatch):
    run = Mock(return_value=Mock(returncode=1, stderr="non-Ollama process"))
    monkeypatch.setattr(startup.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="non-Ollama"):
        startup._restart_windows_listener(11434)
    script = run.call_args.args[0][-1]
    assert "-LocalPort 11434" in script
    assert "ProcessName -ne 'ollama'" in script
    assert "Stop-Process -Id $processId" in script
