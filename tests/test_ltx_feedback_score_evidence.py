from src.audio_analyze.ltx_feedback_analyzer import analyze_feature
from src.audio_analyze.ltx_policy_store import update_policy_from_feedback


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
    assert set(feedback["unscored_metrics"]) == set(feedback["scores"])
    assert feedback["detected_issues"] == []
    assert feedback["recommended_adjustments"] == {}


def test_partially_scored_feature_only_uses_present_metric():
    feedback = analyze_feature(
        {
            "clip_index": 2,
            "status": "complete",
            "human_scores": {"beat_sync": 5},
            "prompt_length_chars": 1000,
            "conflict_directive_count": 0,
            "motion_directive_count": 4,
            "camera_directive_count": 3,
        }
    )

    assert feedback["scores"]["beat_sync"] == 0.5
    assert feedback["score_evidence"]["beat_sync"] == "human_scorecard"
    assert feedback["scored_metrics"] == ["beat_sync"]
    assert feedback["detected_issues"] == ["weak_beat_sync"]
    assert "motion_intent_mismatch" not in feedback["detected_issues"]
    assert "camera_intent_mismatch" not in feedback["detected_issues"]
    assert "prompt_obedience_low" not in feedback["detected_issues"]


def test_policy_ignores_numeric_scores_without_evidence(tmp_path):
    packet = {
        "scene_feedback": [
            {
                "scene_id": 1,
                "scores": {
                    "beat_sync": 0.1,
                    "motion_intent_match": 0.1,
                    "camera_intent_match": 0.1,
                    "prompt_obedience": 0.1,
                    "visual_quality": 0.1,
                },
            }
        ]
    }

    policy = update_policy_from_feedback(tmp_path, packet)

    assert policy["strategies"]["simple_downbeat_locked_choreo"] == {
        "weight": 1.0,
        "wins": 0,
        "losses": 0,
    }
    assert policy["learned_adjustments"]["downbeat_lock_boost"] == 0.0
    assert policy["learned_adjustments"]["prompt_compression_bias"] == 0.0
    assert policy["last_feedback_evidence"]["policy_updated_from_scores"] is False
    assert policy["last_feedback_evidence"]["accepted_score_counts"]["beat_sync"] == 0
    assert policy["last_feedback_evidence"]["ignored_unproven_score_counts"]["beat_sync"] == 1


def test_policy_updates_only_from_trusted_human_evidence(tmp_path):
    packet = {
        "scene_feedback": [
            {
                "scene_id": 1,
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
    assert policy["strategies"]["camera_follows_hips"] == {
        "weight": 1.0,
        "wins": 0,
        "losses": 0,
    }
    assert policy["learned_adjustments"]["downbeat_lock_boost"] == 0.08
    assert policy["last_feedback_evidence"]["policy_updated_from_scores"] is True
    assert policy["last_feedback_evidence"]["accepted_score_counts"] == {
        "beat_sync": 1,
        "motion_intent_match": 1,
        "camera_intent_match": 0,
        "prompt_obedience": 0,
        "visual_quality": 0,
    }
