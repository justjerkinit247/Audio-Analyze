from pathlib import Path
import argparse
import json
import math
import os
import re
import traceback

import librosa
import numpy as np
import soundfile as sf

try:
    from .ltx_client import LTXClient, LTXError
    from .ltx_seed_mapper import collect_labeled_seed_images, expected_scene_mapping_key, validate_seed_mapping
    from .path_policy import is_windows_absolute_path, resolve_runtime_path, serialize_path, validate_path_config
except ImportError:
    from ltx_client import LTXClient, LTXError
    from ltx_seed_mapper import collect_labeled_seed_images, expected_scene_mapping_key, validate_seed_mapping
    from path_policy import is_windows_absolute_path, resolve_runtime_path, serialize_path, validate_path_config


ALLOWED_IMAGES = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_AUDIO = {".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg", ".aiff", ".aif"}
ALLOWED_LTX_MODELS = {"ltx-2-3-pro"}
RESOLUTION_MAP = {"9:16": "1080x1920", "16:9": "1920x1080", "1:1": "1080x1080"}
MIN_LTX_AUDIO_SECONDS = 2.0
MAX_LTX_AUDIO_SECONDS = 20.0
PROMPT_MAX_CHARS = 5000
MIN_GUIDANCE_SCALE = 0.0
MAX_GUIDANCE_SCALE = 20.0
DEFAULT_SCENE_SECONDS = 8.0
DEFAULT_MODEL = "ltx-2-3-pro"
DEFAULT_GUIDANCE_SCALE = 9.0
DEFAULT_AUDIO = "inputs/audio/hop out the whip.mp3"
DEFAULT_PLAN_JSON = "outputs/ltx_video_run/holy_cheeks_ltx_plan.json"
DEFAULT_SEED_DIR = "inputs/ltx_seed_images"

SEED_HINT_STOP_TOKENS = {
    "seed", "image", "img", "ltx", "scene", "clip", "final", "new", "v1", "v2", "v3",
    "jpg", "jpeg", "png", "webp", "photo", "picture", "render", "output",
}

LTX_AUDIO_EXPORT_CANDIDATES = [
    {"format": "MP3", "extension": ".mp3", "subtype": None},
    {"format": "OGG", "extension": ".ogg", "subtype": "VORBIS"},
]


def write_json(path, data):
    path = resolve_runtime_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def read_json(path):
    return json.loads(resolve_runtime_path(path).read_text(encoding="utf-8-sig"))


def scalarize(value):
    arr = np.asarray(value)
    if arr.size == 0:
        return None
    return float(arr.reshape(-1)[0])


def safe_name(name):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._-")
    return cleaned or "ltx_output"


def normalize_resolution(value):
    return RESOLUTION_MAP.get(value, value)


def seed_filename_hint(seed_image):
    if not seed_image:
        return ""
    stem = Path(seed_image).stem.lower()
    raw_tokens = re.split(r"[^a-z0-9]+", stem)
    tokens = [token for token in raw_tokens if token and token not in SEED_HINT_STOP_TOKENS]
    return " ".join(tokens).strip()


def list_seed_images(seed_dir):
    seed_dir = resolve_runtime_path(seed_dir)
    if not seed_dir.exists():
        raise FileNotFoundError(f"Seed image folder not found: {seed_dir.resolve()}")
    images = sorted(p for p in seed_dir.iterdir() if p.is_file() and p.suffix.lower() in ALLOWED_IMAGES)
    if not images:
        raise FileNotFoundError(f"No seed images found in {seed_dir.resolve()}")
    return images


def analyze_audio(audio_path):
    y, sr = librosa.load(str(audio_path), sr=None, mono=True)
    duration = float(librosa.get_duration(y=y, sr=sr))
    tempo_raw, beats = librosa.beat.beat_track(y=y, sr=sr)
    tempo = scalarize(tempo_raw)
    rms = librosa.feature.rms(y=y)[0]
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)

    avg_rms = float(np.mean(rms)) if len(rms) else 0.0
    avg_centroid = float(np.mean(centroid)) if len(centroid) else 0.0
    onset_strength = float(np.mean(onset_env)) if len(onset_env) else 0.0

    if tempo and tempo >= 140:
        energy = "very high"
        pacing = "fast"
        movement = "sharp downbeat hits, punchy footwork, confident hip and shoulder accents"
        camera = "quick push-ins, lateral tracking, clean punch-in accents"
    elif tempo and tempo >= 110:
        energy = "high"
        pacing = "medium-fast"
        movement = "locked rhythmic movement, visible groove, confident body accents on kick and snare"
        camera = "smooth tracking, energized reframes, steady controlled motion"
    elif tempo and tempo >= 85:
        energy = "moderate-high"
        pacing = "medium"
        movement = "groove-led movement, readable choreography, controlled rhythmic phrasing"
        camera = "controlled tracking, readable framing, cinematic drift"
    else:
        energy = "slow-burn"
        pacing = "slow"
        movement = "deliberate pose transitions, restrained performance movement, slow groove"
        camera = "slow push-ins, held compositions, gradual cinematic movement"

    if avg_centroid >= 3000:
        lighting = "bright crisp high-contrast studio lighting"
    elif avg_centroid >= 1800:
        lighting = "balanced polished studio lighting"
    else:
        lighting = "moody contrast with selective highlights"

    return {
        "tempo_bpm": round(tempo, 3) if tempo is not None else None,
        "duration_seconds": round(duration, 3),
        "energy_profile": energy,
        "edit_pacing": pacing,
        "movement_notes": movement,
        "camera_notes": camera,
        "lighting_notes": lighting,
        "mix_reactivity_notes": f"Average RMS {avg_rms:.4f}, spectral centroid {avg_centroid:.2f}, onset strength {onset_strength:.2f}",
    }


def detect_beats(audio_path):
    y, sr = librosa.load(str(audio_path), sr=None, mono=True)
    duration = float(librosa.get_duration(y=y, sr=sr))
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    tempo_raw, beat_frames = librosa.beat.beat_track(y=y, sr=sr, onset_envelope=onset_env)
    tempo = scalarize(tempo_raw)
    beat_times = [float(t) for t in librosa.frames_to_time(beat_frames, sr=sr)]
    return duration, tempo, beat_times


def _first_beat_at_or_after(beat_times, target, fallback):
    for beat in beat_times:
        if beat >= target:
            return beat
    return fallback


def _nearest_beat(beat_times, target, max_shift=0.75):
    candidates = [beat for beat in beat_times if abs(beat - target) <= max_shift]
    if not candidates:
        return target
    return min(candidates, key=lambda beat: abs(beat - target))


def resolve_scene_count(duration_seconds, requested_scenes=None, scene_seconds=DEFAULT_SCENE_SECONDS, start_offset_seconds=0.0):
    duration_seconds = float(duration_seconds)
    start_offset_seconds = max(0.0, float(start_offset_seconds or 0.0))
    usable_seconds = max(0.0, duration_seconds - start_offset_seconds)
    scene_seconds = max(MIN_LTX_AUDIO_SECONDS, min(MAX_LTX_AUDIO_SECONDS, float(scene_seconds)))
    if requested_scenes is None:
        requested_scenes = max(1, int(np.ceil(usable_seconds / scene_seconds)))
    requested_scenes = max(1, int(requested_scenes))
    max_possible_by_min_duration = max(1, int(usable_seconds // MIN_LTX_AUDIO_SECONDS))
    return min(requested_scenes, max_possible_by_min_duration)


def build_scenes(duration_seconds, max_scenes=None, scene_seconds=DEFAULT_SCENE_SECONDS, start_offset_seconds=0.0, beat_align=False, beat_times=None):
    scene_seconds = max(MIN_LTX_AUDIO_SECONDS, min(MAX_LTX_AUDIO_SECONDS, float(scene_seconds)))
    duration_seconds = float(duration_seconds)
    start_offset_seconds = max(0.0, float(start_offset_seconds or 0.0))
    if start_offset_seconds >= duration_seconds:
        raise ValueError(f"start_offset_seconds {start_offset_seconds:.3f} is beyond audio duration {duration_seconds:.3f}")

    scene_count = resolve_scene_count(duration_seconds, requested_scenes=max_scenes, scene_seconds=scene_seconds, start_offset_seconds=start_offset_seconds)
    scenes = []
    beat_times = beat_times or []
    beat_times_after_start = [t for t in beat_times if t >= start_offset_seconds]

    current_start = start_offset_seconds
    if beat_align and beat_times_after_start:
        current_start = _first_beat_at_or_after(beat_times_after_start, start_offset_seconds, start_offset_seconds)

    for i in range(scene_count):
        if current_start >= duration_seconds:
            break
        target_end = min(duration_seconds, current_start + scene_seconds)
        end = target_end
        if beat_align and beat_times_after_start:
            snapped = _nearest_beat(beat_times_after_start, target_end, max_shift=0.75)
            if MIN_LTX_AUDIO_SECONDS <= snapped - current_start <= MAX_LTX_AUDIO_SECONDS:
                end = snapped
        if end - current_start < MIN_LTX_AUDIO_SECONDS:
            end = min(duration_seconds, current_start + MIN_LTX_AUDIO_SECONDS)
        if end - current_start > MAX_LTX_AUDIO_SECONDS:
            end = current_start + MAX_LTX_AUDIO_SECONDS
        if end - current_start < MIN_LTX_AUDIO_SECONDS:
            break

        scenes.append({
            "scene_index": len(scenes) + 1,
            "start": round(current_start, 3),
            "end": round(end, 3),
            "duration": round(end - current_start, 3),
            "scene_type": "beat-aligned performance phrase" if beat_align else ("intro phrase" if i == 0 else "closing phrase" if i == scene_count - 1 else "performance phrase"),
            "sync_start_rule": "scene starts on or near detected beat" if beat_align else "fixed scene grid",
            "sync_end_rule": "scene ends on or near detected beat" if beat_align else "fixed scene grid",
        })

        next_start = end
        if beat_align and beat_times_after_start:
            next_start = _first_beat_at_or_after(beat_times_after_start, end, end)
            if next_start <= current_start:
                next_start = end
        current_start = next_start
    return scenes


def build_prompt(file_stem, analysis, scene, seed_image=None):
    bpm = analysis.get("tempo_bpm") or analysis.get("tempo_bpm_from_full_track")
    bpm_text = f"{bpm:.2f} BPM" if bpm else "the song rhythm"
    hint = seed_filename_hint(seed_image)
    hint_sentence = f"Seed filename visual instructions: {hint}. " if hint else ""
    beat_sentence = "Scene timing is beat-aligned; visible movement, body accents, camera changes, and scene transitions must land on kick, snare, bass hits, or strong beat accents. " if analysis.get("beat_alignment_enabled") else ""
    return (
        f"Image-to-video continuation for {file_stem}. "
        f"Use the seed image as the primary source of truth for subject count, body layout, pose, camera angle, framing, lighting, and background. "
        f"{hint_sentence}"
        f"Scene {scene['scene_index']} covers {scene['start']:.2f}s to {scene['end']:.2f}s of the source song. "
        f"Motion must feel locked to {bpm_text}. {beat_sentence}"
        f"Keep the existing subjects anatomically consistent and preserve the seed image composition. "
        f"Add controlled, beat-synced hip, glute, thigh, and lower-body dance motion without changing the pose category. "
        f"Keep all movement grounded, natural, and humanly believable. "
        f"Preserve low squat stance if present in the seed image; feet stay planted, knees stay bent, hips stay back. "
        f"Camera motion should be subtle and controlled: {analysis['camera_notes']}. "
        f"Movement direction: {analysis['movement_notes']}. "
        f"Lighting direction: {analysis['lighting_notes']}. "
        f"Do not add clothing, fabric, straps, accessories, props, body paint, censor blur, or coverage artifacts if they are not present in the seed image. "
        f"No costume changes, no random wardrobe, no new people, no scene teleportation, no chaotic camera spin. "
        f"No inverted poses, no bridge poses, no head-on-floor pose, no contortion, no impossible spine bending, no fused bodies, no extra limbs, no mutated hands or feet. "
        f"Maintain clear readable anatomy, stable identities, realistic skin texture, and clean temporal continuity."
    )


def build_plan(
    audio_path,
    seed_dir,
    output_json,
    resolution="9:16",
    max_scenes=None,
    scene_seconds=DEFAULT_SCENE_SECONDS,
    start_offset_seconds=0.0,
    beat_align=False,
    allow_sorted_seed_fallback=False,
    allow_duplicate_seed_reuse=False,
):
    audio_path = resolve_runtime_path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path.resolve()}")
    images = list_seed_images(seed_dir)
    labeled_seed_images, _ = collect_labeled_seed_images(seed_dir)
    analysis = analyze_audio(audio_path)
    duration, tempo, beat_times = detect_beats(audio_path)
    start_offset_seconds = max(0.0, float(start_offset_seconds or 0.0))
    if start_offset_seconds >= duration:
        raise ValueError(f"Start offset {start_offset_seconds:.3f}s is beyond audio duration {duration:.3f}s")
    auto_scene_count = len(images) if max_scenes is None else int(max_scenes)
    scenes = build_scenes(duration, max_scenes=auto_scene_count, scene_seconds=scene_seconds, start_offset_seconds=start_offset_seconds, beat_align=beat_align, beat_times=beat_times)
    resolution = normalize_resolution(resolution)

    analysis["start_offset_seconds"] = round(start_offset_seconds, 3)
    analysis["beat_alignment_enabled"] = bool(beat_align)
    analysis["tempo_bpm_from_full_track"] = round(tempo, 3) if tempo else analysis.get("tempo_bpm")
    analysis["detected_beat_count"] = len(beat_times)
    analysis["sync_policy"] = "Scene starts and scene changes are snapped to detected beat positions." if beat_align else "Fixed scene intervals."

    results = []
    seed_assignments = []
    for idx, scene in enumerate(scenes, start=1):
        expected_key = expected_scene_mapping_key(idx)
        if idx in labeled_seed_images:
            image = labeled_seed_images[idx][0]
            seed_mapping_method = "scene_label"
        elif idx - 1 < len(images):
            image = images[idx - 1]
            seed_mapping_method = "sorted_seed_fallback"
        else:
            image = None
            seed_mapping_method = "missing"
        seed_path = serialize_path(image) if image else ""
        seed_hint = seed_filename_hint(image) if image else ""
        seed_assignment = {
            "method": seed_mapping_method,
            "seed_file": image.name if image else None,
            "seed_image_path": seed_path,
            "scene_label_expected": expected_key,
            "filename_prompt_hint": seed_hint,
            "fallback_allowed": bool(allow_sorted_seed_fallback),
            "mapping_source": "build_plan",
        }
        results.append({
            "clip_index": idx,
            "file_stem": audio_path.stem,
            "source_audio_path": serialize_path(audio_path),
            "seed_image_used": seed_path,
            "seed_filename_prompt_hint": seed_hint,
            "seed_assignment": seed_assignment,
            "scene": scene,
            "resolution": resolution,
            "prompt_text": build_prompt(audio_path.stem, analysis, scene, seed_image=image),
            "status": "planned",
            "audio_to_video_confirmed": True,
            "beat_alignment_enabled": bool(beat_align),
        })
        seed_assignments.append(
            {
                "clip_index": idx,
                "seed_file": image.name if image else None,
                "seed_image_path": seed_path,
                "method": seed_mapping_method,
                "scene_label_expected": expected_key,
                "filename_prompt_hint": seed_hint,
            }
        )
    plan = {
        "file_stem": audio_path.stem,
        "analysis": analysis,
        "scene_count": len(results),
        "seed_image_count": len(images),
        "scene_count_source": "seed_image_count" if max_scenes is None else "manual_max_scenes",
        "resolution": resolution,
        "scene_seconds": scene_seconds,
        "start_offset_seconds": round(start_offset_seconds, 3),
        "beat_alignment_enabled": bool(beat_align),
        "audio_to_video_enabled": True,
        "audio_plus_seed_image_sent_to_ltx": True,
        "results": results,
        "status": "planned",
    }
    seed_mapping_report = validate_seed_mapping(
        plan,
        seed_dir=seed_dir,
        allow_sorted_seed_fallback=allow_sorted_seed_fallback,
        allow_duplicate_seed_reuse=allow_duplicate_seed_reuse,
    )
    plan["seed_mapping"] = {
        **seed_mapping_report,
        "seed_dir": serialize_path(seed_dir),
        "seed_dir_resolved": str(resolve_runtime_path(seed_dir).resolve()),
        "source": "build_plan",
        "assignments": seed_assignments,
        "label_examples": [
            "scene_01_intro_walk_forward.png",
            "scene_02_over_shoulder_glance.webp",
            "clip_03_twerk_accent_wide_angle.jpg",
            "s04_group_walk_camera_arc.jpeg",
        ],
    }
    write_json(output_json, plan)
    return plan


def validation_problem(clip_index, field, reason):
    return f"Scene {clip_index}: {field}: {reason}"


def _positive_int(value):
    if isinstance(value, bool):
        return None
    try:
        if isinstance(value, float) and not value.is_integer():
            return None
        parsed = int(value)
    except Exception:
        return None
    return parsed if parsed > 0 else None


def _numeric_guidance_scale(value):
    try:
        if isinstance(value, bool):
            return None
        parsed = float(value)
    except Exception:
        return None
    return parsed if math.isfinite(parsed) else None


def _validate_media_path(problems, clip_index, field, value, allowed_exts):
    if value is None or not str(value).strip():
        problems.append(validation_problem(clip_index, field, "path is required"))
        return
    try:
        path = resolve_runtime_path(value)
    except TypeError:
        problems.append(validation_problem(clip_index, field, "path must be a string"))
        return
    if path.suffix.lower() not in allowed_exts:
        problems.append(validation_problem(clip_index, field, f"unsupported extension '{path.suffix}'"))
    if not path.exists():
        reason = (
            "file missing: stale absolute local media path is missing"
            if is_windows_absolute_path(value)
            else "file missing"
        )
        problems.append(
            validation_problem(clip_index, field, f"{reason}: {value}; resolved_path={path.resolve()}")
        )
        return
    if path.stat().st_size <= 0:
        problems.append(validation_problem(clip_index, field, f"file is empty: {path}"))


def _validate_submit_settings(problems, clip_index, model=None, guidance_scale=None):
    if model is not None and model not in ALLOWED_LTX_MODELS:
        problems.append(validation_problem(clip_index, "model", f"unsupported model '{model}'"))
    if guidance_scale is not None:
        numeric = _numeric_guidance_scale(guidance_scale)
        if numeric is None:
            problems.append(validation_problem(clip_index, "guidance_scale", "must be numeric"))
        elif numeric < MIN_GUIDANCE_SCALE or numeric > MAX_GUIDANCE_SCALE:
            problems.append(
                validation_problem(
                    clip_index,
                    "guidance_scale",
                    f"must be between {MIN_GUIDANCE_SCALE:g} and {MAX_GUIDANCE_SCALE:g}",
                )
            )


def validate_plan(
    plan,
    model=None,
    guidance_scale=None,
    clip_index=None,
    require_seed_mapping=False,
    allow_sorted_seed_fallback=False,
    allow_duplicate_seed_reuse=False,
    seed_dir=None,
):
    problems = []
    if not plan.get("results"):
        problems.append("Plan has no scene results.")
    requested_clip_index = _positive_int(clip_index) if clip_index is not None else None
    if clip_index is not None and requested_clip_index is None:
        problems.append(validation_problem(clip_index, "clip_index", "must be a positive integer"))
    if clip_index is not None and requested_clip_index is not None:
        if not any(_positive_int(item.get("clip_index")) == requested_clip_index for item in plan.get("results", [])):
            problems.append(validation_problem(requested_clip_index, "clip_index", "not found in plan results"))
    for item in plan.get("results", []):
        parsed_idx = _positive_int(item.get("clip_index"))
        idx = parsed_idx if parsed_idx is not None else item.get("clip_index", "unknown")
        if parsed_idx is None:
            problems.append(validation_problem(idx, "clip_index", "must be a positive integer"))
        if requested_clip_index is not None and parsed_idx != requested_clip_index:
            continue
        audio_path_value = item.get("source_audio_path", "")
        image_path_value = item.get("seed_image_used", "")
        scene = item.get("scene", {})
        try:
            duration = float(scene.get("duration", 0))
        except Exception:
            duration = 0.0
            problems.append(validation_problem(idx, "scene.duration", "must be numeric"))
        prompt = item.get("prompt_text", "")
        resolution = item.get("resolution", "")
        _validate_media_path(problems, idx, "source_audio_path", audio_path_value, ALLOWED_AUDIO)
        _validate_media_path(problems, idx, "seed_image_used", image_path_value, ALLOWED_IMAGES)
        if duration < MIN_LTX_AUDIO_SECONDS or duration > MAX_LTX_AUDIO_SECONDS:
            problems.append(validation_problem(idx, "scene.duration", f"{duration:.2f}s is outside {MIN_LTX_AUDIO_SECONDS}-{MAX_LTX_AUDIO_SECONDS}s"))
        if prompt is None or not str(prompt).strip():
            problems.append(validation_problem(idx, "prompt_text", "prompt is empty"))
        if len(str(prompt)) > PROMPT_MAX_CHARS:
            problems.append(validation_problem(idx, "prompt_text", f"prompt is over {PROMPT_MAX_CHARS} characters"))
        if resolution not in set(RESOLUTION_MAP.values()):
            problems.append(validation_problem(idx, "resolution", f"unsupported or unnormalized value: {resolution}"))
        _validate_submit_settings(problems, idx, model=model, guidance_scale=guidance_scale)
    if require_seed_mapping:
        seed_mapping_report = validate_seed_mapping(
            plan,
            seed_dir=seed_dir,
            allow_sorted_seed_fallback=allow_sorted_seed_fallback,
            allow_duplicate_seed_reuse=allow_duplicate_seed_reuse,
        )
        problems.extend(seed_mapping_report.get("problems", []))
    return problems


def run_preflight(
    plan_json,
    output_json=None,
    require_seed_mapping=True,
    allow_sorted_seed_fallback=False,
    allow_duplicate_seed_reuse=False,
    seed_dir=None,
):
    plan = read_json(plan_json)
    seed_mapping_report = None
    path_policy_report = validate_path_config(plan)
    problems = validate_plan(plan)
    if require_seed_mapping:
        seed_mapping_report = validate_seed_mapping(
            plan,
            seed_dir=seed_dir,
            allow_sorted_seed_fallback=allow_sorted_seed_fallback,
            allow_duplicate_seed_reuse=allow_duplicate_seed_reuse,
        )
        problems.extend(seed_mapping_report.get("problems", []))
    report = {
        "status": "FAILED" if problems else "PASSED",
        "scene_count": len(plan.get("results", [])),
        "problems": problems,
        "plan_json": serialize_path(plan_json),
        "plan_json_resolved": str(resolve_runtime_path(plan_json).resolve()),
        "path_policy": path_policy_report,
        "seed_mapping_validation": seed_mapping_report,
    }
    if output_json:
        write_json(output_json, report)
    return report


def export_audio_candidate(path, y, sr, candidate):
    if candidate["subtype"]:
        sf.write(str(path), y, sr, format=candidate["format"], subtype=candidate["subtype"])
    else:
        sf.write(str(path), y, sr, format=candidate["format"])


def export_scene_audio(source_audio_path, scene, output_dir, file_stem, clip_index):
    output_dir = resolve_runtime_path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    source_audio_path = resolve_runtime_path(source_audio_path)
    start = float(scene["start"])
    end = float(scene["end"])
    duration = max(MIN_LTX_AUDIO_SECONDS, min(MAX_LTX_AUDIO_SECONDS, end - start))
    y, sr = librosa.load(str(source_audio_path), sr=None, mono=False, offset=start, duration=duration)
    if y.size == 0:
        raise RuntimeError(f"Could not extract audio for scene {clip_index} from {source_audio_path}")
    if y.ndim == 2:
        y = y.T
    errors = []
    for candidate in LTX_AUDIO_EXPORT_CANDIDATES:
        scene_audio = output_dir / f"{safe_name(file_stem)}_ltx_scene_{int(clip_index):02d}{candidate['extension']}"
        try:
            export_audio_candidate(scene_audio, y, sr, candidate)
            return {
                "path": serialize_path(scene_audio),
                "resolved_path": str(scene_audio.resolve()),
                "format": candidate["format"],
                "extension": candidate["extension"],
            }
        except Exception as exc:
            errors.append(f"{candidate['format']} failed: {exc}")
            try:
                if scene_audio.exists():
                    scene_audio.unlink()
            except Exception:
                pass
    raise RuntimeError("Could not export LTX-compatible scene audio. " + " | ".join(errors))


def _get_plan_item(plan, clip_index):
    for item in plan["results"]:
        if int(item["clip_index"]) == int(clip_index):
            return item
    raise ValueError(f"Clip index {clip_index} not found")


def submit_one(
    plan_json,
    output_json,
    clip_index,
    model=DEFAULT_MODEL,
    guidance_scale=DEFAULT_GUIDANCE_SCALE,
    dry_run=True,
    live=False,
    allow_sorted_seed_fallback=False,
    allow_duplicate_seed_reuse=False,
):
    if live and dry_run:
        raise ValueError("Use either dry_run or live, not both.")
    if not dry_run and not live:
        raise RuntimeError("Live LTX calls require live=True. Default is dry-run to prevent accidental credit spending.")
    if live and not os.environ.get("LTXV_API_KEY"):
        raise RuntimeError("LTXV_API_KEY is not set. Refusing live LTX call.")

    plan = read_json(plan_json)
    problems = validate_plan(
        plan,
        model=model,
        guidance_scale=guidance_scale,
        clip_index=clip_index,
        require_seed_mapping=True,
        allow_sorted_seed_fallback=allow_sorted_seed_fallback,
        allow_duplicate_seed_reuse=allow_duplicate_seed_reuse,
    )
    if problems:
        raise RuntimeError("Preflight failed; refusing submit. Problems:\n" + "\n".join(problems))

    match = _get_plan_item(plan, clip_index)
    source_audio_path = resolve_runtime_path(match["source_audio_path"])
    seed_image_path = resolve_runtime_path(match["seed_image_used"])
    output_root = resolve_runtime_path(output_json).parent
    downloads_dir = output_root / "downloads"
    scene_audio_dir = output_root / "scene_audio"
    downloads_dir.mkdir(parents=True, exist_ok=True)
    scene_audio_dir.mkdir(parents=True, exist_ok=True)

    result = {
        "clip_index": int(clip_index), "file_stem": match["file_stem"], "scene": match["scene"],
        "seed_image_used": match["seed_image_used"], "seed_filename_prompt_hint": match.get("seed_filename_prompt_hint"),
        "source_audio_path": match["source_audio_path"], "prompt_text": match["prompt_text"], "resolution": match["resolution"],
        "seed_image_resolved_path": str(seed_image_path.resolve()),
        "source_audio_resolved_path": str(source_audio_path.resolve()),
        "model": model, "guidance_scale": guidance_scale, "dry_run": dry_run, "live": live,
        "status": "submitting" if live else "dry_run", "audio_to_video_confirmed": True,
    }
    write_json(output_json, result)

    try:
        scene_audio = export_scene_audio(source_audio_path, match["scene"], scene_audio_dir, match["file_stem"], clip_index)
        scene_audio_path = scene_audio["path"]
        scene_audio_resolved_path = scene_audio["resolved_path"]
        mp4_path = downloads_dir / f"{safe_name(match['file_stem'])}_ltx_scene_{int(clip_index):02d}.mp4"
        result["scene_audio_path"] = scene_audio_path
        result["scene_audio_resolved_path"] = scene_audio_resolved_path
        result["scene_audio_format"] = scene_audio["format"]
        write_json(output_json, result)
        client = LTXClient(api_key="dry-run-key" if dry_run else None)
        ltx_result = client.audio_to_video(
            audio_uri=scene_audio_resolved_path,
            image_uri=str(seed_image_path),
            prompt=match["prompt_text"],
            output_path=str(mp4_path),
            model=model,
            resolution=match["resolution"],
            guidance_scale=guidance_scale,
            dry_run=dry_run,
        )
        result["ltx_result"] = ltx_result
        result["status"] = ltx_result.get("status", "complete")
        downloaded_mp4 = ltx_result.get("downloaded_mp4")
        result["downloaded_mp4"] = serialize_path(downloaded_mp4) if downloaded_mp4 else None
        result["downloaded_mp4_resolved_path"] = str(resolve_runtime_path(downloaded_mp4).resolve()) if downloaded_mp4 else None
    except Exception as exc:
        result["status"] = "failed"
        result["error_type"] = type(exc).__name__
        result["error"] = str(exc)
        result["traceback"] = traceback.format_exc()
        if isinstance(exc, LTXError) and "HTTP 500" in str(exc):
            result["retry_recommended"] = True
            result["failure_class"] = "ltx_server_500"
        else:
            result["retry_recommended"] = False
            result["failure_class"] = "local_or_request_error"
    write_json(output_json, result)
    return result


def submit_all(
    plan_json,
    output_dir,
    model=DEFAULT_MODEL,
    guidance_scale=DEFAULT_GUIDANCE_SCALE,
    dry_run=True,
    live=False,
    allow_sorted_seed_fallback=False,
    allow_duplicate_seed_reuse=False,
):
    plan = read_json(plan_json)
    output_dir = resolve_runtime_path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "status": "running",
        "dry_run": dry_run,
        "live": live,
        "plan_json": serialize_path(plan_json),
        "plan_json_resolved": str(resolve_runtime_path(plan_json).resolve()),
        "results": [],
    }
    summary_path = output_dir / "ltx_submit_all_summary.json"
    write_json(summary_path, summary)
    failed_count = 0
    for item in plan.get("results", []):
        idx = int(item["clip_index"])
        result_path = output_dir / f"scene_{idx:02d}_result.json"
        result = submit_one(
            plan_json,
            result_path,
            idx,
            model,
            guidance_scale,
            dry_run=dry_run,
            live=live,
            allow_sorted_seed_fallback=allow_sorted_seed_fallback,
            allow_duplicate_seed_reuse=allow_duplicate_seed_reuse,
        )
        if result.get("status") == "failed":
            failed_count += 1
        summary["results"].append({
            "clip_index": idx, "status": result.get("status"), "failure_class": result.get("failure_class"),
            "retry_recommended": result.get("retry_recommended"), "error": result.get("error"),
            "scene_audio_path": result.get("scene_audio_path"), "scene_audio_format": result.get("scene_audio_format"),
            "downloaded_mp4": result.get("downloaded_mp4"),
            "downloaded_mp4_resolved_path": result.get("downloaded_mp4_resolved_path"),
            "result_json": serialize_path(result_path),
            "result_resolved_path": str(result_path.resolve()),
        })
        summary["failed_count"] = failed_count
        write_json(summary_path, summary)
    summary["status"] = "complete_with_failures" if failed_count else "complete"
    summary["failed_count"] = failed_count
    write_json(summary_path, summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description="LTX Studio seed-image-first video pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    p1 = sub.add_parser("plan")
    p1.add_argument("--audio", default=DEFAULT_AUDIO)
    p1.add_argument("--seed-dir", default=DEFAULT_SEED_DIR)
    p1.add_argument("--output", default=DEFAULT_PLAN_JSON)
    p1.add_argument("--resolution", default="9:16")
    p1.add_argument("--max-scenes", type=int, default=None)
    p1.add_argument("--scene-seconds", type=float, default=DEFAULT_SCENE_SECONDS)
    p1.add_argument("--start-offset-seconds", type=float, default=0.0)
    p1.add_argument("--beat-align", action="store_true")
    p1.add_argument("--allow-sorted-seed-fallback", action="store_true")
    p1.add_argument("--allow-duplicate-seed-reuse", action="store_true")
    p_pre = sub.add_parser("preflight")
    p_pre.add_argument("--plan-json", required=True)
    p_pre.add_argument("--output", default=None)
    p_pre.add_argument("--allow-sorted-seed-fallback", action="store_true")
    p_pre.add_argument("--allow-duplicate-seed-reuse", action="store_true")
    p2 = sub.add_parser("submit-one")
    p2.add_argument("--plan-json", required=True)
    p2.add_argument("--output", required=True)
    p2.add_argument("--clip-index", type=int, default=1)
    p2.add_argument("--model", default=DEFAULT_MODEL)
    p2.add_argument("--guidance-scale", type=float, default=DEFAULT_GUIDANCE_SCALE)
    p2.add_argument("--live", action="store_true")
    p2.add_argument("--allow-sorted-seed-fallback", action="store_true")
    p2.add_argument("--allow-duplicate-seed-reuse", action="store_true")
    p_all = sub.add_parser("submit-all")
    p_all.add_argument("--plan-json", required=True)
    p_all.add_argument("--output-dir", required=True)
    p_all.add_argument("--model", default=DEFAULT_MODEL)
    p_all.add_argument("--guidance-scale", type=float, default=DEFAULT_GUIDANCE_SCALE)
    p_all.add_argument("--live", action="store_true")
    p_all.add_argument("--allow-sorted-seed-fallback", action="store_true")
    p_all.add_argument("--allow-duplicate-seed-reuse", action="store_true")
    args = parser.parse_args()
    if args.command == "plan":
        plan = build_plan(
            args.audio,
            args.seed_dir,
            args.output,
            args.resolution,
            args.max_scenes,
            args.scene_seconds,
            args.start_offset_seconds,
            args.beat_align,
            allow_sorted_seed_fallback=args.allow_sorted_seed_fallback,
            allow_duplicate_seed_reuse=args.allow_duplicate_seed_reuse,
        )
        print("LTX scene plan created.")
        print(Path(args.output).resolve())
        print(f"Seed images found: {plan.get('seed_image_count')}")
        print(f"Scene count: {plan['scene_count']}")
        print(f"Scene count source: {plan.get('scene_count_source')}")
        print(f"Seed mapping status: {plan.get('seed_mapping', {}).get('status')}")
        print(json.dumps(plan["analysis"], indent=2))
    elif args.command == "preflight":
        report = run_preflight(
            args.plan_json,
            args.output,
            allow_sorted_seed_fallback=args.allow_sorted_seed_fallback,
            allow_duplicate_seed_reuse=args.allow_duplicate_seed_reuse,
        )
        print(f"Preflight status: {report['status']}")
        print(f"Scene count: {report['scene_count']}")
        for problem in report["problems"]:
            print(f"PROBLEM: {problem}")
        if args.output:
            print(Path(args.output).resolve())
    elif args.command == "submit-one":
        result = submit_one(
            args.plan_json,
            args.output,
            args.clip_index,
            args.model,
            args.guidance_scale,
            dry_run=not args.live,
            live=args.live,
            allow_sorted_seed_fallback=args.allow_sorted_seed_fallback,
            allow_duplicate_seed_reuse=args.allow_duplicate_seed_reuse,
        )
        print("LTX scene submit complete.")
        print(Path(args.output).resolve())
        print(f"Status: {result.get('status')}")
        print(f"Downloaded MP4: {result.get('downloaded_mp4')}")
    elif args.command == "submit-all":
        summary = submit_all(
            args.plan_json,
            args.output_dir,
            args.model,
            args.guidance_scale,
            dry_run=not args.live,
            live=args.live,
            allow_sorted_seed_fallback=args.allow_sorted_seed_fallback,
            allow_duplicate_seed_reuse=args.allow_duplicate_seed_reuse,
        )
        print("LTX submit-all complete.")
        print(f"Status: {summary['status']}")
        print(f"Scenes: {len(summary['results'])}")
        print(f"Failures: {summary.get('failed_count', 0)}")
        print(Path(args.output_dir).resolve())


if __name__ == "__main__":
    main()
