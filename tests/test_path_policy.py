import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from audio_analyze import ltx_holy_cheeks_pipeline as ltx
from audio_analyze.path_policy import (
    describe_path,
    is_windows_absolute_path,
    resolve_runtime_path,
    serialize_path,
    validate_config_file,
    validate_path_config,
)


def test_repo_relative_path_serialization(tmp_path):
    repo_root = tmp_path / "repo"
    media = repo_root / "inputs" / "audio" / "song.mp3"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"audio")

    assert serialize_path(media, repo_root=repo_root) == "inputs/audio/song.mp3"
    detail = describe_path(media, repo_root=repo_root)
    assert detail["path"] == "inputs/audio/song.mp3"
    assert detail["resolved_path"] == str(media.resolve())
    assert detail["inside_repo"] is True


def test_absolute_windows_path_detection():
    assert is_windows_absolute_path(r"C:\Users\Example\song.mp3") is True
    assert is_windows_absolute_path(r"\\server\share\seed.png") is True
    assert is_windows_absolute_path("inputs/audio/song.mp3") is False


def test_missing_absolute_media_path_fails_validation(tmp_path):
    missing = r"Z:\stale-machine\missing\song.mp3"
    report = validate_path_config({"audio_path": missing}, repo_root=tmp_path)

    assert report["status"] == "FAILED"
    assert report["absolute_windows_paths"][0]["field"] == "audio_path"
    assert report["missing_paths"][0]["resolved_path"]
    assert "stale absolute local media path does not exist" in report["problems"][0]


def test_pipeline_validation_rejects_missing_absolute_media_path(tmp_path):
    seed = tmp_path / "scene_01_seed.png"
    seed.write_bytes(b"image")
    plan = {
        "results": [
            {
                "clip_index": 1,
                "source_audio_path": r"Z:\stale-machine\missing\song.mp3",
                "seed_image_used": str(seed),
                "scene": {"duration": 8.0},
                "resolution": "1080x1920",
                "prompt_text": "Valid prompt",
            }
        ]
    }

    problems = ltx.validate_plan(plan, model="ltx-2-3-pro", guidance_scale=9.0)

    assert any("source_audio_path" in problem for problem in problems)
    assert any("stale absolute local media path is missing" in problem for problem in problems)


def test_valid_repo_relative_path_resolves_for_runtime(tmp_path):
    repo_root = tmp_path / "repo"
    media = repo_root / "inputs" / "images" / "seed.png"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"image")

    resolved = resolve_runtime_path("inputs/images/seed.png", repo_root=repo_root)
    report = validate_path_config(
        {"seed_image_path": "inputs/images/seed.png"},
        repo_root=repo_root,
    )

    assert resolved.resolve() == media.resolve()
    assert report["status"] == "PASSED"
    assert report["paths"][0]["path"] == "inputs/images/seed.png"
    assert report["paths"][0]["resolved_path"] == str(media.resolve())


def test_preflight_report_includes_portable_and_resolved_path_diagnostics(tmp_path):
    audio = tmp_path / "song.mp3"
    seed = tmp_path / "scene_01_seed.png"
    audio.write_bytes(b"audio")
    seed.write_bytes(b"image")
    plan_path = tmp_path / "plan.json"
    report_path = tmp_path / "preflight.json"
    plan = {
        "seed_mapping": {"seed_dir": str(tmp_path)},
        "results": [
            {
                "clip_index": 1,
                "file_stem": "song",
                "source_audio_path": str(audio),
                "seed_image_used": str(seed),
                "seed_assignment": {
                    "method": "scene_label",
                    "seed_file": seed.name,
                    "seed_image_path": str(seed),
                    "scene_label_expected": "scene_01",
                },
                "scene": {"duration": 8.0},
                "resolution": "1080x1920",
                "prompt_text": "Valid prompt",
            }
        ],
    }
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    report = ltx.run_preflight(plan_path, report_path)

    assert report["status"] == "PASSED"
    assert report["plan_json"]
    assert report["plan_json_resolved"] == str(plan_path.resolve())
    assert report["path_policy"]["status"] == "PASSED"
    assert any(row["field"] == "results[0].source_audio_path" for row in report["path_policy"]["paths"])


def test_committed_prompt_configs_do_not_contain_absolute_windows_paths():
    configs = sorted((ROOT / "inputs" / "prompts").glob("*.json"))

    assert configs
    for config_path in configs:
        report = validate_config_file(config_path)
        assert report["absolute_windows_paths"] == []

    club_config = json.loads(configs[0].read_text(encoding="utf-8-sig"))
    assert club_config["path_policy"] == "repo_relative_template"
    assert club_config["local_media_required"] is True
