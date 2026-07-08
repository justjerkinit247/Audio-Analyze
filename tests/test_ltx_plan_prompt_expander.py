from audio_analyze.ltx_plan_prompt_expander import (
    AUDIO_TIMING_MARKER,
    SUBJECT_LOCK_MARKER,
    expand_plan_data,
)


def fake_expander(scene_hint, filename, provider, model):
    return {
        "filename": filename,
        "scene_hint": scene_hint,
        "provider": provider,
        "model": model,
        "ltx_motion_prompt": f"Expanded motion for {scene_hint}.",
        "negative_prompt": "blurry motion, scene drift",
        "combined_ltx_text": "[MOTION_PROMPT]\nExpanded motion.\n\n[NEGATIVE_PROMPT]\nblurry motion, scene drift\n",
        "motion_notes": ["fake expander used"],
    }


def sample_plan():
    return {
        "file_stem": "test_song",
        "analysis": {
            "tempo_bpm": 120.0,
            "duration_seconds": 30.0,
            "energy_profile": "high",
            "edit_pacing": "medium-fast",
            "movement_notes": "locked rhythmic movement",
            "camera_notes": "smooth tracking",
            "lighting_notes": "balanced polished studio lighting",
            "mix_reactivity_notes": "Average RMS 0.1000, spectral centroid 2000.00, onset strength 1.00",
            "beat_alignment_enabled": True,
            "detected_beat_count": 64,
            "sync_policy": "Scene starts and scene changes are snapped to detected beat positions.",
        },
        "scene_count": 1,
        "beat_alignment_enabled": True,
        "results": [
            {
                "clip_index": 1,
                "file_stem": "test_song",
                "source_audio_path": "inputs/audio/test.mp3",
                "seed_image_used": "inputs/ltx_seed_images/scene_01_neon_cube_rotates_on_concrete_floor.png",
                "seed_filename_prompt_hint": "stale legacy hint that must not win",
                "scene": {
                    "scene_index": 1,
                    "start": 8.25,
                    "end": 12.25,
                    "duration": 4.0,
                    "scene_type": "beat-aligned performance phrase",
                    "sync_start_rule": "scene starts on or near detected beat",
                    "sync_end_rule": "scene ends on or near detected beat",
                },
                "resolution": "1080x1920",
                "prompt_text": "old hardcoded prompt text",
                "status": "planned",
                "beat_alignment_enabled": True,
            }
        ],
    }


def test_expand_plan_data_replaces_old_prompt_with_filename_hint_expansion():
    patched = expand_plan_data(
        sample_plan(),
        provider="ollama",
        model="gemma3:4b",
        expander=fake_expander,
    )

    item = patched["results"][0]

    assert patched["filename_hint_expansion"]["status"] == "applied"
    assert patched["filename_hint_expansion"]["provider"] == "ollama"
    assert patched["filename_hint_expansion"]["seed_filename_source"] == "exact_seed_image_basename"
    assert patched["prompt_transport_mode"] == "audio_and_image_to_video"
    assert item["prompt_build_method"] == "seed_filename_ollama_expansion_with_audio_timing_and_subject_lock"
    assert item["prompt_transport_mode"] == "audio_and_image_to_video"
    assert item["prompt_text_before_filename_hint_expansion"] == "old hardcoded prompt text"
    assert item["filename_hint_expansion"]["ltx_motion_prompt"] == "Expanded motion for neon cube rotates on concrete floor."
    assert item["prompt_text"].startswith("Audio-and-image-to-video continuation synchronized to the supplied audio")
    assert "Image-to-video continuation" not in item["prompt_text"]
    assert AUDIO_TIMING_MARKER in item["prompt_text"]
    assert SUBJECT_LOCK_MARKER in item["prompt_text"]
    assert "[MOTION_PROMPT]" in item["prompt_text"]
    assert "[NEGATIVE_PROMPT]" in item["prompt_text"]
    assert "Expanded motion for neon cube rotates on concrete floor." in item["prompt_text"]
    assert "blurry motion, scene drift" in item["prompt_text"]
    assert "hip, glute, thigh" not in item["prompt_text"]


def test_expand_plan_data_uses_exact_seed_filename_not_stale_hint():
    calls = {}

    def recording_expander(scene_hint, filename, provider, model):
        calls["scene_hint"] = scene_hint
        calls["filename"] = filename
        return fake_expander(scene_hint, filename, provider, model)

    patched = expand_plan_data(
        sample_plan(),
        provider="ollama",
        model="gemma3:4b",
        expander=recording_expander,
    )

    item = patched["results"][0]
    expected_filename = "scene_01_neon_cube_rotates_on_concrete_floor.png"

    assert calls["filename"] == expected_filename
    assert calls["scene_hint"] == "neon cube rotates on concrete floor"
    assert item["seed_filename_used_for_prompt_hint"] == expected_filename
    assert item["seed_filename_prompt_hint"] == "neon cube rotates on concrete floor"
    assert "stale legacy hint" not in item["prompt_text"]
    assert f"Seed image filename used as the Ollama prompt hint: {expected_filename}." in item["prompt_text"]
    assert "Seed filename scene direction: neon cube rotates on concrete floor." in item["prompt_text"]


def test_expand_plan_data_injects_audio_timing_metadata_and_prompt_block():
    patched = expand_plan_data(
        sample_plan(),
        provider="ollama",
        model="gemma3:4b",
        expander=fake_expander,
    )

    item = patched["results"][0]
    audio_timing = item["audio_timing"]
    prompt = item["prompt_text"]

    assert patched["prompt_build_method"] == "seed_filename_ollama_expansion_with_audio_timing_and_subject_lock"
    assert patched["filename_hint_expansion"]["audio_timing_prompt_blocks"] == "applied"
    assert patched["filename_hint_expansion"]["subject_lock_prompt_blocks"] == "applied"
    assert audio_timing["start_seconds"] == 8.25
    assert audio_timing["end_seconds"] == 12.25
    assert audio_timing["duration_seconds"] == 4.0
    assert audio_timing["tempo_bpm"] == 120.0
    assert audio_timing["estimated_beats_in_scene"] == 8.0
    assert audio_timing["detected_beat_count_full_track"] == 64
    assert item["audio_timing_prompt_block"].startswith(AUDIO_TIMING_MARKER)
    assert "Scene 1 audio window: 8.25s to 12.25s, duration 4.00s." in prompt
    assert "Tempo target: 120.00 BPM; approximately 8.0 beats in this clip." in prompt
    assert "Beat alignment: enabled." in prompt
    assert "Start rule: scene starts on or near detected beat; end rule: scene ends on or near detected beat." in prompt
    assert "Energy/pacing cue: high, medium-fast." in prompt
    assert prompt.index(SUBJECT_LOCK_MARKER) < prompt.index(AUDIO_TIMING_MARKER)
    assert prompt.index(AUDIO_TIMING_MARKER) < prompt.index("[MOTION_PROMPT]")


def test_duet_and_choir_filename_removes_false_solitary_language():
    plan = sample_plan()
    filename = (
        "scene_01_sunlit_cathedral_gospel_twerk_duet_woman_deep_squat_"
        "hip_glute_pulses_man_partner_white_gold_choir_clapping.png"
    )
    plan["results"][0]["seed_image_used"] = f"inputs/ltx_seed_images/{filename}"
    plan["results"][0]["seed_filename_prompt_hint"] = "wrong one-woman legacy hint"

    def bad_singular_expander(scene_hint, filename, provider, model):
        return {
            "filename": filename,
            "scene_hint": scene_hint,
            "provider": provider,
            "model": model,
            "ltx_motion_prompt": (
                "A solitary female dancer performs alone in the cathedral while the camera circles slowly."
            ),
            "negative_prompt": "blurry motion",
            "combined_ltx_text": "unused",
            "motion_notes": [],
        }

    patched = expand_plan_data(
        plan,
        provider="ollama",
        model="gemma3:4b",
        expander=bad_singular_expander,
    )

    item = patched["results"][0]
    prompt = item["prompt_text"]
    motion = item["filename_hint_expansion"]["ltx_motion_prompt"]
    policy = item["subject_count_policy"]

    assert item["seed_filename_used_for_prompt_hint"] == filename
    assert policy["multiple_subjects"] is True
    assert policy["has_pair"] is True
    assert policy["has_choir"] is True
    assert "solitary" not in motion.lower()
    assert "performs alone" not in motion.lower()
    assert "female lead dancer and male dance partner remain visible together" in motion
    assert "choir remains visible in the background" in motion
    assert "Keep the female lead dancer and male dance partner visible together" in prompt
    assert "Keep the existing choir visible in the background" in prompt
    assert "Never describe or render this scene as solitary" in prompt
    negative = item["filename_hint_expansion"]["negative_prompt"]
    assert "missing dance partner" in negative
    assert "missing choir" in negative
    assert "changed subject count" in negative
