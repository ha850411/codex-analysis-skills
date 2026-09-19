import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from summarize_forecast import summarize
from shared.forecast.cli import forecast
from shared.forecast.core import digest, mixture, series_tree
from shared.forecast.fixtures import event, history
from shared.forecast.models import train


def constant_nodes(bo, p):
    nodes = {}

    def walk(a, b, path):
        if max(a, b) == bo // 2 + 1:
            return
        nodes[path or "ROOT"] = p
        walk(a + 1, b, path + "W")
        walk(a, b + 1, path + "L")

    walk(0, 0, "")
    return nodes


class SummaryTests(unittest.TestCase):
    def setUp(self):
        e = event("cs")
        self.base = forecast(train(history("cs"), "cs", e["data_cutoff"], "baseline"), e)

    def record(self, scores, bo=3):
        r = copy.deepcopy(self.base)
        r.pop("derived", None)
        r.pop("scenarios", None)
        r["score_distribution"] = scores
        r["best_of"] = bo
        return r

    def test_winner_and_representative_score_do_not_overwrite_global_mode(self):
        r = self.record({"2-0": .29, "2-1": .28, "1-2": .40, "0-2": .03})
        original = copy.deepcopy(r)
        s = summarize(r)
        self.assertEqual(s["winner_pick"], "a")
        self.assertEqual(s["representative_scores"]["a"]["scores"], ["2-0"])
        self.assertEqual(s["representative_scores"]["a"]["probability"], .29)
        self.assertEqual(s["score_modes"], ["1-2"])
        self.assertAlmostEqual(s["winner_probabilities"]["a"], .57)
        self.assertAlmostEqual(s["expected_total_maps"], 2.68)
        self.assertAlmostEqual(s["expected_maps_won"]["a"], 1.54)
        self.assertAlmostEqual(s["expected_map_margin_a_minus_b"], .4)
        self.assertAlmostEqual(s["total_lines"]["2.5"]["over"], .68)
        self.assertAlmostEqual(s["at_least_maps"]["1"]["a"], .97)
        self.assertEqual(r, original)
        self.assertEqual(s["forecast_hash"], digest(r))

    def test_bo5_metrics_and_ties(self):
        scores = series_tree(5, constant_nodes(5, .5))
        s = summarize(self.record(scores, 5))
        self.assertIsNone(s["winner_pick"])
        self.assertEqual(s["winner_ties"], ["a", "b"])
        self.assertEqual(s["representative_scores"]["a"]["scores"], ["3-1", "3-2"])
        self.assertAlmostEqual(s["expected_total_maps"], 4.125)
        self.assertAlmostEqual(s["expected_map_margin_a_minus_b"], 0)
        self.assertAlmostEqual(s["total_lines"]["3.5"]["over"], .75)
        self.assertAlmostEqual(s["total_lines"]["4.5"]["over"], .375)
        self.assertAlmostEqual(s["at_least_maps"]["2"]["a"], .6875)

    def test_small_edge_is_still_selected(self):
        s = summarize(self.record({"1-0": .50001, "0-1": .49999}, 1))
        self.assertEqual(s["winner_pick"], "a")
        self.assertEqual(s["total_lines"], {})
        self.assertEqual(s["at_least_maps"], {})
        self.assertEqual(s["expected_total_maps"], 1)
        self.assertEqual(s["maps"][0]["a_win_given_played"], .50001)
        self.assertIsNone(s["map_rate_reason"])

    def test_map_rates_reweight_scenarios_on_reaching_later_map(self):
        scenarios = [{"id": str(p), "weight": .5, "nodes": constant_nodes(3, p),
                      "score_distribution": series_tree(3, constant_nodes(3, p))}
                     for p in (.9, .5)]
        r = self.record(mixture(scenarios))
        r["scenarios"] = scenarios
        s = summarize(r)
        self.assertAlmostEqual(s["maps"][2]["reach_probability"], .34)
        self.assertAlmostEqual(s["maps"][2]["a_win_given_played"], .206 / .34)
        self.assertAlmostEqual(s["maps"][0]["a_win_given_played"], .7)
        self.assertIsNone(s["map_rate_reason"])

    def test_unreachable_map_and_impossible_winner_are_null(self):
        nodes = constant_nodes(3, 1.)
        scores = series_tree(3, nodes)
        r = self.record(scores)
        r["scenarios"] = [{"id": "sweep", "weight": 1., "nodes": nodes,
                           "score_distribution": scores}]
        s = summarize(r)
        self.assertEqual(s["maps"][2]["reach_probability"], 0)
        self.assertIsNone(s["maps"][2]["a_win_given_played"])
        self.assertIsNone(s["winner_fair_odds"]["b"])
        self.assertEqual(s["representative_scores"]["b"]["scores"], [])

    def test_does_not_invent_map_or_round_probabilities(self):
        s = summarize(self.record({"2-0": .25, "2-1": .25, "1-2": .25, "0-2": .25}))
        self.assertIsNone(s["maps"][2]["a_win_given_played"])
        self.assertAlmostEqual(s["maps"][2]["reach_probability"], .5)
        self.assertIsNone(s["round_player_predictions"])

    def test_rejects_nodes_that_disagree_with_scores(self):
        r = copy.deepcopy(self.base)
        r["scenarios"][0]["nodes"]["ROOT"] = .99
        with self.assertRaisesRegex(ValueError, "conditional tree differs"):
            summarize(r)

    def test_unmodeled_has_no_numeric_prediction(self):
        r = self.record({})
        r["status"] = "unmodeled"
        s = summarize(r)
        self.assertIsNone(s["winner_pick"])
        self.assertNotIn("winner_probabilities", s)
        self.assertNotIn("score_distribution", s)

    def test_rejects_other_sports_and_unsupported_bo(self):
        r = copy.deepcopy(self.base)
        r["sport"] = "lol"
        with self.assertRaisesRegex(ValueError, "CS forecasts only"):
            summarize(r)
        with self.assertRaisesRegex(ValueError, "BO1, BO3 and BO5"):
            summarize(self.record({"2-0": .25, "1-1": .5, "0-2": .25}, 2))

    def test_cli_preserves_existing_artifact_on_changed_input(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "forecast.json"
            target = Path(directory) / "cs-presentation.json"
            source.write_text(json.dumps(self.base))
            cmd = [sys.executable, str(Path(__file__).with_name("summarize_forecast.py")),
                   str(source), "--output", str(target)]
            first = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            original = target.read_bytes()
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
            changed = copy.deepcopy(self.base)
            changed["missing_data"].append("new evidence gap")
            source.write_text(json.dumps(changed))
            blocked = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(blocked.returncode, 2)
            self.assertIn("already exists with different content", blocked.stderr)
            self.assertEqual(target.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
