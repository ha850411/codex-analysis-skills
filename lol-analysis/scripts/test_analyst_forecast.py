"""Synthetic offline regression cases. No live results, odds, or publications."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from shared.forecast.cli import forecast
from shared.forecast.core import derive
from shared.forecast.fixtures import event, history
from shared.forecast.models import train
from shared.forecast.render import render

spec = importlib.util.spec_from_file_location("analyst_forecast", Path(__file__).with_name("analyst_forecast.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture(best_of=3):
    e = event()
    e["best_of"] = best_of
    for item in e["evidence"]:
        item.update(kind="match_detail", teams=e["participants"])
    e["evidence"].append(dict(e["evidence"][0], id="counter", claim="Synthetic observed counterexample"))
    b = forecast(train(history(), "lol", e["data_cutoff"]), e)
    e["created_at"] = "2020-03-01T10:05:00+08:00"

    def scenario(name, weight, p):
        return dict(id=name, weight=weight, weight_reason="Synthetic relative plausibility for the offline test",
                    mechanism="Synthetic game 1 setup protects the carry at the first objective",
                    evidence_ids=["fixture"], counterevidence_ids=["counter"],
                    game_probabilities=[p]*best_of, probabilities_reason="Synthetic hypothetical rates, not fitted",
                    invalidation="The opponent denies access to the objective before the setup")
    return dict(event=e, baseline=b, judgment=dict(locked_at=e["created_at"],
        baseline_departure="Synthetic shared match state rather than independent map strength",
        counterargument="Synthetic opponent can break the setup; not a real match analysis",
        scenarios=[scenario("setup_holds", .5, .8), scenario("setup_denied", .5, .2)]))


class AnalystTests(unittest.TestCase):
    def test_mixture_preserves_equal_winner_but_changes_sweep_risk(self):
        p = fixture()
        original = copy.deepcopy(p)
        f = module.build(p)
        self.assertEqual(p, original)
        self.assertAlmostEqual(f["derived"]["winner_probabilities"]["a"], .5)
        self.assertAlmostEqual(f["score_distribution"]["2-0"], .34)
        self.assertAlmostEqual(f["score_distribution"]["0-2"], .34)
        self.assertAlmostEqual(f["derived"]["both_at_least_one"], .32)
        self.assertEqual(f["score_distribution"], module.build(p)["score_distribution"])
        self.assertTrue(module.replay(f)["replay_passed"])
        self.assertFalse(f["recommendation_eligible"])

    def test_formats_and_swapping_team_coordinate(self):
        for bo in (1, 2, 3, 5):
            p = fixture(bo)
            p["judgment"]["scenarios"][0]["weight"] = .7
            p["judgment"]["scenarios"][1]["weight"] = .3
            f = module.build(p)
            mirror = copy.deepcopy(p)
            mirror["event"]["participants"].reverse()
            mirror["baseline"]["participants"].reverse()
            bd = mirror["baseline"]["score_distribution"]
            mirror["baseline"]["score_distribution"] = {"-".join(k.split("-")[::-1]):v for k,v in bd.items()}
            mirror["baseline"]["derived"] = derive(mirror["baseline"]["score_distribution"])
            for scenario in mirror["baseline"].get("scenarios", []):
                scenario["score_distribution"] = {"-".join(k.split("-")[::-1]):v
                                                    for k,v in scenario["score_distribution"].items()}
            for s in mirror["judgment"]["scenarios"]:
                s["game_probabilities"] = [1-v for v in s["game_probabilities"]]
            m = module.build(mirror)
            for score, probability in f["score_distribution"].items():
                self.assertAlmostEqual(probability, m["score_distribution"]["-".join(score.split("-")[::-1])])
            self.assertAlmostEqual(sum(f["score_distribution"].values()), 1)

    def test_distribution_and_status_tampering_cannot_pass_replay(self):
        original = module.build(fixture())
        for field, value in (("status", "production"), ("parameter_source", "fitted"),
                             ("model_artifact_hash", "other"), ("calibration_status", "calibrated")):
            f = copy.deepcopy(original)
            f[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                module.replay(f)
        f = copy.deepcopy(original)
        f["score_distribution"]["2-0"] += .01
        f["score_distribution"]["0-2"] -= .01
        f["derived"] = derive(f["score_distribution"])
        with self.assertRaises(ValueError):
            module.replay(f)

    def test_rejects_market_inputs(self):
        p = fixture()
        p["event"]["market_data"] = [{"odds": 1.5}]
        with self.assertRaises(ValueError):
            module.build(p)
        p = fixture()
        p["event"]["evidence"][0]["kind"] = "market"
        with self.assertRaises(ValueError):
            module.build(p)

    def test_schedule_only_or_one_sided_evidence_is_insufficient(self):
        for kind, teams in (("schedule", ["Example A", "Example B"]), ("match_detail", ["Example A"])):
            p = fixture()
            for e in p["event"]["evidence"]:
                e.update(kind=kind, teams=teams)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                module.build(p)

    def test_unknown_refs_empty_counter_and_missing_mechanism_rejected(self):
        for field, value in (("evidence_ids", ["unknown"]), ("counterevidence_ids", []),
                             ("mechanism", ""), ("probabilities_reason", "")):
            p = fixture()
            p["judgment"]["scenarios"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                module.build(p)

    def test_invalid_weights_probabilities_and_duplicate_ids(self):
        for field, value in (("weight", .8), ("game_probabilities", [60, 60, 60]),
                             ("game_probabilities", [True]*3), ("game_probabilities", [float("nan")]*3),
                             ("game_probabilities", [1]*3), ("game_probabilities", [.5]),
                             ("id", "setup_denied")):
            p = fixture()
            p["judgment"]["scenarios"][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                module.build(p)

    def test_future_evidence_and_poststart_estimates_rejected(self):
        for target, field, value in (("evidence", "available_at", "2020-03-02T00:00:00Z"),
                                     ("evidence", "retrieved_at", "2020-03-01T10:06:00+08:00"),
                                     ("event", "created_at", "2020-03-01T20:00:00+08:00"),
                                     ("judgment", "locked_at", "2020-03-01T10:06:00+08:00")):
            p = fixture()
            obj = p["event"]["evidence"][0] if target=="evidence" else p[target]
            obj[field] = value
            with self.subTest(target=target, field=field), self.assertRaises(ValueError):
                module.build(p)

    def test_baseline_other_event_or_orientation_rejected(self):
        for field, value in (("event_id", "different"), ("participants", ["Example B", "Example A"]),
                             ("data_cutoff", "2020-03-01T08:30:00+08:00")):
            p = fixture()
            p["event"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                module.build(p)

    def test_evidence_cannot_arrive_between_lock_and_creation(self):
        p = fixture()
        p["event"]["created_at"] = "2020-03-01T10:10:00+08:00"
        p["event"]["evidence"][0]["retrieved_at"] = "2020-03-01T10:06:00+08:00"
        with self.assertRaises(ValueError):
            module.build(p)

    def test_render_explains_subjective_basis_and_baseline(self):
        f = module.build(fixture())
        text = render([f])
        self.assertIn("分析者情境估計（實驗，未實證校準）", text)
        self.assertIn(f["generation_input"]["judgment"]["baseline_departure"], text)
        self.assertIn("比分基準比較", text)
        self.assertIn("60/100（證據品質）", text)
        self.assertIn("0u", text)
        self.assertEqual(text.count("簡表總結"), 1)

    def test_cli_build_replay_and_create_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp)/"input.json", Path(tmp)/"forecast.json"
            p = fixture()
            src.write_text(json.dumps(p))
            base = [sys.executable, str(Path(module.__file__))]
            built = subprocess.run(base+["build", str(src), "--output", str(dst)], capture_output=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            replayed = subprocess.run(base+["validate", str(dst)], capture_output=True)
            self.assertEqual(replayed.returncode, 0, replayed.stderr)
            p["judgment"]["scenarios"][0]["game_probabilities"] = [.7]*3
            src.write_text(json.dumps(p))
            overwrite = subprocess.run(base+["build", str(src), "--output", str(dst)], capture_output=True)
            self.assertNotEqual(overwrite.returncode, 0)
            self.assertEqual(json.loads(dst.read_text())["generation_input"]["judgment"]["scenarios"][0]["game_probabilities"], [.8]*3)


if __name__ == "__main__":
    unittest.main()
