import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from audio_analyze import ltx_ffmpeg_assembler as assembler


def write_manifest(path, clips):
    path.write_text(json.dumps({"status": "planned", "clips": clips}), encoding="utf-8")


def clip_row(index, mp4_path):
    return {
        "clip_index": index,
        "stitch_order": index,
        "expected_mp4": str(mp4_path) if mp4_path is not None else None,
    }


def test_complete_manifest_dry_run_passes(tmp_path, monkeypatch):
    monkeypatch.setattr(assembler, "require_ffmpeg", lambda: "ffmpeg")

    clip_1 = tmp_path / "scene_01.mp4"
    clip_2 = tmp_path / "scene_02.mp4"
    clip_1.write_bytes(b"fake mp4 1")
    clip_2.write_bytes(b"fake mp4 2")
    manifest = tmp_path / "stitching_manifest.json"
    write_manifest(manifest, [clip_row(1, clip_1), clip_row(2, clip_2)])

    report = assembler.assemble_from_manifest(
        stitching_manifest=manifest,
        output_mp4=tmp_path / "final.mp4",
        dry_run=True,
    )

    assert report["status"] == "dry_run"
    assert report["clip_count"] == 2
    assert report["expected_clip_count"] == 2
    assert report["missing"] == []
    assert report["allow_partial"] is False


def test_manifest_missing_clip_fails_by_default(tmp_path, monkeypatch):
    def fail_if_ffmpeg_is_needed():
        raise AssertionError("missing manifest clips should stop before ffmpeg is required")

    monkeypatch.setattr(assembler, "require_ffmpeg", fail_if_ffmpeg_is_needed)

    clip_1 = tmp_path / "scene_01.mp4"
    missing_clip = tmp_path / "scene_02.mp4"
    clip_1.write_bytes(b"fake mp4 1")
    manifest = tmp_path / "stitching_manifest.json"
    write_manifest(manifest, [clip_row(1, clip_1), clip_row(2, missing_clip)])

    report = assembler.assemble_from_manifest(
        stitching_manifest=manifest,
        output_mp4=tmp_path / "final.mp4",
        dry_run=True,
    )

    assert report["status"] == "failed_missing_clips"
    assert report["clip_count"] == 1
    assert report["expected_clip_count"] == 2
    assert report["missing"][0]["clip_index"] == 2
    assert report["missing"][0]["expected_mp4"] == str(missing_clip)
    assert report["missing"][0]["path"] == str(missing_clip)
    assert report["allow_partial"] is False


def test_allow_partial_explicitly_allows_partial_dry_run(tmp_path, monkeypatch):
    monkeypatch.setattr(assembler, "require_ffmpeg", lambda: "ffmpeg")

    clip_1 = tmp_path / "scene_01.mp4"
    missing_clip = tmp_path / "scene_02.mp4"
    clip_1.write_bytes(b"fake mp4 1")
    manifest = tmp_path / "stitching_manifest.json"
    write_manifest(manifest, [clip_row(1, clip_1), clip_row(2, missing_clip)])

    report = assembler.assemble_from_manifest(
        stitching_manifest=manifest,
        output_mp4=tmp_path / "final.mp4",
        dry_run=True,
        allow_partial=True,
    )

    assert report["status"] == "dry_run"
    assert report["clip_count"] == 1
    assert report["expected_clip_count"] == 2
    assert report["missing"][0]["clip_index"] == 2
    assert report["allow_partial"] is True


def test_cli_missing_clip_returns_nonzero(tmp_path, monkeypatch):
    clip_1 = tmp_path / "scene_01.mp4"
    missing_clip = tmp_path / "scene_02.mp4"
    clip_1.write_bytes(b"fake mp4 1")
    manifest = tmp_path / "stitching_manifest.json"
    report_json = tmp_path / "assembly_report.json"
    write_manifest(manifest, [clip_row(1, clip_1), clip_row(2, missing_clip)])

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ltx_ffmpeg_assembler",
            "--stitching-manifest",
            str(manifest),
            "--output",
            str(tmp_path / "final.mp4"),
            "--report-json",
            str(report_json),
            "--dry-run",
        ],
    )

    exit_code = assembler.main()
    report = json.loads(report_json.read_text(encoding="utf-8"))

    assert exit_code == 1
    assert report["status"] == "failed_missing_clips"
    assert report["missing"][0]["clip_index"] == 2
    assert report["missing"][0]["expected_mp4"] == str(missing_clip)
