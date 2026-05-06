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
        7: {
            "scene_role": "mid-video energy lift and movement reset",
            "camera": "wide readable vertical framing, smooth forward or side tracking, stable horizon",
            "motion": "new phrase begins with a clear on-beat body accent, then continuous groove-led walking or vehicle-adjacent motion",
            "emotion": "confident, energized, controlled, hook-ready",
            "continuity": "preserve the same project world, same character identity logic, and same clean music-video language",
        },
        8: {
            "scene_role": "rural whip movement and environment continuity",
            "camera": "wide establishing shot with controlled motion parallax, full subject visibility, no unstable shake",
            "motion": "vehicle or character movement should visibly hit downbeats, with wheel/body motion reading as rhythmic rather than random",
            "emotion": "street-video confidence, rural nighttime attitude, polished swagger",
            "continuity": "maintain rural neighborhood geography, nighttime lighting continuity, and vehicle identity if car appears",
        },
        9: {
            "scene_role": "beat-punch transition scene",
            "camera": "clear wide or medium-wide angle designed to cut cleanly on a downbeat",
            "motion": "one strong movement phrase starts on beat 1, lands a visible accent halfway through, and ends on a stable beat-ready frame",
            "emotion": "impactful, clean, not chaotic",
            "continuity": "keep the same seed-image identity and avoid introducing a new unrelated scene world",
        },
        10: {
            "scene_role": "late-video momentum scene",
            "camera": "smooth tracking with readable subject motion, no random zoom or drift",
            "motion": "movement accents should follow kick-snare pulse with stronger emphasis on phrase starts and scene ending",
            "emotion": "rising confidence, music-video polish",
            "continuity": "preserve wardrobe, car, rural neighborhood, and character identity established by the seed imagery",
        },
        11: {
            "scene_role": "pre-final hook reinforcement",
            "camera": "controlled cinematic angle that creates anticipation for the final scene",
            "motion": "performer or vehicle movement should tighten rhythmically, ending with a usable downbeat transition frame",
            "emotion": "focused, confident, about to land the final punchline",
            "continuity": "same world, same car/character logic, no visual teleportation",
        },
        12: {
            "scene_role": "final hero endpoint",
            "camera": "wide or medium-wide final composition with a clean resolved endpoint",
            "motion": "final motion lands clearly on the last downbeat, then stabilizes for the closing frame",
            "emotion": "victory, final pose, polished music-video finish",
            "continuity": "end with the same visual world and no distorted last-frame artifacts",
        },
    }
    return profiles.get(int(clip_index), profiles[1])


def build_audio_to_video_beat_instruction(item, plan):
    """Build prompt text that tells the audio-to-video model how to use the supplied audio."""
    scene = item.get("scene", {})
    analysis = plan.get("analysis", {})
    bpm = analysis.get("tempo_bpm")
    start = float(scene.get("start", 0) or 0)
    duration = float(scene.get("duration", 0) or 0)
    end = float(scene.get("end", start + duration) or (start + duration))
    beat_seconds = 60.0 / float(bpm) if bpm else None
    beat_count = round(duration / beat_seconds) if beat_seconds else None
    midpoint = start + (duration / 2.0)

    if bpm and beat_seconds and beat_count:
        return (
            f"Audio-to-video timing mandate: use the uploaded scene audio as the primary timing authority. "
            f"The song is approximately {float(bpm):.2f} BPM, one beat is about {beat_seconds:.3f} seconds, and this scene spans "
            f"{start:.2f}s to {end:.2f}s for about {duration:.2f}s, roughly {beat_count} beats. "
            f"Begin the visible action exactly on the first downbeat of this clip. Place body hits, car motion accents, door swings, foot plants, "
            f"head turns, wheel movement, camera pushes, and pose changes on kicks, snares, downbeats, or clear subdivisions of the beat. "
            f"Create one readable movement phrase: start on beat 1, land a strong visible accent around {midpoint:.2f}s, and end on a stable frame that can cut cleanly on the next downbeat. "
            f"Do not drift off tempo, do not make random motion between beats, and do not create a scene change that ignores the supplied audio rhythm."
        )
    return (
        "Audio-to-video timing mandate: use the uploaded scene audio as the primary timing authority. "
        "Start visible action on the first downbeat, make movement accents land on kicks and snares, and end on a stable beat-ready frame. "
        "Do not drift off tempo or create random motion that ignores the supplied audio."
    )


def build_expansion_sections(item, plan, target_chars):
    clip_index = int(item.get("clip_index", 1))
    profile = scene_profile(clip_index)
    scene = item.get("scene", {})
    assignment = item.get("seed_assignment", {})
    analysis = plan.get("analysis", {})
    seed_hint = assignment.get("filename_prompt_hint") or ""
    scene_addon = assignment.get("scene_addon") or ""
    seed_file = assignment.get("seed_file") or Path(item.get("seed_image_used", "")).name
    beat_instruction = build_audio_to_video_beat_instruction(item, plan)

    sections = [
        f"Maximum-detail director layer for scene {clip_index:02d}.",
        f"Scene role: {profile['scene_role']}.",
        f"Seed image used: {seed_file}. Treat this seed image as the visual anchor for character identity, wardrobe, pose logic, lighting language, framing, and spatial continuity.",
        f"Filename-derived direction: {seed_hint or 'use the assigned scene image as visual reference without adding extra filename direction'}.",
        f"Mapped scene control: {scene_addon or 'preserve the base prompt and prioritize clean music-video continuity'}.",
        beat_instruction,
        f"Timing: this clip represents {scene.get('start', 0)}s to {scene.get('end', '')}s of the source song, duration about {scene.get('duration', '')}s. Motion should feel locked to approximately {analysis.get('tempo_bpm', 'the detected')} BPM.",
        f"Camera: {profile['camera']}. Keep the camera physically plausible. Avoid snap zooms, random jump cuts, warped field of view, spinning camera, or sudden framing changes unless explicitly requested.",
        f"Motion: {profile['motion']}. Movement should be readable, beat-aware, and choreographed rather than chaotic. The performers should continue the forward-walking music-video language already established in the project.",
        f"Performance emotion: {profile['emotion']}. Expressions should be intentional, confident, and stage-ready. Keep the humor and edge polished rather than sleazy.",
        f"Continuity: {profile['continuity']}. Maintain consistent faces, body proportions, robe-inspired white wardrobe, number of performers, lighting direction, and sacred-meets-club Gospel Twerk performance-art tone.",
        "Composition: use vertical short-form framing suitable for reels. Keep important bodies inside frame. Avoid cropping heads, hands, feet, or choreography unless the scene explicitly calls for a closeup.",
        "Lighting and texture: bright crisp high-contrast music-video lighting, clean highlights on white robe fabric, readable skin tones, stage polish, controlled shadows, no dirty low-resolution smearing.",
        "Choreography safety: dance accents should read as rhythmic performance and musical choreography, not explicit sexual framing. Keep the energy bold, comedic, reverent, and polished.",
        "Artifact avoidance: no extra limbs, no duplicate faces, no melted hands, no broken knees, no random performers, no costume mutation, no text overlays, no logos, no watermarks, no low-quality blur, no face-swapping, no scene teleportation.",
        "Audio-reactive feel: the visible motion must appear driven by the supplied audio, with clear accelerations, impacts, and pose changes on kicks, snares, downbeats, and subdivisions.",
        "Edit usefulness: generate a clip that can cut cleanly into adjacent scenes. Start with a stable readable frame, preserve motion direction, and end with a usable transition frame rather than an unstable blur.",
        "Final priority order: supplied audio rhythm first, character consistency second, beat-synced motion third, camera stability fourth, choreography readability fifth, polished sacred-club tone sixth.",
    ]

    filler_sentences = [
        "Use the uploaded audio track as the driver of all visible motion, not just as background sound.",
        "Keep the movement on a clear beat grid so the clip feels intentionally edited to the music before final assembly.",
        "Make body movement, car movement, and camera movement land on musical accents instead of floating randomly.",
        "Keep the seed image as the reference for pose, wardrobe, facial identity, and scene composition while still allowing natural video motion.",
        "Preserve clean vertical framing with a professional music-video finish and no random background changes.",
        "If the model must choose between wild motion and beat-locked continuity, choose beat-locked continuity.",
        "Avoid overcomplicating the scene; make one strong rhythmic idea read clearly from start to finish.",
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
            "audio_to_video_beat_instruction": True,
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
        "audio_to_video_beat_instruction": True,
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
    print(f"Audio-to-video beat instruction: {info.get('audio_to_video_beat_instruction')}")
    for scene in info.get("scene_summaries", []):
        print(f"Scene {int(scene['clip_index']):02d}: {scene['actual_chars']} chars, {scene['remaining_chars']} remaining")
    for problem in info.get("problems", []):
        print(f"PROBLEM: {problem}")


if __name__ == "__main__":
    main()
