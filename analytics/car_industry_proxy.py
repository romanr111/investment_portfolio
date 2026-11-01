"""Car business vs an industry proxy: one retrospective check, no network.

Inputs: a saved combined-data snapshot (its sealed allocation_score_v2 record) and a
one-time CSV of monthly USD returns, one column per listed name (the basket).
Nothing is fetched or saved.
"""
import argparse
import json
import math
from pathlib import Path

import pandas as pd

from analytics.allocation_v2_inputs import _group_history
from analytics.allocation_score_v2 import score_components_v2

CAR = 'car_business'
MIN_MONTHS = 36  # the repo's own rule for a measured pair


def load_record(snapshot_path):
    payload = json.loads(Path(snapshot_path).read_text(encoding='utf-8'))
    data = payload.get('data', payload)
    record = (data.get('DIVERSIFICATION_DATA') or {}).get('allocation_score_v2') or {}
    if 'm60_r025' not in (record.get('scenarios') or {}) or 'groups' not in record:
        raise SystemExit('Snapshot has no scored allocation_score_v2 record with car_business scenarios.')
    return record


def load_proxy(csv_path):
    frame = pd.read_csv(csv_path, index_col=0)
    frame.index = pd.to_datetime(frame.index).tz_localize(None).normalize()
    # Equal weight across every name in the CSV, rebalanced monthly; a month with any name missing is dropped.
    return frame.mean(axis=1, skipna=False), [c[3:] if c.startswith('yf:') else c for c in frame.columns]


def _stats(returns):
    r = returns.dropna()
    if len(r) < 2:
        return dict(ann_return=math.nan, ann_vol=math.nan, max_drawdown=math.nan)
    wealth = (1 + r).cumprod()
    return dict(ann_return=wealth.iloc[-1] ** (12 / len(r)) - 1,
                ann_vol=r.std() * math.sqrt(12),
                max_drawdown=(wealth / wealth.cummax() - 1).min())


def _interval(r, n, z=1.645):  # 90% Fisher interval
    r, se = max(-.999999, min(.999999, r)), 1 / math.sqrt(n - 3)
    return math.tanh(math.atanh(r) - z * se), math.tanh(math.atanh(r) + z * se)


def analyse(record, proxy):
    weights = {g['id']: g['weight'] for g in record['groups']}
    groups = _group_history(record['histories'], weights, record['configuration']['group_definitions'])
    proxy = proxy.reindex(groups.index)
    rows = {}
    for g in groups.columns:
        pair = pd.concat([groups[g], proxy], axis=1).dropna()
        n = len(pair)
        measurable = n >= MIN_MONTHS and bool((pair.std() > 0).all())  # same rule as the repo's pairs
        r = float(pair.iloc[:, 0].corr(pair.iloc[:, 1])) if measurable else None
        rows[g] = dict(weight=weights[g], n=n, corr=r,
                       interval=_interval(r, n) if r is not None else None, **_stats(groups[g]))

    scenarios = record['scenarios']
    base = {(p['left'], p['right']): p['correlation'] for p in scenarios['m60_r025']['pairs']
            if p['correlation'] is not None and CAR not in (p['left'], p['right'])}
    others = [g for g in weights if g not in (CAR, 'unknown')]  # car-unknown stays missing, as saved

    def score(car_rho):
        corr = dict(base)
        corr.update({tuple(sorted((g, CAR))): v for g, v in car_rho.items()})
        return score_components_v2(weights, corr, record['sectors'])['score']

    # Plumbing check against the sealed record.
    for rho, key in ((.25, 'm60_r025'), (.75, 'm60_r075')):
        if abs(score({g: rho for g in others}) - scenarios[key]['score']) > 1e-8:
            raise ValueError(f'rebuild does not reproduce saved {key}')

    def pick(g, part):  # groups without a measurable overlap fall back to the saved stress value
        row = rows.get(g)
        if not row or row['corr'] is None:
            return .75
        return row['corr'] if part == 'point' else row['interval'][1]

    scores = dict(saved_base_025=scenarios['m60_r025']['score'],
                  saved_stress_075=scenarios['m60_r075']['score'],
                  proxy_point=score({g: pick(g, 'point') for g in others}),
                  proxy_upper90=score({g: pick(g, 'upper') for g in others}))
    return rows, _stats(proxy), scores


def render(rows, proxy_stats, scores, names):
    pct = lambda v: '-' if math.isnan(v) else f'{v * 100:+.1f}%'
    vol = lambda v: '-' if math.isnan(v) else f'{v * 100:.1f}%'
    lines = [f"Industry proxy ({', '.join(names)}), not your business. Assumes the business moves with it.", '',
             '| Group | Weight | Ann. return | Ann. vol | Max drawdown | Corr. with proxy [90%] | n |',
             '| --- | --- | --- | --- | --- | --- | --- |',
             f"| Industry proxy | - | {pct(proxy_stats['ann_return'])} | {vol(proxy_stats['ann_vol'])} "
             f"| {pct(proxy_stats['max_drawdown'])} | - | - |"]
    for g, row in sorted(rows.items(), key=lambda item: -item[1]['weight']):
        corr = 'unavailable' if row['corr'] is None else \
            f"{row['corr']:+.2f} [{row['interval'][0]:+.2f}, {row['interval'][1]:+.2f}]"
        lines.append(f"| {g} | {row['weight'] * 100:.1f}% | {pct(row['ann_return'])} | {vol(row['ann_vol'])} "
                     f"| {pct(row['max_drawdown'])} | {corr} | {row['n']} |")
    lines += ['', 'Diversification score (invested part):',
              f"- saved base, car correlation 0.25: {scores['saved_base_025']:.1f}",
              f"- saved stress, car correlation 0.75: {scores['saved_stress_075']:.1f}",
              f"- industry proxy, point estimates: {scores['proxy_point']:.1f}",
              f"- industry proxy, upper 90% limits: {scores['proxy_upper90']:.1f}"]
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', required=True)
    parser.add_argument('--proxy', default='data/car_industry_proxy_returns.csv')
    args = parser.parse_args()
    proxy, names = load_proxy(args.proxy)
    print(render(*analyse(load_record(args.snapshot), proxy), names))


if __name__ == '__main__':
    main()
