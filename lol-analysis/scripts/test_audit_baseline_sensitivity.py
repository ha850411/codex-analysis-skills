import copy
import unittest
from audit_baseline_sensitivity import audit
from shared.forecast.cli import forecast
from shared.forecast.models import train


class SensitivityTest(unittest.TestCase):
    def setUp(self):
        self.history = [dict(event_id=f'h{i}', sport='lol', participants=['A', 'B'],
                             score=score, best_of=3, completed_at=f'2026-01-0{i}T10:00:00Z',
                             available_at=f'2026-01-0{i}T11:00:00Z', result_status='final',
                             source_url='https://example.org/results')
                        for i, score in enumerate(([2, 0], [0, 2], [2, 1]), 1)]
        self.event = dict(event_id='target', sport='lol', competition='fixture', snapshot='pre-lineup',
                          created_at='2026-01-04T12:00:00Z', data_cutoff='2026-01-04T12:00:00Z',
                          scheduled_start='2026-01-05T12:00:00Z', participants=['A', 'B'],
                          scope='series', best_of=5, confidence=None, missing_data=['synthetic fixture'],
                          evidence=[dict(id='results', url='https://example.org/results', claim='fixture',
                                         available_at='2026-01-04T11:00:00Z', retrieved_at='2026-01-04T11:00:00Z')])
        self.forecast = forecast(train(self.history, 'lol', self.event['data_cutoff']), self.event)

    def test_all_rows_and_no_mutation(self):
        original = copy.deepcopy((self.history, self.event, self.forecast))
        result = audit(self.history, self.event, self.forecast)
        self.assertEqual({c['removed_event_id'] for c in result['cases']}, {'h1', 'h2', 'h3'})
        self.assertTrue(result['replay_passed'])
        self.assertFalse(result['production_change'])
        self.assertEqual((self.history, self.event, self.forecast), original)

    def test_changed_history_rejected(self):
        self.history[0]['score'] = [2, 1]
        with self.assertRaisesRegex(ValueError, 'hash'):
            audit(self.history, self.event, self.forecast)

    def test_future_result_excluded(self):
        extra = dict(self.history[0], event_id='future', completed_at='2026-01-06T10:00:00Z',
                     available_at='2026-01-06T11:00:00Z')
        result = audit(self.history + [extra], self.event, self.forecast)
        self.assertEqual(result['training_n'], 3)

    def test_identity_mismatch_rejected(self):
        self.event['participants'] = ['B', 'A']
        with self.assertRaisesRegex(ValueError, 'participants'):
            audit(self.history, self.event, self.forecast)


if __name__ == '__main__':
    unittest.main()
