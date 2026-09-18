import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_model import audit
from shared.forecast.fixtures import event, history
from shared.forecast.models import train, predict


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.rows = history("cs")
        self.event = event("cs")
        self.event["best_of"] = 5
        self.event["veto_scenarios"] = [{"id": "fixture", "weight": 1.,
            "maps": ["Ancient", "Mirage", "Dust2", "Inferno", "Cache"],
            "evidence_ids": [self.event["evidence"][0]["id"]]}]
        self.model = train(self.rows, "cs", self.event["data_cutoff"], "challenger")

    def test_rejects_false_opponent_and_update_claims(self):
        r = audit(self.model, self.event, self.rows, {
            "map_offsets_opponent_adjusted": True,
            "rating_update_unit": "one_update_per_map"})
        self.assertFalse(r["audit_passed"])
        self.assertEqual(len(r["claim_mismatches"]), 2)
        self.assertTrue(audit(self.model, self.event, self.rows, {
            "map_offsets_opponent_adjusted": False,
            "rating_update_unit": "one_update_per_series_using_map_share"})["audit_passed"])

    def test_detects_identical_map_representation(self):
        r = audit(self.model, self.event, self.rows)
        self.assertIn(["Cache", "Dust2"], r["same_probability_pairs"])

    def test_ablations_preserve_originals_and_probability_mass(self):
        before = copy.deepcopy((self.model, self.event, self.rows))
        r = audit(self.model, self.event, self.rows)
        self.assertEqual(before, (self.model, self.event, self.rows))
        self.assertEqual(r["original_distribution"], predict(self.model, self.event)["score_distribution"])
        for v in r["ablations"].values():
            self.assertAlmostEqual(sum(v["score_distribution"].values()), 1.)
        self.assertFalse(r["production_change"])

    def test_rejects_mismatched_training_artifact(self):
        self.model["ratings"][next(iter(self.model["ratings"]))] += 1
        with self.assertRaisesRegex(ValueError, "does not replay"):
            audit(self.model, self.event, self.rows)

    def test_flags_collapsed_times_without_inventing_timestamps(self):
        stamp = self.rows[-1]["completed_at"]
        for row in self.rows:
            row["completed_at"] = row["available_at"] = stamp
        self.model = train(self.rows, "cs", self.event["data_cutoff"], "challenger")
        r = audit(self.model, self.event, self.rows)
        self.assertIn("completion_times_collapsed_check_upper_bound_semantics", r["flags"])
        self.assertEqual({row["completed_at"] for row in self.rows}, {stamp})

    def test_rejects_unsupported_engine(self):
        self.model["model_version"] = "cs-custom-v3"
        with self.assertRaisesRegex(ValueError, "unsupported"):
            audit(self.model, self.event, self.rows)


if __name__ == "__main__":
    unittest.main()
