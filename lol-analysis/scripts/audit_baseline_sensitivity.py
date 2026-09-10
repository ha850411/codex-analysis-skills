#!/usr/bin/env python3
"""Replay a saved LoL baseline and audit every training-series deletion offline.

No outcomes are used to select variants; these are diagnostics, not new forecasts.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.forecast.core import derive, digest, validate
from shared.forecast.models import history_before, predict, train


def audit(history, event, forecast):
    validate(forecast)
    if forecast['sport'] != 'lol' or forecast['status'] != 'baseline':
        raise ValueError('requires a saved LoL baseline')
    for key in ('event_id', 'sport', 'participants', 'data_cutoff', 'best_of'):
        if event[key] != forecast[key]:
            raise ValueError('event/forecast mismatch: ' + key)
    cutoff = event['data_cutoff']
    rows = history_before(history, cutoff, 'lol')
    model = train(rows, 'lol', cutoff)
    scores = predict(model, event)['score_distribution']
    if digest(model) != forecast['model_artifact_hash']:
        raise ValueError('saved model hash cannot be reproduced from this history')
    if set(scores) != set(forecast['score_distribution']) or any(
        abs(p - forecast['score_distribution'][s]) > 1e-10 for s, p in scores.items()
    ):
        raise ValueError('saved score distribution cannot be reproduced')
    baseline = derive(scores)
    cases = []
    for removed in rows:
        subset = [r for r in rows if r['event_id'] != removed['event_id']]
        case = {'removed_event_id': removed['event_id']}
        missing = set(event['participants']) - {t for r in subset for t in r['participants']}
        if not subset or missing:
            case.update(status='unavailable', reason='no remaining history for target team')
        else:
            shadow = train(subset, 'lol', cutoff)
            d = predict(shadow, event)['score_distribution']
            result = derive(d)
            case.update(status='experiment-only', score_distribution=d,
                        p_a=result['winner_probabilities']['a'],
                        winner_pick=result['winner_pick'],
                        direction_changed=result['winner_pick'] != baseline['winner_pick'],
                        delta_p_a=result['winner_probabilities']['a'] - baseline['winner_probabilities']['a'])
        cases.append(case)
    valid = [c for c in cases if c['status'] == 'experiment-only']
    probabilities = [baseline['winner_probabilities']['a']] + [c['p_a'] for c in valid]
    return dict(schema_version=1, decision='experiment-only', production_change=False,
                method='leave-one-series-out sensitivity; not out-of-sample evaluation',
                forecast_id=forecast['forecast_id'], event_id=event['event_id'],
                data_cutoff=cutoff, forecast_hash=digest(forecast), history_hash=digest(history),
                replay_passed=True, training_n=len(rows), baseline=baseline,
                p_a_range=[min(probabilities), max(probabilities)],
                direction_changes=sum(c['direction_changed'] for c in valid),
                available_cases=len(valid), unavailable_cases=len(cases)-len(valid), cases=cases)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for flag in ('history', 'event', 'forecast', 'output'):
        p.add_argument('--' + flag, required=True, type=Path)
    args = p.parse_args()
    result = audit(*[json.loads(getattr(args, k).read_text()) for k in ('history', 'event', 'forecast')])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')
    print(json.dumps({k: result[k] for k in ('replay_passed', 'training_n', 'p_a_range', 'direction_changes')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
