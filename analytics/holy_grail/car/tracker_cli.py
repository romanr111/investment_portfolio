"""Command line for the car-category tracker: freeze the input block, report per-group measures."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from analytics.holy_grail.allocation_score_v2 import score_components_v2
from analytics.holy_grail.allocation_score_v3 import derive_allocation_score_v3
from analytics.holy_grail.car import category
from analytics.holy_grail.car.category import CAR, build_block


def _report(snapshot_path, block_path, history_path=None):
    payload = json.loads(Path(snapshot_path).read_text(encoding='utf-8'))
    snapshot = payload.get('data', payload)
    v2 = (snapshot.get('DIVERSIFICATION_DATA') or {}).get('allocation_score_v2') or {}
    block = json.loads(Path(block_path).read_text(encoding='utf-8'))
    v3 = derive_allocation_score_v3(v2, block)
    if v3 is None or v3['status'] == 'unavailable':
        raise SystemExit('No v3 record: ' + ('snapshot has no car business scenarios' if v3 is None else str(v3['warnings'])))
    weights = {g['id']: g['weight'] for g in v2['groups']}
    headline = v3['scenarios'][v3['method']['headline_scenario']]
    non_car = {(p['left'], p['right']): p['correlation'] for p in headline['pairs']
               if p['correlation'] is not None and CAR not in (p['left'], p['right'])}

    def uniform_score(rho):
        pairs = dict(non_car)
        pairs.update({tuple(sorted((g, CAR))): rho for g in weights if g not in (CAR, 'unknown')})
        return score_components_v2(weights, pairs, v2['sectors'])['score']

    low, high = 0., 1.
    for _ in range(50):
        mid = (low + high) / 2
        low, high = (mid, high) if uniform_score(mid) > headline['score'] else (low, mid)
    measures = v3['measures']['m60']
    lines = ['Category proxy (used-vehicle price index), not your business. R=1 is a price-channel scenario assumption, not a bound.',
             'Stress n counts worst-quintile US-equity months since 1997, not the window. Upper 90% = largest per-measure Fisher endpoint (nominal, per estimate).', '',
             '| Group | Weight | Monthly | Lag 1m | Stress | Point (measure, n) | Upper 90% (measure, n) |',
             '| --- | --- | --- | --- | --- | --- | --- |']
    fmt = lambda m: '-' if not m else f"{m['r']:+.2f}"
    for group in sorted(measures, key=lambda g: -weights.get(g, 0)):
        m = measures[group]
        lines.append(f"| {group} | {weights[group] * 100:.1f}% | {fmt(m['monthly'])} | {fmt(m['lagged_1m'])} | "
                     f"{fmt(m['stress_quintile'])} | "
                     f"{'-' if m['point'] is None else format(m['point'], '+.2f') + ' ' + m['selected'] + ' n=' + str(m['n'])} | "
                     f"{'-' if m['upper90'] is None else format(m['upper90'], '+.2f') + ' ' + m['upper_selected'] + ' n=' + str(m['upper_n'])} |")
    scores = {key: s['score'] for key, s in v3['scenarios'].items()}
    lines += ['', 'Diversification score (invested part):',
              f"- v2 saved base (car correlation 0.25): {v2['scenarios']['m60_r025']['score']:.1f}",
              f"- v2 saved stress (car correlation 0.75): {v2['scenarios']['m60_r075']['score']:.1f}"]
    lines += [f"- v3 {key}: " + ('unavailable' if value is None else f'{value:.1f}') for key, value in scores.items()]
    lines += [f"- headline ({v3['method']['headline_scenario']}): {v3['display_score']}",
              f'- uniform car correlation equivalent to the headline: {low:.2f}']
    print('\n'.join(lines))
    if history_path:
        entry = dict(as_of_date=v3['as_of_date'], block_fingerprint=block['fingerprint'],
                     v2_fingerprint=v2['result_fingerprint'], headline=v3['method']['headline_scenario'],
                     scores=scores, uniform_equivalent=round(low, 4),
                     points={g: m['point'] for g, m in measures.items()},
                     recorded_at=datetime.now(timezone.utc).isoformat())
        path = Path(history_path)
        keys = ('as_of_date', 'block_fingerprint', 'v2_fingerprint')
        if path.exists() and any(all(json.loads(l).get(k) == entry[k] for k in keys)
                                 for l in path.read_text(encoding='utf-8').splitlines() if l.strip()):
            print('history: entry already recorded')
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('a', encoding='utf-8') as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + '\n')
            print('history: appended to', path)


def main():
    parser = argparse.ArgumentParser(description=category.__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    build = sub.add_parser('build', help='freeze the index and long asset histories into one block file')
    build.add_argument('--raw', required=True)
    build.add_argument('--long-returns', required=True)
    build.add_argument('--as-of', required=True)
    build.add_argument('--out', required=True)
    report = sub.add_parser('report', help='per-group measures and scenario scores for a snapshot')
    report.add_argument('--snapshot', required=True)
    report.add_argument('--block', required=True)
    report.add_argument('--append-history', help='append-only JSONL tracking file (e.g. data/car_category/history.jsonl)')
    args = parser.parse_args()
    if args.command == 'build':
        target = Path(args.out)
        if target.exists():
            raise SystemExit('Output exists; choose a new path.')
        try:
            block = build_block(args.raw, args.long_returns, args.as_of)
        except (ValueError, OSError, KeyError) as error:
            raise SystemExit(f'Block not built: {error}')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(block, ensure_ascii=False, allow_nan=False), encoding='utf-8')
        print(f"block written: {target} fingerprint {block['fingerprint'][:12]}")
    else:
        _report(args.snapshot, args.block, args.append_history)


if __name__ == '__main__':
    main()
