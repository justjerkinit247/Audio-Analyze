from audio_analyze.ltx_plan_prompt_expander import AUDIO_TIMING_MARKER, expand_plan_data


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
                "seed_filename_prompt_hint": "neon cube rotates on concrete floor",
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
    assert item["prompt_build_method"] == "filename_hint_expansion_with_audio_timing"
    assert item["prompt_text_before_filename_hint_expansion"] == "old hardcoded prompt text"
    assert item["filename_hint_expansion"]["ltx_motion_prompt"] == "Expanded motion for neon cube rotates on concrete floor."
    assert AUDIO_TIMING_MARKER in item["prompt_text"]
    assert "[MOTION_PROMPT]" in item["prompt_text"]
    assert "[NEGATIVE_PROMPT]" in item["prompt_text"]
    assert "Expanded motion for neon cube rotates on concrete floor." in item["prompt_text"]
    assert "blurry motion, scene drift" in item["prompt_text"]
    assert "hip, glute, thigh" not in item["prompt_text"]


def test_expand_plan_data_records_seed_filename_scene_hint():
    patched = expand_plan_data(
        sample_plan(),
        provider="template",
        model="gemma3:4b",
        expander=fake_expander,
    )

    item = patched["results"][0]

    assert item["seed_filename_prompt_hint"] == "neon cube rotates on concrete floor"
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

    assert patched["prompt_build_method"] == "filename_hint_expansion_with_audio_timing"
    assert patched["filename_hint_expansion"]["audio_timing_prompt_blocks"] == "applied"
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
    assert prompt.index(AUDIO_TIMING_MARKER) < prompt.index("[MOTION_PROMPT]")
