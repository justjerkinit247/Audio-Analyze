from pathlib import Path, PureWindowsPath
import argparse
import json
import os


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REQUIRED_INPUT_FIELDS = {
    "audio_path",
    "seed_image_path",
    "prompt_path",
    "negative_prompt_path",
    "source_audio_path",
    "seed_image_used",
}


def is_windows_absolute_path(value):
    if value is None:
        return False
    try:
        return PureWindowsPath(os.fspath(value)).is_absolute()
    except TypeError:
        return False


def resolve_runtime_path(value, repo_root=REPO_ROOT):
    raw = os.fspath(value)
    path = Path(raw)
    if path.is_absolute() or is_windows_absolute_path(raw):
        return path
    return Path(repo_root) / path


def serialize_path(value, repo_root=REPO_ROOT):
    resolved = resolve_runtime_path(value, repo_root=repo_root).resolve()
    try:
        return resolved.relative_to(Path(repo_root).resolve()).as_posix()
    except ValueError:
        return str(resolved)


def describe_path(value, repo_root=REPO_ROOT):
    resolved = resolve_runtime_path(value, repo_root=repo_root).resolve()
    serialized = serialize_path(resolved, repo_root=repo_root)
    inside_repo = not Path(serialized).is_absolute() and not is_windows_absolute_path(serialized)
    exists = resolved.exists()
    return {
        "path": serialized,
        "resolved_path": str(resolved),
        "inside_repo": inside_repo,
        "windows_absolute_input": is_windows_absolute_path(value),
        "exists": exists,
        "size_bytes": resolved.stat().st_size if exists and resolved.is_file() else None,
    }


def validate_path_config(data, repo_root=REPO_ROOT, required_input_fields=None):
    required_input_fields = set(required_input_fields or DEFAULT_REQUIRED_INPUT_FIELDS)
    report = {
        "status": "PASSED",
        "repo_root": str(Path(repo_root).resolve()),
        "paths": [],
        "absolute_windows_paths": [],
        "missing_paths": [],
        "problems": [],
        "warnings": [],
    }

    def visit(value, key_path=""):
        if isinstance(value, dict):
            for key, child in value.items():
                visit(child, f"{key_path}.{key}" if key_path else str(key))
            return
        if isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{key_path}[{index}]")
            return
        if not isinstance(value, str):
            return

        field = key_path.rsplit(".", 1)[-1]
        if field not in required_input_fields and not field.endswith(("_path", "_dir", "_root", "_json")):
            return

        detail = {"field": key_path, **describe_path(value, repo_root=repo_root)}
        report["paths"].append(detail)
        if detail["windows_absolute_input"]:
            report["absolute_windows_paths"].append(detail)
            report["warnings"].append(f"{key_path}: absolute Windows path is machine-specific: {value}")
        if field in required_input_fields and not detail["exists"]:
            report["missing_paths"].append(detail)
            reason = (
                "stale absolute local media path does not exist"
                if detail["windows_absolute_input"]
                else "configured input path does not exist"
            )
            report["problems"].append(
                f"{key_path}: {reason}; path={detail['path']}; resolved_path={detail['resolved_path']}"
            )

    visit(data)
    if report["problems"]:
        report["status"] = "FAILED"
    return report


def validate_config_file(path, repo_root=REPO_ROOT, required_input_fields=None):
    config_path = resolve_runtime_path(path, repo_root=repo_root)
    data = json.loads(config_path.read_text(encoding="utf-8-sig"))
    report = validate_path_config(data, repo_root=repo_root, required_input_fields=required_input_fields)
    report["config_path"] = serialize_path(config_path, repo_root=repo_root)
    report["config_resolved_path"] = str(config_path.resolve())
    return report


def main():
    parser = argparse.ArgumentParser(description="Validate portable paths in a JSON config.")
    parser.add_argument("config")
    args = parser.parse_args()
    report = validate_config_file(args.config)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
