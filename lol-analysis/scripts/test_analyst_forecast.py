"""Synthetic offline regression cases. No live results, odds, or publications."""
import copy
import importlib.util
import json
import math
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
    def test_solo_queue_evidence_is_replayable_without_an_automatic_probability_bonus(self):
        p = fixture()
        original = module.build(p)
        p["event"]["evidence"].append(dict(p["event"]["evidence"][0],
            id="solo", kind="solo_queue", claim="Synthetic public ranked champion practice"))
        p["judgment"]["scenarios"][0]["evidence_ids"].append("solo")
        p["judgment"]["scenarios"][1]["counterevidence_ids"].append("solo")
        result = module.build(p)
        self.assertEqual(result["score_distribution"], original["score_distribution"])
        self.assertEqual(result["confidence"], original["confidence"])
        self.assertEqual(result["generation_input"], p)
        self.assertTrue(module.replay(result)["replay_passed"])
        self.assertFalse(result["recommendation_eligible"])

    def test_solo_queue_cannot_replace_official_match_or_dependence_evidence(self):
        for replace in ("all_match_evidence", "one_team", "dependence"):
            p = fixture()
            if replace == "all_match_evidence":
                for evidence in p["event"]["evidence"]:
                    evidence["kind"] = "solo_queue"
            else:
                p["event"]["evidence"].append(dict(p["event"]["evidence"][0],
                    id="solo", kind="solo_queue"))
                if replace == "one_team":
                    for evidence in p["event"]["evidence"]:
                        if evidence["kind"] == "match_detail":
                            evidence["teams"] = [p["event"]["participants"][0]]
                    p["judgment"]["scenarios"][0]["evidence_ids"].append("solo")
                else:
                    scenario = p["judgment"]["scenarios"][0]
                    rates = scenario.pop("game_probabilities")
                    scenario.update(conditional_probabilities=module.game_tree(3, rates),
                        dependence_reason="Synthetic ranked streak; no official match evidence",
                        dependence_evidence_ids=["solo"])
            with self.subTest(replace=replace), self.assertRaises(ValueError):
                module.build(p)

    def test_solo_queue_evidence_keeps_cutoff_and_lock_requirements(self):
        for field, value in (("available_at", "2020-03-02T00:00:00Z"),
                             ("retrieved_at", "2020-03-01T10:06:00+08:00")):
            p = fixture()
            ranked = dict(p["event"]["evidence"][0], id="solo", kind="solo_queue")
            ranked[field] = value
            p["event"]["evidence"].append(ranked)
            p["judgment"]["scenarios"][0]["evidence_ids"].append("solo")
            with self.subTest(field=field), self.assertRaises(ValueError):
                module.build(p)

    def test_repeated_risk_wording_never_penalizes_quality_or_probabilities(self):
        p = fixture(5)
        p["judgment"]["scenarios"][0]["weight"] = .7
        p["judgment"]["scenarios"][1]["weight"] = .3
        p["event"]["missing_data"] = ["Synthetic missing early gold timeline"]
        p["event"]["risks"] = ["Synthetic uncertainty about the early gold lead"]
        original = module.build(p)
        expanded = copy.deepcopy(p)
        expanded["event"]["missing_data"] *= 5
        expanded["event"]["risks"] *= 5
        expanded["event"]["analysis_sections"] = [{"heading": "Same issue restated",
            "markdown": "The same synthetic timeline is missing; no new information."}]
        result = module.build(expanded)
        self.assertEqual(result["confidence"], original["confidence"])
        self.assertEqual(result["score_distribution"], original["score_distribution"])
        self.assertEqual(result["derived"], original["derived"])

    def test_evidence_quality_can_rise_or_fall_without_moving_winner_probability(self):
        p = fixture(5)
        p["judgment"]["scenarios"][0]["weight"] = .7
        p["judgment"]["scenarios"][1]["weight"] = .3
        original = module.build(p)
        # An absolute quality assessment is separate from team strength inputs.
        # This checks arithmetic/independence, not whether human scores are justified.
        for lineup_score, expected_total in ((20, 50), (100, 70)):
            updated = copy.deepcopy(p)
            updated["event"]["confidence"]["components"]["lineup_certainty"] = lineup_score
            updated["event"]["confidence"]["value"] = expected_total
            result = module.build(updated)
            self.assertEqual(result["confidence"]["value"], expected_total)
            self.assertEqual(result["score_distribution"], original["score_distribution"])
            self.assertEqual(result["derived"], original["derived"])
            self.assertFalse(result["recommendation_eligible"])

    def test_changed_team_assumptions_can_reverse_direction_without_quality_penalty(self):
        p = fixture(5)
        p["judgment"]["scenarios"][0]["weight"] = .7
        p["judgment"]["scenarios"][1]["weight"] = .3
        original = module.build(p)
        updated = copy.deepcopy(p)
        # Synthetic alternate assumptions, not a rule to reweight real opponents.
        updated["judgment"]["scenarios"][0]["weight"] = .3
        updated["judgment"]["scenarios"][1]["weight"] = .7
        result = module.build(updated)
        self.assertEqual(original["derived"]["winner_pick"], "a")
        self.assertEqual(result["derived"]["winner_pick"], "b")
        self.assertEqual(result["confidence"], original["confidence"])

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

    def test_audit_bo3_bo5_against_closed_form_and_preserves_input(self):
        for bo in (3, 5):
            f = module.build(fixture(bo))
            original = copy.deepcopy(f)
            result = module.audit(f)
            self.assertEqual(f, original)
            self.assertEqual(result, module.audit(f))
            self.assertFalse(result["production_change"])
            report = result["forecasts"][0]
            self.assertEqual(len(report["cases"]), 6)
            needed = bo//2+1
            # Independent closed-form score probability for constant game rates.
            for case in report["cases"]:
                expected = {}
                for lost in range(needed):
                    for winner in ("a", "b"):
                        key = f"{needed}-{lost}" if winner == "a" else f"{lost}-{needed}"
                        expected[key] = sum(s["weight"] * math.comb(needed+lost-1, lost)
                            * (s["game_probabilities"][0] if winner == "a" else 1-s["game_probabilities"][0])**needed
                            * (1-s["game_probabilities"][0] if winner == "a" else s["game_probabilities"][0])**lost
                            for s in case["parameters"])
                for key, probability in expected.items():
                    self.assertAlmostEqual(case["score_distribution"][key], probability)
                self.assertAlmostEqual(sum(case["score_distribution"].values()), 1)
                for line, probability in case["metrics"]["over_probabilities"].items():
                    self.assertAlmostEqual(probability, sum(p for k, p in expected.items()
                        if sum(map(int, k.split("-"))) > float(line)))
                self.assertNotIn("forecast_id", case)
            self.assertTrue(module.replay(f)["replay_passed"])

    def test_audit_handles_ties_and_real_direction_flips_separately(self):
        tied = module.audit(module.build(fixture()))["forecasts"][0]
        self.assertTrue(tied["summary"]["winner_set_change_case_ids"])
        self.assertFalse(tied["summary"]["winner_flip_case_ids"])
        payload = fixture()
        payload["judgment"]["scenarios"][0]["weight"] = .55
        payload["judgment"]["scenarios"][1]["weight"] = .45
        r = module.audit(module.build(payload))["forecasts"][0]
        self.assertIn("weight:0:1:-0.10", r["summary"]["winner_flip_case_ids"])

    def test_audit_exposes_one_sided_scenario_space_without_changing_forecast(self):
        p = fixture(5)
        for s, weight, rate in zip(p["judgment"]["scenarios"], (.7, .3), (.74, .5)):
            s.update(weight=weight, game_probabilities=[rate]*5)
        f = module.build(p)
        before = copy.deepcopy(f)
        audit = module.audit(f)
        geometry = audit["forecasts"][0]["scenario_space"]
        self.assertEqual(f, before)
        self.assertEqual(geometry["teams_without_strict_favorite_scenario"], ["b"])
        # With fixed scenario rates, no possible reweighting can favor B.
        self.assertAlmostEqual(geometry["winner_reweighting_envelope"]["b"][1], .5)
        self.assertAlmostEqual(geometry["winner_reweighting_envelope"]["a"][0], .5)
        expected_a = sum(math.comb(5, k)*.74**k*.26**(5-k) for k in range(3, 6))
        self.assertAlmostEqual(geometry["winner_reweighting_envelope"]["a"][1], expected_a)
        self.assertIn("one_sided_scenario_space", [w["kind"] for w in audit["warnings"]])
        self.assertTrue(module.replay(f)["replay_passed"])

    def test_scenario_space_uses_series_tree_not_average_game_rate(self):
        p = fixture(5)
        # Late near-certain wins are rarely reached after three near-certain losses.
        p["judgment"]["scenarios"][0]["game_probabilities"] = [.2, .2, .2, .99, .99]
        p["judgment"]["scenarios"][1]["game_probabilities"] = [.8, .8, .8, .01, .01]
        f = module.build(p)
        g = module.audit(f)["forecasts"][0]["scenario_space"]
        self.assertEqual(g["teams_without_strict_favorite_scenario"], [])
        self.assertEqual(g["scenarios"][0]["winner_ties"], ["b"])
        for s, actual in zip(f["scenarios"], g["scenarios"]):
            self.assertEqual(actual["winner_probabilities"], derive(s["score_distribution"])["winner_probabilities"])

    def test_scenario_space_ties_and_single_scenario_are_diagnostic(self):
        p = fixture(2)
        p["judgment"]["scenarios"] = p["judgment"]["scenarios"][:1]
        p["judgment"]["scenarios"][0].update(weight=1, game_probabilities=[.5, .5])
        f = module.build(p)
        g = module.audit(f)["forecasts"][0]["scenario_space"]
        self.assertEqual(g["teams_without_strict_favorite_scenario"], ["a", "b"])
        self.assertEqual(g["scenarios"][0]["winner_ties"], ["draw"])
        self.assertEqual(g["winner_reweighting_envelope"]["draw"], [.5, .5])

    def test_audit_skips_invalid_boundaries_without_clamping(self):
        payload = fixture()
        for s, w, p in zip(payload["judgment"]["scenarios"], (.1, .9), (.05, .95)):
            s.update(weight=w, game_probabilities=[p]*3)
        r = module.audit(module.build(payload))["forecasts"][0]
        self.assertEqual(len(r["skipped"]), 3)
        self.assertEqual(len(r["cases"]), 3)
        self.assertEqual({s["case_id"] for s in r["skipped"]},
                         {"weight:0:1:-0.10", "game_rates:0:-0.05", "game_rates:1:+0.05"})
        for case in r["cases"]:
            self.assertAlmostEqual(sum(s["weight"] for s in case["parameters"]), 1)

    def test_audit_all_scenario_pairs_and_single_scenario(self):
        p = fixture(5)
        third = copy.deepcopy(p["judgment"]["scenarios"][0])
        third.update(id="third", weight=.2, game_probabilities=[.5]*5)
        for s in p["judgment"]["scenarios"]:
            s["weight"] = .4
        p["judgment"]["scenarios"].append(third)
        self.assertEqual(len(module.audit(module.build(p))["forecasts"][0]["cases"]), 12)
        p["judgment"]["scenarios"] = [third]
        third["weight"] = 1
        r = module.audit(module.build(p))["forecasts"][0]
        self.assertEqual(len(r["cases"]), 2)
        self.assertFalse(r["skipped"])

    def test_audit_mirrored_reordered_parameters_flag_review_not_failure(self):
        p = fixture(5)
        p["judgment"]["scenarios"][0]["weight"] = .65
        p["judgment"]["scenarios"][1]["weight"] = .35
        first = module.build(p)
        other = copy.deepcopy(p)
        other["event"]["event_id"] = other["baseline"]["event_id"] = "other-event"
        for s in other["judgment"]["scenarios"]:
            s["game_probabilities"] = [1-x for x in s["game_probabilities"]]
        other["judgment"]["scenarios"].reverse()
        second = module.build(other)
        r = module.audit([first, second])
        self.assertEqual(r["warnings"][0]["kind"], "mirrored_parameters")
        self.assertEqual(r["warnings"][0]["severity"], "review")
        a, b = r["forecasts"]
        self.assertAlmostEqual(a["summary"]["first_team_probability_range"][0],
                               1-b["summary"]["first_team_probability_range"][1])
        other["event"]["event_id"] = other["baseline"]["event_id"] = p["event"]["event_id"]
        self.assertFalse([w for w in module.audit([first, module.build(other)])["warnings"]
                          if w["kind"] in ("mirrored_parameters", "repeated_parameters")])
        other["event"]["event_id"] = other["baseline"]["event_id"] = "other-event"
        other["judgment"]["scenarios"] = copy.deepcopy(p["judgment"]["scenarios"])
        self.assertEqual(module.audit([first, module.build(other)])["warnings"][0]["kind"], "repeated_parameters")

    def test_audit_rejects_tampered_or_duplicate_batch_before_output(self):
        f = module.build(fixture())
        for payload in ([], [f, f]):
            with self.assertRaises(ValueError):
                module.audit(payload)
        bad = copy.deepcopy(f)
        bad["generation_input"]["judgment"]["scenarios"][0]["weight_reason"] = "Changed"
        with self.assertRaises(ValueError):
            module.audit([f, bad])
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp)/"batch.json", Path(tmp)/"audit.json"
            src.write_text(json.dumps([f, bad]))
            cli = [sys.executable, module.__file__, "audit", str(src), "--output", str(dst)]
            result = subprocess.run(cli, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(dst.exists())
            src.write_text(json.dumps([f]))
            result = subprocess.run(cli, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            before = dst.read_bytes()
            self.assertEqual(subprocess.run(cli, capture_output=True).returncode, 0)
            p = fixture()
            p["judgment"]["scenarios"][0]["game_probabilities"] = [.7]*3
            src.write_text(json.dumps(module.build(p)))
            self.assertNotEqual(subprocess.run(cli, capture_output=True).returncode, 0)
            self.assertEqual(dst.read_bytes(), before)


def conditional_fixture(best_of=5, persistence=.2):
    """Synthetic prior-result dependence, not an estimate for any real team."""
    payload = fixture(best_of)
    s = payload["judgment"]["scenarios"][0]
    payload["judgment"]["scenarios"] = [s]
    s["weight"] = 1
    s["conditional_probabilities"] = {path: .5 if path == "ROOT" else
        persistence if path.endswith("W") else 1-persistence
        for path in module.game_tree(best_of, [.5]*best_of)}
    del s["game_probabilities"]
    s["dependence_reason"] = "Synthetic symmetric Markov test; not a fitted comeback effect"
    s["dependence_evidence_ids"] = ["fixture"]
    return payload


class ConditionalTests(unittest.TestCase):
    def test_constant_mixture_is_weighted_over_not_over_of_average_strength(self):
        p = fixture(5)
        template = p["judgment"]["scenarios"][0]
        p["judgment"]["scenarios"] = [dict(template, id=str(i), weight=w, game_probabilities=[rate]*5)
            for i, (w, rate) in enumerate(((.5, .38), (.3, .6), (.2, .5)))]
        f = module.build(p)
        d = module.length_diagnostics(f)
        self.assertAlmostEqual(d["over_3_5"], .7194)
        average = .5*.38+.3*.6+.2*.5
        self.assertNotAlmostEqual(d["over_3_5"], 3*average*(1-average))
        self.assertEqual(d["structural_over_3_5_ceiling"], .75)

    def test_negative_and_positive_dependence_have_exact_sweep_probabilities(self):
        for persistence in (.2, .5, .8):
            with self.subTest(persistence=persistence):
                payload = conditional_fixture(persistence=persistence)
                before = copy.deepcopy(payload)
                f = module.build(payload)
                self.assertEqual(payload, before)
                self.assertEqual(f["model_version"], module.CONDITIONAL_VERSION)
                self.assertTrue(module.replay(f)["replay_passed"])
                self.assertAlmostEqual(f["score_distribution"]["3-0"], .5*persistence**2)
                self.assertAlmostEqual(f["score_distribution"]["0-3"], .5*persistence**2)
                self.assertAlmostEqual(f["derived"]["both_at_least_one"], 1-persistence**2)
                self.assertAlmostEqual(f["derived"]["winner_probabilities"]["a"], .5)
                self.assertAlmostEqual(sum(f["score_distribution"].values()), 1)
                d = f["length_diagnostics"]
                self.assertAlmostEqual(d["over_3_5"]+d["under_3_5"], 1)
                self.assertLessEqual(d["over_4_5"], d["over_3_5"])
                self.assertEqual(d["structural_over_3_5_ceiling"], .75 if persistence == .5 else None)
                self.assertFalse(f["recommendation_eligible"])

    def test_all_formats_and_mixed_input_scenarios(self):
        for bo in (1, 2, 3, 5):
            p = conditional_fixture(bo)
            legacy = fixture(bo)["judgment"]["scenarios"][1]
            p["judgment"]["scenarios"][0]["weight"] = .5
            p["judgment"]["scenarios"].append(legacy)
            f = module.build(p)
            self.assertTrue(module.replay(f)["replay_passed"])
            self.assertAlmostEqual(sum(f["score_distribution"].values()), 1)
            self.assertTrue(module.audit(f)["forecasts"][0]["cases"])

    def test_sweeps_use_history_not_game_index_or_average_rate(self):
        p = conditional_fixture()
        nodes = p["judgment"]["scenarios"][0]["conditional_probabilities"]
        nodes.update(ROOT=.6, W=.8, WW=.9, L=.3, LL=.2)
        f = module.build(p)
        self.assertAlmostEqual(f["score_distribution"]["3-0"], .6*.8*.9)
        self.assertAlmostEqual(f["score_distribution"]["0-3"], .4*.7*.8)
        self.assertAlmostEqual(f["length_diagnostics"]["over_3_5"], 1-.6*.8*.9-.4*.7*.8)
        original_over = f["length_diagnostics"]["over_3_5"]
        # Late-game rates can change winners and O4.5, but cannot change O3.5.
        for path in nodes:
            if path != "ROOT" and len(path) >= 3:
                nodes[path] = .91
        changed = module.build(p)
        self.assertAlmostEqual(changed["length_diagnostics"]["over_3_5"], original_over)
        self.assertNotEqual(changed["score_distribution"], f["score_distribution"])

    def test_incomplete_extra_invalid_nodes_and_ambiguous_inputs_rejected(self):
        for mutation in (lambda s: s["conditional_probabilities"].pop("WL"),
                         lambda s: s["conditional_probabilities"].update(WWW=.5),
                         lambda s: s["conditional_probabilities"].update(ROOT=True),
                         lambda s: s["conditional_probabilities"].update(ROOT=float("nan")),
                         lambda s: s["conditional_probabilities"].update(ROOT=1),
                         lambda s: s.update(game_probabilities=[.5]*5),
                         lambda s: s.update(conditional_probabilities=[.5]*5),
                         lambda s: s.update(dependence_reason=""),
                         lambda s: s.update(dependence_evidence_ids=[]),
                         lambda s: s.update(dependence_evidence_ids=["unknown"])):
            p = conditional_fixture()
            mutation(p["judgment"]["scenarios"][0])
            with self.assertRaises(ValueError):
                module.build(p)

    def test_dependence_needs_match_detail_not_a_roster_reference(self):
        p = conditional_fixture()
        p["event"]["evidence"].append(dict(p["event"]["evidence"][0], id="roster", kind="lineup"))
        p["judgment"]["scenarios"][0]["dependence_evidence_ids"] = ["roster"]
        with self.assertRaises(ValueError):
            module.build(p)

    def test_conditional_mirror_swaps_history_and_next_game_probability(self):
        p = conditional_fixture()
        nodes = p["judgment"]["scenarios"][0]["conditional_probabilities"]
        nodes.update(ROOT=.65, W=.4, L=.8, WW=.3, LL=.75)
        f = module.build(p)
        other = copy.deepcopy(p)
        other["event"]["event_id"] = other["baseline"]["event_id"] = "mirror-event"
        other["judgment"]["scenarios"][0]["conditional_probabilities"] = {
            path.translate(str.maketrans("WL", "LW")): 1-rate for path, rate in nodes.items()}
        m = module.build(other)
        for score, probability in f["score_distribution"].items():
            self.assertAlmostEqual(probability, m["score_distribution"]["-".join(score.split("-")[::-1])])
        self.assertIn("mirrored_parameters", [w["kind"] for w in module.audit([f, m])["warnings"]])

    def test_audit_stresses_dependence_separately_from_strength(self):
        f = module.build(conditional_fixture())
        original = copy.deepcopy(f)
        a = module.audit(f)
        self.assertEqual(f, original)
        self.assertEqual(a["schema_version"], "lol-analyst-audit-v2")
        cases = a["forecasts"][0]["cases"]
        self.assertEqual(len(cases), 4)
        dependence = [c for c in cases if c["change"]["kind"] == "previous_result_dependence"]
        for case in dependence:
            delta = case["change"]["delta_after_win"]
            self.assertAlmostEqual(case["metrics"]["winner_probabilities"]["a"], .5)
            self.assertAlmostEqual(case["metrics"]["over_probabilities"]["3.5"], 1-(.2+delta)**2)
        self.assertFalse([w for w in a["warnings"] if w["kind"] == "constant_rate_length_constraint"])

    def test_conditional_container_does_not_hide_constant_rate_constraint(self):
        p = conditional_fixture()
        p["judgment"]["scenarios"][0]["conditional_probabilities"] = module.game_tree(5, [.6]*5)
        f = module.build(p)
        self.assertAlmostEqual(f["length_diagnostics"]["over_3_5"], .72)
        self.assertIn("constant_rate_length_constraint", [w["kind"] for w in module.audit(f)["warnings"]])

    def test_diagnostics_catch_tampering_and_cli_replays_v2(self):
        f = module.build(conditional_fixture())
        tampered = copy.deepcopy(f)
        tampered["length_diagnostics"]["over_3_5"] = .72
        with self.assertRaises(ValueError):
            module.replay(tampered)
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp)/"input.json", Path(tmp)/"forecast.json"
            src.write_text(json.dumps(conditional_fixture()))
            base = [sys.executable, module.__file__]
            build = subprocess.run(base+["build", str(src), "--output", str(dst)], capture_output=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            check = subprocess.run(base+["validate", str(dst)], capture_output=True)
            self.assertEqual(check.returncode, 0, check.stderr)
            self.assertEqual(json.loads(dst.read_text()), f)


if __name__ == "__main__":
    unittest.main()
