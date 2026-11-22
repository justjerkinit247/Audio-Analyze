"""Standard-library regression checks for the isolated ASMO narrative validator."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from audio_analyze.asmo_narrative_timing import (  # noqa: E402
    evaluate_narrative_timing,
    example_complete,
)


class NarrativeTimingTests(unittest.TestCase):
    def test_complete_synthetic_sequence_passes(self):
        self.assertEqual(evaluate_narrative_timing(example_complete())["decision"], "pass")

    def test_incomplete_clip_requires_review(self):
        report = evaluate_narrative_timing({"clip": "C"})
        self.assertEqual(report["decision"], "review_required")
        self.assertTrue(report["unverified"])

    def test_early_footprints_rejected(self):
        report = evaluate_narrative_timing({
            "clip": "D", "fire_hot_at_first_footprint": True,
            "early_night_at_first_footprint": True,
        })
        self.assertEqual(report["decision"], "reject")
        self.assertEqual({v["code"] for v in report["violations"]},
                         {"EARLY_FOOTPRINT_FIRE", "EARLY_FOOTPRINT_NIGHT"})

    def test_wrong_gait_rejected(self):
        seq = example_complete()
        seq["events"]["trail_to_tree"]["steps"][1]["foot"] = "L"
        self.assertEqual(evaluate_narrative_timing(seq)["decision"], "reject")

    def test_overlapping_gifts_rejected(self):
        seq = example_complete()
        seq["gifts"][1]["start"] = 4.2
        self.assertEqual(evaluate_narrative_timing(seq)["decision"], "reject")

    def test_beat_sync_remains_disabled(self):
        self.assertIs(evaluate_narrative_timing(example_complete())["beat_sync_applied"], False)


if __name__ == "__main__":
    unittest.main()
