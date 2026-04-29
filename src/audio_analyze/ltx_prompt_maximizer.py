from pathlib import Path
import argparse
import json
import re


DEFAULT_PROMPT_MAX_CHARS = 5000
DEFAULT_PROMPT_TARGET_CHARS = 4850
MIN_SAFE_TARGET_CHARS = 1000


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def compact(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def safe_truncate(text, max_chars):
    text = compact(text)
    if len(text) <= max_chars:
        return text
    clipped = text[:max_chars].rstrip()
    last_period = clipped.rfind(". ")
    if last_period > max(500, int(max_chars * 0.75)):
        return clipped[: last_period + 1]
    return clipped


def scene_profile(clip_index):
    profiles = {
        1: {
            "scene_role": "opening establishment and character lock-in",
            "camera": "vertical cinematic backward tracking shot, centered group formation, smooth stabilized camera, clean stage geography",
            "motion": "three performers walk forward in rhythm, confident entrance energy, subtle shoulder and hip groove on downbeats",
            "emotion": "playful reverence, polished confidence, performance-ready facial control",
            "continuity": "introduce wardrobe, faces, body proportions, spacing, and sacred-meets-club tone for later scenes",
        },
        2: {
            "scene_role": "over-shoulder attitude and personality reveal",
            "camera": "slight side arc while tracking backward, readable over-shoulder glances, no sudden lens jumps",
            "motion": "performers glance back over their shoulders while continuing forward, two female performers add small rhythmic accents",
            "emotion": "confident, teasing, controlled, never chaotic or explicit",
            "continuity": "keep same characters, same robe-inspired wardrobe, same stage lighting direction, same vertical reel framing",
        },
        3: {
            "scene_role": "peak dance-accent scene",
            "camera": "wide vertical shot with enough full-body visibility to read choreography, slight low-angle energy, smooth tracking",
            "motion": "brief twerk-inspired rhythmic hip accents on beat, clean gospel-club choreography, readable timing at 100 BPM",
            "emotion": "joyful, bold, funny, polished, performance-art confidence",
            "continuity": "movement is dance and choreography, not explicit framing; keep faces stable and limbs anatomically correct",
        },
        4: {
            "scene_role": "group formation and camera movement variation",
            "camera": "controlled camera arc around the group, mild parallax, stage-light shimmer, vertical composition preserved",
            "motion": "group walk continues with synchronized footwork, shoulder rolls, robe movement reacting naturally",
            "emotion": "anthem energy, unified group presence, sacred performance intensity",
            "continuity": "no random scene change, no new performers, no costume swap, no background teleportation",
        },
        5: {
            "scene_role": "closeup confidence and facial identity reinforcement",
            "camera": "medium-close vertical framing alternating readable faces and upper-body rhythm, no aggressive zoom distortion",
            "motion": "subtle head turns, shoulder accents, hand placement controlled and natural, choreography stays on beat",
            "emotion": "charismatic, proud, playful, expressive but not exaggerated",
            "continuity": "face identity must stay consistent with seed image; eyes, mouth, hands, robe folds remain stable",
        },
        6: {
            "scene_role": "final pose and reel endpoint",
            "camera": "smooth settle into strong final composition, stage lights bright, camera stops cleanly without drift",
            "motion": "walk resolves into confident final pose or unified group finish, final beat lands visibly",
            "emotion": "victory, holy-club punchline, polished finish, memorable closing frame",
            "continuity": "end with same characters and wardrobe; no sudden environment change, no distorted last-frame artifacts",
        },
    }
    return profiles.get(int(clip_index), profiles[1])


def build_expansion_sections(item, plan, target_chars):
    clip_index = int(item.get("clip_index", 1))
    profile = scene_profile(clip_index)
    scene = item.get("scene", {})
    assignment = item.get("seed_assignment", {})
    analysis = plan.get("analysis", {})
    seed_hint = assignment.get("filename_prompt_hint") or ""
    scene_addon = assignment.get("scene_addon") or ""
    seed_file = assignment.get("seed_file") or Path(item.get("seed_image_used", "")).name

    sections = [
        f"Maximum-detail director layer for scene {clip_index:02d}.",
        f"Scene role: {profile['scene_role']}.",
        f"Seed image used: {seed_file}. Treat this seed image as the visual anchor for character identity, wardrobe, pose logic, lighting language, framing, and spatial continuity.",
        f"Filename-derived direction: {seed_hint or 'use the assigned scene image as visual reference without adding extra filename direction'}.",
        f"Mapped scene control: {scene_addon or 'preserve the base prompt and prioritize clean music-video continuity'}.",
        f"Timing: this clip represents {scene.get('start', 0)}s to {scene.get('end', '')}s of the source song, duration about {scene.get('duration', '')}s. Motion should feel locked to approximately {analysis.get('tempo_bpm', 'the detected')} BPM.",
        f"Camera: {profile['camera']}. Keep the camera physically plausible. Avoid snap zooms, random jump cuts, warped field of view, spinning camera, or sudden framing changes unless explicitly requested.",
        f"Motion: {profile['motion']}. Movement should be readable, beat-aware, and choreographed rather than chaotic. The performers should continue the forward-walking music-video language already established in the project.",
        f"Performance emotion: {profile['emotion']}. Expressions should be intentional, confident, and stage-ready. Keep the humor and edge polished rather than sleazy.",
        f"Continuity: {profile['continuity']}. Maintain consistent faces, body proportions, robe-inspired white wardrobe, number of performers, lighting direction, and sacred-meets-club Gospel Twerk performance-art tone.",
        "Composition: use vertical short-form framing suitable for reels. Keep important bodies inside frame. Avoid cropping heads, hands, feet, or choreography unless the scene explicitly calls for a closeup.",
        "Lighting and texture: bright crisp high-contrast music-video lighting, clean highlights on white robe fabric, readable skin tones, stage polish, controlled shadows, no dirty low-resolution smearing.",
        "Choreography safety: dance accents should read as rhythmic performance and musical choreography, not explicit sexual framing. Keep the energy bold, comedic, reverent, and polished.",
        "Artifact avoidance: no extra limbs, no duplicate faces, no melted hands, no broken knees, no random performers, no costume mutation, no text overlays, no logos, no watermarks, no low-quality blur, no face-swapping, no scene teleportation.",
        "Audio-reactive feel: even if the model does not perfectly analyze audio, the visible motion should look timed to kicks, snares, and downbeats with subtle accelerations on musical accents.",
        "Edit usefulness: generate a clip that can cut cleanly into adjacent scenes. Start with a stable readable frame, preserve motion direction, and end with a usable transition frame rather than an unstable blur.",
        "Final priority order: character consistency first, beat-synced motion second, camera stability third, choreography readability fourth, polished sacred-club tone fifth.",
    ]

    filler_sentences = [
        "Keep the three-performer group visually consistent and avoid changing their identity between frames.",
        "Use the seed image as the reference for pose, wardrobe, facial identity, and scene composition while still allowing natural video motion.",
        "Preserve clean vertical framing with a professional music-video finish and no random background changes.",
        "Make the motion intentional, physical, and rhythmic, with clear cause-and-effect between body movement and camera movement.",
        "If the model must choose between wild motion and stable continuity, choose stable continuity.",
        "If the model must choose between literal twerk shock and polished choreography, choose polished choreography.",
        "Avoid overcomplicating the scene; make one strong idea read clearly from start to finish.",
    ]

    text = " ".join(sections)
    idx = 0
    while len(text) < target_chars and idx < 200:
        sentence = filler_sentences[idx % len(filler_sentences)]
        if len(text) + len(sentence) + 1 > target_chars:
            break
        text += " " + sentence
        idx += 1
    return text


def maximize_prompt(base_prompt, expansion_text, max_chars, target_chars):
    base_prompt = compact(base_prompt)
    expansion_text = compact(expansion_text)
    marker = "Maximum scene-control expansion:"
    addon = f" {marker} {expansion_text}"
    if len(base_prompt) + len(addon) <= min(max_chars, target_chars):
        return base_prompt + addon
    available_for_addon = max_chars - len(base_prompt) - len(f" {marker} ")
    if available_for_addon >= 500:
        return base_prompt + f" {marker} " + safe_truncate(expansion_text, available_for_addon)
    # If the base prompt itself is too long, keep as much base as possible and still include a useful control layer.
    minimum_addon = safe_truncate(expansion_text, 900)
    base_room = max_chars - len(f" {marker} ") - len(minimum_addon)
    return safe_truncate(base_prompt, base_room) + f" {marker} " + minimum_addon


def maximize_plan_prompts(plan_json, output_json=None, max_chars=DEFAULT_PROMPT_MAX_CHARS, target_chars=DEFAULT_PROMPT_TARGET_CHARS):
    if max_chars < MIN_SAFE_TARGET_CHARS:
        raise ValueError(f"max_chars must be at least {MIN_SAFE_TARGET_CHARS}")
    if target_chars > max_chars:
        target_chars = max_chars
    if target_chars < MIN_SAFE_TARGET_CHARS:
        target_chars = min(max_chars, MIN_SAFE_TARGET_CHARS)

    plan = read_json(plan_json)
    problems = []
    summaries = []

    for item in plan.get("results", []):
        if "base_prompt_text" not in item:
            item["base_prompt_text"] = item.get("prompt_text", "")
        base = item.get("prompt_text", item.get("base_prompt_text", ""))
        if "Maximum scene-control expansion:" in base:
            base = base.split("Maximum scene-control expansion:")[0].strip()
        expansion = build_expansion_sections(item, plan, target_chars=target_chars)
        final_prompt = maximize_prompt(base, expansion, max_chars=max_chars, target_chars=target_chars)
        item["prompt_text"] = final_prompt
        item["prompt_maximizer"] = {
            "enabled": True,
            "max_chars": max_chars,
            "target_chars": target_chars,
            "actual_chars": len(final_prompt),
            "remaining_chars": max_chars - len(final_prompt),
        }
        if len(final_prompt) > max_chars:
            problems.append(f"Scene {item.get('clip_index')}: prompt length {len(final_prompt)} exceeds max {max_chars}")
        summaries.append({
            "clip_index": item.get("clip_index"),
            "actual_chars": len(final_prompt),
            "remaining_chars": max_chars - len(final_prompt),
        })

    plan["prompt_maximizer"] = {
        "max_chars": max_chars,
        "target_chars": target_chars,
        "scene_summaries": summaries,
        "problems": problems,
    }

    destination = output_json or plan_json
    write_json(destination, plan)
    return plan


def main():
    parser = argparse.ArgumentParser(description="Expand LTX scene prompts toward a configurable character ceiling.")
    parser.add_argument("--plan-json", required=True)
    parser.add_argument("--output", default=None)
    parser.add_argument("--prompt-max-chars", type=int, default=DEFAULT_PROMPT_MAX_CHARS)
    parser.add_argument("--prompt-target-chars", type=int, default=DEFAULT_PROMPT_TARGET_CHARS)
    args = parser.parse_args()

    plan = maximize_plan_prompts(
        plan_json=args.plan_json,
        output_json=args.output,
        max_chars=args.prompt_max_chars,
        target_chars=args.prompt_target_chars,
    )

    info = plan.get("prompt_maximizer", {})
    print("LTX prompt maximization complete.")
    print(f"Max chars: {info.get('max_chars')}")
    print(f"Target chars: {info.get('target_chars')}")
    for scene in info.get("scene_summaries", []):
        print(f"Scene {int(scene['clip_index']):02d}: {scene['actual_chars']} chars, {scene['remaining_chars']} remaining")
    for problem in info.get("problems", []):
        print(f"PROBLEM: {problem}")


if __name__ == "__main__":
    main()
