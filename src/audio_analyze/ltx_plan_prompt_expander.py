from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
import json

try:
    from .ltx_filename_hint_expander import (
        DEFAULT_OLLAMA_MODEL,
        DEFAULT_PROVIDER,
        NEGATIVE_MARKER,
        MOTION_MARKER,
        clean_scene_hint,
        expand_scene_hint,
    )
    from .path_policy import resolve_runtime_path, serialize_path
except ImportError:
    from ltx_filename_hint_expander import (
        DEFAULT_OLLAMA_MODEL,
        DEFAULT_PROVIDER,
        NEGATIVE_MARKER,
        MOTION_MARKER,
        clean_scene_hint,
        expand_scene_hint,
    )
    from path_policy import resolve_runtime_path, serialize_path


DEFAULT_PLAN_EXPANSION_PROVIDER = "ollama"


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(resolve_runtime_path(path).read_text(encoding="utf-8-sig"))


def write_json(path: str | Path, data: dict[str, Any]) -> None:
    path = resolve_runtime_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _scene_timing_sentence(item: dict[str, Any], plan: dict[str, Any]) -> str:
    scene = item.get("scene") or {}
    idx = scene.get("scene_index") or item.get("clip_index")
    start = scene.get("start")
    end = scene.get("end")
    tempo = (plan.get("analysis") or {}).get("tempo_bpm") or (plan.get("analysis") or {}).get("tempo_bpm_from_full_track")
    if start is None or end is None:
        timing = f"Scene {idx} uses the current planned clip timing."
    else:
        timing = f"Scene {idx} covers {float(start):.2f}s to {float(end):.2f}s of the source audio."
    if tempo:
        timing += f" Motion should feel rhythm-aware around {float(tempo):.2f} BPM without adding unrelated choreography."
    return timing


def build_scene_prompt_from_expansion(item: dict[str, Any], plan: dict[str, Any], expansion: dict[str, Any]) -> str:
    file_stem = item.get("file_stem") or plan.get("file_stem") or "ltx_scene"
    seed_hint = expansion.get("scene_hint") or item.get("seed_filename_prompt_hint") or ""
    timing = _scene_timing_sentence(item, plan)
    return (
        f"Image-to-video continuation for {file_stem}. "
        "Use the seed image as the exact source of truth for subject count, identity, pose, camera angle, framing, lighting, and background. "
        f"Seed filename scene direction: {seed_hint}. "
        f"{timing} "
        "Do not import assumptions from previous projects, genres, songs, characters, religious imagery, nightclub imagery, or dance choreography unless directly present in the seed filename. "
        "Preserve the seed composition and make only the scene motion described below. "
        f"\n\n{MOTION_MARKER}\n{expansion['ltx_motion_prompt']}\n\n{NEGATIVE_MARKER}\n{expansion['negative_prompt']}\n"
    )


def _seed_filename(item: dict[str, Any]) -> str:
    seed_path = item.get("seed_image_used") or (item.get("seed_assignment") or {}).get("seed_image_path") or "seed_image.png"
    return Path(str(seed_path)).name


def expand_plan_data(
    plan: dict[str, Any],
    provider: str = DEFAULT_PLAN_EXPANSION_PROVIDER,
    model: str | None = DEFAULT_OLLAMA_MODEL,
    expander: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    expander = expander or expand_scene_hint
    patched = dict(plan)
    results = []
    expansion_count = 0

    for raw_item in plan.get("results", []):
        item = dict(raw_item)
        filename = _seed_filename(item)
        scene_hint = clean_scene_hint(filename) or item.get("seed_filename_prompt_hint") or filename
        expansion = expander(scene_hint, filename=filename, provider=provider, model=model)
        item["seed_filename_prompt_hint"] = expansion.get("scene_hint", scene_hint)
        item["filename_hint_expansion"] = expansion
        item["prompt_text_before_filename_hint_expansion"] = raw_item.get("prompt_text")
        item["prompt_text"] = build_scene_prompt_from_expansion(item, plan, expansion)
        item["prompt_build_method"] = "filename_hint_expansion"
        item["prompt_expansion_provider"] = provider
        if model:
            item["prompt_expansion_model"] = model
        results.append(item)
        expansion_count += 1

    patched["results"] = results
    patched["filename_hint_expansion"] = {
        "status": "applied",
        "provider": provider,
        "model": model,
        "scene_count": expansion_count,
    }
    patched["prompt_build_method"] = "filename_hint_expansion"
    return patched


def expand_plan_file(
    plan_json: str | Path,
    output_json: str | Path | None = None,
    provider: str = DEFAULT_PLAN_EXPANSION_PROVIDER,
    model: str | None = DEFAULT_OLLAMA_MODEL,
) -> dict[str, Any]:
    plan = read_json(plan_json)
    patched = expand_plan_data(plan, provider=provider, model=model)
    write_json(output_json or plan_json, patched)
    return patched


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Apply filename-hint prompt expansion to an existing LTX plan JSON.")
    parser.add_argument("--plan-json", required=True)
    parser.add_argument("--output", default=None)
    parser.add_argument("--provider", default=DEFAULT_PLAN_EXPANSION_PROVIDER, choices=["template", "openai", "ollama"])
    parser.add_argument("--model", default=DEFAULT_OLLAMA_MODEL)
    args = parser.parse_args()

    patched = expand_plan_file(
        args.plan_json,
        output_json=args.output,
        provider=args.provider,
        model=args.model,
    )
    print("Filename-hint prompt expansion applied.")
    print(f"Scenes: {patched.get('filename_hint_expansion', {}).get('scene_count')}")
    print(f"Provider: {patched.get('filename_hint_expansion', {}).get('provider')}")


if __name__ == "__main__":
    main()
