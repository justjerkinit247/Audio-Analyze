from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
import json
import re

try:
    from .ltx_filename_hint_expander import (
        DEFAULT_OLLAMA_MODEL,
        NEGATIVE_MARKER,
        DEFAULT_PROVIDER,
        MOTION_MARKER,
        clean_scene_hint,
        expand_scene_hint,
        render_combined_ltx_text,
    )
    from .ltx_seed_image_analyzer import (
        SEED_IMAGE_DESCRIPTION_MARKER,
        analyze_seed_image,
        failed_seed_image_analysis,
        render_seed_image_description_block,
    )
    from .path_policy import resolve_runtime_path
except ImportError:
    from ltx_filename_hint_expander import (
        DEFAULT_OLLAMA_MODEL,
        NEGATIVE_MARKER,
        DEFAULT_PROVIDER,
        MOTION_MARKER,
        clean_scene_hint,
        expand_scene_hint,
        render_combined_ltx_text,
    )
    from ltx_seed_image_analyzer import (
        SEED_IMAGE_DESCRIPTION_MARKER,
        analyze_seed_image,
        failed_seed_image_analysis,
        render_seed_image_description_block,
    )
    from path_policy import resolve_runtime_path


DEFAULT_PLAN_EXPANSION_PROVIDER = "ollama"
AUDIO_TIMING_MARKER = "[AUDIO_TIMING]"
SUBJECT_LOCK_MARKER = "[SUBJECT_LOCK]"

FEMALE_TOKENS = {"woman", "female", "girl", "lady"}
MALE_TOKENS = {"man", "male", "guy", "gentleman"}
PAIR_TOKENS = {"duet", "pair", "couple", "partners", "partner", "two", "both"}
GROUP_TOKENS = {"choir", "group", "ensemble", "crowd", "team", "dancers", "performers"}


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(resolve_runtime_path(path).read_text(encoding="utf-8-sig"))


def write_json(path: str | Path, data: dict[str, Any]) -> None:
    path = resolve_runtime_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_seconds(value: Any) -> str:
    parsed = _as_float(value)
    return "unknown" if parsed is None else f"{parsed:.2f}s"


def _format_bpm(value: Any) -> str:
    parsed = _as_float(value)
    return "unknown BPM" if parsed is None else f"{parsed:.2f} BPM"


def _scene_tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", str(value or "").lower()))


def build_subject_count_policy(
    filename: str,
    scene_hint: str,
    scene_description: str = "",
) -> dict[str, Any]:
    tokens = _scene_tokens(f"{filename} {scene_hint} {scene_description}")
    has_female = bool(tokens & FEMALE_TOKENS)
    has_male = bool(tokens & MALE_TOKENS)
    has_pair = bool(tokens & PAIR_TOKENS) or (has_female and has_male)
    has_choir = "choir" in tokens
    has_group = bool(tokens & GROUP_TOKENS)
    multiple_subjects = has_pair or has_group

    requirements = [
        "The seed image is authoritative for subject count and body layout.",
        "Preserve every visible person from the seed image; do not add, remove, merge, replace, or hide subjects.",
    ]
    negative_terms = [
        "changed subject count",
        "removed visible subject",
        "added unrelated subject",
        "merged people",
    ]

    if has_pair:
        requirements.append(
            "Keep both visible foreground subjects together as the foreground pair for the complete clip."
        )
        negative_terms.extend(
            [
                "solitary dancer",
                "solo dancer",
                "missing foreground partner",
                "missing visible foreground subject",
            ]
        )

    if has_choir:
        requirements.append(
            "Keep the existing choir visible in the background; the choir may clap or sway subtly but must not disappear."
        )
        negative_terms.extend(
            ["missing choir", "removed background performers", "empty performance background"]
        )
    elif has_group:
        requirements.append(
            "Keep all background group members or performers visible in their original positions."
        )
        negative_terms.append("removed background performers")

    if multiple_subjects:
        requirements.append(
            "Never describe or render this scene as solitary, solo, lone, alone, or single-person."
        )

    return {
        "filename": filename,
        "scene_hint": scene_hint,
        "selection_source": "exact_seed_filename_and_visible_seed_layout",
        "role_policy": "role_neutral_visible_subject_preservation",
        "multiple_subjects": multiple_subjects,
        "has_pair": has_pair,
        "has_choir": has_choir,
        "has_group": has_group,
        "requirements": requirements,
        "negative_terms": negative_terms,
    }


def render_subject_lock_block(policy: dict[str, Any]) -> str:
    return f"{SUBJECT_LOCK_MARKER}\n" + " ".join(policy.get("requirements") or []) + "\n"


def _merge_negative_terms(existing: str, additions: list[str]) -> str:
    terms = [part.strip() for part in str(existing or "").split(",") if part.strip()]
    seen: set[str] = set()
    merged: list[str] = []
    for term in terms + list(additions):
        cleaned = re.sub(r"\s+", " ", str(term or "")).strip().strip(",")
        key = cleaned.lower()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        merged.append(cleaned)
    return ", ".join(merged)


def enforce_subject_count_in_expansion(
    expansion: dict[str, Any],
    *,
    filename: str,
    scene_hint: str,
    scene_description: str = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    policy = build_subject_count_policy(filename, scene_hint, scene_description)
    patched = dict(expansion)
    motion_prompt = re.sub(
        r"\s+", " ", str(patched.get("ltx_motion_prompt") or "").strip()
    )
    original_motion_prompt = motion_prompt

    if policy["multiple_subjects"]:
        replacements = (
            (r"\ba solitary female dancer\b", "the visible foreground pair"),
            (r"\ba solitary male dancer\b", "the visible foreground pair"),
            (r"\ba solitary dancer\b", "the visible foreground pair"),
            (r"\bthe solitary female dancer\b", "the visible foreground pair"),
            (r"\bthe solitary male dancer\b", "the visible foreground pair"),
            (r"\bthe solitary dancer\b", "the visible foreground pair"),
            (r"\bsolitary\b", ""),
            (r"\bsolo\b", ""),
            (r"\blone\b", ""),
            (r"\balone\b", "with the other visible subjects"),
        )
        for pattern, replacement in replacements:
            motion_prompt = re.sub(pattern, replacement, motion_prompt, flags=re.IGNORECASE)
        motion_prompt = re.sub(r"\s+", " ", motion_prompt).strip()

        required_motion_sentences: list[str] = []
        if policy["has_pair"]:
            required_motion_sentences.append(
                "The visible foreground pair remains together throughout the shot; both subjects maintain coordinated grounded motion."
            )
        if policy["has_choir"]:
            required_motion_sentences.append(
                "The existing choir remains visible in the background, clapping and swaying subtly without changing subject count."
            )
        elif policy["has_group"]:
            required_motion_sentences.append(
                "All existing background performers remain visible and maintain restrained supporting motion."
            )
        motion_prompt = " ".join(required_motion_sentences + [motion_prompt]).strip()

    negative_prompt = _merge_negative_terms(
        str(patched.get("negative_prompt") or ""), policy["negative_terms"]
    )

    patched["filename"] = filename
    patched["scene_hint"] = scene_hint
    patched["ltx_motion_prompt"] = motion_prompt
    patched["negative_prompt"] = negative_prompt
    patched["combined_ltx_text"] = render_combined_ltx_text(motion_prompt, negative_prompt)
    patched["subject_count_policy"] = policy
    if motion_prompt != original_motion_prompt:
        patched["ltx_motion_prompt_before_subject_count_guard"] = original_motion_prompt
        notes = list(patched.get("motion_notes") or [])
        notes.append(
            "subject-layout guard removed false solitary wording and restored seed-required visible subjects"
        )
        patched["motion_notes"] = notes

    return patched, policy


def build_audio_timing_metadata(item: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    scene = item.get("scene") or {}
    analysis = plan.get("analysis") or {}
    start = _as_float(scene.get("start"))
    end = _as_float(scene.get("end"))
    duration = _as_float(scene.get("duration"))
    tempo = analysis.get("tempo_bpm") or analysis.get("tempo_bpm_from_full_track")
    beat_alignment_enabled = bool(
        item.get(
            "beat_alignment_enabled",
            plan.get("beat_alignment_enabled", analysis.get("beat_alignment_enabled", False)),
        )
    )

    estimated_beats_in_scene = None
    tempo_float = _as_float(tempo)
    if tempo_float and duration:
        estimated_beats_in_scene = round((duration / 60.0) * tempo_float, 2)

    return {
        "scene_index": scene.get("scene_index") or item.get("clip_index"),
        "source_audio_path": item.get("source_audio_path"),
        "start_seconds": round(start, 3) if start is not None else None,
        "end_seconds": round(end, 3) if end is not None else None,
        "duration_seconds": round(duration, 3) if duration is not None else None,
        "tempo_bpm": round(tempo_float, 3) if tempo_float is not None else None,
        "estimated_beats_in_scene": estimated_beats_in_scene,
        "beat_alignment_enabled": beat_alignment_enabled,
        "scene_type": scene.get("scene_type"),
        "sync_start_rule": scene.get("sync_start_rule"),
        "sync_end_rule": scene.get("sync_end_rule"),
        "sync_policy": analysis.get("sync_policy"),
        "detected_beat_count_full_track": analysis.get("detected_beat_count"),
        "energy_profile": analysis.get("energy_profile"),
        "edit_pacing": analysis.get("edit_pacing"),
        "movement_notes": analysis.get("movement_notes"),
        "camera_notes": analysis.get("camera_notes"),
        "lighting_notes": analysis.get("lighting_notes"),
        "mix_reactivity_notes": analysis.get("mix_reactivity_notes"),
    }


def render_audio_timing_block(audio_timing: dict[str, Any]) -> str:
    scene_index = audio_timing.get("scene_index") or "unknown"
    start = _format_seconds(audio_timing.get("start_seconds"))
    end = _format_seconds(audio_timing.get("end_seconds"))
    duration = _format_seconds(audio_timing.get("duration_seconds"))
    tempo = _format_bpm(audio_timing.get("tempo_bpm"))
    estimated_beats = audio_timing.get("estimated_beats_in_scene")
    beat_text = (
        f"approximately {estimated_beats} beats in this clip"
        if estimated_beats is not None
        else "beat count unavailable for this clip"
    )
    beat_alignment = "enabled" if audio_timing.get("beat_alignment_enabled") else "not enabled"
    scene_type = audio_timing.get("scene_type") or "planned phrase"
    sync_policy = audio_timing.get("sync_policy") or "Use the planned scene timestamp window."
    sync_start_rule = audio_timing.get("sync_start_rule") or "start at planned clip start"
    sync_end_rule = audio_timing.get("sync_end_rule") or "end at planned clip end"
    energy = audio_timing.get("energy_profile") or "unknown energy"
    pacing = audio_timing.get("edit_pacing") or "unknown pacing"
    movement = audio_timing.get("movement_notes") or "match visible motion to the clip rhythm"
    camera = audio_timing.get("camera_notes") or "keep camera motion controlled and rhythm-aware"
    lighting = audio_timing.get("lighting_notes") or "preserve seed-image lighting"
    mix = audio_timing.get("mix_reactivity_notes") or "audio reactivity values unavailable"

    return (
        f"{AUDIO_TIMING_MARKER}\n"
        f"Scene {scene_index} audio window: {start} to {end}, duration {duration}. "
        f"Tempo target: {tempo}; {beat_text}. Beat alignment: {beat_alignment}. "
        f"Scene type: {scene_type}. Sync policy: {sync_policy} "
        f"Start rule: {sync_start_rule}; end rule: {sync_end_rule}. "
        "Motion timing cue: keep visible motion, camera drift, environmental movement, and any major action changes locked to this timestamp window and the detected rhythmic feel. "
        f"Energy/pacing cue: {energy}, {pacing}. Movement cue: {movement}. Camera cue: {camera}. Lighting cue: {lighting}. Mix cue: {mix}.\n"
    )


def _seed_path(item: dict[str, Any]) -> str:
    return str(
        item.get("seed_image_used")
        or (item.get("seed_assignment") or {}).get("seed_image_path")
        or "seed_image.png"
    )


def _seed_filename(item: dict[str, Any]) -> str:
    return Path(_seed_path(item)).name


def build_scene_prompt_from_expansion(
    item: dict[str, Any],
    plan: dict[str, Any],
    expansion: dict[str, Any],
    audio_timing: dict[str, Any] | None = None,
    subject_policy: dict[str, Any] | None = None,
    seed_image_analysis: dict[str, Any] | None = None,
) -> str:
    file_stem = item.get("file_stem") or plan.get("file_stem") or "ltx_scene"
    seed_filename = _seed_filename(item)
    seed_hint = expansion.get("scene_hint") or clean_scene_hint(seed_filename)
    audio_timing = audio_timing or build_audio_timing_metadata(item, plan)
    audio_timing_block = render_audio_timing_block(audio_timing)
    seed_image_analysis = seed_image_analysis or item.get("seed_image_analysis") or {}
    scene_description = str(seed_image_analysis.get("description") or "")
    seed_description_block = render_seed_image_description_block(seed_image_analysis)
    subject_policy = subject_policy or build_subject_count_policy(
        seed_filename, seed_hint, scene_description
    )
    subject_lock_block = render_subject_lock_block(subject_policy)

    return (
        f"Audio-and-image-to-video continuation synchronized to the supplied audio for {file_stem}. "
        "Use the supplied audio as the timing source and the seed image as the authoritative visual source for subject count, identity, pose family, body layout, camera angle, framing, lighting, and background. "
        f"Seed image filename used as the Ollama prompt hint: {seed_filename}. "
        f"Seed filename scene direction: {seed_hint}. "
        "The Gemma seed-image description is observational context only; it must not override visible pixels or supply choreography. "
        "Allow creative motion only within the filename direction, audio timing, subject lock, natural-language seed description, and visible seed-image composition. "
        "Do not import assumptions from previous projects or remove subjects that already exist in the seed image. "
        f"\n\n{subject_lock_block}\n{seed_description_block}\n{audio_timing_block}\n{MOTION_MARKER}\n{expansion['ltx_motion_prompt']}\n\n{NEGATIVE_MARKER}\n{expansion['negative_prompt']}\n"
    )


def _run_seed_image_analysis(
    item: dict[str, Any],
    *,
    model: str | None,
    image_analyzer: Callable[..., dict[str, Any]],
    strict: bool,
) -> dict[str, Any]:
    image_path = _seed_path(item)
    try:
        return image_analyzer(image_path, model=model)
    except Exception as exc:
        if strict:
            raise
        return failed_seed_image_analysis(image_path, exc, model=model)


def expand_plan_data(
    plan: dict[str, Any],
    provider: str = DEFAULT_PLAN_EXPANSION_PROVIDER,
    model: str | None = DEFAULT_OLLAMA_MODEL,
    expander: Callable[..., dict[str, Any]] | None = None,
    image_analyzer: Callable[..., dict[str, Any]] | None = None,
    analyze_images: bool = True,
    strict_image_analysis: bool = False,
) -> dict[str, Any]:
    expander = expander or expand_scene_hint
    image_analyzer = image_analyzer or analyze_seed_image
    patched = dict(plan)
    results = []
    expansion_count = 0
    vision_complete_count = 0

    for raw_item in plan.get("results", []):
        item = dict(raw_item)
        filename = _seed_filename(item)
        scene_hint = clean_scene_hint(filename)
        if not scene_hint:
            raise ValueError(f"Seed image filename produced an empty Ollama prompt hint: {filename}")

        if analyze_images:
            seed_analysis = _run_seed_image_analysis(
                item,
                model=model,
                image_analyzer=image_analyzer,
                strict=strict_image_analysis,
            )
        else:
            seed_analysis = {
                "status": "disabled",
                "provider": "ollama",
                "model": model,
                "description_format": "natural_language",
                "description": "",
                "error": "seed-image analysis was disabled for this run",
            }
        if seed_analysis.get("status") == "complete":
            vision_complete_count += 1

        raw_expansion = expander(
            scene_hint,
            filename=filename,
            provider=provider,
            model=model,
        )
        expansion, subject_policy = enforce_subject_count_in_expansion(
            raw_expansion,
            filename=filename,
            scene_hint=scene_hint,
            scene_description=str(seed_analysis.get("description") or ""),
        )
        audio_timing = build_audio_timing_metadata(item, plan)
        item["seed_filename_used_for_prompt_hint"] = filename
        item["seed_filename_prompt_hint"] = scene_hint
        item["seed_image_analysis"] = seed_analysis
        item["seed_image_description_prompt_block"] = render_seed_image_description_block(seed_analysis)
        item["filename_hint_expansion"] = expansion
        item["subject_count_policy"] = subject_policy
        item["subject_lock_prompt_block"] = render_subject_lock_block(subject_policy)
        item["audio_timing"] = audio_timing
        item["audio_timing_prompt_block"] = render_audio_timing_block(audio_timing)
        item["prompt_text_before_filename_hint_expansion"] = raw_item.get("prompt_text")
        item["prompt_text"] = build_scene_prompt_from_expansion(
            item,
            plan,
            expansion,
            audio_timing=audio_timing,
            subject_policy=subject_policy,
            seed_image_analysis=seed_analysis,
        )
        item["prompt_build_method"] = (
            "seed_filename_ollama_expansion_with_audio_timing_and_subject_lock"
        )
        item["prompt_build_method_version"] = "vision_enriched_natural_language_v1"
        item["prompt_transport_mode"] = "audio_and_image_to_video"
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
        "audio_timing_prompt_blocks": "applied",
        "subject_lock_prompt_blocks": "applied",
        "seed_image_description_prompt_blocks": "applied",
        "seed_filename_source": "exact_seed_image_basename",
        "transport_mode": "audio_and_image_to_video",
    }
    patched["seed_image_analysis"] = {
        "status": "applied" if vision_complete_count == expansion_count else "partial",
        "provider": "ollama",
        "model": model,
        "description_format": "natural_language",
        "scene_count": expansion_count,
        "completed_scene_count": vision_complete_count,
        "marker": SEED_IMAGE_DESCRIPTION_MARKER,
        "observation_policy": "visible_details_only_no_motion_invention",
    }
    patched["prompt_build_method"] = (
        "seed_filename_ollama_expansion_with_audio_timing_and_subject_lock"
    )
    patched["prompt_build_method_version"] = "vision_enriched_natural_language_v1"
    patched["prompt_transport_mode"] = "audio_and_image_to_video"
    return patched


def expand_plan_file(
    plan_json: str | Path,
    output_json: str | Path | None = None,
    provider: str = DEFAULT_PLAN_EXPANSION_PROVIDER,
    model: str | None = DEFAULT_OLLAMA_MODEL,
    *,
    analyze_images: bool = True,
    strict_image_analysis: bool = False,
) -> dict[str, Any]:
    plan = read_json(plan_json)
    patched = expand_plan_data(
        plan,
        provider=provider,
        model=model,
        analyze_images=analyze_images,
        strict_image_analysis=strict_image_analysis,
    )
    write_json(output_json or plan_json, patched)
    return patched


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Apply Ollama seed-image analysis and filename-hint prompt expansion to an existing LTX plan JSON."
    )
    parser.add_argument("--plan-json", required=True)
    parser.add_argument("--output", default=None)
    parser.add_argument(
        "--provider",
        default=DEFAULT_PLAN_EXPANSION_PROVIDER,
        choices=["template", "openai", "ollama"],
    )
    parser.add_argument("--model", default=DEFAULT_OLLAMA_MODEL)
    parser.add_argument("--skip-image-analysis", action="store_true")
    parser.add_argument("--strict-image-analysis", action="store_true")
    args = parser.parse_args()

    patched = expand_plan_file(
        args.plan_json,
        output_json=args.output,
        provider=args.provider,
        model=args.model,
        analyze_images=not args.skip_image_analysis,
        strict_image_analysis=args.strict_image_analysis,
    )
    print("Seed-image analysis and filename-hint prompt expansion applied.")
    print(f"Scenes: {patched.get('filename_hint_expansion', {}).get('scene_count')}")
    print(f"Provider: {patched.get('filename_hint_expansion', {}).get('provider')}")
    print(
        "Vision descriptions: "
        f"{patched.get('seed_image_analysis', {}).get('completed_scene_count')} complete"
    )


if __name__ == "__main__":
    main()
