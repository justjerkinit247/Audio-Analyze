from audio_analyze.asmo_engine.ltx_run_integrator import (
    apply_asmo_timeline_to_plan_data,
)


class FakeASMOEngine:
    def __init__(self, events=None):
        self.calls = []
        self.events = events

    def generate_timeline(self, lyric_path, audio_path):
        self.calls.append((lyric_path, audio_path))
        default_events = [
            {
                "timestamp_ms": 1000,
                "lyric": "twerk",
                "motion_directive": {
                    "prompt_fragment": "perform controlled hip isolation",
                    "camera_behavior": "waist_tracking",
                },
            },
            {
                "timestamp_ms": 9000,
                "lyric": "drop low",
                "motion_directive": {
                    "prompt_fragment": "drop low with hip-driven motion",
                    "camera_behavior": "downward_follow",
                },
            },
        ]
        return {
            "schema": "asmo.motion_timeline.v2",
            "events": self.events if self.events is not None else default_events,
        }


def test_in_memory_asmo_integration_assigns_events_to_each_scene(tmp_path):
    audio = tmp_path / "track.wav"
    audio.write_bytes(b"audio")
    lyrics = tmp_path / "lyrics.lrc"
    lyrics.write_text("[00:01.000] twerk\n[00:09.000] drop low\n", encoding="utf-8")
    plan = {
        "results": [
            {
                "clip_index": 1,
                "source_audio_path": str(audio),
                "scene": {"start": 0.0, "end": 8.0},
                "prompt_text": "scene one",
            },
            {
                "clip_index": 2,
                "source_audio_path": str(audio),
                "scene": {"start": 8.0, "end": 16.0},
                "prompt_text": "scene two",
            },
        ]
    }
    engine = FakeASMOEngine()

    patched = apply_asmo_timeline_to_plan_data(
        plan,
        lyric_path=lyrics,
        engine=engine,
    )

    assert patched["asmo_ltx_run_integration"] is True
    assert len(engine.calls) == 1
    first, second = patched["results"]
    assert first["asmo_injection_status"] == "injected"
    assert second["asmo_injection_status"] == "injected"
    assert first["asmo_motion_event_count"] == 1
    assert second["asmo_motion_event_count"] == 1
    assert "+1.000s" in first["asmo_motion_prompt_block"]
    assert "+1.000s" in second["asmo_motion_prompt_block"]
    assert plan["results"][0].get("asmo_injection_status") is None


def test_in_memory_asmo_integration_records_scene_without_events(tmp_path):
    audio = tmp_path / "track.wav"
    audio.write_bytes(b"audio")
    lyrics = tmp_path / "lyrics.lrc"
    lyrics.write_text("[00:01.000] twerk\n", encoding="utf-8")
    engine = FakeASMOEngine(
        events=[
            {
                "timestamp_ms": 1000,
                "lyric": "twerk",
                "motion_directive": {
                    "prompt_fragment": "perform controlled hip isolation",
                    "camera_behavior": "waist_tracking",
                },
            }
        ]
    )
    plan = {
        "results": [
            {
                "clip_index": 2,
                "source_audio_path": str(audio),
                "scene": {"start": 8.0, "end": 16.0},
            }
        ]
    }

    patched = apply_asmo_timeline_to_plan_data(
        plan,
        lyric_path=lyrics,
        engine=engine,
    )

    assert patched["results"][0]["asmo_injection_status"] == (
        "skipped_no_events_in_scene_window"
    )
    assert "asmo_motion_prompt_block" not in patched["results"][0]
