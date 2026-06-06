from __future__ import annotations

from pathlib import Path
from typing import Any
import argparse
import json
import math
import re
import shutil
import statistics
import subprocess

try:
    import cv2
except Exception:
    cv2 = None

try:
    from .path_policy import resolve_runtime_path, serialize_path
    from .clip_plan_export import scene_specific_prompt_block
except ImportError:
    from path_policy import resolve_runtime_path, serialize_path
    from clip_plan_export import scene_specific_prompt_block


DEFAULT_MAX_SHIFT_SECONDS = 0.35
DEFAULT_MOTION_THRESHOLD_PERCENTILE = 85.0
DEFAULT_BAD_SCENE_THRESHOLD = 0.10
DEFAULT_MIN_MOTION_EVENTS = 2
GOOD_OFFSET_SECONDS = 0.10
NEEDS_CALIBRATION_SECONDS = 0.25


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def as_float(value: Any, default: float | None = None) -> float | None:
    try:
        parsed = float(value)
    except Exception:
        return default
    if not math.isfinite(parsed):
        return default
    return parsed


def round_seconds(value: Any) -> float | None:
    parsed = as_float(value)
    if parsed is None:
        return None
    return round(parsed, 3)


def path_for_report(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return serialize_path(path)
    except Exception:
        return str(path)


def resolve_artifact_path(value: Any, run_dir: Path) -> Path | None:
    if value is None or str(value).strip() == "":
        return None
    raw = str(value)
    candidates: list[Path] = []
    try:
        candidates.append(resolve_runtime_path(raw))
    except Exception:
        pass
    raw_path = Path(raw)
    if not raw_path.is_absolute():
        candidates.append(run_dir / raw_path)
    candidates.append(raw_path)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0] if candidates else None


def clip_index_from_name(path: Path) -> int | None:
    match = re.search(r"scene[_-](\d+)", path.name, flags=re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))


def load_clip_plans(run_dir: Path) -> dict[int, dict[str, Any]]:
    plans: dict[int, dict[str, Any]] = {}
    clip_plan_dir = run_dir / "clip_plans"
    if not clip_plan_dir.exists():
        return plans
    for path in sorted(clip_plan_dir.glob("scene_*_clip_plan.json")):
        try:
            plan = read_json(path)
        except Exception as exc:
            idx = clip_index_from_name(path)
            if idx is None:
                continue
            plans[idx] = {
                "clip_index": idx,
                "clip_plan_path": path,
                "clip_plan_read_error": str(exc),
            }
            continue
        idx = as_float(plan.get("clip_index"))
        if idx is None:
            idx = clip_index_from_name(path)
        if idx is None:
            continue
        plan["clip_plan_path"] = path
        plans[int(idx)] = plan
    return plans


def load_submit_clip_paths(run_dir: Path) -> dict[int, dict[str, Any]]:
    summary_path = run_dir / "submissions" / "ltx_submit_all_summary.json"
    if not summary_path.exists():
        return {}
    try:
        summary = read_json(summary_path)
    except Exception:
        return {}
    by_clip: dict[int, dict[str, Any]] = {}
    for item in summary.get("results", []):
        idx = as_float(item.get("clip_index"))
        if idx is None:
            continue
        clip_path = resolve_artifact_path(
            item.get("downloaded_mp4") or item.get("downloaded_mp4_resolved_path"),
            run_dir,
        )
        by_clip[int(idx)] = {
            "clip_path": clip_path,
            "source": "submit_summary.downloaded_mp4",
            "raw_path": item.get("downloaded_mp4") or item.get("downloaded_mp4_resolved_path"),
            "result": item,
        }
    return by_clip


def load_manifest_clip_paths(run_dir: Path) -> dict[int, dict[str, Any]]:
    manifest_path = run_dir / "orchestration" / "stitching_manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        manifest = read_json(manifest_path)
    except Exception:
        return {}
    by_clip: dict[int, dict[str, Any]] = {}
    for item in manifest.get("clips", []):
        idx = as_float(item.get("clip_index"))
        if idx is None:
            continue
        clip_path = resolve_artifact_path(item.get("expected_mp4"), run_dir)
        by_clip[int(idx)] = {
            "clip_path": clip_path,
            "source": "stitching_manifest.expected_mp4",
            "raw_path": item.get("expected_mp4"),
            "manifest_clip": item,
        }
    return by_clip


def locate_clip(clip_index: int, submit_paths: dict[int, dict[str, Any]], manifest_paths: dict[int, dict[str, Any]]) -> dict[str, Any]:
    info = submit_paths.get(clip_index) or manifest_paths.get(clip_index)
    if info is None:
        return {
            "clip_path": None,
            "clip_path_source": None,
            "clip_path_missing_reason": "No downloaded_mp4 in submit summary and no expected_mp4 in stitching manifest.",
        }
    clip_path = info.get("clip_path")
    missing_reason = None
    if clip_path is None:
        missing_reason = "Clip path was empty."
    elif not clip_path.exists():
        missing_reason = "Clip file does not exist."
    elif clip_path.stat().st_size <= 0:
        missing_reason = "Clip file is empty."
    return {
        "clip_path": clip_path,
        "clip_path_source": info.get("source"),
        "clip_path_missing_reason": missing_reason,
        "raw_clip_path": info.get("raw_path"),
    }


def cue_times_from_plan(plan: dict[str, Any]) -> list[float]:
    sync_targets = plan.get("sync_targets", {}) if isinstance(plan.get("sync_targets"), dict) else {}
    raw = sync_targets.get("clip_local_seconds") or []
    times: list[float] = []
    for value in raw:
        parsed = as_float(value)
        if parsed is not None:
            times.append(round(parsed, 3))
    return times


def percentile(values: list[float], rank: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * max(0.0, min(100.0, rank)) / 100.0
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def resize_gray(frame: Any, max_width: int = 320) -> Any:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape[:2]
    if width > max_width:
        scale = max_width / float(width)
        gray = cv2.resize(gray, (max_width, max(1, int(height * scale))), interpolation=cv2.INTER_AREA)
    return gray


def analyze_motion(video_path: Path, threshold_percentile: float) -> dict[str, Any]:
    if cv2 is None:
        return analyze_motion_with_ffmpeg(video_path, threshold_percentile)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return {
            "status": "analysis_failed",
            "notes": [f"OpenCV could not open clip: {video_path}"],
            "motion_samples": [],
            "motion_events": [],
            "fps": None,
            "duration_seconds": None,
        }

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0) or 24.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = float(frame_count / fps) if fps and frame_count else None
    sample_stride = 2 if frame_count > 720 or fps > 32 else 1
    notes: list[str] = []
    method = "optical_flow"
    samples: list[dict[str, float]] = []
    prev_gray = None
    frame_index = -1
    flow_failed = False

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame_index += 1
        if frame_index % sample_stride != 0:
            continue
        gray = resize_gray(frame)
        if prev_gray is not None:
            time_seconds = frame_index / fps
            energy = None
            if not flow_failed and hasattr(cv2, "calcOpticalFlowFarneback"):
                try:
                    flow = cv2.calcOpticalFlowFarneback(prev_gray, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
                    mag, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
                    energy = float(mag.mean())
                except Exception as exc:
                    flow_failed = True
                    method = "frame_difference"
                    notes.append(f"Optical flow failed; using grayscale frame difference. Reason: {exc}")
            if energy is None:
                diff = cv2.absdiff(prev_gray, gray)
                energy = float(diff.mean())
                method = "frame_difference"
            samples.append({"time_seconds": round(time_seconds, 4), "motion_energy": round(energy, 6)})
        prev_gray = gray
    cap.release()

    if not samples:
        return {
            "status": "analysis_failed",
            "notes": notes + ["No decodable motion samples were found."],
            "motion_samples": [],
            "motion_events": [],
            "fps": round(fps, 3),
            "duration_seconds": round(duration, 3) if duration is not None else None,
        }

    events = detect_twerk_hit_events(samples, threshold_percentile, fps)
    return {
        "status": "analyzed",
        "notes": notes,
        "motion_method": method,
        "sample_stride_frames": sample_stride,
        "motion_threshold_percentile": threshold_percentile,
        "motion_samples": samples,
        "motion_events": events,
        "fps": round(fps, 3),
        "duration_seconds": round(duration, 3) if duration is not None else None,
    }


def parse_rate(value: Any, fallback: float) -> float:
    text = str(value or "")
    if "/" in text:
        left, right = text.split("/", 1)
        numerator = as_float(left)
        denominator = as_float(right)
        if numerator is not None and denominator:
            return numerator / denominator
    parsed = as_float(text)
    return parsed if parsed is not None and parsed > 0 else fallback


def ffprobe_video(path: Path) -> dict[str, Any]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe executable was not found on PATH.")
    command = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,r_frame_rate,nb_frames,duration",
        "-of",
        "json",
        str(path),
    ]
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    data = json.loads(completed.stdout or "{}")
    streams = data.get("streams") or []
    if not streams:
        raise RuntimeError(f"ffprobe found no video stream: {path}")
    return streams[0]


def frame_diff_energy(previous: bytes, current: bytes) -> float:
    if not previous or not current or len(previous) != len(current):
        return 0.0
    total = 0
    for before, after in zip(previous, current):
        total += abs(after - before)
    return total / float(len(current))


def analyze_motion_with_ffmpeg(video_path: Path, threshold_percentile: float) -> dict[str, Any]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return {
            "status": "analysis_failed",
            "notes": ["OpenCV is unavailable and ffmpeg executable was not found on PATH."],
            "motion_samples": [],
            "motion_events": [],
            "fps": None,
            "duration_seconds": None,
        }
    try:
        stream = ffprobe_video(video_path)
        source_width = int(stream.get("width") or 0)
        source_height = int(stream.get("height") or 0)
        source_fps = parse_rate(stream.get("r_frame_rate"), fallback=24.0)
        duration = as_float(stream.get("duration"))
        if source_width <= 0 or source_height <= 0:
            raise RuntimeError("ffprobe returned invalid video dimensions.")
        target_width = 160
        target_height = max(2, int(round(source_height * (target_width / float(source_width)))))
        if target_height % 2:
            target_height += 1
        sample_fps = min(12.0, max(1.0, source_fps))
        command = [
            ffmpeg,
            "-v",
            "error",
            "-i",
            str(video_path),
            "-vf",
            f"fps={sample_fps:g},scale={target_width}:{target_height},format=gray",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "-",
        ]
        completed = subprocess.run(command, check=True, capture_output=True)
        frame_size = target_width * target_height
        raw = completed.stdout
        if len(raw) < frame_size * 2:
            raise RuntimeError("ffmpeg decoded fewer than two grayscale frames.")
        samples: list[dict[str, float]] = []
        previous = None
        frame_number = 0
        for offset in range(0, len(raw) - frame_size + 1, frame_size):
            current = raw[offset : offset + frame_size]
            if len(current) != frame_size:
                break
            if previous is not None:
                samples.append(
                    {
                        "time_seconds": round(frame_number / sample_fps, 4),
                        "motion_energy": round(frame_diff_energy(previous, current), 6),
                    }
                )
            previous = current
            frame_number += 1
        events = detect_twerk_hit_events(samples, threshold_percentile, sample_fps)
        return {
            "status": "analyzed",
            "notes": ["OpenCV unavailable; used ffmpeg grayscale frame-difference fallback."],
            "motion_method": "ffmpeg_frame_difference",
            "sample_stride_frames": None,
            "sample_fps": round(sample_fps, 3),
            "motion_threshold_percentile": threshold_percentile,
            "motion_samples": samples,
            "motion_events": events,
            "fps": round(source_fps, 3),
            "duration_seconds": round(duration, 3) if duration is not None else None,
            "decode_size": {"width": target_width, "height": target_height},
        }
    except Exception as exc:
        return {
            "status": "analysis_failed",
            "notes": [f"OpenCV unavailable and ffmpeg fallback failed: {exc}"],
            "motion_samples": [],
            "motion_events": [],
            "fps": None,
            "duration_seconds": None,
        }


def detect_twerk_hit_events(samples: list[dict[str, float]], threshold_percentile: float, fps: float) -> list[dict[str, float]]:
    energies = [float(sample["motion_energy"]) for sample in samples]
    times = [float(sample["time_seconds"]) for sample in samples]
    if len(energies) < 3:
        return []
    threshold = percentile(energies, threshold_percentile)
    min_gap_seconds = max(0.10, 3.0 / max(fps, 1.0))
    events: list[dict[str, float]] = []
    last_hit = -999.0

    for index in range(1, len(energies) - 1):
        energy = energies[index]
        if energy < threshold:
            continue
        if energy < energies[index - 1] or energy < energies[index + 1]:
            continue

        search_end = min(len(energies) - 1, index + max(2, int(max(fps, 1.0) * 0.35)))
        peak_energy = max(energy, 1e-9)
        fall_threshold = max(threshold * 0.60, peak_energy * 0.45)
        hit_index = None
        for candidate in range(index + 1, search_end + 1):
            prev_energy = energies[candidate - 1]
            curr_energy = energies[candidate]
            next_energy = energies[candidate + 1] if candidate + 1 < len(energies) else curr_energy
            local_arrival = curr_energy <= prev_energy and curr_energy <= next_energy
            decelerated = curr_energy <= fall_threshold
            if local_arrival or decelerated:
                hit_index = candidate
                break
        if hit_index is None:
            hit_index = min(search_end, index + 1)

        hit_time = times[hit_index]
        if hit_time - last_hit < min_gap_seconds:
            continue
        last_hit = hit_time
        peak_time = times[index]
        frame_seconds = 1.0 / max(fps, 1.0)
        events.append(
            {
                "prep_load_seconds": round(max(0.0, peak_time - 0.20), 3),
                "motion_peak_seconds": round(peak_time, 3),
                "deceleration_seconds": round(max(0.0, hit_time - peak_time), 3),
                "detected_twerk_hit_seconds": round(hit_time, 3),
                "lock_seconds": round(hit_time + frame_seconds, 3),
                "held_pose_seconds": round(hit_time + 0.12, 3),
                "rebound_seconds": round(hit_time + 0.20, 3),
                "motion_peak_energy": round(peak_energy, 6),
                "hit_motion_energy": round(energies[hit_index], 6),
            }
        )
    return events


def nearest_event(cue_time: float, events: list[dict[str, float]]) -> dict[str, Any] | None:
    if not events:
        return None
    return min(events, key=lambda event: abs(float(event["detected_twerk_hit_seconds"]) - cue_time))


def clamp_shift(value: float, max_shift: float) -> float:
    return max(-max_shift, min(max_shift, value))


def classify_scene(
    pairs: list[dict[str, float]],
    events: list[dict[str, float]],
    min_motion_events: int,
    max_shift_seconds: float,
    bad_scene_threshold: float,
) -> dict[str, Any]:
    offsets = [float(pair["offset_seconds"]) for pair in pairs]
    if offsets:
        average_offset = round(statistics.fmean(offsets), 3)
        median_offset = round(statistics.median(offsets), 3)
        max_abs = round(max(abs(value) for value in offsets), 3)
    else:
        average_offset = None
        median_offset = None
        max_abs = None

    enough_events = len(events) >= min_motion_events
    if not enough_events:
        quality = "bad"
    elif median_offset is not None and abs(median_offset) <= GOOD_OFFSET_SECONDS:
        quality = "good"
    elif median_offset is not None and abs(median_offset) <= NEEDS_CALIBRATION_SECONDS:
        quality = "needs_calibration"
    else:
        quality = "bad"

    adjustment = 0.0
    action = "regenerate_scene_with_stronger_prompt_or_replace_seed"
    calibration_reliability_note = None
    if quality == "good":
        action = "keep"
        adjustment = 0.0
    elif median_offset is not None:
        if quality == "needs_calibration":
            action = "calibrate_cue_timing"
            adjustment = round(-median_offset, 3)
        else:
            action = "regenerate_scene_with_stronger_prompt_or_replace_seed"
            adjustment = round(clamp_shift(-median_offset, max_shift_seconds), 3)
            calibration_reliability_note = "Simple calibration is not reliable for bad scenes."

    outlier_warning = bool(
        enough_events
        and quality == "good"
        and max_abs is not None
        and max_abs > NEEDS_CALIBRATION_SECONDS
    )

    return {
        "average_twerk_hit_offset_seconds": average_offset,
        "median_twerk_hit_offset_seconds": median_offset,
        "max_abs_twerk_hit_offset_seconds": max_abs,
        "outlier_warning": outlier_warning,
        "outlier_note": (
            "Large max offset detected; median timing still controls quality."
            if outlier_warning
            else None
        ),
        "sync_quality": quality,
        "recommended_action": action,
        "cue_time_adjustment_seconds": adjustment,
        "calibration_reliability_note": calibration_reliability_note,
    }


def analyze_scene(
    clip_index: int,
    plan: dict[str, Any],
    clip_info: dict[str, Any],
    max_shift_seconds: float,
    threshold_percentile: float,
    bad_scene_threshold: float,
    min_motion_events: int,
) -> dict[str, Any]:
    cue_times = cue_times_from_plan(plan)
    clip_path = clip_info.get("clip_path")
    notes: list[str] = []
    if "clip_plan_read_error" in plan:
        notes.append(f"Clip plan could not be read: {plan['clip_plan_read_error']}")
    if clip_info.get("clip_path_missing_reason"):
        notes.append(str(clip_info["clip_path_missing_reason"]))

    base = {
        "clip_index": clip_index,
        "scene_index": int(as_float(plan.get("scene_index"), clip_index) or clip_index),
        "clip_plan_path": path_for_report(plan.get("clip_plan_path")),
        "clip_path": path_for_report(clip_path) if isinstance(clip_path, Path) else None,
        "clip_resolved_path": str(clip_path.resolve()) if isinstance(clip_path, Path) else None,
        "clip_path_source": clip_info.get("clip_path_source"),
        "cue_times_seconds": cue_times,
        "notes": notes,
    }

    if not cue_times:
        base.update(
            {
                "detected_motion_peak_seconds": [],
                "detected_twerk_hit_seconds": [],
                "matched_twerk_hit_pairs": [],
                "average_twerk_hit_offset_seconds": None,
                "median_twerk_hit_offset_seconds": None,
                "max_abs_twerk_hit_offset_seconds": None,
                "sync_quality": "bad",
                "recommended_action": "regenerate_scene_with_stronger_prompt_or_replace_seed",
                "cue_time_adjustment_seconds": 0.0,
            }
        )
        base["notes"].append("No sync_targets.clip_local_seconds cues were found.")
        base["notes"].append("Simple calibration is not reliable for bad scenes.")
        return base

    if not isinstance(clip_path, Path) or clip_info.get("clip_path_missing_reason"):
        base.update(
            {
                "detected_motion_peak_seconds": [],
                "detected_twerk_hit_seconds": [],
                "matched_twerk_hit_pairs": [],
                "average_twerk_hit_offset_seconds": None,
                "median_twerk_hit_offset_seconds": None,
                "max_abs_twerk_hit_offset_seconds": None,
                "sync_quality": "analysis_failed",
                "recommended_action": "locate_or_regenerate_missing_clip",
                "cue_time_adjustment_seconds": 0.0,
            }
        )
        return base

    motion = analyze_motion(clip_path, threshold_percentile)
    events = motion.get("motion_events", [])
    peaks = [event["motion_peak_seconds"] for event in events]
    hits = [event["detected_twerk_hit_seconds"] for event in events]
    pairs: list[dict[str, float]] = []
    for cue_time in cue_times:
        event = nearest_event(cue_time, events)
        if event is None:
            continue
        hit_time = float(event["detected_twerk_hit_seconds"])
        peak_time = float(event["motion_peak_seconds"])
        pairs.append(
            {
                "cue_time_seconds": round(cue_time, 3),
                "motion_peak_seconds": round(peak_time, 3),
                "detected_twerk_hit_seconds": round(hit_time, 3),
                "offset_seconds": round(hit_time - cue_time, 3),
            }
        )

    if motion.get("status") != "analyzed":
        base.update(
            {
                "motion_analysis_status": motion.get("status"),
                "motion_analysis": {key: value for key, value in motion.items() if key != "motion_samples"},
                "detected_motion_peak_seconds": [],
                "detected_twerk_hit_seconds": [],
                "matched_twerk_hit_pairs": [],
                "average_twerk_hit_offset_seconds": None,
                "median_twerk_hit_offset_seconds": None,
                "max_abs_twerk_hit_offset_seconds": None,
                "sync_quality": "analysis_failed",
                "recommended_action": "analysis_failed",
                "cue_time_adjustment_seconds": 0.0,
            }
        )
        base["notes"].extend(motion.get("notes", []))
        return base

    classification = classify_scene(pairs, events, min_motion_events, max_shift_seconds, bad_scene_threshold)
    if len(events) < min_motion_events:
        notes.append(f"Detected {len(events)} twerk-hit events; required at least {min_motion_events}.")
    if classification.get("calibration_reliability_note"):
        notes.append(str(classification["calibration_reliability_note"]))
    if classification.get("outlier_warning") and classification.get("outlier_note"):
        notes.append(str(classification["outlier_note"]))
    base.update(
        {
            "motion_analysis_status": motion.get("status"),
            "motion_method": motion.get("motion_method"),
            "fps": motion.get("fps"),
            "clip_duration_seconds": motion.get("duration_seconds"),
            "detected_motion_peak_seconds": peaks,
            "detected_twerk_hit_seconds": hits,
            "detected_twerk_hit_events": events,
            "matched_twerk_hit_pairs": pairs,
            **classification,
        }
    )
    base["notes"].extend(motion.get("notes", []))
    return base


def correction_entry(scene: dict[str, Any]) -> dict[str, Any]:
    offset = scene.get("median_twerk_hit_offset_seconds")
    adjustment = scene.get("cue_time_adjustment_seconds")
    if offset is None:
        timing_direction = "unknown"
    elif offset > 0:
        timing_direction = "late"
    elif offset < 0:
        timing_direction = "early"
    else:
        timing_direction = "on_time"
    return {
        "clip_index": scene.get("clip_index"),
        "scene_index": scene.get("scene_index"),
        "sync_quality": scene.get("sync_quality"),
        "recommended_action": scene.get("recommended_action"),
        "median_twerk_hit_offset_seconds": offset,
        "cue_time_adjustment_seconds": adjustment,
        "timing_direction": timing_direction,
        "clip_plan_path": scene.get("clip_plan_path"),
    }


def _cue_text_from_item(item: dict[str, Any]) -> str:
    return ", ".join(f"{value:.2f}s" for value in cue_times_from_plan(item))


def rebuild_clean_prompt_fields(
    item: dict[str, Any],
    calibration_note_text: str | None = None,
) -> None:
    previous_prompt = str(item.get("prompt_text") or "").strip()
    previous_base = str(item.get("base_prompt_text") or "").strip()
    if previous_base:
        item["base_prompt_text"] = previous_base
    elif previous_prompt:
        item["base_prompt_text"] = previous_prompt
    item["base_prompt_preserved_for_audit_only"] = bool(item.get("base_prompt_text"))
    item["generic_prompt_removed"] = True

    clean_prompt = scene_specific_prompt_block(item)
    if calibration_note_text:
        clean_prompt = f"{calibration_note_text}\n\n{clean_prompt}"
    item["prompt_text"] = clean_prompt
    item["ltx_payload_prompt"] = clean_prompt

    seed_hint = item.get("seed_filename_prompt_hint") or ""
    item["prompt_sections"] = {
        "visual_prompt": (
            f"Assigned seed image: {item.get('seed_image_used')}. "
            f"Seed filename hint: {seed_hint}."
        ),
        "motion_prompt": (
            f"Hard motion cue times inside this clip: {_cue_text_from_item(item)}. "
            "Land the visible movement arrival or reversal on these cue times; do not time the fastest travel point or the held pose to the beat. "
            "Keep motion between cue points smooth, controlled, and continuous."
        ),
        "camera_prompt": "Preserve the seed framing, layout, lighting direction, background continuity, and subject identity.",
        "constraint_prompt": "Avoid off-grid random motion, geometry drift, identity drift, and unplanned scene changes.",
    }


def calibration_note(offset: float | None) -> str:
    if offset is None:
        timing = "at an unknown offset"
    elif offset > 0:
        timing = f"{abs(offset):.3f} seconds late"
    elif offset < 0:
        timing = f"{abs(offset):.3f} seconds early"
    else:
        timing = "on time"
    return (
        "ASMO SYNC CALIBRATION: previous detected twerk-hit timing landed "
        f"{timing}; cue timing has been adjusted for this rerender."
    )


def patch_plan_item(
    item: dict[str, Any],
    adjustment_seconds: float,
    median_offset: float | None,
    changed: bool = True,
) -> dict[str, Any]:
    patched = json.loads(json.dumps(item, default=str))
    patched.pop("clip_plan_path", None)
    sync_targets = patched.get("sync_targets", {}) if isinstance(patched.get("sync_targets"), dict) else {}
    old_times = [value for value in cue_times_from_plan(patched)]
    new_times = [round(max(0.0, old + adjustment_seconds), 3) for old in old_times]
    if isinstance(sync_targets, dict):
        sync_targets["clip_local_seconds"] = new_times
        patched["sync_targets"] = sync_targets

    note = calibration_note(median_offset) if changed else None
    rebuild_clean_prompt_fields(patched, calibration_note_text=note)
    patched["asmo_sync_calibration"] = {
        "changed": bool(changed),
        "median_twerk_hit_offset_seconds": median_offset,
        "cue_time_adjustment_seconds": round(adjustment_seconds, 3),
        "note": note,
    }
    return patched


def write_patched_plans(
    run_dir: Path,
    clip_plans: dict[int, dict[str, Any]],
    scenes: list[dict[str, Any]],
    output_patched_plan: Path,
) -> dict[str, Any]:
    motion_sync_dir = run_dir / "motion_sync"
    patched_clip_dir = motion_sync_dir / "patched_clip_plans"
    patched_clip_dir.mkdir(parents=True, exist_ok=True)
    scene_by_index = {
        int(scene["clip_index"]): scene
        for scene in scenes
        if scene.get("sync_quality") in {"needs_calibration", "bad"}
    }
    written_clip_plans: list[str] = []
    patched_clip_paths: dict[int, Path] = {}

    for clip_index, scene in sorted(scene_by_index.items()):
        adjustment = as_float(scene.get("cue_time_adjustment_seconds"), 0.0) or 0.0
        original = clip_plans.get(clip_index)
        if not original:
            continue
        patched = patch_plan_item(original, adjustment, scene.get("median_twerk_hit_offset_seconds"))
        output_path = patched_clip_dir / f"scene_{clip_index:02d}_clip_plan.json"
        patched["clip_plan_json"] = path_for_report(output_path)
        patched["clip_plan_resolved_path"] = str(output_path.resolve())
        write_json(output_path, patched)
        patched_clip_paths[clip_index] = output_path
        written_clip_plans.append(path_for_report(output_path) or str(output_path))

    holy_plan_path = run_dir / "holy_cheeks_ltx_plan.json"
    patched_holy_written = None
    if holy_plan_path.exists():
        holy_plan = read_json(holy_plan_path)
        for item in holy_plan.get("results", []):
            idx = as_float(item.get("clip_index"))
            if idx is None:
                continue
            scene = scene_by_index.get(int(idx))
            changed = scene is not None
            adjustment = as_float(scene.get("cue_time_adjustment_seconds"), 0.0) if scene else 0.0
            adjustment = adjustment or 0.0
            median_offset = scene.get("median_twerk_hit_offset_seconds") if scene else None
            patched_item = patch_plan_item(item, adjustment, median_offset, changed=changed)
            if int(idx) in patched_clip_paths:
                patched_path = patched_clip_paths[int(idx)]
                patched_item["clip_plan_json"] = path_for_report(patched_path)
                patched_item["clip_plan_resolved_path"] = str(patched_path.resolve())
            item.clear()
            item.update(patched_item)
        holy_plan["asmo_sync_calibration"] = {
            "source_report": path_for_report(run_dir / "motion_sync" / "asmo_sync_report.json"),
            "patched_clip_plan_dir": path_for_report(patched_clip_dir),
            "patched_clip_plans": written_clip_plans,
            "changed_scene_indices": sorted(scene_by_index),
            "unchanged_scene_indices": [
                int(item.get("clip_index"))
                for item in holy_plan.get("results", [])
                if int(item.get("clip_index", 0)) not in scene_by_index
            ],
        }
        output_patched_plan.parent.mkdir(parents=True, exist_ok=True)
        write_json(output_patched_plan, holy_plan)
        patched_holy_written = path_for_report(output_patched_plan) or str(output_patched_plan)

    return {
        "patched_clip_plan_dir": path_for_report(patched_clip_dir),
        "patched_clip_plans": written_clip_plans,
        "patched_holy_cheeks_ltx_plan": patched_holy_written,
    }


def print_table(scenes: list[dict[str, Any]]) -> None:
    rows = []
    for scene in scenes:
        rows.append(
            [
                str(scene.get("clip_index")),
                str(scene.get("sync_quality")),
                format_optional_seconds(scene.get("median_twerk_hit_offset_seconds")),
                format_optional_seconds(scene.get("max_abs_twerk_hit_offset_seconds")),
                str(scene.get("recommended_action")),
                format_optional_seconds(scene.get("cue_time_adjustment_seconds")),
            ]
        )
    headers = ["Scene", "Quality", "Median Twerk-Hit Offset", "Max Offset", "Action", "Cue Adjustment"]
    widths = [len(header) for header in headers]
    for row in rows:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))
    print(" | ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
    print("-+-".join("-" * width for width in widths))
    for row in rows:
        print(" | ".join(value.ljust(widths[index]) for index, value in enumerate(row)))


def format_optional_seconds(value: Any) -> str:
    parsed = as_float(value)
    if parsed is None:
        return "n/a"
    return f"{parsed:+.3f}s"


def run_calibration(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = resolve_runtime_path(args.run_dir).resolve()
    audio_path = resolve_runtime_path(args.audio).resolve()
    motion_sync_dir = run_dir / "motion_sync"
    output_report = resolve_artifact_path(args.output_report, run_dir) if args.output_report else motion_sync_dir / "asmo_sync_report.json"
    output_correction = motion_sync_dir / "asmo_correction_plan.json"
    output_patched_plan = (
        resolve_artifact_path(args.output_patched_plan, run_dir)
        if args.output_patched_plan
        else motion_sync_dir / "patched_holy_cheeks_ltx_plan.json"
    )

    clip_plans = load_clip_plans(run_dir)
    submit_paths = load_submit_clip_paths(run_dir)
    manifest_paths = load_manifest_clip_paths(run_dir)
    all_clip_indices = sorted(set(clip_plans) | set(submit_paths) | set(manifest_paths))
    scenes = []
    for clip_index in all_clip_indices:
        plan = clip_plans.get(clip_index, {"clip_index": clip_index})
        clip_info = locate_clip(clip_index, submit_paths, manifest_paths)
        scenes.append(
            analyze_scene(
                clip_index,
                plan,
                clip_info,
                max_shift_seconds=float(args.max_shift_seconds),
                threshold_percentile=float(args.motion_threshold_percentile),
                bad_scene_threshold=float(args.bad_scene_threshold),
                min_motion_events=int(args.min_motion_events),
            )
        )

    missing_clips = [
        {
            "clip_index": scene.get("clip_index"),
            "scene_index": scene.get("scene_index"),
            "clip_path": scene.get("clip_path"),
            "notes": scene.get("notes", []),
        }
        for scene in scenes
        if scene.get("sync_quality") == "analysis_failed" and not scene.get("clip_path")
    ]
    correction_scenes = [correction_entry(scene) for scene in scenes if scene.get("sync_quality") != "good"]
    correction_plan: dict[str, Any] = {
        "schema": "asmo.sync_correction_plan.v1",
        "dry_run": bool(args.dry_run),
        "run_dir": path_for_report(run_dir),
        "run_dir_resolved": str(run_dir),
        "audio": path_for_report(audio_path),
        "audio_resolved_path": str(audio_path),
        "max_shift_seconds": float(args.max_shift_seconds),
        "motion_threshold_percentile": float(args.motion_threshold_percentile),
        "bad_scene_threshold": float(args.bad_scene_threshold),
        "min_motion_events": int(args.min_motion_events),
        "scenes": correction_scenes,
        "patched_outputs": None,
    }
    if args.patch_bad_scenes:
        correction_plan["patched_outputs"] = write_patched_plans(run_dir, clip_plans, scenes, output_patched_plan)

    report = {
        "schema": "asmo.sync_report.v1",
        "dry_run": bool(args.dry_run),
        "run_dir": path_for_report(run_dir),
        "run_dir_resolved": str(run_dir),
        "audio": path_for_report(audio_path),
        "audio_resolved_path": str(audio_path),
        "opencv_available": cv2 is not None,
        "max_shift_seconds": float(args.max_shift_seconds),
        "motion_threshold_percentile": float(args.motion_threshold_percentile),
        "bad_scene_threshold": float(args.bad_scene_threshold),
        "min_motion_events": int(args.min_motion_events),
        "scene_count": len(scenes),
        "missing_clips": missing_clips,
        "scenes": scenes,
        "report_path": path_for_report(output_report),
        "correction_plan_path": path_for_report(output_correction),
    }
    write_json(output_report, report)
    write_json(output_correction, correction_plan)
    print_table(scenes)
    print(f"\nReport: {path_for_report(output_report)}")
    print(f"Correction plan: {path_for_report(output_correction)}")
    if args.patch_bad_scenes:
        print(f"Patched plan: {path_for_report(output_patched_plan)}")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze LTX clip motion against ASMO twerk-hit cue timing.")
    parser.add_argument("--run-dir", required=True, help="LTX run directory containing clip_plans, submissions, and orchestration artifacts.")
    parser.add_argument("--audio", required=True, help="Source audio path used by the run.")
    parser.add_argument("--dry-run", action="store_true", help="Run local analysis only; no LTX submit is performed.")
    parser.add_argument("--output-report", help="Optional output path for asmo_sync_report.json.")
    parser.add_argument("--output-patched-plan", help="Optional output path for patched_holy_cheeks_ltx_plan.json.")
    parser.add_argument("--max-shift-seconds", type=float, default=DEFAULT_MAX_SHIFT_SECONDS)
    parser.add_argument("--motion-threshold-percentile", type=float, default=DEFAULT_MOTION_THRESHOLD_PERCENTILE)
    parser.add_argument("--patch-bad-scenes", action="store_true", help="Write copied patched plans under motion_sync for non-good scenes.")
    parser.add_argument("--bad-scene-threshold", type=float, default=DEFAULT_BAD_SCENE_THRESHOLD)
    parser.add_argument("--min-motion-events", type=int, default=DEFAULT_MIN_MOTION_EVENTS)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    run_calibration(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
