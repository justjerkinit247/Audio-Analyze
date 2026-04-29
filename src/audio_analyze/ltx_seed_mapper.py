from pathlib import Path
import argparse
import json
import re


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
    "seed", "image", "img", "ltx", "holy", "cheeks", "gospel", "twerk",
    "png", "jpg", "jpeg", "webp", "final", "v1", "v2", "new"
}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def scene_number_from_name(path):
    stem = Path(path).stem
    normalized = stem.replace(".", "_")
    for pattern in SCENE_PATTERNS:
        match = pattern.search(normalized)
        if match:
            return int(match.group(1))
    return None


def hint_from_filename(path):
    stem = Path(path).stem
    cleaned = stem.replace(".", "_")
    for pattern in LABEL_CLEAN_PATTERNS:
        cleaned = pattern.sub("_", cleaned)
    tokens = re.split(r"[_\-\s]+", cleaned)
    words = []
    for token in tokens:
        token = token.strip().lower()
        if not token or token.isdigit() or token in STOP_TOKENS:
            continue
        words.append(token)
    hint = " ".join(words).strip()
    return hint[:PROMPT_HINT_MAX_CHARS]


def normalize_directive_text(text):
    if not text:
        return ""
    text = str(text).replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:PROMPT_HINT_MAX_CHARS]


def load_scene_manifest(manifest_path):
    if not manifest_path:
        return {}
    path = Path(manifest_path)
    if not path.exists():
        raise FileNotFoundError(f"Scene manifest not found: {path.resolve()}")
    raw = read_json(path)
    if isinstance(raw, dict) and "scenes" in raw:
        raw_scenes = raw["scenes"]
    elif isinstance(raw, list):
        raw_scenes = raw
    else:
        raw_scenes = []
    manifest = {}
    for entry in raw_scenes:
        if not isinstance(entry, dict):
            continue
        scene = entry.get("scene") or entry.get("clip_index") or entry.get("clip")
        if scene is None:
            continue
        scene = int(scene)
        manifest[scene] = {
            "prompt_addon": normalize_directive_text(entry.get("prompt_addon") or entry.get("direction") or entry.get("prompt_hint")),
            "negative_prompt": normalize_directive_text(entry.get("negative_prompt") or entry.get("avoid")),
            "camera": normalize_directive_text(entry.get("camera")),
            "motion": normalize_directive_text(entry.get("motion")),
            "seed_file": normalize_directive_text(entry.get("seed_file") or entry.get("seed")),
            "notes": normalize_directive_text(entry.get("notes")),
        }
    return manifest


def collect_labeled_seed_images(seed_dir):
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


def choose_manifest_seed(seed_dir, manifest_entry):
    requested = (manifest_entry or {}).get("seed_file")
    if not requested:
        return None
    candidate = Path(requested)
    if candidate.is_absolute() and candidate.exists():
        return candidate
    candidate = Path(seed_dir) / requested
    if candidate.exists():
        return candidate
    return None


def build_scene_addon(seed_hint, manifest_entry, use_filename_hints=True):
    pieces = []
    if use_filename_hints and seed_hint:
        pieces.append(f"Seed filename direction: {seed_hint}.")
    if manifest_entry:
        if manifest_entry.get("prompt_addon"):
            pieces.append(f"Scene direction: {manifest_entry['prompt_addon']}.")
        if manifest_entry.get("camera"):
            pieces.append(f"Camera instruction: {manifest_entry['camera']}.")
        if manifest_entry.get("motion"):
            pieces.append(f"Motion instruction: {manifest_entry['motion']}.")
        if manifest_entry.get("negative_prompt"):
            pieces.append(f"Avoid: {manifest_entry['negative_prompt']}.")
    return " ".join(pieces).strip()


def rebuild_prompt(original_prompt, scene_addon):
    base = original_prompt.strip()
    if not scene_addon:
        return base
    marker = "Scene-specific control layer:"
    if marker in base:
        base = base.split(marker)[0].strip()
    addon = f" {marker} {scene_addon}"
    max_base_len = PROMPT_MAX_CHARS - len(addon)
    if max_base_len < 1000:
        addon = addon[: max(0, PROMPT_MAX_CHARS - 1000)]
        max_base_len = PROMPT_MAX_CHARS - len(addon)
    return (base[:max_base_len].rstrip() + addon).strip()


def make_preview_report(plan, output_path):
    lines = []
    lines.append("# LTX Scene Control Preview")
    lines.append("")
    lines.append(f"Scene count: {len(plan.get('results', []))}")
    lines.append("")
    for item in plan.get("results", []):
        assignment = item.get("seed_assignment", {})
        lines.append(f"## Scene {int(item.get('clip_index', 0)):02d}")
        lines.append(f"Seed: {assignment.get('seed_file', item.get('seed_image_used'))}")
        lines.append(f"Method: {assignment.get('method')}")
        if assignment.get("filename_prompt_hint"):
            lines.append(f"Filename hint: {assignment['filename_prompt_hint']}")
        if assignment.get("scene_addon"):
            lines.append(f"Scene add-on: {assignment['scene_addon']}")
        lines.append(f"Prompt chars: {len(item.get('prompt_text', ''))}")
        lines.append("")
    problems = plan.get("seed_mapping", {}).get("problems", [])
    if problems:
        lines.append("## Notes / Problems")
        for problem in problems:
            lines.append(f"- {problem}")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text("\n".join(lines), encoding="utf-8")


def apply_seed_mapping(plan_json, seed_dir, output_json=None, strict=False, manifest_json=None, no_filename_hints=False, preview_md=None):
    plan = read_json(plan_json)
    labeled, unlabeled = collect_labeled_seed_images(seed_dir)
    manifest = load_scene_manifest(manifest_json)

    problems = []
    assignments = []

    for item in plan.get("results", []):
        clip_index = int(item.get("clip_index"))
        existing_seed = item.get("seed_image_used")
        manifest_entry = manifest.get(clip_index, {})
        manifest_seed = choose_manifest_seed(seed_dir, manifest_entry)

        if manifest_seed:
            chosen = manifest_seed
            method = "manifest_seed_file"
        elif clip_index in labeled:
            chosen = labeled[clip_index][0]
            method = "scene_label"
            if len(labeled[clip_index]) > 1:
                problems.append(
                    f"Scene {clip_index}: multiple labeled seed images found; using {chosen.name}"
                )
        elif strict:
            problems.append(f"Scene {clip_index}: no labeled seed image found")
            chosen = Path(existing_seed) if existing_seed else None
            method = "missing_strict"
        elif existing_seed:
            chosen = Path(existing_seed)
            method = "existing_plan_seed"
        elif unlabeled:
            chosen = unlabeled[(clip_index - 1) % len(unlabeled)]
            method = "unlabeled_round_robin"
        else:
            problems.append(f"Scene {clip_index}: no usable seed image found")
            chosen = None
            method = "missing"

        if chosen:
            seed_hint = hint_from_filename(chosen)
            scene_addon = build_scene_addon(seed_hint, manifest_entry, use_filename_hints=not no_filename_hints)
            if "base_prompt_text" not in item:
                item["base_prompt_text"] = item.get("prompt_text", "")
            item["seed_image_used"] = str(Path(chosen).resolve())
            item["prompt_text"] = rebuild_prompt(item.get("base_prompt_text", item.get("prompt_text", "")), scene_addon)
            if len(item["prompt_text"]) > PROMPT_MAX_CHARS:
                problems.append(f"Scene {clip_index}: prompt is over {PROMPT_MAX_CHARS} characters after mapping")
            item["seed_assignment"] = {
                "method": method,
                "seed_file": Path(chosen).name,
                "scene_label_expected": f"scene_{clip_index:02d}",
                "filename_prompt_hint": seed_hint,
                "scene_addon": scene_addon,
                "manifest_applied": bool(manifest_entry),
                "prompt_chars": len(item["prompt_text"]),
            }
            assignments.append(
                {
                    "clip_index": clip_index,
                    "seed_file": Path(chosen).name,
                    "method": method,
                    "filename_prompt_hint": seed_hint,
                    "scene_addon": scene_addon,
                    "prompt_chars": len(item["prompt_text"]),
                }
            )

    plan["seed_mapping"] = {
        "seed_dir": str(Path(seed_dir).resolve()),
        "strict": strict,
        "manifest_json": str(Path(manifest_json).resolve()) if manifest_json else None,
        "filename_hints_enabled": not no_filename_hints,
        "assignments": assignments,
        "problems": problems,
        "label_examples": [
            "scene_01_intro_walk_forward.png",
            "scene_02_over_shoulder_glance.webp",
            "clip_03_twerk_accent_wide_angle.jpg",
            "s04_group_walk_camera_arc.jpeg",
        ],
    }

    destination = output_json or plan_json
    write_json(destination, plan)
    if preview_md:
        make_preview_report(plan, preview_md)
    return plan


def write_template(output_path):
    template = {
        "scenes": [
            {
                "scene": 1,
                "seed_file": "scene_01_intro_walk_forward.png",
                "prompt_addon": "establish the performers walking forward with clean group formation",
                "camera": "smooth backward tracking shot, vertical reel framing",
                "motion": "confident synchronized walk, subtle groove on the beat",
                "negative_prompt": "avoid face warping, extra limbs, random costume changes",
                "notes": "Use this as a planning/control template only."
            },
            {
                "scene": 2,
                "seed_file": "scene_02_over_shoulder_glance.png",
                "prompt_addon": "performers glance back over shoulder with playful stage confidence",
                "camera": "slight side arc while tracking backward",
                "motion": "controlled hip accent on the downbeat",
                "negative_prompt": "avoid explicit framing, chaotic motion, off-beat gestures",
                "notes": "Edit these values per scene."
            }
        ]
    }
    write_json(output_path, template)
    return template


def main():
    parser = argparse.ArgumentParser(description="Map labeled LTX seed images and scene-control hints into an existing plan JSON.")
    sub = parser.add_subparsers(dest="command", required=True)

    apply_parser = sub.add_parser("apply")
    apply_parser.add_argument("--plan-json", required=True)
    apply_parser.add_argument("--seed-dir", default="inputs\\ltx_seed_images")
    apply_parser.add_argument("--output", default=None, help="Optional output plan path. If omitted, rewrites the input plan in place.")
    apply_parser.add_argument("--strict", action="store_true", help="Require every scene to have a labeled seed image.")
    apply_parser.add_argument("--manifest-json", default=None, help="Optional JSON file with per-scene prompt/camera/motion overrides.")
    apply_parser.add_argument("--no-filename-hints", action="store_true", help="Assign images by filename but do not inject filename words into prompt_text.")
    apply_parser.add_argument("--preview-md", default="outputs\\ltx_video_run\\scene_control_preview.md")

    template_parser = sub.add_parser("template")
    template_parser.add_argument("--output", default="inputs\\ltx_seed_images\\scene_manifest_template.json")

    args = parser.parse_args()

    if args.command == "template":
        write_template(args.output)
        print("Scene manifest template written.")
        print(Path(args.output).resolve())
        return

    plan = apply_seed_mapping(
        plan_json=args.plan_json,
        seed_dir=args.seed_dir,
        output_json=args.output,
        strict=args.strict,
        manifest_json=args.manifest_json,
        no_filename_hints=args.no_filename_hints,
        preview_md=args.preview_md,
    )

    mapping = plan.get("seed_mapping", {})
    print("LTX scene control mapping complete.")
    print(f"Assignments: {len(mapping.get('assignments', []))}")
    print(f"Filename hints enabled: {mapping.get('filename_hints_enabled')}")
    for assignment in mapping.get("assignments", []):
        print(f"Scene {assignment['clip_index']:02d}: {assignment['seed_file']} ({assignment['method']})")
        if assignment.get("scene_addon"):
            print(f"  Add-on: {assignment['scene_addon']}")
    for problem in mapping.get("problems", []):
        print(f"NOTE: {problem}")
    if args.preview_md:
        print(f"Preview: {Path(args.preview_md).resolve()}")


if __name__ == "__main__":
    main()
