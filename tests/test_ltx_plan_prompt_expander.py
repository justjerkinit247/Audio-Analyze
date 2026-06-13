from audio_analyze.ltx_plan_prompt_expander import expand_plan_data


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
        "analysis": {"tempo_bpm": 120.0},
        "scene_count": 1,
        "results": [
            {
                "clip_index": 1,
                "file_stem": "test_song",
                "source_audio_path": "inputs/audio/test.mp3",
                "seed_image_used": "inputs/ltx_seed_images/scene_01_neon_cube_rotates_on_concrete_floor.png",
                "seed_filename_prompt_hint": "neon cube rotates on concrete floor",
                "scene": {"scene_index": 1, "start": 0.0, "end": 4.0, "duration": 4.0},
                "resolution": "1080x1920",
                "prompt_text": "old hardcoded prompt text",
                "status": "planned",
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
    assert item["prompt_build_method"] == "filename_hint_expansion"
    assert item["prompt_text_before_filename_hint_expansion"] == "old hardcoded prompt text"
    assert item["filename_hint_expansion"]["ltx_motion_prompt"] == "Expanded motion for neon cube rotates on concrete floor."
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
