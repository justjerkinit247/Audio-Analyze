from pathlib import Path
import json

import numpy as np
import soundfile as sf

from src.audio_analyze.ltx_run_state import rotate_for_new_live_session, ingest_scene_result, append_assembly_attempt
from src.audio_analyze.ltx_intelligence_loop import run_intelligence_loop


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def make_test_wav(path: Path):
    sr = 22050
    duration = 4.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    y = 0.1 * np.sin(2 * np.pi * 220 * t)
    for beat in np.arange(0, duration, 0.5):
        idx = int(beat * sr)
        y[idx:idx + 300] += np.hanning(300) * 0.8
    sf.write(str(path), y, sr)


def test_integrated_intelligence_loop_smoke(tmp_path):
    state = tmp_path / "_state"
    rotate_for_new_live_session(state)

    result = tmp_path / "scene_01_result.json"
    write_json(result, {
        "clip_index": 1,
        "status": "complete",
        "model": "ltx-2-3-pro",
        "guidance_scale": 9.0,
        "resolution": "1080x1920",
        "downloaded_mp4": "scene_01.mp4",
        "scene_audio_format": "MP3",
        "scene": {"start": 0.0, "end": 4.0, "duration": 4.0},
        "prompt_text": "performance motion beat camera dolly downbeat rhythm " * 20,
    })
    ingest_scene_result(state, result)
    append_assembly_attempt(state, {"status": "complete", "audio_offset_seconds": -0.1})

    write_json(state / "active" / "review" / "human_scorecard.json", {
        "scene_01": {
            "beat_sync": 8,
            "motion_match": 8,
            "camera_match": 8,
            "visual_quality": 8,
            "prompt_obedience": 7,
            "notes": "good motion and camera timing",
        }
    })

    plan = tmp_path / "plan.json"
    out = tmp_path / "plan_next.json"
    audio = tmp_path / "test.wav"
    make_test_wav(audio)
    write_json(plan, {
        "results": [
            {"clip_index": 1, "scene": {"start": 0.0, "end": 4.0}, "prompt_text": "original prompt"}
        ]
    })

    summary = run_intelligence_loop(
        plan_json=plan,
        state_root=state,
        output_plan=out,
        audio=audio,
        update_policy=True,
        update_memory=True,
    )

    assert summary["status"] == "complete"
    assert out.exists()
    patched = json.loads(out.read_text(encoding="utf-8"))
    assert patched["asmo_memory_bank_applied"] is True
    assert "ASMO Memory Bank update" in patched["results"][0]["prompt_text"]
    assert (state / "active" / "feedback" / "intelligence_loop_summary.json").exists()
