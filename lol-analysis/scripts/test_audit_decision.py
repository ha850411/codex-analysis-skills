"""Decision diagnostics must expose joint fragility without changing forecasts."""
import copy
from itertools import product
import unittest

from analyst_forecast import audit, build, derive, series_tree
from audit_decision import audit_decision, bounded_weights, joint_cases
from test_analyst_forecast import fixture


def example():
    data = fixture(5)
    first = data["judgment"]["scenarios"][0]
    data["judgment"]["scenarios"] = [dict(copy.deepcopy(first), id=str(i), weight=w,
        game_probabilities=[p]*5) for i, (w, p) in enumerate(((.5, .38), (.3, .6), (.2, .5)))]
    f = build(data)
    q = dict(forecast_id=f["forecast_id"], event_id=f["event_id"], market="series_ml",
        participants=f["participants"], decimal_odds={"a": 2.8, "b": 1.45},
        retrieved_at=f["created_at"], source_url="https://example.org/quote", book="synthetic",
        entry_floor={"a": 2.6})
    return f, q


class DecisionAuditTests(unittest.TestCase):
    def test_local_positive_ev_can_fail_joint_stress_without_mutation(self):
        f, q = example()
        original = copy.deepcopy((f, q))
        r = audit_decision(f, q)["results"]["a"]
        self.assertGreater(r["one_at_a_time_range"][0]*2.8-1, 0)
        self.assertLess(r["joint_ev_range"][0], 0)
        self.assertTrue(r["positive_ev_lost_under_joint_stress"])
        self.assertEqual((f, q), original)
        self.assertAlmostEqual(r["joint_stress_range"][0], .32297785148)

    def test_joint_optimizer_matches_exhaustive_finite_grid(self):
        f, _ = example()
        # For these three weights, every bounded-simplex vertex is on this grid.
        values = []
        for shifts in product((-.05, 0., .05), repeat=3):
            ps = [derive(series_tree(5, {k: round(p+d, 15) for k, p in s["nodes"].items()}))
                  ["winner_probabilities"]["a"] for s, d in zip(f["scenarios"], shifts)]
            for ws in product(*[(w-.1, w, w+.1) for w in (.5, .3, .2)]):
                if abs(sum(ws)-1) < 1e-10:
                    values.append(sum(w*p for w, p in zip(ws, ps)))
        cases, _ = joint_cases(f, "a")
        self.assertAlmostEqual(cases["minimum"]["probability"], min(values))
        self.assertAlmostEqual(cases["maximum"]["probability"], max(values))

    def test_complements_and_witnesses(self):
        f, q = example()
        r = audit_decision(f, q)
        a, b = r["results"]["a"], r["results"]["b"]
        self.assertAlmostEqual(a["joint_stress_range"][0]+b["joint_stress_range"][1], 1)
        self.assertAlmostEqual(a["market_no_vig_probability"]+b["market_no_vig_probability"], 1)
        for side in ("a", "b"):
            for case in r["results"][side]["joint_witnesses"].values():
                self.assertAlmostEqual(sum(p["weight"] for p in case["parameters"]), 1)
                scores = {k: sum(s["weight"]*series_tree(5, s["nodes"])[k]
                                 for s in case["parameters"]) for k in f["score_distribution"]}
                self.assertAlmostEqual(derive(scores)["winner_probabilities"][side], case["probability"])

    def test_price_changes_never_change_probability_stress(self):
        f, q = example()
        a = audit_decision(f, q)
        q["decimal_odds"] = {"a": 4., "b": 1.2}
        b = audit_decision(f, q)
        self.assertEqual(a["results"]["a"]["joint_stress_range"], b["results"]["a"]["joint_stress_range"])
        self.assertEqual(a["forecast_sha256"], b["forecast_sha256"])

    def test_identity_timing_and_market_rejection(self):
        f, q = example()
        for key, value in (("forecast_id", "wrong"), ("event_id", "wrong"),
            ("participants", q["participants"][::-1]), ("market", "map_ml"),
            ("retrieved_at", f["scheduled_start"]), ("retrieved_at", "2019-01-01T00:00:00Z"),
            ("decimal_odds", {"a": float("nan"), "b": 1.45}), ("actual_score", "1-3")):
            broken = copy.deepcopy(q); broken[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                audit_decision(f, broken)

    def test_near_boundary_and_single_scenario(self):
        data = fixture(3)
        s = data["judgment"]["scenarios"][0]
        s.update(weight=1., game_probabilities=[.98]*3)
        data["judgment"]["scenarios"] = [s]
        f = build(data)
        cases, skipped = joint_cases(f, "a")
        self.assertEqual(len(skipped), 1)
        self.assertEqual(cases["minimum"]["parameters"][0]["weight"], 1)
        self.assertAlmostEqual(cases["maximum"]["probability"], f["derived"]["winner_probabilities"]["a"])

    def test_conditional_tree_uses_actual_nodes(self):
        f, _ = example()
        data = copy.deepcopy(f["generation_input"])
        for s, generated in zip(data["judgment"]["scenarios"], f["scenarios"]):
            del s["game_probabilities"]
            s["conditional_probabilities"] = generated["nodes"].copy()
            s["conditional_probabilities"]["W"] += .04
            s["dependence_reason"] = "Synthetic state-dependent case"
            s["dependence_evidence_ids"] = ["fixture"]
        conditional = build(data)
        cases, _ = joint_cases(conditional, "a")
        self.assertLessEqual(cases["minimum"]["probability"], conditional["derived"]["winner_probabilities"]["a"])
        self.assertGreaterEqual(cases["maximum"]["probability"], conditional["derived"]["winner_probabilities"]["a"])


if __name__ == "__main__":
    unittest.main()
