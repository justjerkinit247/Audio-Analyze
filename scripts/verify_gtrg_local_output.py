#!/usr/bin/env python3
"""Verify a local GTRG canary MP4 with ffprobe; never submits a render job."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _integer(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _probe_one(
    video_path: Path,
    ffprobe: str,
    *,
    expected_width: int,
    expected_height: int,
    expected_frames: int,
    require_audio: bool,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": str(video_path),
        "status": "VERIFICATION_FAILED",
        "expected": {
            "width": expected_width,
            "height": expected_height,
            "video_frames": expected_frames,
            "audio_stream_required": require_audio,
        },
        "checks": {},
    }
    if not video_path.is_file():
        result["error"] = "Output file does not exist"
        return result

    command = [
        ffprobe, "-v", "error", "-count_frames", "-show_streams",
        "-show_format", "-of", "json", str(video_path),
    ]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, check=False, timeout=90,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        result["error"] = f"ffprobe could not inspect the file: {type(exc).__name__}"
        return result
    if completed.returncode != 0:
        result["error"] = "ffprobe rejected the output file"
        return result
    try:
        metadata = json.loads(completed.stdout)
    except (TypeError, json.JSONDecodeError):
        result["error"] = "ffprobe returned invalid JSON"
        return result
    if not isinstance(metadata, dict):
        result["error"] = "ffprobe JSON must be an object"
        return result

    streams = metadata.get("streams")
    if not isinstance(streams, list):
        streams = []
    video_streams = [s for s in streams if isinstance(s, dict) and s.get("codec_type") == "video"]
    audio_streams = [s for s in streams if isinstance(s, dict) and s.get("codec_type") == "audio"]
    video = video_streams[0] if video_streams else {}
    actual_width = _integer(video.get("width"))
    actual_height = _integer(video.get("height"))
    actual_frames = _integer(video.get("nb_read_frames"))
    if actual_frames is None:
        actual_frames = _integer(video.get("nb_frames"))

    format_data = metadata.get("format")
    if not isinstance(format_data, dict):
        format_data = {}
    result["actual"] = {
        "video_stream_count": len(video_streams),
        "audio_stream_count": len(audio_streams),
        "width": actual_width,
        "height": actual_height,
        "video_frames": actual_frames,
        "video_codec": video.get("codec_name"),
        "audio_codecs": [s.get("codec_name") for s in audio_streams],
        "duration_seconds": format_data.get("duration"),
    }
    result["checks"] = {
        "one_video_stream": len(video_streams) == 1,
        "expected_dimensions": actual_width == expected_width and actual_height == expected_height,
        "expected_frame_count": actual_frames == expected_frames,
        "audio_stream_present": bool(audio_streams) if require_audio else True,
    }
    if all(result["checks"].values()):
        result["status"] = "VERIFIED_STREAMS_AND_FRAME_COUNT"
    else:
        result["error"] = "One or more media checks failed"
    return result


def verify_report(
    report_path: Path,
    *,
    ffprobe: str | None = None,
    output_path: Path | None = None,
    require_audio: bool = True,
) -> dict[str, Any]:
    report_path = report_path.resolve()
    try:
        source = json.loads(report_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read canary report: {type(exc).__name__}") from exc
    if not isinstance(source, dict):
        raise ValueError("Canary report must contain a JSON object")
    if source.get("mode") != "LOCAL_RENDER":
        raise ValueError("Canary report is not from an explicitly run local render")

    settings = source.get("tiny_settings")
    if not isinstance(settings, dict):
        raise ValueError("Canary report is missing tiny_settings")
    if settings.get("preview_uses_repeated_motion") is not False:
        raise ValueError("Report is not a genuine-frame render; repeated preview motion cannot be verified as a finished scene")
    resolution = settings.get("resolution")
    try:
        width_text, height_text = str(resolution).lower().split("x", 1)
        expected_width, expected_height = int(width_text), int(height_text)
    except (ValueError, TypeError):
        raise ValueError("Canary report has an invalid resolution") from None
    expected_frames = _integer(settings.get("expected_finish_frames"))
    if expected_frames is None or expected_frames < 1:
        raise ValueError("Canary report has no valid expected output frame count")
    if (
        _integer(settings.get("video_frames")) != 57
        or expected_frames != 51
        or _integer(settings.get("genuine_frames_for_output")) != 51
    ):
        raise ValueError("Verifier accepts only the documented 57-generated-frame / 51-output-frame canary")
    result_data = source.get("result")
    if not isinstance(result_data, dict) or result_data.get("status") != "PLAYABLE_FILE_NOT_YET_VERIFIED":
        raise ValueError("Canary report does not record a completed video file awaiting verification")
    videos = result_data.get("output_videos") if isinstance(result_data, dict) else None
    if not isinstance(videos, list) or not videos or not all(isinstance(p, str) for p in videos):
        raise ValueError("Canary report has no output_videos paths to verify")

    probe_path = ffprobe or shutil.which("ffprobe")
    if not probe_path:
        raise ValueError("ffprobe was not found; install it or pass --ffprobe")

    files = [
        _probe_one(
            Path(path), probe_path,
            expected_width=expected_width,
            expected_height=expected_height,
            expected_frames=expected_frames,
            require_audio=require_audio,
        )
        for path in videos
    ]
    all_verified = all(item["status"] == "VERIFIED_STREAMS_AND_FRAME_COUNT" for item in files)
    output = {
        "schema": "gtrg_local_output_verification_v1",
        "source_report": str(report_path),
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "verification_scope": [
            "file is probeable",
            "exactly one video stream",
            "expected dimensions",
            "expected decoded frame count",
            "audio stream present" if require_audio else "audio stream not required",
        ],
        "status": "VERIFIED_STREAMS_AND_FRAME_COUNT" if all_verified else "VERIFICATION_FAILED",
        "files": files,
        "limitations": [
            "This does not verify subjective playback quality or confirm that the audio is the intended song or is synchronized.",
        ],
    }
    target = output_path or report_path.with_name(report_path.stem + ".verification.json")
    target = target.resolve()
    if target == report_path:
        raise ValueError("Verification output must not overwrite the source canary report")
    target.parent.mkdir(parents=True, exist_ok=True)
    output["verification_report"] = str(target)
    target.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path, help="Local gtrg_tiny_ltx_local.py JSON report")
    parser.add_argument("--output", type=Path, help="Verification JSON path; defaults beside input report")
    parser.add_argument("--ffprobe", help="ffprobe executable path; defaults to PATH lookup")
    parser.add_argument("--allow-no-audio", action="store_true", help="Do not require an audio stream")
    args = parser.parse_args(argv)
    try:
        result = verify_report(
            args.report, ffprobe=args.ffprobe, output_path=args.output,
            require_audio=not args.allow_no_audio,
        )
    except ValueError as exc:
        print(f"Verification stopped: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "VERIFIED_STREAMS_AND_FRAME_COUNT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
