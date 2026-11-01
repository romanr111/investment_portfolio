"""Risk progress v1: effective independent equal-risk streams (DR squared) for the covered groups.

A sibling record derived offline from a saved, replayed capital_diversification_v2 record. It reads
only the frozen group histories and weights, never prices or networks, and nothing else imports it,
so v2/v3, the sheets and the reports are untouched. The scale is a policy choice (target 15 streams
mapped linearly to 0-100), not a percentage of risk. Groups without a return history (car_business)
are excluded from the headline and reported. With a frozen `car_proxies_v1` block the record also holds
labeled car-business scenarios ("the business behaves like this public series"); a scenario is an
assumption shown as a range next to the headline, never the headline. Cash is outside the metric.
"""
import argparse
import copy
from datetime import datetime, timezone
import json
import math
from pathlib import Path

import numpy as np

from analytics.allocation_inputs import _seal
from analytics.allocation_score import monthly_window
from analytics.allocation_score_v2 import TOLERANCE, _same
from analytics.allocation_v2_inputs import _group_history, validate_saved_allocation_v2
from analytics.car_risk_proxies import LATEST_BLOCK, load_block, series_map, validate_block
from analytics.holy_grail import completed_month_end, fingerprint

VERSION = 'risk_progress_v1'
WINDOWS = (60, 36)
PRIMARY = 60
TARGET = 15
METHOD = {
    'version': VERSION, 'estimator': 'sample_covariance_ddof1', 'stream': 'v2_group_representative_history',
    'windows': list(WINDOWS), 'primary_window': PRIMARY, 'minimum_observations': 36,
    'target_streams': TARGET, 'scale': 'linear_clip_0_100', 'scope': 'covered_groups_of_invested_assets',
    'cash': 'excluded', 'hedge_flag': 'effective_streams_gt_stream_count', 'variance_floor': 1e-12,
    'psd_tolerance': 1e-12, 'integer_snap': 1e-10,
}
CAR_ID = 'car_business'
SCENARIO_METHOD = {
    'version': 'car_scenarios_v1', 'assumption': 'business_behaves_like_proxy', 'window': PRIMARY,
    'weight': 'v2_car_business_weight', 'baseline': 'covered_only_on_scenario_common_months',
    'relation_basis': 'abs_pearson_with_covered_portfolio',
    'not_correlated_below': .25, 'correlated_from': .75, 'range': 'min_max_of_displayed_points',
}
IGNORED = {'calculated_at', 'result_fingerprint'}
EPS = METHOD['integer_snap']


def _source(v2):
    return dict(result_fingerprint=v2['result_fingerprint'], method_fingerprint=v2['method_fingerprint'],
                history_fingerprint=v2['history_fingerprint'], score=v2['score'])


def _record(v2, **fields):
    result = dict(version=VERSION, unit='points', scope=METHOD['scope'], as_of_date=v2['as_of_date'],
                  calculated_at=datetime.now(timezone.utc).isoformat(), status='unavailable',
                  progress_points=None, progress_display=None, windows={}, coverage=None, warnings=[],
                  method=dict(METHOD), method_fingerprint=fingerprint(METHOD), source_v2=_source(v2))
    result.update(fields)
    return _seal(result)


def _applicable(v2):
    return (isinstance(v2, dict) and v2.get('status') in {'modeled', 'provisional'}
            and isinstance(v2.get('histories'), dict) and isinstance(v2.get('groups'), list)
            and isinstance(v2.get('coverage'), dict) and isinstance(v2.get('configuration'), dict)
            and all(isinstance(v2.get(key), str) for key in (
                'as_of_date', 'result_fingerprint', 'method_fingerprint', 'history_fingerprint')))


def _display(points, streams):
    """One decimal, rounded down; 100.0 only once the target is reached."""
    if streams >= TARGET - EPS:
        return 100.0
    return min(99.9, math.floor(points * 10 + TOLERANCE) / 10)


def _window(frame, weights, months, cutoff):
    """DR squared for the last `months` rows of the covered-group frame."""
    cols = [g for g in sorted(weights) if g in frame and weights[g] > 0]
    out = dict(months=months, status='unavailable', reason=None, observations=0, window_start=None, window_end=None,
               streams=len(cols), effective_streams=None, diversification_ratio=None, volatility_reduction_pct=None,
               progress_points=None, progress_display=None, flags=[], min_eigenvalue=None,
               risk_share={}, annual_volatility_pct={})
    if not cols:
        return dict(out, reason='no_covered_streams')
    data = frame[cols].iloc[-months:].dropna()
    out['observations'] = len(data)
    if len(data) < METHOD['minimum_observations']:
        return dict(out, reason='insufficient_common_history')
    out.update(window_start=data.index[0].date().isoformat(), window_end=data.index[-1].date().isoformat())
    cov = np.atleast_2d(np.cov(data.to_numpy(dtype=float), rowvar=False))
    w = np.array([weights[g] for g in cols], dtype=float)
    if not np.isfinite(cov).all() or not np.isfinite(w).all():
        return dict(out, reason='degenerate_covariance')
    sigma = np.sqrt(np.diag(cov))
    variance, standalone = float(w @ cov @ w), float(w @ sigma)
    if (sigma <= 0).any() or variance <= standalone ** 2 * METHOD['variance_floor']:
        return dict(out, reason='degenerate_covariance')
    eigenvalues = np.linalg.eigvalsh(cov)
    if eigenvalues[0] < -METHOD['psd_tolerance'] * max(eigenvalues[-1], 1e-300):
        return dict(out, reason='not_positive_semidefinite')
    ratio = standalone / math.sqrt(variance)
    streams = ratio ** 2
    if abs(streams - round(streams)) <= EPS:
        streams = float(round(streams))
    points = 100 * min(1., max(0., (streams - 1) / (TARGET - 1)))
    if streams > len(cols) + 1e-9:
        out['flags'].append('hedge_driven_count')
    complete = len(data) == months and data.index[-1] == cutoff
    shares = w * (cov @ w) / variance
    return dict(out, status='modeled' if complete else 'provisional', effective_streams=float(streams),
                diversification_ratio=float(ratio), volatility_reduction_pct=float(100 * (1 - 1 / ratio)),
                progress_points=float(points), progress_display=_display(points, streams),
                min_eigenvalue=float(eigenvalues[0]),
                risk_share={g: float(s) for g, s in zip(cols, shares)},
                annual_volatility_pct={g: float(s * math.sqrt(12) * 100) for g, s in zip(cols, sigma)})


def _coverage(v2, frame):
    invested_pct_nav = float(v2['coverage']['invested_pct_nav'])
    covered, excluded = [], []
    for group in sorted(v2['groups'], key=lambda g: g['id']):
        if group['weight'] <= 0:
            continue
        row = dict(id=group['id'], weight_pct_invested=100 * group['weight'],
                   weight_pct_nav=group['weight'] * invested_pct_nav)
        if group['id'] in frame:
            covered.append(row)
        else:
            excluded.append(dict(row, reason='unclassified' if group['id'] == 'unknown' else 'no_return_history'))
    return dict(covered=covered, excluded=excluded, cash_pct_nav=float(v2['coverage']['cash_pct_nav']),
                covered_pct_invested=sum(r['weight_pct_invested'] for r in covered),
                covered_pct_nav=sum(r['weight_pct_nav'] for r in covered),
                excluded_pct_invested=sum(r['weight_pct_invested'] for r in excluded),
                excluded_pct_nav=sum(r['weight_pct_nav'] for r in excluded))


def _relation(r):
    size = abs(r)
    if size < SCENARIO_METHOD['not_correlated_below']:
        return 'not_correlated'
    return 'correlated' if size >= SCENARIO_METHOD['correlated_from'] else 'moderately_correlated'


def _scenario(frame, weights, cutoff, meta, series):
    """Primary-window result with the car business added as one more stream carrying this proxy's returns.

    The change in the count is measured against the covered-only count on the same months as the scenario,
    so a proxy that is shorter than the headline sample cannot turn a change of sample into an effect.
    """
    merged = frame.assign(**{CAR_ID: series.reindex(frame.index)})
    window = _window(merged, weights, PRIMARY, cutoff)
    out = dict(label=meta['label'], channel=meta['channel'], confidence=meta['confidence'], last_month=meta['last_month'],
               status=window['status'], reason=window['reason'], observations=window['observations'],
               window_start=window['window_start'], window_end=window['window_end'], flags=window['flags'],
               effective_streams=window['effective_streams'], baseline_streams=None, delta_streams=None,
               progress_points=window['progress_points'], progress_display=window['progress_display'],
               annual_volatility_pct=None, correlation_covered=None, correlation_equity_us=None,
               relation=None, effect=None)
    if window['effective_streams'] is None:
        return out
    data = merged[list(window['risk_share'])].iloc[-PRIMARY:].dropna()
    covered = [c for c in data.columns if c != CAR_ID]
    car = data[CAR_ID].to_numpy(dtype=float)
    portfolio = data[covered].to_numpy(dtype=float) @ np.array([weights[c] for c in covered], dtype=float)
    r = float(np.corrcoef(portfolio, car)[0, 1])
    r_equity = float(np.corrcoef(data['equity_us'].to_numpy(dtype=float), car)[0, 1]) if 'equity_us' in covered else None
    if not math.isfinite(r) or (r_equity is not None and not math.isfinite(r_equity)):
        return dict(out, status='unavailable', reason='degenerate_correlation', effective_streams=None,
                    progress_points=None, progress_display=None)
    same_months = _window(frame.loc[data.index], weights, PRIMARY, cutoff)
    if same_months['effective_streams'] is None:
        return dict(out, status='unavailable', reason='baseline_unavailable_on_common_months', effective_streams=None,
                    progress_points=None, progress_display=None)
    baseline = same_months['effective_streams']
    delta = window['effective_streams'] - baseline
    return dict(out, baseline_streams=float(baseline), delta_streams=float(delta),
                annual_volatility_pct=window['annual_volatility_pct'][CAR_ID],
                correlation_covered=r, correlation_equity_us=r_equity, relation=_relation(r),
                effect='adds_diversification' if delta > EPS else 'reduces_diversification' if delta < -EPS else 'neutral')


def _car_scenarios(v2, frame, weights, cutoff, base, proxies):
    """Labeled car-business scenarios from a frozen proxy block; a bad block removes only the scenarios."""
    out = dict(method=dict(SCENARIO_METHOD), status='unavailable', reason=None, block=None, block_fingerprint=None,
               car_weight_pct_invested=None, baseline=None, items={}, range=None)
    if not validate_block(proxies, v2['as_of_date']):
        return dict(out, reason='invalid_car_proxies_block')
    out.update(block=copy.deepcopy(proxies), block_fingerprint=proxies['fingerprint'])
    if weights.get(CAR_ID, 0) <= 0 or CAR_ID in frame:
        return dict(out, reason='no_uncovered_car_business_weight')
    if base['effective_streams'] is None:
        return dict(out, reason='baseline_unavailable')
    out.update(car_weight_pct_invested=100 * weights[CAR_ID],
               baseline={k: base[k] for k in ('status', 'observations', 'effective_streams', 'progress_points',
                                              'progress_display')})
    for name, series in series_map(proxies).items():
        out['items'][name] = _scenario(frame, weights, cutoff, proxies['series'][name], series)
    usable = {name: item for name, item in out['items'].items() if item['effective_streams'] is not None}
    if not usable:
        return dict(out, reason='no_computable_scenario')
    low = min(usable, key=lambda name: usable[name]['progress_points'])
    high = max(usable, key=lambda name: usable[name]['progress_points'])
    return dict(out, status='modeled' if all(i['status'] == 'modeled' for i in usable.values()) else 'provisional',
                range=dict(low_display=usable[low]['progress_display'], high_display=usable[high]['progress_display'],
                           low_proxy=low, high_proxy=high))


def derive_risk_progress_v1(v2, proxies=None):
    """Build the record from a saved v2 record; None when v2 is not usable.

    The primary window (60) sets the status and the headline; the 36-month window is a comparison.
    `proxies` (a car_proxies_v1 block, or any non-None value that fails validation) adds `car_scenarios`;
    without it the record has no such key. A failure to compute is an explicit unavailable record,
    never a silent fallback.
    """
    if not _applicable(v2):
        return None
    try:
        weights = {g['id']: g['weight'] for g in v2['groups']}
        frame = monthly_window(_group_history(v2['histories'], weights, v2['configuration']['group_definitions']),
                               v2['as_of_date'])
        cutoff = completed_month_end(v2['as_of_date'])
        windows = {f'm{months}': _window(frame, weights, months, cutoff) for months in WINDOWS}
        coverage = _coverage(v2, frame)
        warnings = ['partial_scope_excluded_weight'] if coverage['excluded_pct_invested'] > TOLERANCE else []
        main = windows[f'm{PRIMARY}']
        extra = {} if proxies is None else dict(car_scenarios=_car_scenarios(v2, frame, weights, cutoff, main, proxies))
        if main['status'] == 'unavailable':
            return _record(v2, windows=windows, coverage=coverage, warnings=warnings + [main['reason']], **extra)
        return _record(v2, status=main['status'], progress_points=main['progress_points'],
                       progress_display=main['progress_display'], windows=windows, coverage=coverage,
                       warnings=warnings + main['flags'], **extra)
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, np.linalg.LinAlgError):
        return _record(v2, warnings=['invalid_inputs'])


def validate_saved_risk_progress_v1(result, data, v2, expected_date=None, *, v2_validated=False):
    """Integrity plus full recomputation from the saved v2 record's frozen histories."""
    try:
        if not isinstance(result, dict) or result.get('version') != VERSION or result.get('unit') != 'points' \
                or result.get('scope') != METHOD['scope']:
            return False
        if result.get('result_fingerprint') != fingerprint({k: v for k, v in result.items() if k != 'result_fingerprint'}):
            return False
        if not v2_validated and not validate_saved_allocation_v2(v2, data, expected_date, replay=True):
            return False
        if result['as_of_date'] != v2['as_of_date'] or (expected_date and result['as_of_date'] != expected_date):
            return False
        if result.get('method') != METHOD or result.get('method_fingerprint') != fingerprint(METHOD):
            return False
        if result.get('source_v2') != _source(v2):
            return False
        datetime.fromisoformat(result['calculated_at'])
        if result['status'] not in {'modeled', 'provisional', 'unavailable'} or (
                result['status'] == 'unavailable' and result['progress_points'] is not None):
            return False
        scenarios = result.get('car_scenarios')
        proxies = None if 'car_scenarios' not in result else (
            scenarios.get('block') or {} if isinstance(scenarios, dict) else {})
        fresh = derive_risk_progress_v1(v2, proxies)
        if fresh is None:
            return False
        return _same({k: v for k, v in fresh.items() if k not in IGNORED},
                     {k: v for k, v in result.items() if k not in IGNORED})
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return False


def _points(streams, target):
    return 100 * min(1., max(0., (streams - 1) / (target - 1)))


def _print(record):
    cov = record['coverage'] or {}
    print(f"risk_progress_v1 as of {record['as_of_date']}: status={record['status']}, "
          f"progress={record['progress_display']} / 100 (target {TARGET} streams, linear policy scale)")
    for name, w in record['windows'].items():
        if w['effective_streams'] is None:
            print(f"  {name}: unavailable ({w['reason']}), observations={w['observations']}")
            continue
        print(f"  {name}: {w['status']} n={w['observations']} {w['window_start']}..{w['window_end']} "
              f"N_DR={w['effective_streams']:.4f} DR={w['diversification_ratio']:.4f} "
              f"vol_reduction={w['volatility_reduction_pct']:.2f}% points@{TARGET}={w['progress_points']:.2f} "
              f"points@25(reference only)={_points(w['effective_streams'], 25):.2f} flags={w['flags'] or '-'}")
    if cov:
        excluded = ', '.join('{} ({})'.format(r['id'], r['reason']) for r in cov['excluded']) or 'none'
        print(f"  covered {cov['covered_pct_invested']:.2f}% of invested ({cov['covered_pct_nav']:.2f}% of NAV); "
              f"excluded {cov['excluded_pct_invested']:.2f}% ({cov['excluded_pct_nav']:.2f}% of NAV): {excluded}; "
              f"cash {cov['cash_pct_nav']:.2f}% of NAV outside the metric")
    main = record['windows'].get(f'm{PRIMARY}')
    if main and main['risk_share']:
        shares = sorted(main['risk_share'].items(), key=lambda item: -item[1])
        print('  variance share (m60): ' + ', '.join(f'{g} {s * 100:.1f}%' for g, s in shares))
    if record['warnings']:
        print('  warnings: ' + ', '.join(record['warnings']))
    scenarios = record.get('car_scenarios')
    if scenarios is None:
        return
    if scenarios['status'] == 'unavailable':
        print(f"  car-business scenarios unavailable ({scenarios['reason']})")
        return
    print(f"  car-business scenarios (assumption: the business behaves like the series; weight "
          f"{scenarios['car_weight_pct_invested']:.2f}% of invested; covered m60 N_DR="
          f"{scenarios['baseline']['effective_streams']:.4f}, points={scenarios['baseline']['progress_display']}):")
    for name, item in scenarios['items'].items():
        if item['effective_streams'] is None:
            print(f"    {name}: unavailable ({item['reason']}), observations={item['observations']}")
            continue
        equity = 'n/a' if item['correlation_equity_us'] is None else f"{item['correlation_equity_us']:+.2f}"
        print(f"    {name}: {item['status']} n={item['observations']} N_DR={item['effective_streams']:.4f} "
              f"(change {item['delta_streams']:+.4f}) points={item['progress_display']} "
              f"r_covered={item['correlation_covered']:+.2f} r_equity_us={equity} "
              f"vol={item['annual_volatility_pct']:.1f}% {item['relation']}, {item['effect']}")
    span = scenarios['range']
    print(f"    range of points: {span['low_display']} ({span['low_proxy']}) .. {span['high_display']} ({span['high_proxy']})")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True, help='Dated combined-data snapshot with a saved v2 record')
    parser.add_argument('--out', type=Path, help='Write the record to a new file (never overwrites; not in snapshot dirs)')
    parser.add_argument('--car-proxies', type=Path, help=f'car_proxies_v1 block for the car-business scenarios '
                        f'(default: {LATEST_BLOCK.name} in data/car_category when present)')
    parser.add_argument('--json', action='store_true', help='Print the record as JSON instead of a table')
    args = parser.parse_args()
    try:
        payload = json.loads(args.snapshot.read_text())
        data = payload.get('data', payload)
        v2 = (data.get('DIVERSIFICATION_DATA') or {}).get('allocation_score_v2')
        expected = payload.get('as_of_date')
        if not validate_saved_allocation_v2(v2, data, expected, replay=True):
            parser.exit(2, 'The saved v2 record does not replay from its frozen inputs; no number is shown.\n')
        if args.car_proxies and not args.car_proxies.exists():
            parser.exit(2, 'The car proxy block file does not exist.\n')
        proxies = load_block(args.car_proxies or LATEST_BLOCK)
        record = derive_risk_progress_v1(v2, proxies)
        if record is None or not validate_saved_risk_progress_v1(record, data, v2, expected, v2_validated=True):
            parser.exit(2, 'No risk progress can be derived from this v2 record.\n')
        if args.out:
            destination, source = args.out.resolve(), args.snapshot.resolve()
            if (destination == source or destination.parent == source.parent or 'snapshots' in destination.parts
                    or destination.name in {'combined_data_latest.json', 'final_data.json'}):
                parser.exit(2, 'Choose a new output path outside the source and automatic snapshot directories.\n')
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open('x', encoding='utf-8') as handle:
                json.dump(record, handle, ensure_ascii=False, indent=2, allow_nan=False)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        parser.exit(2, f'Risk progress failed ({type(error).__name__}). Original data was not changed.\n')
    if args.json:
        print(json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False))
    else:
        _print(record)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
