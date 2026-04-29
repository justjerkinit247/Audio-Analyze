from pathlib import Path
import argparse
import json
import re


ALLOWED_IMAGES = {".jpg", ".jpeg", ".png", ".webp"}
SCENE_PATTERNS = [
    re.compile(r"(?:^|[_\-\s])scene[_\-\s]?(\d{1,2})(?:[_\-\s]|$)", re.IGNORECASE),
    re.compile(r"(?:^|[_\-\s])clip[_\-\s]?(\d{1,2})(?:[_\-\s]|$)", re.IGNORECASE),
    re.compile(r"(?:^|[_\-\s])s(\d{1,2})(?:[_\-\s]|$)", re.IGNORECASE),
]


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


def apply_seed_mapping(plan_json, seed_dir, output_json=None, strict=False):
    plan = read_json(plan_json)
    labeled, unlabeled = collect_labeled_seed_images(seed_dir)

    problems = []
    assignments = []

    for item in plan.get("results", []):
        clip_index = int(item.get("clip_index"))
        existing_seed = item.get("seed_image_used")

        if clip_index in labeled:
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
            item["seed_image_used"] = str(Path(chosen).resolve())
            item["seed_assignment"] = {
                "method": method,
                "seed_file": Path(chosen).name,
                "scene_label_expected": f"scene_{clip_index:02d}",
            }
            assignments.append(
                {
                    "clip_index": clip_index,
                    "seed_file": Path(chosen).name,
                    "method": method,
                }
            )

    plan["seed_mapping"] = {
        "seed_dir": str(Path(seed_dir).resolve()),
        "strict": strict,
        "assignments": assignments,
        "problems": problems,
        "label_examples": [
            "scene_01.png",
            "scene_02_back_shoulder.webp",
            "clip_03_closeup.jpg",
            "s04_wide_angle.jpeg",
        ],
    }

    destination = output_json or plan_json
    write_json(destination, plan)
    return plan


def main():
    parser = argparse.ArgumentParser(description="Map labeled LTX seed images to scene numbers inside an existing plan JSON.")
    parser.add_argument("--plan-json", required=True)
    parser.add_argument("--seed-dir", default="inputs\\ltx_seed_images")
    parser.add_argument("--output", default=None, help="Optional output plan path. If omitted, rewrites the input plan in place.")
    parser.add_argument("--strict", action="store_true", help="Require every scene to have a labeled seed image.")
    args = parser.parse_args()

    plan = apply_seed_mapping(
        plan_json=args.plan_json,
        seed_dir=args.seed_dir,
        output_json=args.output,
        strict=args.strict,
    )

    mapping = plan.get("seed_mapping", {})
    print("LTX seed mapping complete.")
    print(f"Assignments: {len(mapping.get('assignments', []))}")
    for assignment in mapping.get("assignments", []):
        print(f"Scene {assignment['clip_index']:02d}: {assignment['seed_file']} ({assignment['method']})")
    for problem in mapping.get("problems", []):
        print(f"NOTE: {problem}")


if __name__ == "__main__":
    main()
