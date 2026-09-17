"""Start local Ollama with the saved model directory and recover stale servers."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request


WINDOWS = os.name == "nt"

def model_directory() -> Path:
    # Read persisted Windows settings: a long-lived terminal may have stale values.
    if WINDOWS:
        import winreg
        for hive, key in (
            (winreg.HKEY_CURRENT_USER, "Environment"),
            (winreg.HKEY_LOCAL_MACHINE,
             r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
        ):
            try:
                with winreg.OpenKey(hive, key) as registry_key:
                    value, _ = winreg.QueryValueEx(registry_key, "OLLAMA_MODELS")
                if str(value).strip():
                    return Path(os.path.expandvars(str(value))).expanduser()
            except OSError:
                pass
    return Path(os.path.expandvars(os.environ.get(
        "OLLAMA_MODELS", str(Path.home() / ".ollama" / "models")
    ))).expanduser()


def has_manifest(directory: Path, model: str) -> bool:
    # Match Ollama's registry / namespace / model / tag layout without allowing
    # a model name to escape the manifests directory.
    parts = model.split("/")
    name, separator, tag = parts[-1].partition(":")
    parts[-1] = name
    if len(parts) == 1:
        parts = ["registry.ollama.ai", "library", *parts]
    elif len(parts) == 2:
        parts = ["registry.ollama.ai", *parts]
    parts.append(tag if separator else "latest")
    if any(not part or part in (".", "..") or "\\" in part for part in parts):
        return False
    return (directory / "manifests").joinpath(*parts).is_file()


def _read_tags(url: str) -> dict | None:
    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/api/tags", timeout=4) as response:
            data = json.loads(response.read().decode("utf-8"))
        return data if isinstance(data, dict) and isinstance(data.get("models"), list) else None
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return None


def _contains(tags: dict | None, model: str) -> bool:
    expected = model if ":" in model.rsplit("/", 1)[-1] else f"{model}:latest"
    return any(expected in (item.get("name"), item.get("model"))
               for item in (tags or {}).get("models", []) if isinstance(item, dict))


def _start(env: dict[str, str]) -> None:
    try:
        subprocess.Popen(
            ["ollama", "serve"], env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if WINDOWS else 0,
        )
    except OSError as exc:
        raise RuntimeError("Ollama is not installed or is not available on PATH.") from exc


def _restart_windows_listener(port: int) -> None:
    # Only stop the Ollama listener on the requested local port, not unrelated
    # Ollama instances or any other application that happens to use that port.
    script = r'''
$ErrorActionPreference = 'Stop'
$listeners = @(Get-NetTCPConnection -State Listen -LocalPort PORT_NUMBER -ErrorAction SilentlyContinue)
$processIds = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
foreach ($processId in $processIds) {
    $listenerProcess = Get-Process -Id $processId -ErrorAction Stop
    if ($listenerProcess.ProcessName -ne 'ollama') {
        throw 'The requested port is owned by a non-Ollama process; refusing to stop it.'
    }
}
foreach ($processId in $processIds) {
    Stop-Process -Id $processId -ErrorAction Stop
    Wait-Process -Id $processId -Timeout 10 -ErrorAction SilentlyContinue
}
'''.replace("PORT_NUMBER", str(int(port)))
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, timeout=20, check=False,
    )
    if result.returncode:
        raise RuntimeError("Could not restart the local Ollama listener: " + result.stderr.strip())


def ensure_ollama(url: str, model: str) -> None:
    endpoint = urllib.parse.urlsplit(url)
    local = (endpoint.scheme == "http" and endpoint.hostname in
             {"127.0.0.1", "localhost", "::1"} and endpoint.path in ("", "/"))
    directory = model_directory()
    env = os.environ.copy()
    env["OLLAMA_MODELS"] = str(directory)
    env["OLLAMA_HOST"] = url.rstrip("/")
    tags = _read_tags(url)
    if _contains(tags, model):
        print(f"Using installed Ollama model {model}.")
        return
    if not local:
        raise RuntimeError(f"Ollama endpoint {url} does not report model {model}; local recovery is not applicable.")

    on_disk = has_manifest(directory, model)
    if tags is not None and on_disk:
        if not WINDOWS:
            raise RuntimeError(f"Model {model} exists in {directory}, but the server cannot see it. Restart Ollama with OLLAMA_MODELS set to that folder. No download attempted.")
        print(f"Found {model} in {directory}. Restarting local Ollama to refresh its model path...")
        _restart_windows_listener(endpoint.port or 80)
        tags = None
    if tags is None:
        _start(env)
        for _ in range(25):
            time.sleep(1)
            tags = _read_tags(url)
            if _contains(tags, model):
                print(f"Using installed Ollama model {model}.")
                return
            if tags is not None and not on_disk:
                break
    if tags is None:
        raise RuntimeError("Ollama did not start or respond. No download attempted.")
    if on_disk:
        raise RuntimeError(f"Model files exist in {directory}, but Ollama still does not list {model}. No download attempted; check the manifest and Ollama server log.")

    print(f"Model {model} is absent from the server and {directory}. Downloading...")
    completed = subprocess.run(["ollama", "pull", model], env=env, check=False)
    if completed.returncode != 0 or not _contains(_read_tags(url), model):
        raise RuntimeError(f"Unable to download or register Ollama model {model}.")
