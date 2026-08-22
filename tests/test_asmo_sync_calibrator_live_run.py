import json

from audio_analyze.asmo_sync_calibrator import (
    cue_times_from_plan,
    load_clip_plans,
    load_submit_clip_paths,
)


def test_calibrator_reads_validated_plan_tap_targets(tmp_path):
    plan_path = tmp_path / "validated_plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "clip_index": 1,
                        "tap_sync": {
                            "primary_sync_targets_relative_seconds": [0.25, 1.5]
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    plans = load_clip_plans(tmp_path)

    assert list(plans) == [1]
    assert plans[1]["clip_plan_path"] == plan_path
    assert cue_times_from_plan(plans[1]) == [0.25, 1.5]


def test_calibrator_reads_multi_scene_live_result_paths(tmp_path):
    clip = tmp_path / "scene_01.mp4"
    clip.write_bytes(b"video")
    (tmp_path / "live_result.json").write_text(
        json.dumps(
            {
                "results": [
                    {
                        "clip_index": 1,
                        "downloaded_mp4_resolved_path": str(clip),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    paths = load_submit_clip_paths(tmp_path)

    assert paths[1]["clip_path"] == clip
    assert paths[1]["source"] == "live_result.downloaded_mp4"
