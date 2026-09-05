from __future__ import annotations

import copy
import json
import tempfile
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path

from shared.forecast.core import derive,series_tree,mixture,validate,record_forecast,settlement_ev
from shared.forecast.models import train,predict,SPORTS
from shared.forecast.cli import forecast,walk_forward
from shared.forecast.evaluation import score,evaluate,compare
from shared.forecast.adapters import adapt_evaluation
from shared.forecast.render import render,youtube
from shared.forecast.bridge import archive


from shared.forecast.fixtures import event, history


def sample(sport="lol"):
    e=event(sport)
    return forecast(train(history(sport),sport,e["data_cutoff"]),e)


class DistributionTests(unittest.TestCase):
    def test_conditional_tree_not_iid(self):
        d=series_tree(3,{"ROOT":.5,"W":.8,"L":.2,"WL":.7,"LW":.3})
        self.assertAlmostEqual(d["2-0"],.4)
        self.assertAlmostEqual(d["0-2"],.4)
        self.assertAlmostEqual(sum(d.values()),1)

    def test_bo2_draw(self):
        d=derive(series_tree(2,{"ROOT":.5,"W":.5,"L":.5}))
        self.assertEqual(d["winner_probabilities"]["draw"],.5)

    def test_bo1(self):
        self.assertEqual(series_tree(1,{"ROOT":.6}),{"1-0":.6,"0-1":.4})

    def test_incomplete_and_unused_nodes_rejected(self):
        for nodes in ({"ROOT":.5},{"ROOT":.5,"W":.5}):
            with self.assertRaises(ValueError): series_tree(3,nodes)
        with self.assertRaises(ValueError): series_tree(1,{"ROOT":.5,"W":.4})

    def test_winner_and_mode_can_differ(self):
        d=derive({"2-0":.27,"2-1":.26,"1-2":.4,"0-2":.07})
        self.assertEqual(d["winner_pick"],"a")
        self.assertEqual(d["score_mode"],"1-2")

    def test_settlement(self):
        self.assertAlmostEqual(settlement_ev(1.9,win=.52,push=.06),.048)
        self.assertAlmostEqual(settlement_ev(2,win=.4,half_win=.2,push=.1,half_loss=.1),.25)
        with self.assertRaises(ValueError): settlement_ev(2,win=.8,push=.3)

    def test_units_and_nonfinite_rejected(self):
        for values in ({"1-0":60,"0-1":40},{"1-0":float("nan")},{"1-0":True}):
            with self.assertRaises(ValueError): derive(values)


class ForecastTests(unittest.TestCase):
    def test_feature_candidate_fit_and_market_gate(self):
        rows=history()
        registry={"factors":[{"factor_id":"rest-difference","status":"candidate",
                             "mechanism":"rest may affect performance","pre_match_observable":"A rest days minus B"}]}
        for i,r in enumerate(rows):
            r["started_at"]=f"2020-02-{i+1:02d}T18:00:00+08:00"
            r["feature_snapshot"]={"available_at":f"2020-02-{i+1:02d}T17:00:00+08:00",
                                   "evidence_ids":["fixture"],"values":{"rest-difference":i%3-1}}
            r["evidence"]=[{"id":"fixture","available_at":r["feature_snapshot"]["available_at"]}]
        model=train(rows,"lol",event()["data_cutoff"],"challenger",registry)
        self.assertEqual(model["feature_model"]["n"],20)
        self.assertEqual(model["status"],"experiment")
        registry["factors"][0]["factor_id"]="market-odds"
        with self.assertRaises(ValueError): train(rows,"lol",event()["data_cutoff"],"challenger",registry)

    def test_feature_snapshot_cannot_use_postmatch_values(self):
        from shared.forecast.features import extract
        r={"feature_snapshot":{"available_at":"2020-03-02T00:00:00Z","evidence_ids":["e"],"values":{"x":1}}}
        with self.assertRaises(ValueError): extract(r,["x"],cutoff="2020-03-01T00:00:00Z")

    def test_latent_state_preserves_game_marginal(self):
        from shared.forecast.models import latent_games
        self.assertAlmostEqual(sum(w*p for w,p in latent_games(.7,1.)),.7)

    def test_shared_state_changes_sweep_shape_coherently(self):
        e=event();m=train(history(),"lol",e["data_cutoff"],"challenger")
        independent=predict(m,e)["score_distribution"]
        m["shared_state_sigma"]=1.
        correlated=predict(m,e)["score_distribution"]
        self.assertGreater(correlated["2-0"]+correlated["0-2"],independent["2-0"]+independent["0-2"])
        self.assertAlmostEqual(sum(correlated.values()),1.)

    def test_seven_sports_both_variants(self):
        for sport in SPORTS:
            for variant in ("baseline","challenger"):
                with self.subTest(sport=sport,variant=variant):
                    e=event(sport);m=train(history(sport),sport,e["data_cutoff"],variant)
                    r=forecast(m,e)
                    validate(r)
                    self.assertAlmostEqual(sum(r["score_distribution"].values()),1)
                    self.assertFalse(r["recommendation_eligible"])
                    self.assertEqual(predict(m,e),predict(m,e))

    def test_evidence_time_leak_rejected(self):
        r=sample(); r["evidence"][0]["available_at"]="2020-03-02T00:00:00Z"
        with self.assertRaises(ValueError): validate(r)

    def test_poststart_cannot_be_prospective(self):
        r=sample();r["actual_start"]=r["created_at"]
        with self.assertRaises(ValueError): validate(r)

    def test_forecast_is_create_only_and_idempotent(self):
        with tempfile.TemporaryDirectory() as root:
            r=sample()
            r["created_at"]=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat()
            r["scheduled_start"]=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
            first=record_forecast(r,root)
            self.assertEqual(first,record_forecast(r,root))
            r["missing_data"].append("new information")
            with self.assertRaises(ValueError): record_forecast(r,root)

    def test_backdated_first_record_is_not_prospective(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError): record_forecast(sample(),root)

    def test_path_traversal_rejected(self):
        r=sample();r["forecast_id"]="../../erase"
        with self.assertRaises(ValueError): validate(r)

    def test_uncalibrated_cannot_get_positive_stake(self):
        r=sample();r["decision"]={"status":"bet","stake_units":1,"advice":"主推"}
        with self.assertRaises(ValueError): validate(r)

    def test_unmodeled_cannot_be_recommendation_eligible(self):
        r=sample();r.update(status="unmodeled",score_distribution=None,recommendation_eligible=True)
        with self.assertRaises(ValueError): validate(r)

    def test_veto_scenarios_need_evidence_and_complete_order(self):
        e=event();m=train(history(),"lol",e["data_cutoff"])
        e["veto_scenarios"]=[{"id":"path","weight":1.,"maps":["a","b","c"]}]
        with self.assertRaises(ValueError): predict(m,e)
        e["veto_scenarios"][0]["evidence_ids"]=["fixture"]
        self.assertAlmostEqual(sum(predict(m,e)["score_distribution"].values()),1.)

    def test_bad_confidence_and_derived_rejected(self):
        r=sample();r["confidence"]["value"]=80
        with self.assertRaises(ValueError): validate(r)
        r=sample();r["derived"]["score_mode"]="99-99"
        with self.assertRaises(ValueError): validate(r)

    def test_postcutoff_training_excluded(self):
        e=event();rows=history();m=train(rows,"lol",e["data_cutoff"])
        late=copy.deepcopy(rows[0]);late["event_id"]="late";late["available_at"]="2020-03-02T00:00:00Z"
        self.assertEqual(m,train(rows+[late],"lol",e["data_cutoff"]))

    def test_target_training_leak_rejected(self):
        e=event();m=train(history(),"lol",e["data_cutoff"])
        e["event_id"]="h-0"
        with self.assertRaises(ValueError): predict(m,e)

    def test_render_consistency_and_final_narrow_table(self):
        r=sample()
        for mode in ("chat","full"):
            text=render([r],mode)
            self.assertEqual(text.count("簡表總結"),1)
            self.assertTrue(text.rstrip().endswith("|"))
            self.assertIn(r["derived"]["score_mode"],text)
            self.assertIn("證據品質",text)
        self.assertIn(r["derived"]["score_mode"],youtube([r]))

    def test_render_discloses_direction_disagreement(self):
        r=sample();r["score_distribution"]={"2-0":.27,"2-1":.26,"1-2":.4,"0-2":.07}
        del r["scenarios"];r["derived"]=derive(r["score_distribution"])
        self.assertIn("方向不同",render([r]))


class EvaluationTests(unittest.TestCase):
    def record(self):
        r=sample();r.update(actual_score="2-0",result_status="final")
        return r

    def test_unmodeled_stays_in_denominator(self):
        r=self.record(); missing=copy.deepcopy(r)
        missing.update(event_id="missing",status="unmodeled",score_distribution=None)
        result=evaluate([r,missing])["overall"]
        self.assertEqual(result["published_n"],2)
        self.assertEqual(result["coverage"],.5)

    def test_excludes_cancelled_and_reconstructed(self):
        r=self.record();r["result_status"]="cancelled"
        self.assertIsNone(score(r))
        r["result_status"]="final";r["eligibility"]="reconstructed_after_start"
        self.assertIsNone(score(r))

    def test_duplicates_rejected(self):
        r=self.record()
        with self.assertRaises(ValueError): evaluate([r,r])

    def test_small_sample_never_promoted(self):
        a=self.record();b=copy.deepcopy(a);b["model_version"]="challenger"
        result=compare([a,b],a["model_version"],"challenger")
        self.assertFalse(result["passed"])
        self.assertEqual(result["decision"],"experiment-only")

    def test_paired_outcomes_must_match(self):
        a=self.record();b=copy.deepcopy(a);b.update(model_version="challenger",actual_score="0-2")
        with self.assertRaises(ValueError): compare([a,b],a["model_version"],"challenger")

    def test_legacy_missing_distribution_is_not_fabricated(self):
        r={"game_id":"1","predicted_at":"2020-01-01T00:00:00Z","first_pitch":"2020-01-02T00:00:00Z",
           "model_version":"old","home_win_prob":.6,"away_runs_mean":4.,"home_runs_mean":5.}
        output=adapt_evaluation(r,"mlb-history-v1")
        self.assertIsNone(output["score_distribution"])
        self.assertEqual(output["eligibility"],"legacy_unverified")

    def test_walk_forward_preserves_missing_predictions(self):
        e=event();e.update(actual_score="2-0",result_status="final")
        output=walk_forward({"history":[],"events":[e]})
        self.assertEqual(len(output["records"]),2)
        self.assertEqual(output["evaluation"]["overall"]["coverage"],0)

    def test_archive_preserves_original(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);run=root/"run";run.mkdir()
            legacy={"match_id":"1","predicted_at":"2020-01-01T00:00:00Z","start_time":"2020-01-02T00:00:00Z",
                    "model_version":"old","team1_win_prob":.6}
            original=json.dumps(legacy)+"\n"
            (run/"forecasts.jsonl").write_text(original)
            result=archive(run,"lol",root/"state")
            self.assertEqual((Path(result["source_archive"])/"forecasts.jsonl").read_text(),original)
            self.assertEqual((run/"forecasts.jsonl").read_text(),original)


if __name__=="__main__": unittest.main()
