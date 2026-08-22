from audio_analyze.ltx_feedback_analyzer import analyze_feature
from audio_analyze.ltx_policy_store import update_policy_from_feedback


def test_unscored_feature_does_not_invent_score_failures():
    feedback = analyze_feature(
        {
            "clip_index": 1,
            "status": "complete",
            "human_scores": {},
            "prompt_length_chars": 1000,
            "conflict_directive_count": 0,
            "motion_directive_count": 4,
            "camera_directive_count": 3,
        }
    )

    assert all(value is None for value in feedback["scores"].values())
    assert set(feedback["score_evidence"].values()) == {"missing"}
    assert feedback["scored_metrics"] == []
    assert feedback["detected_issues"] == []
    assert feedback["recommended_adjustments"] == {}


def test_policy_ignores_numeric_scores_without_evidence(tmp_path):
    packet = {
        "scene_feedback": [
            {
                "scores": {
                    "beat_sync": 0.1,
                    "motion_intent_match": 0.1,
                    "camera_intent_match": 0.1,
                    "prompt_obedience": 0.1,
                    "visual_quality": 0.1,
                }
            }
        ]
    }

    policy = update_policy_from_feedback(tmp_path, packet)

    assert policy["strategies"]["simple_downbeat_locked_choreo"] == {
        "weight": 1.0,
        "wins": 0,
        "losses": 0,
    }
    assert policy["last_feedback_evidence"]["policy_updated_from_scores"] is False


def test_policy_updates_only_from_trusted_human_evidence(tmp_path):
    packet = {
        "scene_feedback": [
            {
                "scores": {
                    "beat_sync": 0.4,
                    "motion_intent_match": 0.8,
                    "camera_intent_match": None,
                    "prompt_obedience": None,
                    "visual_quality": None,
                },
                "score_evidence": {
                    "beat_sync": "human_scorecard",
                    "motion_intent_match": "human_scorecard",
                    "camera_intent_match": "missing",
                    "prompt_obedience": "missing",
                    "visual_quality": "missing",
                },
            }
        ]
    }

    policy = update_policy_from_feedback(tmp_path, packet)

    assert policy["strategies"]["simple_downbeat_locked_choreo"]["losses"] == 1
    assert policy["strategies"]["prompt_compressed_motion_first"]["wins"] == 1
    assert policy["strategies"]["camera_follows_hips"]["wins"] == 0
    assert policy["last_feedback_evidence"]["policy_updated_from_scores"] is True
