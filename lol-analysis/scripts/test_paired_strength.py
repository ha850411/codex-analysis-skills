"""Synthetic behavior tests, independent of the reviewed teams and match results."""
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paired_strength as model
from shared.forecast.cli import forecast, write
from shared.forecast.core import derive, digest, validate
from shared.forecast.fixtures import event, history
from shared.forecast.models import train


def fixture(bo=5):
    e = event()
    e.update(best_of=bo, snapshot="pre-draft-established-lineups", scope="series")
    rows = history()
    for row in rows:
        row['best_of'] = 3
    return forecast(train(rows, 'lol', e['data_cutoff']), e), rows


class StrengthTests(unittest.TestCase):
    def test_joint_opponents_can_reverse_raw_record_ranking(self):
        games = [('A', 'Strong', [1, 2])]*6 + [('B', 'Weak', [2, 1])]*6 + [('Strong', 'Weak', [2, 0])]*20
        rows = []
        for i, (a, b, result) in enumerate(games):
            end = (datetime(2020, 1, 1, tzinfo=timezone.utc)+timedelta(days=i)).isoformat()
            rows.append(dict(event_id=f'network-{i}', sport='lol', participants=[a, b], score=result,
                             best_of=3, completed_at=end, available_at=end, result_status='final',
                             source_url='https://example.invalid/synthetic'))
        joint = model.fit(rows, '2020-03-01T00:00:00Z')
        raw = model.fit(rows, '2020-03-01T00:00:00Z', 'opponent_zero_ablation')
        self.assertGreater(joint['strengths']['A'], joint['strengths']['B'])
        self.assertLess(raw['strengths']['A'], raw['strengths']['B'])
        self.assertLess(joint['optimization']['max_abs_gradient'], 1e-8)

    def test_gradient_matches_finite_difference(self):
        strengths = [.2, -.4, .1]
        observations = [([(0, 1.), (1, -1.)], .75), ([(1, 1.), (2, -1.)], 0.)]
        _, gradient, _ = model.objective(strengths, observations)
        for i in range(3):
            low, high = list(strengths), list(strengths)
            low[i] -= 1e-6
            high[i] += 1e-6
            numerical = (model.objective(high, observations)[0]-model.objective(low, observations)[0])/2e-6
            self.assertAlmostEqual(numerical, gradient[i], places=8)

    def test_renaming_orientation_and_chronology_do_not_change_strength(self):
        control, rows = fixture()
        original = model.fit(rows, control['data_cutoff'])
        modified = copy.deepcopy(rows)
        for row, other in zip(modified, reversed(rows)):
            row['participants'].reverse()
            row['score'].reverse()
            row['completed_at'] = other['completed_at']
            row['available_at'] = other['available_at']
        replay = model.fit(modified, control['data_cutoff'])
        for team in original['strengths']:
            self.assertAlmostEqual(original['strengths'][team], replay['strengths'][team], places=12)

    def test_future_results_are_excluded_and_original_inputs_unchanged(self):
        control, rows = fixture()
        future = dict(rows[0], event_id=control['event_id'], completed_at='2020-03-03T00:00:00Z', available_at='2020-03-03T00:00:00Z')
        source = rows+[future]
        before = digest(dict(control=control, history=source))
        outputs = model.pair(control, source, now='2020-03-01T04:00:00Z')
        self.assertEqual(outputs['pair-audit.json']['excluded_series'], 1)
        self.assertNotIn(future['event_id'], outputs['model.json']['training_event_ids'])
        self.assertEqual(before, digest(dict(control=control, history=source)))
        self.assertEqual(outputs['control.json'], control)

    def test_invalid_or_duplicate_results_are_rejected(self):
        control, rows = fixture()
        with self.assertRaises(ValueError):
            model.fit(rows+[rows[0]], control['data_cutoff'])
        for bad in ([3, 3], [3, 1], [0, 0]):
            data = copy.deepcopy(rows)
            data[0]['score'] = bad
            with self.assertRaises(ValueError):
                model.fit(data, control['data_cutoff'])

    def test_same_cutoff_history_must_reproduce_original_baseline(self):
        control, rows = fixture()
        rows[0]['score'] = [0, 2]
        with self.assertRaisesRegex(ValueError, 'reproduce'):
            model.pair(control, rows, now='2020-03-01T04:00:00Z')

    def test_real_creation_time_and_post_start_replay_are_separate(self):
        control, rows = fixture()
        now = '2020-03-03T00:00:00Z'
        with self.assertRaisesRegex(ValueError, '--replay'):
            model.pair(control, rows, now=now)
        output = model.pair(control, rows, replay_mode=True, now=now)
        self.assertEqual(output['challenger.json']['created_at'], now)
        self.assertEqual(output['challenger.json']['eligibility'], 'historical_replay')
        self.assertFalse(output['pair-audit.json']['forward_sample'])
        self.assertEqual(output['challenger.json']['data_cutoff'], control['data_cutoff'])

    def test_prices_and_target_results_never_become_features(self):
        for key, value in [('market_data', [{'odds': 2.}]), ('actual_score', '3-0')]:
            control, rows = fixture()
            control[key] = value
            with self.assertRaises(ValueError):
                model.pair(control, rows, now='2020-03-01T04:00:00Z')
        control, rows = fixture()
        rows[0]['odds'] = 2.
        with self.assertRaises(ValueError):
            model.pair(control, rows, now='2020-03-01T04:00:00Z')

    def test_bo3_bo5_full_support_and_swapped_teams(self):
        for bo in (3, 5):
            control, rows = fixture(bo)
            fitted = model.fit(rows, control['data_cutoff'])
            a = model.build_forecast(fitted, control, '2020-03-01T04:00:00Z', 'prospective')
            control['participants'].reverse()
            b = model.build_forecast(fitted, control, '2020-03-01T04:00:00Z', 'prospective')
            validate(a)
            self.assertFalse(a['recommendation_eligible'])
            self.assertEqual(len(a['score_distribution']), bo+1)
            for key, p in a['score_distribution'].items():
                self.assertAlmostEqual(p, b['score_distribution']['-'.join(reversed(key.split('-')))])

    def test_disconnected_or_missing_team_and_postdraft_rejected(self):
        control, rows = fixture()
        fitted = model.fit(rows, control['data_cutoff'])
        for key, value in [('participants', ['Unknown', 'Example B']), ('snapshot', 'post-draft'), ('scope', 'map-1')]:
            e = copy.deepcopy(control)
            e[key] = value
            with self.assertRaises(ValueError):
                model.build_forecast(fitted, e, '2020-03-01T04:00:00Z', 'prospective')
        separate = dict(rows[0], event_id='separate', participants=['C', 'D'])
        fitted = model.fit(rows+[separate], control['data_cutoff'])
        control['participants'] = ['C', 'Example A']
        with self.assertRaisesRegex(ValueError, 'connected'):
            model.build_forecast(fitted, control, '2020-03-01T04:00:00Z', 'prospective')

    def test_saved_pair_replays_and_tamper_is_detected(self):
        control, rows = fixture()
        output = model.pair(control, rows, replay_mode=True, now='2020-03-03T00:00:00Z')
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            for name, value in output.items():
                write(str(directory/name), value)
            self.assertTrue(model.verify_pair(directory)['valid'])
            audit = output['pair-audit.json']
            audit['forward_sample'] = True
            (directory/'pair-audit.json').write_text(json.dumps(audit))
            with self.assertRaises(ValueError):
                model.verify_pair(directory)

    def test_cli_refuses_backdating_and_overwriting(self):
        control, rows = fixture()
        with tempfile.TemporaryDirectory() as temp:
            d = Path(temp)
            write(str(d/'control.json'), control)
            write(str(d/'history.json'), rows)
            args = [sys.executable, str(Path(model.__file__)), 'pair', '--control', str(d/'control.json'),
                    '--history', str(d/'history.json'), '--output-dir', str(d/'pair')]
            failed = subprocess.run(args, capture_output=True, text=True)
            self.assertNotEqual(failed.returncode, 0)
            passed = subprocess.run(args+['--replay'], capture_output=True, text=True)
            self.assertEqual(passed.returncode, 0, passed.stderr)
            frozen = (d/'pair/challenger.json').read_bytes()
            changed = subprocess.run(args+['--replay'], capture_output=True, text=True)
            self.assertNotEqual(changed.returncode, 0)
            self.assertEqual((d/'pair/challenger.json').read_bytes(), frozen)

    def test_integrated_build_preserves_main_and_emits_pair(self):
        from test_analyst_forecast import fixture as analyst_fixture
        from analyst_forecast import build, build_paired
        payload = analyst_fixture(5)
        payload['event'].update(snapshot='pre-draft-established-lineups', scope='series')
        payload['baseline'].update(snapshot='pre-draft-established-lineups', scope='series')
        rows = history()
        for row in rows:
            row['best_of'] = 3
        original = build(payload)
        result, outputs = build_paired(payload, rows, now='2020-03-01T04:00:00Z')
        self.assertEqual(result, original)
        self.assertEqual(outputs['control.json'], original)
        self.assertTrue(outputs['pair-audit.json']['baseline_replay_passed'])
        self.assertTrue(outputs['pair-audit.json']['forward_sample'])
        with self.assertRaisesRegex(ValueError, '--replay'):
            build_paired(payload, rows, now='2020-03-03T00:00:00Z')

    def test_integrated_cli_fails_without_leaving_a_partial_prediction(self):
        from test_analyst_forecast import fixture as analyst_fixture
        payload = analyst_fixture(5)
        payload['event'].update(snapshot='pre-draft-established-lineups', scope='series')
        payload['baseline'].update(snapshot='pre-draft-established-lineups', scope='series')
        rows = history()
        for row in rows:
            row['best_of'] = 3
        with tempfile.TemporaryDirectory() as temp:
            d = Path(temp)
            write(str(d/'input.json'), payload)
            write(str(d/'history.json'), rows)
            args = [sys.executable, str(Path(model.__file__).with_name('analyst_forecast.py')), 'build-paired',
                    str(d/'input.json'), '--history', str(d/'history.json'), '--output', str(d/'forecast.json'),
                    '--pair-output-dir', str(d/'pair')]
            failed = subprocess.run(args, capture_output=True, text=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertFalse((d/'forecast.json').exists())
            self.assertFalse((d/'pair').exists())
            # A genuine pre-start invocation must also exercise the CLI write path.
            current = datetime.now(timezone.utc)
            cutoff = (current-timedelta(hours=1)).isoformat()
            payload['event'].update(data_cutoff=cutoff, created_at=(current-timedelta(minutes=1)).isoformat(),
                                    scheduled_start=(current+timedelta(hours=1)).isoformat())
            base_event = copy.deepcopy(payload['event'])
            base_event['created_at'] = (current-timedelta(minutes=2)).isoformat()
            payload['baseline'] = forecast(train(rows, 'lol', cutoff), base_event)
            payload['judgment']['locked_at'] = payload['event']['created_at']
            (d/'input.json').write_text(json.dumps(payload))
            passed = subprocess.run(args, capture_output=True, text=True)
            self.assertEqual(passed.returncode, 0, passed.stderr)
            self.assertEqual(json.loads((d/'forecast.json').read_text()), json.loads((d/'pair/control.json').read_text()))
            self.assertTrue(model.verify_pair(d/'pair')['valid'])


if __name__ == '__main__':
    unittest.main()
