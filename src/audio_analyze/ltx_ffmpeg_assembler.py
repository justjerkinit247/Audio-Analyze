from pathlib import Path
import argparse
import json
import shutil
import subprocess

VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v"}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def require_ffmpeg():
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg was not found on PATH. Install FFmpeg or add it to PATH before assembly.")
    return ffmpeg


def normalize_path(path):
    return str(Path(path).resolve()).replace("\\", "/")


def _sorted_manifest_clips(manifest):
    return sorted(manifest.get("clips", []), key=lambda x: int(x.get("stitch_order", x.get("clip_index", 9999))))


def _missing_clip_item(item, reason, path=None):
    scene = item.get("scene", {}) if isinstance(item.get("scene"), dict) else {}
    missing = {
        "clip_index": item.get("clip_index"),
        "scene_index": scene.get("scene_index"),
        "expected_mp4": item.get("expected_mp4"),
        "reason": reason,
    }
    if path is not None:
        missing["path"] = str(path)
    return missing


def collect_clip_paths_from_manifest(manifest):
    clips = []
    missing = []
    for item in _sorted_manifest_clips(manifest):
        mp4 = item.get("expected_mp4")
        if not mp4:
            missing.append(_missing_clip_item(item, "missing expected_mp4 in stitching manifest"))
            continue
        path = Path(mp4)
        if not path.exists():
            missing.append(_missing_clip_item(item, "file not found", path=path))
            continue
        if path.stat().st_size <= 0:
            missing.append(_missing_clip_item(item, "file is empty", path=path))
            continue
        clips.append({"clip_index": item.get("clip_index"), "path": path})
    return clips, missing


def collect_clip_paths(stitching_manifest):
    manifest = read_json(stitching_manifest)
    return collect_clip_paths_from_manifest(manifest)


def collect_clip_paths_from_folder(input_folder):
    input_folder = Path(input_folder)
    if not input_folder.exists():
        raise FileNotFoundError(f"Input folder not found: {input_folder}")
    clips = []
    for path in sorted(input_folder.rglob("*"), key=lambda p: str(p).lower()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        parts_lower = {part.lower() for part in path.parts}
        if "assembled" in parts_lower:
            continue
        if "final_music_video" in path.name.lower():
            continue
        if path.stat().st_size <= 0:
            continue
        clips.append({"clip_index": len(clips) + 1, "path": path})
    return clips


def write_concat_list(clips, output_path):
    lines = []
    for clip in clips:
        safe_path = normalize_path(clip["path"]).replace("'", "'\\''")
        lines.append(f"file '{safe_path}'")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run_ffmpeg(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    return {
        "returncode": result.returncode,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
    }


def assemble_clips(clips, output_mp4, audio_path=None, report_json=None, dry_run=False, audio_start_seconds=0.0, source_label=None):
    ffmpeg = require_ffmpeg()
    output_mp4 = Path(output_mp4)
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    concat_list = output_mp4.parent / "ffmpeg_concat_list.txt"
    write_concat_list(clips, concat_list)

    if not clips:
        report = {"status": "failed_no_clips", "source": source_label, "clip_count": 0}
        if report_json:
            write_json(report_json, report)
        return report

    temp_video = output_mp4.with_suffix(".video_only.mp4")
    concat_cmd = [
        ffmpeg, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        str(temp_video),
    ]

    final_cmd = [ffmpeg, "-y", "-i", str(temp_video), "-c", "copy", str(output_mp4)]
    if audio_path:
        final_cmd = [ffmpeg, "-y", "-i", str(temp_video)]
        audio_start_seconds = max(0.0, float(audio_start_seconds or 0.0))
        if audio_start_seconds > 0:
            final_cmd.extend(["-ss", str(audio_start_seconds)])
        final_cmd.extend([
            "-i", str(Path(audio_path)),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            str(output_mp4),
        ])

    report = {
        "status": "dry_run" if dry_run else "running",
        "source": source_label,
        "ffmpeg": ffmpeg,
        "clip_count": len(clips),
        "clips": [{"clip_index": c["clip_index"], "path": str(c["path"].resolve())} for c in clips],
        "concat_list": str(concat_list.resolve()),
        "temp_video": str(temp_video.resolve()),
        "output_mp4": str(output_mp4.resolve()),
        "audio_path": str(Path(audio_path).resolve()) if audio_path else None,
        "audio_start_seconds": float(audio_start_seconds or 0.0),
        "clip_audio_rule": "ignored during audio mux; final audio comes from --audio when provided",
        "commands": {"concat": concat_cmd, "mux_audio": final_cmd},
    }

    if dry_run:
        if report_json:
            write_json(report_json, report)
        return report

    concat_result = _run_ffmpeg(concat_cmd)
    report["concat_returncode"] = concat_result["returncode"]
    report["concat_stdout"] = concat_result["stdout"]
    report["concat_stderr"] = concat_result["stderr"]
    if concat_result["returncode"] != 0:
        report["status"] = "failed_concat"
        if report_json:
            write_json(report_json, report)
        return report

    final_result = _run_ffmpeg(final_cmd)
    report["final_returncode"] = final_result["returncode"]
    report["final_stdout"] = final_result["stdout"]
    report["final_stderr"] = final_result["stderr"]
    report["status"] = "complete" if final_result["returncode"] == 0 else "failed_final_mux"

    if report_json:
        write_json(report_json, report)
    return report


def _missing_clip_report(stitching_manifest, output_mp4, audio_path, audio_start_seconds, clips, missing, expected_clip_count, allow_partial):
    return {
        "status": "failed_missing_clips",
        "source": str(Path(stitching_manifest).resolve()),
        "stitching_manifest": str(Path(stitching_manifest).resolve()),
        "clip_count": len(clips),
        "expected_clip_count": expected_clip_count,
        "clips": [{"clip_index": c["clip_index"], "path": str(c["path"].resolve())} for c in clips],
        "missing": missing,
        "allow_partial": bool(allow_partial),
        "output_mp4": str(Path(output_mp4).resolve()),
        "audio_path": str(Path(audio_path).resolve()) if audio_path else None,
        "audio_start_seconds": float(audio_start_seconds or 0.0),
        "error": "Missing planned clips; refusing partial assembly. Pass allow_partial=True or --allow-partial to assemble available clips intentionally.",
    }


def assemble_from_manifest(stitching_manifest, output_mp4, audio_path=None, report_json=None, dry_run=False, audio_start_seconds=0.0, allow_partial=False):
    manifest = read_json(stitching_manifest)
    expected_clip_count = len(_sorted_manifest_clips(manifest))
    clips, missing = collect_clip_paths_from_manifest(manifest)

    if not allow_partial and (missing or len(clips) < expected_clip_count):
        report = _missing_clip_report(
            stitching_manifest=stitching_manifest,
            output_mp4=output_mp4,
            audio_path=audio_path,
            audio_start_seconds=audio_start_seconds,
            clips=clips,
            missing=missing,
            expected_clip_count=expected_clip_count,
            allow_partial=allow_partial,
        )
        if report_json:
            write_json(report_json, report)
        return report

    report = assemble_clips(
        clips=clips,
        output_mp4=output_mp4,
        audio_path=audio_path,
        report_json=None,
        dry_run=dry_run,
        audio_start_seconds=audio_start_seconds,
        source_label=str(Path(stitching_manifest).resolve()),
    )
    report["stitching_manifest"] = str(Path(stitching_manifest).resolve())
    report["missing"] = missing
    report["expected_clip_count"] = expected_clip_count
    report["allow_partial"] = bool(allow_partial)
    if report_json:
        write_json(report_json, report)
    return report


def assemble_from_folder(input_folder, output_mp4, audio_path=None, report_json=None, dry_run=False, audio_start_seconds=0.0):
    clips = collect_clip_paths_from_folder(input_folder)
    report = assemble_clips(
        clips=clips,
        output_mp4=output_mp4,
        audio_path=audio_path,
        report_json=None,
        dry_run=dry_run,
        audio_start_seconds=audio_start_seconds,
        source_label=str(Path(input_folder).resolve()),
    )
    report["input_folder"] = str(Path(input_folder).resolve())
    if report_json:
        write_json(report_json, report)
    return report


def main():
    parser = argparse.ArgumentParser(description="Assemble LTX scene clips with FFmpeg from stitching_manifest.json or a run folder")
    parser.add_argument("--stitching-manifest", default=None)
    parser.add_argument("--input-folder", default=None, help="Folder to scan recursively for MP4/MOV clips when no manifest is available.")
    parser.add_argument("--output", default="outputs/ltx_video_run/assembled/ltx_assembled_reel.mp4")
    parser.add_argument("--audio", default=None)
    parser.add_argument("--audio-start-seconds", type=float, default=0.0, help="Start the supplied audio at this offset, e.g. 85 for 1:25.")
    parser.add_argument("--report-json", default="outputs/ltx_video_run/assembled/ffmpeg_assembly_report.json")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-partial", action="store_true", help="Assemble available clips even when planned clips are missing.")
    args = parser.parse_args()

    if args.input_folder:
        report = assemble_from_folder(
            input_folder=args.input_folder,
            output_mp4=args.output,
            audio_path=args.audio,
            report_json=args.report_json,
            dry_run=args.dry_run,
            audio_start_seconds=args.audio_start_seconds,
        )
    else:
        manifest = args.stitching_manifest or "outputs/ltx_video_run/orchestration/stitching_manifest.json"
        report = assemble_from_manifest(
            stitching_manifest=manifest,
            output_mp4=args.output,
            audio_path=args.audio,
            report_json=args.report_json,
            dry_run=args.dry_run,
            audio_start_seconds=args.audio_start_seconds,
            allow_partial=args.allow_partial,
        )

    print(f"FFmpeg assembly status: {report['status']}")
    print(f"Clip count: {report.get('clip_count')}")
    print(f"Output: {report.get('output_mp4')}")
    print(f"Audio start seconds: {report.get('audio_start_seconds')}")
    if report.get("missing"):
        for item in report["missing"]:
            print(f"MISSING: {item}")
    print(f"Report: {Path(args.report_json).resolve()}")
    return 0 if str(report.get("status", "")).lower() in {"complete", "dry_run"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
