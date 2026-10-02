from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from forecast.data import history
from forecast.strength import train, FACTORS, observations, settings, map_probability
from forecast.series import predict, tree, validate_forecast
from forecast.veto import paths
from forecast.compat import render
from forecast.evaluate import evaluate, compare, walk_forward
from forecast.archive_input import import_archive
from shared.forecast.core import canonical

CUTOFF = "2026-09-01T00:00:00Z"


def registry():
    return {"factors": [{"factor_id": f, "status": "candidate", "used_for_prediction": False,
                         "mechanism": "synthetic conditional signal", "pre_match_observable": "timestamped map contexts"}
                        for f in sorted(set(FACTORS.values()) | {"availability-conditioned-veto-selection"})]}


def fixture_history(n=36):
    rows = []
    for i in range(n):
        teams = ["A", "B"] if i % 3 == 0 else (["A", "C"] if i % 3 == 1 else ["B", "C"])
        win_a = i % 4 != 0
        at = (datetime(2026, 6, 1, tzinfo=timezone.utc) + timedelta(days=i)).isoformat()
        # A 2-1 series must end on the winner's map; no maps after the clincher.
        winners = [teams[0], teams[1], teams[0 if win_a else 1]]
        games = [{"map": mp, "winner": w, "context": {"patch": "test-1", "a_start_side": "attack"}}
                 for mp, w in zip(["X", "Y", "Z"], winners)]
        actions = [{"team": teams[0], "action": "pick", "map": "X", "available_before": ["X", "Y", "Z"]},
                   {"team": teams[1], "action": "pick", "map": "Y", "available_before": ["Y", "Z"]},
                   {"team": None, "action": "decider", "map": "Z", "available_before": ["Z"]}]
        rows.append({"event_id": "h" + str(i), "sport": "valorant", "participants": teams, "best_of": 3,
                     "score": [2, 1] if win_a else [1, 2], "completed_at": at, "available_at": at,
                     "result_status": "final", "source_url": "https://example.test/" + str(i), "games": games,
                     "veto": {"pool": ["X", "Y", "Z"], "actions": actions, "available_at": at}})
    return rows


def fixture_event(bo=3):
    pool = ["X", "Y", "Z", "U", "V", "W", "Q"] if bo == 5 else ["X", "Y", "Z"]
    return {"event_id": "target", "sport": "valorant", "competition": "Synthetic", "snapshot": "pre-veto",
            "created_at": CUTOFF, "data_cutoff": CUTOFF, "scheduled_start": "2026-09-02T00:00:00Z",
            "participants": ["A", "B"], "scope": "full-series", "best_of": bo, "confidence": None,
            "evidence": [{"id": "facts", "url": "https://example.test/facts", "claim": "synthetic fixture only", "available_at": CUTOFF, "retrieved_at": CUTOFF}],
            "input_evidence_ids": ["facts"], "map_pool": pool,
            "veto_scenarios": [{"id": "known", "weight": 1., "maps": pool[:bo], "pick_owners": ["a", "b", None] if bo == 3 else [None] * bo,
                                "evidence_ids": ["facts"], "weight_source": "confirmed", "weight_basis": "synthetic confirmed order"}]}


def protocol_event():
    e = fixture_event(); e.pop("veto_scenarios")
    e["veto"] = {"protocol": [{"actor": "first", "action": "pick"}, {"actor": "second", "action": "pick"},
                              {"actor": None, "action": "decider"}], "evidence_ids": ["facts"]}
    return e


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = fixture_history()
        cls.model = train(cls.raw, CUTOFF, registry=registry())

    def test_full_replay_and_canonical_v2(self):
        event = fixture_event(); result = predict(self.model, event)
        self.assertTrue(validate_forecast(result, self.model, event)["full_replay"])
        self.assertAlmostEqual(sum(result["score_distribution"].values()), 1)
        self.assertFalse(result["recommendation_eligible"])

    def test_map_strength_reaches_primary_distribution(self):
        event = fixture_event(); model = copy.deepcopy(self.model)
        before = predict(model, event)
        model["strength"]["weights"][canonical(["map", "A", "X"])] += 1
        after = predict(model, event)
        self.assertNotEqual(before["score_distribution"], after["score_distribution"])
        self.assertGreater(after["derived"]["winner_probabilities"]["a"], before["derived"]["winner_probabilities"]["a"])

    def test_series_and_maps_do_not_duplicate_weight(self):
        rows, _ = history(self.raw[:1], CUTOFF)
        samples = observations(rows, CUTOFF, settings({"half_life_days": None}))
        self.assertAlmostEqual(sum(w for _, _, w in samples), 1)

    def test_future_result_and_late_map_metadata_excluded(self):
        raw = copy.deepcopy(self.raw)
        raw[0]["map_data_verified_at"] = "2027-01-01T00:00:00Z"
        raw[-1]["available_at"] = "2027-01-01T00:00:00Z"
        rows, gaps = history(raw, CUTOFF)
        self.assertEqual(len(rows), len(raw) - 1)
        self.assertEqual(rows[0]["games"], [])
        self.assertEqual(gaps["map_metadata_after_cutoff"], 3)

    def test_context_availability_does_not_erase_known_map_result(self):
        raw = copy.deepcopy(self.raw[:1]); raw[0]["games"][0]["context_available_at"] = "2027-01-01T00:00:00Z"
        rows, _ = history(raw, CUTOFF)
        self.assertEqual(rows[0]["games"][0]["context"], {})
        self.assertEqual(len(rows[0]["games"]), 3)

    def test_duplicate_maps_and_contradictory_winners_rejected(self):
        raw = copy.deepcopy(self.raw[:1]); raw[0]["games"].append(raw[0]["games"][0])
        with self.assertRaisesRegex(ValueError, "duplicate"): history(raw, CUTOFF)
        raw = copy.deepcopy(self.raw[:1])
        for g in raw[0]["games"]: g["winner"] = "A"
        with self.assertRaisesRegex(ValueError, "contradict"): history(raw, CUTOFF)

    def test_target_leak_market_inputs_and_retired_factor_rejected(self):
        for field, value, message in [("event_id", "h0", "leaked"), ("market_odds", 2., "market"), ("actual_score", "2-0", "outcomes")]:
            e = fixture_event(); e[field] = value
            with self.assertRaisesRegex(ValueError, message): predict(self.model, e)
        reg = registry(); reg["factors"][0]["status"] = "retired"
        with self.assertRaisesRegex(ValueError, "non-retired"): train(self.raw, CUTOFF, registry=reg)

    def test_unseen_map_borrows_team_strength(self):
        m = copy.deepcopy(self.model)
        m["strength"]["weights"][canonical(["team", "A"])] = 1.
        m["strength"]["weights"][canonical(["team", "B"])] = 0.
        p, trace = map_probability(m, ["A", "B"], "NEW", {})
        self.assertGreater(p, .7); self.assertTrue(trace["unseen"])

    def test_six_player_map_rotation_changes_primary(self):
        e = fixture_event(); la, lb = ["a" + str(i) for i in range(5)], ["b" + str(i) for i in range(5)]
        e["contexts_by_map"] = {"X": {"lineups": [la, lb]}}
        m = copy.deepcopy(self.model); m["strength"]["weights"][canonical(["roster", "A", sorted(la)])] = 1.
        before = predict(m, e)
        alternate = [*la[:4], "sixth"]
        e["roster_scenarios"] = [{"id": "rotation", "weight": 1., "weight_source": "confirmed", "weight_basis": "map specialist",
                                 "evidence_ids": ["facts"], "contexts_by_map": {"X": {"lineups": [alternate, lb]}}}]
        after = predict(m, e)
        self.assertNotEqual(before["score_distribution"], after["score_distribution"])
        self.assertEqual(after["scenarios"][0]["contexts"][0]["lineups"][0], alternate)

    def test_team_order_symmetry(self):
        e = fixture_event(); a = predict(self.model, e)
        e["participants"] = ["B", "A"]; e["veto_scenarios"][0]["pick_owners"] = ["b", "a", None]
        b = predict(self.model, e)
        for s, p in a["score_distribution"].items():
            x, y = s.split("-"); self.assertAlmostEqual(p, b["score_distribution"][y + "-" + x])

    def test_known_bo3_answer(self):
        t = tree([.8, .3, .6], 0., 3)
        self.assertAlmostEqual(t["score_distribution"]["2-0"], .24)
        self.assertAlmostEqual(t["score_distribution"]["0-2"], .14)
        self.assertAlmostEqual(t["score_distribution"]["2-1"], .62 * .6)
        self.assertAlmostEqual(t["played"][2], .62)

    def test_shared_state_conditions_on_reaching_decider(self):
        t = tree([.8, .7, .65], 1., 3)
        self.assertNotAlmostEqual(t["won"][2] / t["played"][2], .65, places=5)
        self.assertAlmostEqual(sum(t["score_distribution"].values()), 1)

    def test_bo1_and_bo5_legal_support(self):
        for bo, outcomes in [(1, 2), (5, 6)]:
            r = predict(self.model, fixture_event(bo)); validate_forecast(r)
            self.assertEqual(len(r["score_distribution"]), outcomes)

    def test_exact_veto_enumeration_and_prefix_conditioning(self):
        e = protocol_event(); orders, audit = paths(self.model, e)
        self.assertEqual(audit["legal_paths"], 12)
        self.assertAlmostEqual(sum(p["weight"] for p in orders), 1)
        self.assertTrue(all(len(set(p["maps"])) == 3 for p in orders))
        e["veto"]["observed"] = [{"actor": "a", "action": "pick", "map": "X"}]
        orders, _ = paths(self.model, e)
        self.assertTrue(all(o["maps"][0] == "X" and o["pick_owners"][0] == "a" for o in orders))
        self.assertAlmostEqual(sum(o["weight"] for o in orders), 1)

    def test_bad_opportunity_sets_rejected(self):
        raw = copy.deepcopy(self.raw[:1]); raw[0]["veto"]["actions"][1]["available_before"].append("X")
        with self.assertRaisesRegex(ValueError, "opportunity"): history(raw, CUTOFF)

    def test_confirmed_veto_does_not_need_historical_choice_samples(self):
        e = protocol_event(); e["snapshot"] = "post-veto"
        e["veto"]["observed"] = [{"actor": a, "action": k, "map": mp} for a, k, mp in
                                [("a", "pick", "X"), ("b", "pick", "Y"), (None, "decider", "Z")]]
        m = copy.deepcopy(self.model); m["veto"]["records"] = []
        f = predict(m, e)
        self.assertEqual(f["valorant"]["veto"]["mode"], "observed")
        self.assertEqual(len(f["scenarios"]), 1)

    def test_unresolved_fallback_and_false_post_veto(self):
        e = fixture_event(); e.pop("veto_scenarios"); f = predict(self.model, e)
        self.assertEqual(f["valorant"]["maps"]["X"]["status"], "standalone-unintegrated")
        self.assertIsNone(f["valorant"]["maps"]["X"]["played_probability"])
        e["snapshot"] = "post-veto"
        with self.assertRaises(ValueError): predict(self.model, e)

    def test_tampered_map_rate_and_input_fail_replay(self):
        e = fixture_event(); f = predict(self.model, e)
        f["valorant"]["maps"]["X"]["a"] += .01; f["valorant"]["maps"]["X"]["b"] -= .01
        with self.assertRaisesRegex(ValueError, "conditional"): validate_forecast(f)
        f = predict(self.model, e); f["key_points"] = ["altered"]
        with self.assertRaisesRegex(ValueError, "replay"): validate_forecast(f, self.model, e)

    def test_template_fields_quick_daily_full(self):
        f = predict(self.model, fixture_event())
        for mode in ("quick", "daily-summary", "full"):
            text = render([f], mode)
            for label in ("預測結論", "獨贏", "完整比分分布", "至少一圖", "橫掃", "大於 2.5", "小於 2.5", "預期總圖數", "逐圖勝率預測"):
                self.assertIn(label, text)
            self.assertEqual(text.count("| 比賽 | 核心預測 | 模型信心度 | 建議 | 核心風險 |"), 1)
            for mp in ("X", "Y", "Z"): self.assertEqual(text.count("- **" + mp + "**"), 1)
            self.assertTrue(text.rstrip().endswith("|"))

    def test_excluded_maps_bo5_markets_and_bo1_no_invalid_lines(self):
        text = render([predict(self.model, fixture_event(5))])
        self.assertIn("- **Q**：A **N/A**｜B **N/A**", text)
        for label in ("-2.5", "+2.5", "-1.5", "+1.5", "3.5", "4.5"): self.assertIn(label, text)
        self.assertNotIn("1.5", render([predict(self.model, fixture_event(1))]))

    def test_outcomes_scored_separately_and_small_cohort_not_promoted(self):
        f = predict(self.model, fixture_event()); f.update(actual_score="2-1", result_status="final", eligibility="historical_replay")
        result = evaluate([f]); self.assertEqual(result["overall"]["scored_n"], 1)
        self.assertIn("total_gt_2.5_brier", result["market_metrics"])
        old = copy.deepcopy(f); old["model_version"] = "control"
        comparison = compare([old, f], "control", f["model_version"])
        self.assertFalse(comparison["passed"]); self.assertEqual(comparison["decision"], "experiment-only")

    def test_walk_forward_preserves_failed_candidate(self):
        e = fixture_event(); e["map_pool"] = []
        result = walk_forward({"history": self.raw, "targets": [{"event": e}]}, registry())
        self.assertEqual(len(result["records"]), 2)
        self.assertEqual(result["records"][1]["status"], "unmodeled")
        self.assertFalse(result["comparison"]["passed"])

    def test_cli_round_trip_and_create_only_artifacts(self):
        cli = Path(__file__).with_name("valorant_forecast.py")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, value in [("model", self.model), ("event", fixture_event())]: (root / (name + ".json")).write_text(json.dumps(value))
            args = [sys.executable, str(cli), "predict", str(root / "event.json"), "--model", str(root / "model.json"), "--output", str(root / "forecast.json")]
            result = subprocess.run(args, capture_output=True, text=True); self.assertEqual(result.returncode, 0, result.stderr)
            val = subprocess.run([sys.executable, str(cli), "validate", str(root / "forecast.json"), "--model", str(root / "model.json"), "--event", str(root / "event.json")], capture_output=True, text=True)
            self.assertEqual(val.returncode, 0, val.stderr)
            e = fixture_event(); e["key_points"] = ["changed"]; (root / "event.json").write_text(json.dumps(e))
            self.assertEqual(subprocess.run(args, capture_output=True).returncode, 2)

    def test_opponent_adjustment_can_reverse_raw_win_rate_ranking(self):
        rows = []
        for teams, score_value, n in [(["Strong", "Weak"], [2, 0], 100), (["A", "Strong"], [1, 2], 25), (["B", "Weak"], [2, 1], 25)]:
            for _ in range(n):
                r = copy.deepcopy(self.raw[0]); r.update(event_id="opp-" + str(len(rows)), participants=teams, score=score_value)
                r.pop("games"); r.pop("veto"); rows.append(r)
        model = train(rows, CUTOFF, {"layers": ["team"], "half_life_days": None}, registry())
        # A lost every series against Strong; B won every series against Weak.
        self.assertGreater(map_probability(model, ["A", "B"], None, {})[0], .5)

    def test_veto_denominator_excludes_maps_already_banned_by_opponent(self):
        rows = []
        for i in range(80):
            r = copy.deepcopy(self.raw[0]); r.update(event_id="veto-" + str(i)); r.pop("games")
            choices = [("B", "ban", "W"), ("A", "pick", "X"), ("B", "pick", "Y"), (None, "decider", "Z")] if i < 40 else [("B", "ban", "X"), ("A", "pick", "Y"), ("B", "pick", "W"), (None, "decider", "Z")]
            remaining, actions = set("WXYZ"), []
            for team, action, mp in choices:
                actions.append({"team": team, "action": action, "map": mp, "available_before": sorted(remaining)}); remaining.remove(mp)
            r["veto"] = {"pool": list("WXYZ"), "actions": actions, "available_at": r["available_at"]}; rows.append(r)
        m = train(rows, CUTOFF, registry=registry())
        e = protocol_event(); e["map_pool"] = list("WXYZ")
        e["veto"].update(first_actor="b", protocol=[{"actor": a, "action": k} for a, k in [("first", "ban"), ("second", "pick"), ("first", "pick"), (None, "decider")]], observed=[{"actor": "b", "action": "ban", "map": "W"}])
        orders, _ = paths(m, e)
        p = {mp: sum(x["weight"] for x in orders if x["maps"][0] == mp) for mp in "XYZ"}
        self.assertGreater(p["X"], p["Y"])

    def test_zero_and_one_map_probabilities_stay_exact(self):
        self.assertEqual(tree([0.], 1., 1)["score_distribution"], {"1-0": 0., "0-1": 1.})
        self.assertEqual(tree([1.], 1., 1)["score_distribution"], {"1-0": 1., "0-1": 0.})

    def test_archive_import_preserves_earlier_map_availability(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "sources").mkdir()
            row = copy.deepcopy(self.raw[0]); row["event_id"] = "vlr-1"; row["games"][0].pop("context")
            (root / "history.json").write_text(json.dumps([row]))
            match = {"url": "https://www.vlr.gg/1/test", "date": "Patch 1.0", "maps": [{"map": "X", "teams": [{"name": "A", "score": "13"}, {"name": "B", "score": "5"}]}]}
            (root / "matches-complete.json").write_text(json.dumps([match]))
            (root / "sources/match-1-meta.json").write_text(json.dumps({"retrieved_at": "2027-01-01T00:00:00Z"}))
            imported = import_archive({"run_dir": str(root)})
            before, _ = history(imported["history"], CUTOFF)
            self.assertEqual(before[0]["games"][0]["map"], "X")
            self.assertEqual(before[0]["games"][0]["context"], {})
            after, _ = history(imported["history"], "2028-01-01T00:00:00Z")
            self.assertEqual(after[0]["games"][0]["context"]["patch"], "1.0")

    def test_bo5_veto_samples_not_pooled_into_bo3(self):
        m = copy.deepcopy(self.model)
        for row in m["veto"]["records"]: row["best_of"] = 5
        e = protocol_event()
        f = predict(m, e)
        self.assertEqual(f["valorant"]["veto"]["mode"], "unresolved")

    def test_invalid_actual_score_not_counted_as_an_ordinary_miss(self):
        f = predict(self.model, fixture_event()); f.update(actual_score="3-0", result_status="final", eligibility="historical_replay")
        with self.assertRaisesRegex(ValueError, "actual score"): evaluate([f])

    def test_replay_cannot_use_post_start_information(self):
        e = fixture_event(); e.update(eligibility="historical_replay", scheduled_start="2026-08-31T00:00:00Z")
        with self.assertRaisesRegex(ValueError, "cutoff must precede"): predict(self.model, e)

    def test_archive_hash_mismatch_rejected_and_explicit_override_traced(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); old = root / "older"
            (root / "sources").mkdir(); (old / "sources").mkdir(parents=True)
            row = copy.deepcopy(self.raw[0]); row["event_id"] = "vlr-1"
            (root / "history.json").write_text(json.dumps([row]))
            match = {"url": "https://www.vlr.gg/1/test", "date": "Patch 1.0", "maps": []}
            for d in (root, old):
                (d / "matches-complete.json").write_text(json.dumps([match]))
                (d / "sources/match-1-meta.json").write_text(json.dumps({"retrieved_at": CUTOFF, "sha256": hashlib.sha256(b"verified").hexdigest()}))
            (root / "sources/match-1.html").write_text("bad")
            (old / "sources/match-1.html").write_text("verified")
            with self.assertRaisesRegex(ValueError, "does not match receipt"): import_archive({"run_dir": str(root)})
            imported = import_archive({"run_dir": str(root), "source_overrides": {"vlr-1": str(old)}})
            self.assertEqual(imported["audit"]["source_overrides"][0]["event_id"], "vlr-1")
            self.assertTrue(imported["audit"]["enriched"][0]["receipt"].startswith(str(old)))

    def test_real_outcome_walk_forward_is_scored_but_not_promoted(self):
        p = {"history": self.raw, "targets": [{"event": fixture_event(), "outcome": {"actual_score": "2-1", "result_status": "final", "result_source_url": "https://example.test/result", "result_observed_at": "2026-09-03T00:00:00Z"}}]}
        out = walk_forward(p, registry())
        self.assertEqual(out["evaluation"]["overall"]["scored_n"], 2)
        self.assertEqual(out["evaluation"]["prediction_availability"]["value"], 1)
        self.assertFalse(out["comparison"]["passed"])


if __name__ == "__main__": unittest.main()
