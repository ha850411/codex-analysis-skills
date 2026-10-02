from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from forecast.audit import audit_model_use
from forecast.series import predict
from forecast.strength import train
from shared.forecast.cli import forecast as old_predict
from shared.forecast.models import train as old_train
from shared.forecast.core import canonical
from test_valorant_forecast import CUTOFF, fixture_event, fixture_history, registry


def player_context(teams):
    lineups = [[team + str(i) for i in range(5)] for team in teams]
    return {"lineups": lineups, "agents": [{p: "agent" + str(i) for i, p in enumerate(team)} for team in lineups]}


class ModelUseAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = fixture_history()
        cls.plain = train(cls.raw, CUTOFF, registry=registry())
        enriched = copy.deepcopy(cls.raw)
        for row in enriched:
            for game in row["games"]:
                game["context"].update(player_context(row["participants"]))
        cls.enriched = train(enriched, CUTOFF, registry=registry())

    def event(self):
        event = fixture_event()
        event["contexts_by_map"] = {"X": player_context(event["participants"])}
        return event

    def test_supplemental_fitted_agents_do_not_enter_unresolved_series(self):
        event = self.event(); event.pop("veto_scenarios")
        record = predict(self.enriched, event)
        before = canonical(record)
        # The old aggregate union would see fitted agents, though only in map supplements.
        self.assertTrue(any(json.loads(k)[0] == "agents" for t in record["valorant"]["feature_audit"].values() for k in t["used"]))
        audit = audit_model_use(record)
        self.assertEqual(audit["features"]["agents"]["primary_status"], "not_modeled")
        self.assertGreater(audit["features"]["agents"]["supplemental_only_fitted_trace_count"], 0)
        self.assertEqual(audit["map_order"]["unresolved_weight"], 1)
        self.assertEqual(canonical(record), before)

    def test_supplied_unseen_lineup_is_not_a_fitted_effect(self):
        audit = audit_model_use(predict(self.plain, self.event()))
        self.assertEqual(audit["features"]["roster"]["primary_status"], "input_only")
        self.assertEqual(audit["features"]["agents"]["primary_status"], "input_only")
        self.assertIn("agents", audit["primary_contexts_by_map"]["X"]["unseen_families"])

    def test_one_map_feature_does_not_claim_all_maps_or_known_side(self):
        audit = audit_model_use(predict(self.enriched, self.event()))
        self.assertEqual(audit["features"]["agents"]["primary_status"], "fitted_input")
        self.assertEqual(audit["primary_contexts_by_map"]["X"]["input_weight"]["agents"], 1)
        self.assertEqual(audit["primary_contexts_by_map"]["Y"]["input_weight"]["agents"], 0)
        self.assertEqual(audit["features"]["side"]["primary_status"], "not_modeled")

    def test_v2_unresolved_is_known_but_untraced_named_paths_remain_unknown(self):
        model = old_train(self.raw, "valorant", CUTOFF, "challenger")
        event = fixture_event(); event.pop("veto_scenarios")
        audit = audit_model_use(old_predict(model, event), model, event)
        self.assertTrue(audit["full_model_replay"])
        self.assertEqual(audit["features"]["roster"]["primary_status"], "not_modeled")
        audit = audit_model_use(old_predict(model, fixture_event()))
        self.assertEqual(audit["map_order"]["unknown_weight"], 1)
        self.assertEqual(audit["features"]["roster"]["primary_status"], "unknown")

    def test_missing_or_mismatched_primary_trace_is_rejected(self):
        record = predict(self.enriched, self.event())
        key = next(iter(record["valorant"]["feature_audit"]))
        missing = copy.deepcopy(record); del missing["valorant"]["feature_audit"][key]
        with self.assertRaisesRegex(ValueError, "lacks a feature-use trace"):
            audit_model_use(missing)
        record["valorant"]["feature_audit"][key]["map"] = "OTHER"
        with self.assertRaisesRegex(ValueError, "context differs"):
            audit_model_use(record)

    def test_full_replay_is_explicit_and_rejects_different_inputs(self):
        event = self.event(); record = predict(self.enriched, event)
        self.assertFalse(audit_model_use(record)["full_model_replay"])
        self.assertTrue(audit_model_use(record, self.enriched, event)["full_model_replay"])
        with self.assertRaisesRegex(ValueError, "supplied together"):
            audit_model_use(record, self.enriched)
        event["contexts_by_map"]["X"].pop("agents")
        with self.assertRaisesRegex(ValueError, "replay"):
            audit_model_use(record, self.enriched, event)

    def test_cli_preserves_snapshot_bytes(self):
        record = predict(self.enriched, self.event())
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "forecast.json"
            source.write_text(json.dumps(record))
            before = source.read_bytes()
            command = Path(__file__).with_name("valorant_forecast.py")
            proc = subprocess.run([sys.executable, str(command), "audit-model-use", str(source)], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertFalse(json.loads(proc.stdout)["changes_forecast"])
            self.assertEqual(source.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
