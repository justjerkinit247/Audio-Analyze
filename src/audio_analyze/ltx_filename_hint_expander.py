from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

try:
    from .path_policy import resolve_runtime_path, serialize_path
except ImportError:
    from path_policy import resolve_runtime_path, serialize_path


ALLOWED_IMAGES = {".jpg", ".jpeg", ".png", ".webp"}
PROMPT_MAX_CHARS = 5000
DEFAULT_MODEL = "gpt-4.1-mini"
MOTION_MARKER = "[MOTION_PROMPT]"
NEGATIVE_MARKER = "[NEGATIVE_PROMPT]"
DEFAULT_PROVIDER = "template"

SCENE_PREFIX_PATTERNS = [
    re.compile(r"^(?:scene|clip|shot|seed|image|img)[_\-\s]*\d{1,4}[_\-\s]*", re.IGNORECASE),
    re.compile(r"^s\d{1,4}[_\-\s]*", re.IGNORECASE),
    re.compile(r"^\d{1,4}[_\-\s]+", re.IGNORECASE),
]

TECHNICAL_STOP_TOKENS = {
    "seed", "image", "img", "ltx", "final", "new", "render", "output", "upscaled",
    "png", "jpg", "jpeg", "webp", "photo", "picture", "frame", "still",
    "v1", "v2", "v3", "v4", "v5", "v6", "v7", "v8", "draft", "test",
}

DEFAULT_NEGATIVE_TERMS = [
    "blurry motion",
    "jittery motion",
    "chaotic camera movement",
    "sudden cuts",
    "warped background",
    "distorted subject",
    "duplicate subject",
    "extra limbs",
    "malformed anatomy",
    "mutated hands or feet",
    "melted faces",
    "text artifacts",
    "logo artifacts",
    "low detail",
    "flicker",
]

BIRD_HINT_TOKENS = {"duck", "bird", "goose", "swan", "crow", "raven", "eagle", "wings", "wing"}


def _collapse_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def clean_scene_hint(filename: str | Path) -> str:
    """Extract the creative scene hint from a seed-image filename.

    The filename is treated as the source of truth. The image file itself is not
    opened or analyzed here.
    """

    stem = Path(filename).stem.lower().lstrip("\ufeff")
    stem = stem.replace(".", "_")
    for pattern in SCENE_PREFIX_PATTERNS:
        stem = pattern.sub("", stem)
    raw_tokens = re.split(r"[^a-z0-9]+", stem)
    words: list[str] = []
    for token in raw_tokens:
        token = token.strip().lower()
        if not token or token.isdigit() or token in TECHNICAL_STOP_TOKENS:
            continue
        words.append(token)
    return _collapse_spaces(" ".join(words))


def subject_specific_negative_terms(scene_hint: str) -> list[str]:
    tokens = set(re.split(r"\W+", scene_hint.lower()))
    terms: list[str] = []
    if tokens & BIRD_HINT_TOKENS:
        terms.extend(["malformed wings", "duplicate wings", "broken beak", "feather smear"])
    return terms


def build_negative_prompt(scene_hint: str, extra_terms: Iterable[str] | None = None) -> str:
    terms = list(DEFAULT_NEGATIVE_TERMS)
    terms.extend(subject_specific_negative_terms(scene_hint))
    if extra_terms:
        terms.extend(str(term).strip() for term in extra_terms if str(term).strip())
    seen = set()
    unique: list[str] = []
    for term in terms:
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(term)
    return ", ".join(unique)


def render_combined_ltx_text(motion_prompt: str, negative_prompt: str) -> str:
    motion_prompt = _collapse_spaces(str(motion_prompt))
    negative_prompt = _collapse_spaces(str(negative_prompt))
    return f"{MOTION_MARKER}\n{motion_prompt}\n\n{NEGATIVE_MARKER}\n{negative_prompt}\n"


def parse_combined_ltx_text(text: str) -> dict[str, str]:
    if MOTION_MARKER not in text or NEGATIVE_MARKER not in text:
        raise ValueError("LTX prompt text must contain [MOTION_PROMPT] and [NEGATIVE_PROMPT] sections.")
    motion = text.split(MOTION_MARKER, 1)[1].split(NEGATIVE_MARKER, 1)[0].strip()
    negative = text.split(NEGATIVE_MARKER, 1)[1].strip()
    if not motion:
        raise ValueError("MOTION_PROMPT section is empty.")
    if not negative:
        raise ValueError("NEGATIVE_PROMPT section is empty.")
    return {"prompt": motion, "negative_prompt": negative}


def template_motion_prompt(scene_hint: str) -> str:
    scene_hint = _collapse_spaces(scene_hint)
    if not scene_hint:
        raise ValueError("Scene hint is empty after filename cleanup.")
    return (
        f"The shot begins from the seed image and develops the scene direction: {scene_hint}. "
        "The main subject moves first with clear, readable motion while the camera responds with a smooth cinematic push, drift, or gentle follow move that preserves the original framing. "
        "Background elements shift subtly over time so the scene feels alive without changing the location or adding unrelated characters. "
        "The action progresses from a quiet first frame into a stronger final moment, with clean temporal continuity, stable subject identity, and controlled movement. "
        "Keep the mood polished, cinematic, and focused on the filename scene hint."
    )


def build_openai_instruction(filename: str, scene_hint: str) -> str:
    return f"""
Expand this seed-image filename scene hint into a cinematic LTX image-to-video motion prompt.

Filename:
{filename}

Scene hint extracted from filename:
{scene_hint}

Return JSON only.

Rules:
- Do not analyze the actual image.
- Use the filename scene hint as the creative source of truth.
- Do not import assumptions from any previous project, genre, song, brand, character, setting, or conversation.
- Do not mention that the prompt came from a filename.
- The motion prompt must be one flowing paragraph.
- Use present tense.
- Focus on what changes over time.
- Include subject movement, camera movement, environmental movement, and cinematic/emotional tone.
- Keep the seed image as the visual anchor.
- Avoid unrelated characters, locations, religious imagery, nightclub imagery, sexual framing, or genre assumptions unless directly present in the filename hint.
- Keep the motion prompt between 80 and 140 words.
- The negative prompt must be a comma-separated cleanup list suitable for LTX.
- Include general cleanup terms and any obvious subject-specific cleanup terms from the hint.
""".strip()


OPENAI_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "filename": {"type": "string"},
        "scene_hint": {"type": "string"},
        "ltx_motion_prompt": {"type": "string"},
        "negative_prompt": {"type": "string"},
        "motion_notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["filename", "scene_hint", "ltx_motion_prompt", "negative_prompt", "motion_notes"],
}


def _extract_output_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text:
        return str(output_text)
    if isinstance(response, dict) and response.get("output_text"):
        return str(response["output_text"])
    raise ValueError("OpenAI response did not include output_text.")


def expand_with_openai(scene_hint: str, filename: str, model: str | None = None, client: Any = None) -> dict[str, Any]:
    if client is None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("OpenAI provider requested, but the openai package is not installed.") from exc
        client = OpenAI()

    response = client.responses.create(
        model=model or os.environ.get("OPENAI_MODEL", DEFAULT_MODEL),
        input=[
            {
                "role": "system",
                "content": (
                    "You convert seed-image filename scene hints into general-purpose LTX "
                    "image-to-video motion prompts. You are literal, project-neutral, and concise."
                ),
            },
            {"role": "user", "content": build_openai_instruction(filename, scene_hint)},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "ltx_filename_hint_expansion",
                "strict": True,
                "schema": OPENAI_SCHEMA,
            }
        },
    )
    return normalize_expansion(json.loads(_extract_output_text(response)), filename=filename, scene_hint=scene_hint, provider="openai")


def expand_with_template(scene_hint: str, filename: str) -> dict[str, Any]:
    return normalize_expansion(
        {
            "filename": filename,
            "scene_hint": scene_hint,
            "ltx_motion_prompt": template_motion_prompt(scene_hint),
            "negative_prompt": build_negative_prompt(scene_hint),
            "motion_notes": [
                "template fallback; no external AI call was made",
                "seed image remains the visual anchor",
                "filename scene hint drives motion, camera, and environment",
            ],
        },
        filename=filename,
        scene_hint=scene_hint,
        provider="template",
    )


def normalize_expansion(data: dict[str, Any], filename: str, scene_hint: str, provider: str) -> dict[str, Any]:
    motion_prompt = _collapse_spaces(data.get("ltx_motion_prompt") or data.get("motion_prompt") or "")
    if not motion_prompt:
        raise ValueError(f"No LTX motion prompt produced for {filename}")
    negative_prompt = _collapse_spaces(data.get("negative_prompt") or build_negative_prompt(scene_hint))
    result = {
        "filename": str(data.get("filename") or filename),
        "scene_hint": str(data.get("scene_hint") or scene_hint),
        "provider": provider,
        "model": data.get("model"),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "ltx_motion_prompt": motion_prompt,
        "negative_prompt": negative_prompt,
        "combined_ltx_text": render_combined_ltx_text(motion_prompt, negative_prompt),
        "motion_notes": list(data.get("motion_notes") or []),
    }
    if result["model"] is None:
        result.pop("model")
    return result


def expand_scene_hint(
    scene_hint: str,
    filename: str = "seed_image.png",
    provider: str = DEFAULT_PROVIDER,
    model: str | None = None,
    client: Any = None,
) -> dict[str, Any]:
    scene_hint = _collapse_spaces(scene_hint)
    if not scene_hint:
        raise ValueError("Scene hint is empty.")
    if provider == "template":
        return expand_with_template(scene_hint, filename)
    if provider == "openai":
        return expand_with_openai(scene_hint, filename, model=model, client=client)
    raise ValueError(f"Unsupported provider: {provider}")


def iter_seed_images(seed_dir: str | Path) -> list[Path]:
    seed_dir = resolve_runtime_path(seed_dir)
    if not seed_dir.exists():
        raise FileNotFoundError(f"Seed image folder not found: {seed_dir.resolve()}")
    images = sorted(path for path in seed_dir.iterdir() if path.is_file() and path.suffix.lower() in ALLOWED_IMAGES)
    if not images:
        raise FileNotFoundError(f"No seed images found in {seed_dir.resolve()}")
    return images


def write_expansion_files(image_path: str | Path, output_dir: str | Path, expansion: dict[str, Any]) -> dict[str, str]:
    image_path = Path(image_path)
    output_dir = resolve_runtime_path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = image_path.stem
    txt_path = output_dir / f"{stem}_ltx.txt"
    json_path = output_dir / f"{stem}_ltx.json"
    txt_path.write_text(expansion["combined_ltx_text"], encoding="utf-8")
    json_path.write_text(json.dumps(expansion, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"txt_path": serialize_path(txt_path), "json_path": serialize_path(json_path)}


def expand_seed_dir(
    seed_dir: str | Path,
    output_dir: str | Path = "inputs/prompts/ltx_filename_hints",
    provider: str = DEFAULT_PROVIDER,
    model: str | None = None,
    client_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    output_records = []
    client = client_factory() if client_factory and provider == "openai" else None
    for image_path in iter_seed_images(seed_dir):
        scene_hint = clean_scene_hint(image_path.name)
        if not scene_hint:
            output_records.append({"filename": image_path.name, "status": "skipped", "reason": "empty filename scene hint"})
            continue
        expansion = expand_scene_hint(scene_hint, filename=image_path.name, provider=provider, model=model, client=client)
        paths = write_expansion_files(image_path, output_dir, expansion)
        output_records.append({"filename": image_path.name, "status": "expanded", "scene_hint": scene_hint, **paths})
    return {
        "status": "complete",
        "seed_dir": serialize_path(seed_dir),
        "output_dir": serialize_path(output_dir),
        "provider": provider,
        "expanded_count": sum(1 for item in output_records if item["status"] == "expanded"),
        "records": output_records,
    }


def compose_plan_prompt(original_prompt: str, expansion: dict[str, Any], replace_prompt: bool = False) -> str:
    combined = expansion["combined_ltx_text"].strip()
    if replace_prompt:
        return combined[:PROMPT_MAX_CHARS]
    base = str(original_prompt or "").strip()
    marker = "Filename-hint LTX motion expansion:"
    if marker in base:
        base = base.split(marker, 1)[0].strip()
    addon = f"\n\n{marker}\n{combined}"
    max_base_len = max(0, PROMPT_MAX_CHARS - len(addon))
    return (base[:max_base_len].rstrip() + addon).strip()


def apply_expansions_to_plan_data(
    plan: dict[str, Any],
    provider: str = DEFAULT_PROVIDER,
    model: str | None = None,
    replace_prompt: bool = False,
    output_dir: str | Path | None = None,
    client_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    client = client_factory() if client_factory and provider == "openai" else None
    records = []
    for item in plan.get("results", []):
        seed_image = item.get("seed_image_used") or item.get("seed_assignment", {}).get("seed_file")
        if not seed_image:
            records.append({"clip_index": item.get("clip_index"), "status": "skipped", "reason": "missing seed image"})
            continue
        filename = Path(str(seed_image)).name
        scene_hint = item.get("seed_filename_prompt_hint") or item.get("seed_assignment", {}).get("filename_prompt_hint") or clean_scene_hint(filename)
        scene_hint = _collapse_spaces(scene_hint)
        if not scene_hint:
            records.append({"clip_index": item.get("clip_index"), "filename": filename, "status": "skipped", "reason": "empty filename scene hint"})
            continue
        expansion = expand_scene_hint(scene_hint, filename=filename, provider=provider, model=model, client=client)
        item["filename_hint_expansion"] = {
            "status": "expanded",
            "provider": provider,
            "scene_hint": scene_hint,
            "ltx_motion_prompt": expansion["ltx_motion_prompt"],
            "negative_prompt": expansion["negative_prompt"],
            "combined_ltx_text": expansion["combined_ltx_text"],
        }
        item["prompt_text"] = compose_plan_prompt(item.get("prompt_text", ""), expansion, replace_prompt=replace_prompt)
        record = {
            "clip_index": item.get("clip_index"),
            "filename": filename,
            "status": "expanded",
            "scene_hint": scene_hint,
            "prompt_chars": len(item["prompt_text"]),
        }
        if output_dir:
            paths = write_expansion_files(filename, output_dir, expansion)
            record.update(paths)
        records.append(record)
    plan["filename_hint_expander"] = {
        "status": "complete",
        "provider": provider,
        "replace_prompt": bool(replace_prompt),
        "expanded_count": sum(1 for item in records if item["status"] == "expanded"),
        "records": records,
    }
    return plan


def apply_expansions_to_plan(
    plan_json: str | Path,
    output_json: str | Path | None = None,
    provider: str = DEFAULT_PROVIDER,
    model: str | None = None,
    replace_prompt: bool = False,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    plan_path = resolve_runtime_path(plan_json)
    plan = json.loads(plan_path.read_text(encoding="utf-8-sig"))
    apply_expansions_to_plan_data(
        plan,
        provider=provider,
        model=model,
        replace_prompt=replace_prompt,
        output_dir=output_dir,
    )
    destination = resolve_runtime_path(output_json or plan_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    return plan


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Expand seed-image filename scene hints into LTX motion prompts.")
    sub = parser.add_subparsers(dest="command", required=True)

    single = sub.add_parser("single", help="Expand one filename scene hint.")
    single.add_argument("filename")
    single.add_argument("--provider", choices=["template", "openai"], default=DEFAULT_PROVIDER)
    single.add_argument("--model", default=None)

    expand_dir_parser = sub.add_parser("expand-dir", help="Create _ltx.txt and _ltx.json files for every seed image in a directory.")
    expand_dir_parser.add_argument("--seed-dir", default="inputs/ltx_seed_images")
    expand_dir_parser.add_argument("--output-dir", default="inputs/prompts/ltx_filename_hints")
    expand_dir_parser.add_argument("--provider", choices=["template", "openai"], default=DEFAULT_PROVIDER)
    expand_dir_parser.add_argument("--model", default=None)

    plan_parser = sub.add_parser("apply-plan", help="Add expanded filename-hint prompts into an existing LTX plan JSON before submit.")
    plan_parser.add_argument("--plan-json", required=True)
    plan_parser.add_argument("--output", default=None)
    plan_parser.add_argument("--output-dir", default=None, help="Optional folder for per-seed _ltx.txt/_ltx.json prompt files.")
    plan_parser.add_argument("--provider", choices=["template", "openai"], default=DEFAULT_PROVIDER)
    plan_parser.add_argument("--model", default=None)
    plan_parser.add_argument("--replace-prompt", action="store_true", help="Use only the filename expansion as prompt_text instead of appending it.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "single":
        scene_hint = clean_scene_hint(args.filename)
        expansion = expand_scene_hint(scene_hint, filename=Path(args.filename).name, provider=args.provider, model=args.model)
        print(expansion["combined_ltx_text"])
        return 0
    if args.command == "expand-dir":
        report = expand_seed_dir(args.seed_dir, args.output_dir, provider=args.provider, model=args.model)
        print(json.dumps(report, indent=2))
        return 0
    if args.command == "apply-plan":
        plan = apply_expansions_to_plan(
            args.plan_json,
            output_json=args.output,
            provider=args.provider,
            model=args.model,
            replace_prompt=args.replace_prompt,
            output_dir=args.output_dir,
        )
        print(json.dumps(plan.get("filename_hint_expander", {}), indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
