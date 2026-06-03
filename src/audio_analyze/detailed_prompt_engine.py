from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class StyleProfile:
    name: str
    visual_identity: str
    movement_language: str
    camera_language: str
    lighting_language: str
    continuity_rules: str
    safety_rules: str


STYLE_PROFILES: dict[str, StyleProfile] = {
    "generic_performance": StyleProfile(
        name="generic_performance",
        visual_identity=(
            "Polished cinematic music-video performance. Use the supplied image reference as the visual source of truth "
            "for subject count, wardrobe, composition, camera angle, lighting direction, and environment."
        ),
        movement_language=(
            "Use grounded, physically believable performance movement that is visibly synchronized to the song's pulse, "
            "kick, snare, bass accents, vocal emphasis, and phrase changes."
        ),
        camera_language=(
            "Use one clear camera behavior per scene: controlled push-in, side-track, gentle orbit, or stable wide performance framing. "
            "Avoid chaotic camera movement or random reframing."
        ),
        lighting_language=(
            "Preserve the image reference lighting while allowing subtle music-reactive highlights on strong beats."
        ),
        continuity_rules=(
            "Preserve identity, body layout, wardrobe, background geography, and scene composition across the clip. "
            "Do not add or remove performers unless explicitly requested."
        ),
        safety_rules=(
            "Adult performers only if people are present. No nudity, explicit sexual content, minors, gore, weapons, watermarks, logos, subtitles, "
            "extra limbs, melted hands, warped anatomy, or random wardrobe mutation."
        ),
    ),
    "gospel_twerk": StyleProfile(
        name="gospel_twerk",
        visual_identity=(
            "Gospel Twerk performance-art profile: sacred stage energy, church or cathedral atmosphere when compatible with the image reference, "
            "flowing white robes or gospel-performance styling when already present or requested, reverent but bold performance framing. "
            "Movement is praise choreography, not nudity or sleaze."
        ),
        movement_language=(
            "Use beat-synced praise choreography with controlled hip, shoulder, robe, hand, and footwork accents. "
            "Keep the body language reverent, powerful, rhythmic, and performance-art focused. Motion must read as worshipful dance."
        ),
        camera_language=(
            "Use polished gospel-video camera language: altar-stage hero framing, smooth dolly pushes, choir-performance wides, "
            "controlled low-angle emphasis only when it supports sacred performance energy."
        ),
        lighting_language=(
            "Use golden stained-glass light, stage glow, incense haze, marble or sanctuary reflections when compatible with the seed image. "
            "Let light pulse subtly on strong downbeats without breaking realism."
        ),
        continuity_rules=(
            "Preserve the seed image as source of truth. Keep robes, wardrobe, performer identity, sanctuary/stage geometry, and choreography direction stable. "
            "No cheap strip-club framing, no random costume swaps, no sudden new people."
        ),
        safety_rules=(
            "Adult performers only. Fully clothed. No nudity, no lingerie framing, no explicit sexual contact, no minors, no fetish framing, no gore, "
            "no weapons, no watermarks, no subtitles, no logos, no warped anatomy, no extra limbs, no male high heels."
        ),
    ),
}


def normalize_style_profile(style_profile: str | None) -> StyleProfile:
    key = (style_profile or "generic_performance").strip().lower().replace("-", "_")
    return STYLE_PROFILES.get(key, STYLE_PROFILES["generic_performance"])


def compact_text(value: str, max_chars: int = 5000) -> str:
    text = " ".join((value or "").split())
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0].rstrip() + "."


def timeline_events_for_scene(timeline: dict[str, Any] | None, scene: dict[str, Any], limit: int = 10) -> list[dict[str, Any]]:
    if not timeline:
        return []
    start_ms = int(float(scene.get("start", 0.0)) * 1000)
    end_ms = int(float(scene.get("end", 0.0)) * 1000)
    events = []
    for event in timeline.get("events", []) or []:
        try:
            ts = int(event.get("timestamp_ms", 0))
        except Exception:
            continue
        if start_ms <= ts <= end_ms:
            events.append(event)
    return events[:limit]


def build_timed_event_block(events: list[dict[str, Any]], scene: dict[str, Any]) -> str:
    if not events:
        return (
            "Lyric/semantic sync: no timed lyric events were supplied for this scene. "
            "Use the audio beat, vocal energy, and phrase changes as the primary sync source."
        )

    scene_start_ms = int(float(scene.get("start", 0.0)) * 1000)
    lines = ["Lyric/semantic sync directives for this scene:"]
    for event in events:
        timestamp_ms = int(event.get("timestamp_ms", 0))
        rel_seconds = max(0, timestamp_ms - scene_start_ms) / 1000.0
        lyric = str(event.get("lyric", "")).strip()
        directive = event.get("motion_directive", {}) or {}
        motion = directive.get("prompt_fragment") or directive.get("name") or "sync visible movement tightly to lyric and beat"
        camera = directive.get("camera_behavior") or "steady controlled camera"
        lines.append(f"+{rel_seconds:0.3f}s: {motion}; camera={camera}; lyric cue='{lyric}'")
    return " ".join(lines)


def build_audio_sync_block(analysis: dict[str, Any], scene: dict[str, Any]) -> str:
    bpm = analysis.get("tempo_bpm_from_full_track") or analysis.get("tempo_bpm")
    bpm_text = f"{float(bpm):.2f} BPM" if isinstance(bpm, (int, float)) else "detected song tempo"
    start = float(scene.get("start", 0.0))
    end = float(scene.get("end", start))
    duration = max(0.0, end - start)
    beat_policy = analysis.get("sync_policy") or "Movement and camera changes must follow the audio pulse."
    return (
        f"Audio sync: scene covers {start:.2f}s to {end:.2f}s, duration {duration:.2f}s, locked to {bpm_text}. "
        f"{beat_policy} Visible body accents, cuts, robe/fabric motion, facial emphasis, and camera moves must land on kick, snare, bass hits, vocal accents, "
        "strong onsets, or phrase transitions. Do not drift off-beat."
    )


def compose_detailed_prompt(
    file_stem: str,
    analysis: dict[str, Any],
    scene: dict[str, Any],
    seed_image: str | Path | None = None,
    seed_hint: str = "",
    style_profile: str = "generic_performance",
    timeline: dict[str, Any] | None = None,
    max_chars: int = 5000,
) -> str:
    """Compose a detailed, scene-specific, audio-synced video generation prompt.

    This engine is intentionally general: audio + image/video reference + lyric semantics + style profile
    becomes a detailed prompt. Gospel Twerk is a style profile, not a forked pipeline.
    """
    profile = normalize_style_profile(style_profile)
    seed_text = str(seed_image) if seed_image else "supplied image reference"
    events = timeline_events_for_scene(timeline, scene)

    parts = [
        f"Detailed video-generation prompt for {file_stem}, scene {scene.get('scene_index', scene.get('clip_index', 'unknown'))}.",
        f"Image/video reference: use {seed_text} as the source of truth for subject count, identity, body layout, wardrobe, pose category, composition, camera angle, lighting, and background. {('Filename visual hint: ' + seed_hint + '.') if seed_hint else ''}",
        build_audio_sync_block(analysis, scene),
        f"Style profile [{profile.name}]: {profile.visual_identity}",
        f"Movement language: {profile.movement_language} Existing audio analysis says: {analysis.get('movement_notes', 'use music-reactive performance movement')}.",
        f"Camera language: {profile.camera_language} Existing camera analysis says: {analysis.get('camera_notes', 'use controlled performance framing')}.",
        f"Lighting language: {profile.lighting_language} Existing lighting analysis says: {analysis.get('lighting_notes', 'preserve coherent lighting')}.",
        build_timed_event_block(events, scene),
        f"Continuity rules: {profile.continuity_rules}",
        f"Safety and negative rules: {profile.safety_rules}",
        "Generation discipline: prioritize seed fidelity first, audio synchronization second, clean human anatomy third, then cinematic detail. Keep the scene readable and physically believable.",
    ]

    return compact_text(" ".join(part for part in parts if part), max_chars=max_chars)
