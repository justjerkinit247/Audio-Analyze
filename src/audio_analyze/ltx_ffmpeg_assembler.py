from pathlib import Path
import argparse
import json
import shutil
import subprocess


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


def collect_clip_paths(stitching_manifest):
    manifest = read_json(stitching_manifest)
    clips = []
    missing = []
    for item in sorted(manifest.get("clips", []), key=lambda x: int(x.get("stitch_order", x.get("clip_index", 9999)))):
        mp4 = item.get("expected_mp4")
        if not mp4:
            missing.append({"clip_index": item.get("clip_index"), "reason": "missing expected_mp4 in stitching manifest"})
            continue
        path = Path(mp4)
        if not path.exists():
            missing.append({"clip_index": item.get("clip_index"), "path": str(path), "reason": "file not found"})
            continue
        clips.append({"clip_index": item.get("clip_index"), "path": path})
    return clips, missing


def write_concat_list(clips, output_path):
    lines = []
    for clip in clips:
        safe_path = normalize_path(clip["path"]).replace("'", "'\\''")
        lines.append(f"file '{safe_path}'")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def assemble_from_manifest(stitching_manifest, output_mp4, audio_path=None, report_json=None, dry_run=False):
    ffmpeg = require_ffmpeg()
    output_mp4 = Path(output_mp4)
    output_mp4.parent.mkdir(parents=True, exist_ok=True)

    clips, missing = collect_clip_paths(stitching_manifest)
    concat_list = output_mp4.parent / "ffmpeg_concat_list.txt"
    write_concat_list(clips, concat_list)

    if not clips:
        report = {
            "status": "failed_no_clips",
            "stitching_manifest": str(Path(stitching_manifest).resolve()),
            "missing": missing,
        }
        if report_json:
            write_json(report_json, report)
        return report

    temp_video = output_mp4.with_suffix(".video_only.mp4")
    concat_cmd = [
        ffmpeg,
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        str(temp_video),
    ]

    final_cmd = concat_cmd
    if audio_path:
        final_cmd = [
            ffmpeg,
            "-y",
            "-i", str(temp_video),
            "-i", str(Path(audio_path)),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",
            str(output_mp4),
        ]
    else:
        final_cmd = [
            ffmpeg,
            "-y",
            "-i", str(temp_video),
            "-c", "copy",
            str(output_mp4),
        ]

    report = {
        "status": "dry_run" if dry_run else "running",
        "ffmpeg": ffmpeg,
        "stitching_manifest": str(Path(stitching_manifest).resolve()),
        "clip_count": len(clips),
        "clips": [{"clip_index": c["clip_index"], "path": str(c["path"].resolve())} for c in clips],
        "missing": missing,
        "concat_list": str(concat_list.resolve()),
        "temp_video": str(temp_video.resolve()),
        "output_mp4": str(output_mp4.resolve()),
        "audio_path": str(Path(audio_path).resolve()) if audio_path else None,
        "commands": {
            "concat": concat_cmd,
            "mux_audio": final_cmd,
        },
    }

    if dry_run:
        if report_json:
            write_json(report_json, report)
        return report

    concat_result = subprocess.run(concat_cmd, capture_output=True, text=True)
    report["concat_returncode"] = concat_result.returncode
    report["concat_stdout"] = concat_result.stdout[-4000:]
    report["concat_stderr"] = concat_result.stderr[-4000:]
    if concat_result.returncode != 0:
        report["status"] = "failed_concat"
        if report_json:
            write_json(report_json, report)
        return report

    final_result = subprocess.run(final_cmd, capture_output=True, text=True)
    report["final_returncode"] = final_result.returncode
    report["final_stdout"] = final_result.stdout[-4000:]
    report["final_stderr"] = final_result.stderr[-4000:]
    report["status"] = "complete" if final_result.returncode == 0 else "failed_final_mux"

    if report_json:
        write_json(report_json, report)
    return report


def main():
    parser = argparse.ArgumentParser(description="Assemble LTX scene clips with FFmpeg from stitching_manifest.json")
    parser.add_argument("--stitching-manifest", default="outputs/ltx_video_run/orchestration/stitching_manifest.json")
    parser.add_argument("--output", default="outputs/ltx_video_run/assembled/ltx_assembled_reel.mp4")
    parser.add_argument("--audio", default=None)
    parser.add_argument("--report-json", default="outputs/ltx_video_run/assembled/ffmpeg_assembly_report.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    report = assemble_from_manifest(
        stitching_manifest=args.stitching_manifest,
        output_mp4=args.output,
        audio_path=args.audio,
        report_json=args.report_json,
        dry_run=args.dry_run,
    )

    print(f"FFmpeg assembly status: {report['status']}")
    print(f"Clip count: {report.get('clip_count')}")
    print(f"Output: {report.get('output_mp4')}")
    if report.get("missing"):
        for item in report["missing"]:
            print(f"MISSING: {item}")
    print(f"Report: {Path(args.report_json).resolve()}")


if __name__ == "__main__":
    main()
