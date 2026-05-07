from pathlib import Path
import argparse
import json
import re

import librosa
import numpy as np

try:
    from PIL import Image, ImageStat
except Exception:
    Image = None
    ImageStat = None

ALLOWED_IMAGES = {".jpg", ".jpeg", ".png", ".webp"}
PROMPT_MAX_CHARS = 5000
PROMPT_HINT_MAX_CHARS = 700
SCENE_PATTERNS = [
    re.compile(r"(?:^|[_\-\s])scene[_\-\s]?(\d{1,2})(?:[_\-\s]|$)", re.IGNORECASE),
    re.compile(r"(?:^|[_\-\s])clip[_\-\s]?(\d{1,2})(?:[_\-\s]|$)", re.IGNORECASE),
    re.compile(r"(?:^|[_\-\s])s(\d{1,2})(?:[_\-\s]|$)", re.IGNORECASE),
]
LABEL_CLEAN_PATTERNS = [
    re.compile(r"(?:^|[_\-\s])scene[_\-\s]?\d{1,2}(?:[_\-\s]|$)", re.IGNORECASE),
    re.compile(r"(?:^|[_\-\s])clip[_\-\s]?\d{1,2}(?:[_\-\s]|$)", re.IGNORECASE),
    re.compile(r"(?:^|[_\-\s])s\d{1,2}(?:[_\-\s]|$)", re.IGNORECASE),
]
STOP_TOKENS = {
    "seed", "image", "img", "ltx", "runway", "video", "music", "scene", "clip",
    "png", "jpg", "jpeg", "webp", "final", "v1", "v2", "new"
}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def normalize_text(text, limit=PROMPT_HINT_MAX_CHARS):
    if not text:
        return ""
    text = str(text).replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:limit]


def first_text(entry, *keys):
    for key in keys:
        value = normalize_text(entry.get(key))
        if value:
            return value
    return ""


def scene_number_from_name(path):
    stem = Path(path).stem.replace(".", "_")
    for pattern in SCENE_PATTERNS:
        match = pattern.search(stem)
        if match:
            return int(match.group(1))
    return None


def hint_from_filename(path):
    stem = Path(path).stem.replace(".", "_")
    for pattern in LABEL_CLEAN_PATTERNS:
        stem = pattern.sub("_", stem)
    words = []
    for token in re.split(r"[_\-\s]+", stem):
        token = token.strip().lower()
        if not token or token.isdigit() or token in STOP_TOKENS:
            continue
        words.append(token)
    return normalize_text(" ".join(words))


def load_scene_manifest(manifest_path):
    if not manifest_path:
        return {}, None
    path = Path(manifest_path)
    if not path.exists():
        return {}, f"Scene manifest not found; continuing without manifest: {path.resolve()}"
    raw = read_json(path)
    raw_scenes = raw.get("scenes", []) if isinstance(raw, dict) else raw if isinstance(raw, list) else []
    manifest = {}
    for entry in raw_scenes:
        if not isinstance(entry, dict):
            continue
        scene = entry.get("scene") or entry.get("clip_index") or entry.get("clip")
        if scene is None:
            continue
        manifest[int(scene)] = {
            "seed_file": first_text(entry, "seed_file", "seed"),
            "scene_label": first_text(entry, "scene_label", "label", "scene_name"),
            "scene_description": first_text(entry, "scene_description", "description", "scene_desc"),
            "audio_focus": first_text(entry, "audio_focus", "music_focus", "audio_description"),
            "sync_timing": first_text(entry, "sync_timing", "beat_sync", "music_sync", "timing_notes", "sync"),
            "lyric_focus": first_text(entry, "lyric_focus", "lyrics", "lyric_moment"),
            "camera": first_text(entry, "camera", "camera_instruction", "framing"),
            "motion": first_text(entry, "motion", "motion_instruction", "choreography"),
            "performance_action": first_text(entry, "performance_action", "action", "movement_goal"),
            "continuity": first_text(entry, "continuity", "continuity_notes"),
            "negative_prompt": first_text(entry, "negative_prompt", "avoid"),
            "notes": first_text(entry, "notes"),
        }
    return manifest, None


def collect_seed_images(seed_dir):
    seed_dir = Path(seed_dir)
    if not seed_dir.exists():
        raise FileNotFoundError(f"Seed image folder not found: {seed_dir.resolve()}")
    labeled = {}
    unlabeled = []
    for path in sorted(seed_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() not in ALLOWED_IMAGES:
            continue
        scene_number = scene_number_from_name(path)
        if scene_number is None:
            unlabeled.append(path)
        else:
            labeled.setdefault(scene_number, []).append(path)
    return labeled, unlabeled


def choose_seed_image(seed_dir, manifest_entry, labeled, unlabeled, clip_index, existing_seed=None, strict=False):
    requested = (manifest_entry or {}).get("seed_file")
    if requested:
        candidate = Path(requested)
        if not candidate.is_absolute():
            candidate = Path(seed_dir) / requested
        if candidate.exists():
            return candidate, "manifest_seed_file", []
        return None, "missing_manifest_seed", [f"Scene {clip_index}: manifest seed not found: {requested}"]
    if clip_index in labeled:
        problems = []
        if len(labeled[clip_index]) > 1:
            problems.append(f"Scene {clip_index}: multiple labeled seed images found; using {labeled[clip_index][0].name}")
        return labeled[clip_index][0], "scene_label", problems
    if existing_seed:
        candidate = Path(existing_seed)
        if candidate.exists():
            return candidate, "existing_plan_seed", []
    if unlabeled and not strict:
        return unlabeled[(clip_index - 1) % len(unlabeled)], "unlabeled_round_robin", []
    return None, "missing", [f"Scene {clip_index}: no usable seed image found"]


def inspect_seed_image(path):
    path = Path(path)
    info = {
        "file_name": path.name,
        "filename_prompt_hint": hint_from_filename(path),
        "analysis_method": "filename_only",
    }
    if Image is None:
        info["note"] = "Pillow unavailable; install pillow for image metadata, brightness, and contrast analysis."
        return info
    try:
        with Image.open(path) as img:
            width, height = img.size
            info.update({
                "analysis_method": "pillow_metadata",
                "width": width,
                "height": height,
                "aspect_ratio": round(width / height, 4) if height else None,
                "orientation": "vertical" if height > width else "horizontal" if width > height else "square",
                "mode": img.mode,
            })
            gray = img.convert("L")
            stat = ImageStat.Stat(gray)
            brightness = float(stat.mean[0]) if stat.mean else 0.0
            contrast = float(stat.stddev[0]) if stat.stddev else 0.0
            info["brightness"] = round(brightness, 2)
            info["contrast"] = round(contrast, 2)
            info["lighting_hint"] = "bright/high-key" if brightness >= 180 else "dark/moody" if brightness <= 75 else "balanced mid-brightness"
            info["contrast_hint"] = "high contrast" if contrast >= 65 else "soft low contrast" if contrast <= 30 else "moderate contrast"
    except Exception as exc:
        info["note"] = f"Seed image analysis failed: {exc}"
    return info


def scalar(value):
    arr = np.asarray(value)
    if arr.size == 0:
        return 0.0
    return float(arr.reshape(-1)[0])


def analyze_scene_audio(audio_path, scene):
    start = float(scene.get("start", 0.0))
    end = float(scene.get("end", start))
    duration = float(scene.get("duration", max(0.0, end - start)))
    y, sr = librosa.load(str(audio_path), sr=None, mono=True, offset=start, duration=duration)
    if y.size == 0:
        return {"status": "empty_audio", "start": start, "duration": duration}

    rms = librosa.feature.rms(y=y)[0]
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    tempo_raw, _beats = librosa.beat.beat_track(y=y, sr=sr)
    tempo = scalar(tempo_raw)

    onset_times = librosa.times_like(onset_env, sr=sr)
    top_onsets = []
    if len(onset_env):
        count = min(5, len(onset_env))
        top_indices = np.argsort(onset_env)[-count:]
        top_onsets = sorted(round(start + float(onset_times[i]), 3) for i in top_indices)

    avg_rms = float(np.mean(rms)) if len(rms) else 0.0
    peak_rms = float(np.max(rms)) if len(rms) else 0.0
    avg_centroid = float(np.mean(centroid)) if len(centroid) else 0.0
    avg_onset = float(np.mean(onset_env)) if len(onset_env) else 0.0
    peak_onset = float(np.max(onset_env)) if len(onset_env) else 0.0

    if avg_rms >= 0.12 or peak_rms >= 0.25:
        energy_label = "high-energy section; use stronger movement and decisive camera accents"
    elif avg_rms >= 0.05:
        energy_label = "medium-energy section; use readable groove and controlled camera motion"
    else:
        energy_label = "low-energy section; use restrained motion and slower camera movement"

    if peak_onset >= 6.0 or avg_onset >= 1.8:
        onset_label = "strong transient hits; place movement hits on percussion peaks"
    elif peak_onset >= 3.0 or avg_onset >= 0.8:
        onset_label = "moderate rhythmic accents; keep choreography visibly beat-matched"
    else:
        onset_label = "smooth section; avoid frantic motion and emphasize fluid timing"

    brightness_label = "bright/crisp audio; use clearer lighting and sharper edit feel" if avg_centroid >= 3000 else "warm/balanced audio; use polished mid-energy lighting" if avg_centroid >= 1500 else "dark/low-frequency audio; use moodier lighting and heavier movement"

    return {
        "status": "analyzed",
        "start": round(start, 3),
        "duration": round(duration, 3),
        "tempo_bpm_estimate": round(tempo, 3) if tempo else None,
        "avg_rms": round(avg_rms, 5),
        "peak_rms": round(peak_rms, 5),
        "avg_spectral_centroid": round(avg_centroid, 2),
        "avg_onset_strength": round(avg_onset, 3),
        "peak_onset_strength": round(peak_onset, 3),
        "strong_onset_times_seconds": top_onsets,
        "energy_label": energy_label,
        "onset_label": onset_label,
        "brightness_label": brightness_label,
        "movement_sync_hint": "match primary body accents to detected onset times and downbeats; avoid random unsynced motion",
        "camera_sync_hint": "use camera push, arc, or cut emphasis only on major beats/transients, not continuously",
    }


def build_scene_context(plan, item, seed_path, manifest_entry):
    scene = item.get("scene", {}) or {}
    audio_path = item.get("source_audio_path") or plan.get("source_audio_path")
    audio_cues = analyze_scene_audio(audio_path, scene) if audio_path else {"status": "missing_audio_path"}
    seed_info = inspect_seed_image(seed_path)
    return {
        "clip_index": int(item.get("clip_index", 0)),
        "time_range": {
            "start": scene.get("start"),
            "end": scene.get("end"),
            "duration": scene.get("duration"),
        },
        "scene_type": scene.get("scene_type"),
        "audio_cues": audio_cues,
        "seed_image_analysis": seed_info,
        "scene_label": manifest_entry.get("scene_label", "") if manifest_entry else "",
        "scene_description": manifest_entry.get("scene_description", "") if manifest_entry else "",
        "audio_focus": manifest_entry.get("audio_focus", "") if manifest_entry else "",
        "sync_timing": manifest_entry.get("sync_timing", "") if manifest_entry else "",
        "lyric_focus": manifest_entry.get("lyric_focus", "") if manifest_entry else "",
        "camera": manifest_entry.get("camera", "") if manifest_entry else "",
        "motion": manifest_entry.get("motion", "") if manifest_entry else "",
        "performance_action": manifest_entry.get("performance_action", "") if manifest_entry else "",
        "continuity": manifest_entry.get("continuity", "") if manifest_entry else "",
        "negative_prompt": manifest_entry.get("negative_prompt", "") if manifest_entry else "",
    }


def build_fresh_prompt(file_stem, context):
    tr = context.get("time_range", {})
    seed = context.get("seed_image_analysis", {})
    cues = context.get("audio_cues", {})
    lines = [f"Music video scene for {file_stem}."]
    if tr.get("start") is not None and tr.get("end") is not None:
        lines.append(f"This scene covers {float(tr['start']):.2f}s to {float(tr['end']):.2f}s of the provided audio.")
    if context.get("scene_label"):
        lines.append(f"Scene label: {context['scene_label']}.")
    if context.get("scene_description"):
        lines.append(f"Scene description: {context['scene_description']}.")
    elif seed.get("filename_prompt_hint"):
        lines.append(f"Scene description from seed filename: {seed['filename_prompt_hint']}.")
    else:
        lines.append("Scene description: generate a fresh scene from this specific seed image and this exact audio segment; do not reuse a generic project prompt.")
    if context.get("audio_focus"):
        lines.append(f"Audio focus: {context['audio_focus']}.")
    if cues.get("status") == "analyzed":
        lines.append(f"Detected music cues: {cues.get('energy_label')}; {cues.get('onset_label')}; {cues.get('brightness_label')}.")
        if cues.get("strong_onset_times_seconds"):
            lines.append(f"Strong visual hit times in the full song timeline: {cues['strong_onset_times_seconds']} seconds.")
        lines.append(f"Sync rule: {cues.get('movement_sync_hint')} {cues.get('camera_sync_hint')}")
    if context.get("sync_timing"):
        lines.append(f"User sync timing: {context['sync_timing']}.")
    if context.get("lyric_focus"):
        lines.append(f"Lyric/vocal focus: {context['lyric_focus']}.")
    if context.get("performance_action"):
        lines.append(f"Performance action: {context['performance_action']}.")
    if context.get("motion"):
        lines.append(f"Motion: {context['motion']}.")
    if context.get("camera"):
        lines.append(f"Camera: {context['camera']}.")
    if context.get("continuity"):
        lines.append(f"Continuity: {context['continuity']}.")

    seed_bits = []
    if seed.get("orientation"):
        seed_bits.append(f"{seed['orientation']} seed image")
    if seed.get("lighting_hint"):
        seed_bits.append(f"{seed['lighting_hint']} lighting basis")
    if seed.get("contrast_hint"):
        seed_bits.append(f"{seed['contrast_hint']} composition")
    if seed.get("filename_prompt_hint"):
        seed_bits.append(f"filename concept: {seed['filename_prompt_hint']}")
    if seed_bits:
        lines.append("Seed image guidance: preserve seed-image identity and composition; " + "; ".join(seed_bits) + ".")

    lines.append("Generate this scene as a fresh shot-specific prompt, not a generic Holy Cheeks or generic music-video prompt.")
    lines.append("All visible movement must stay synchronized to the provided scene audio, especially kick, snare, bass drops, vocal accents, and detected transient hits.")
    avoid = context.get("negative_prompt") or "face warping, extra limbs, random costume changes, off-beat motion, random scene changes, chaotic camera movement, loss of seed-image identity"
    lines.append(f"Avoid: {avoid}.")
    return normalize_text(" ".join(lines), PROMPT_MAX_CHARS)


def make_preview(plan, output_path):
    lines = ["# music video pipeline fresh scene prompt preview", "", f"Scene count: {len(plan.get('results', []))}", ""]
    for item in plan.get("results", []):
        context = item.get("scene_prompt_context", {})
        seed = context.get("seed_image_analysis", {}) if isinstance(context, dict) else {}
        cues = context.get("audio_cues", {}) if isinstance(context, dict) else {}
        lines.append(f"## Scene {int(item.get('clip_index', 0)):02d}")
        lines.append(f"Seed: {Path(item.get('seed_image_used', '')).name}")
        if seed:
            lines.append(f"Seed analysis: {seed.get('analysis_method')} | {seed.get('orientation', 'unknown')} | {seed.get('lighting_hint', '')} | {seed.get('contrast_hint', '')}")
        if cues:
            lines.append(f"Audio cue status: {cues.get('status')}")
            if cues.get("status") == "analyzed":
                lines.append(f"Audio cues: {cues.get('energy_label')}; {cues.get('onset_label')}; {cues.get('brightness_label')}")
                lines.append(f"Strong hit times: {cues.get('strong_onset_times_seconds')}")
        if context.get("scene_description"):
            lines.append(f"Scene description: {context.get('scene_description')}")
        lines.append(f"Prompt chars: {len(item.get('prompt_text', ''))}")
        lines.append("Final prompt:")
        lines.append(item.get("prompt_text", ""))
        lines.append("")
    problems = plan.get("scene_prompting", {}).get("problems", [])
    if problems:
        lines.append("## Problems")
        for problem in problems:
            lines.append(f"- {problem}")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text("\n".join(lines), encoding="utf-8")


def apply_scene_prompts(plan_json, seed_dir, output_json=None, manifest_json=None, strict=False, preview_md=None):
    plan = read_json(plan_json)
    manifest, manifest_problem = load_scene_manifest(manifest_json)
    labeled, unlabeled = collect_seed_images(seed_dir)
    problems = []
    if manifest_problem:
        problems.append(manifest_problem)
    assignments = []
    for item in plan.get("results", []):
        clip_index = int(item.get("clip_index"))
        manifest_entry = manifest.get(clip_index, {})
        seed_path, method, seed_problems = choose_seed_image(seed_dir, manifest_entry, labeled, unlabeled, clip_index, item.get("seed_image_used"), strict)
        problems.extend(seed_problems)
        if not seed_path:
            continue
        context = build_scene_context(plan, item, seed_path, manifest_entry)
        if "base_prompt_text" not in item:
            item["base_prompt_text"] = item.get("prompt_text", "")
        item["seed_image_used"] = str(seed_path.resolve())
        item["scene_prompt_context"] = context
        item["prompt_text"] = build_fresh_prompt(item.get("file_stem", plan.get("file_stem", "song")), context)
        item["scene_prompt_assignment"] = {
            "method": method,
            "seed_file": seed_path.name,
            "fresh_scene_prompt": True,
            "prompt_chars": len(item["prompt_text"]),
        }
        assignments.append({
            "clip_index": clip_index,
            "method": method,
            "seed_file": seed_path.name,
            "prompt_chars": len(item["prompt_text"]),
            "audio_cue_status": context.get("audio_cues", {}).get("status"),
            "scene_description": context.get("scene_description", ""),
            "filename_prompt_hint": context.get("seed_image_analysis", {}).get("filename_prompt_hint", ""),
        })
    plan["scene_prompting"] = {
        "fresh_scene_prompts": True,
        "main_audio_analyzed_per_scene": True,
        "seed_images_inspected": True,
        "semantic_seed_image_captioning": False,
        "semantic_seed_image_captioning_note": "Local Python inspects filename and image metadata. Add a vision-caption provider later for full visual scene understanding.",
        "manifest_json": str(Path(manifest_json).resolve()) if manifest_json else None,
        "assignments": assignments,
        "problems": problems,
    }
    destination = output_json or plan_json
    write_json(destination, plan)
    if preview_md:
        make_preview(plan, preview_md)
    return plan


def write_template(output_path):
    template = {
        "scenes": [
            {
                "scene": 1,
                "seed_file": "scene_01_intro_walk_forward.png",
                "scene_label": "intro walk-in",
                "scene_description": "Establish the performers walking forward in clean formation at the start of the music video.",
                "audio_focus": "Opening groove and first rhythmic pulse.",
                "sync_timing": "Keep footfalls and subtle shoulder movement locked to the kick and snare.",
                "lyric_focus": "Opening setup phrase before the main hook.",
                "performance_action": "Confident synchronized walk with restrained groove.",
                "camera": "Smooth backward tracking shot in vertical reel framing.",
                "motion": "Subtle groove on beat; no major dance hit yet.",
                "continuity": "Keep wardrobe, faces, group spacing, and walking direction consistent into scene 2.",
                "negative_prompt": "avoid face warping, extra limbs, random costume changes, off-beat motion"
            },
            {
                "scene": 2,
                "seed_file": "scene_02_over_shoulder_glance.png",
                "scene_label": "over-shoulder build",
                "scene_description": "Performers continue walking, then glance back over their shoulders as the music energy builds.",
                "audio_focus": "Pre-hook build, stronger drums, and vocal emphasis.",
                "sync_timing": "Time the glance and body accent to the strongest downbeat in this scene.",
                "lyric_focus": "Anticipation phrase leading into the next visual hit.",
                "performance_action": "Playful confident glance back with controlled lower-body accent.",
                "camera": "Slight side arc while tracking backward.",
                "motion": "Controlled accent on downbeat; no random shaking.",
                "continuity": "Maintain same performers, wardrobe, and camera geography from scene 1.",
                "negative_prompt": "avoid explicit framing, chaotic motion, off-beat gestures, face distortion"
            }
        ]
    }
    write_json(output_path, template)
    return template


def main():
    parser = argparse.ArgumentParser(description="music video pipeline scene prompter")
    sub = parser.add_subparsers(dest="command", required=True)
    apply_parser = sub.add_parser("apply")
    apply_parser.add_argument("--plan-json", required=True)
    apply_parser.add_argument("--seed-dir", default="inputs\\ltx_seed_images")
    apply_parser.add_argument("--manifest-json", default=None)
    apply_parser.add_argument("--output", default=None)
    apply_parser.add_argument("--strict", action="store_true")
    apply_parser.add_argument("--preview-md", default="outputs\\ltx_video_run\\fresh_scene_prompt_preview.md")
    template_parser = sub.add_parser("template")
    template_parser.add_argument("--output", default="inputs\\ltx_seed_images\\scene_manifest_template.json")
    args = parser.parse_args()
    if args.command == "template":
        write_template(args.output)
        print("Scene manifest template written.")
        print(Path(args.output).resolve())
        return
    plan = apply_scene_prompts(args.plan_json, args.seed_dir, args.output, args.manifest_json, args.strict, args.preview_md)
    prompting = plan.get("scene_prompting", {})
    print("Fresh scene prompting complete.")
    print(f"Assignments: {len(prompting.get('assignments', []))}")
    for assignment in prompting.get("assignments", []):
        print(f"Scene {assignment['clip_index']:02d}: {assignment['seed_file']} | {assignment['audio_cue_status']} | {assignment['prompt_chars']} chars")
    for problem in prompting.get("problems", []):
        print(f"NOTE: {problem}")
    if args.preview_md:
        print(f"Preview: {Path(args.preview_md).resolve()}")


if __name__ == "__main__":
    main()
