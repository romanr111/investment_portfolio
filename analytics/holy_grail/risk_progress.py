"""Risk progress v1: effective independent equal-risk streams (DR squared) for the covered groups.

A sibling record derived offline from a saved, replayed capital_diversification_v2 record. It reads
only the frozen group histories and weights, never prices or networks. The enrichment
(`holy_grail_data`) derives it and the view (`allocation_view`) replays it before display; v2/v3 and
balances are never changed. The scale is a policy choice (target 15 streams mapped linearly to 0-100),
not a percentage of risk. Groups without a return history (car_business)
are excluded from the headline and reported. With a frozen `car_proxies` block (v1 or v2) the record also holds
labeled car-business scenarios ("the business behaves like this public series"); a scenario is an
assumption shown as a range next to the headline, never the headline. Cash is outside the metric.

risk_progress_v2 (second half of this file) is the headline record for new snapshots: one 0-100 score over
every positive invested weight, with the car business carried by the labelled CPRT/KMX/OPLN basket of a frozen
car proxy block. v1 above keeps its own records and rules.
"""
import argparse
import copy
from datetime import datetime, timezone
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from analytics.holy_grail.allocation_inputs import seal_result
from analytics.holy_grail.correlation import monthly_window
from analytics.holy_grail.allocation_score_v2 import TOLERANCE, same_value
from analytics.holy_grail.allocation_v2_inputs import build_group_history, validate_saved_allocation_v2
from analytics.holy_grail.car.risk_proxies import LATEST_BLOCK, inspect_block, load_block, series_map, validate_block
from analytics.holy_grail.car import risk_proxies
from analytics.holy_grail.fingerprint import completed_month_end, fingerprint

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
    return seal_result(result)


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
    `proxies` (a car_proxies block, or any non-None value that fails validation) adds `car_scenarios`;
    without it the record has no such key. A failure to compute is an explicit unavailable record,
    never a silent fallback.
    """
    if not _applicable(v2):
        return None
    try:
        weights = {g['id']: g['weight'] for g in v2['groups']}
        frame = monthly_window(build_group_history(v2['histories'], weights, v2['configuration']['group_definitions']),
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
        return same_value({k: v for k, v in fresh.items() if k not in IGNORED},
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
    parser.add_argument('--car-proxies', type=Path, help=f'car_proxies block for the car-business scenarios '
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


# --------------------------------------------------------------------------------------------------------------
# risk_progress_v2: one 0-100 score over every invested weight; the car business enters through the labelled
# CPRT/KMX/OPLN basket of a frozen car proxy block. v1 above is untouched and still replays its own records.
# --------------------------------------------------------------------------------------------------------------
VERSION_V2 = 'risk_progress_v2'
# Values owned by the proxy block code are read from it, so changing them there changes the method fingerprint.
BASKET_ID = risk_proxies.MAIN_SERIES
BASKET_NAMES = list(risk_proxies.BASKET)
COMPARISON_IDS = [BASKET_ID, 'manheim_wholesale', 'bls_used_retail', 'auto1_wholesale_eu']
MULTIPLIERS = [0.5, 1.0, 2.0]
WORST_MONTHS = 6
WRITEOFF_FRACTIONS = [0.5, 1.0]
MAX_LAG = risk_proxies.METHOD['max_lag_months']
WEIGHT_TOLERANCE = 1e-8
HEDGE_TOLERANCE = 1e-9
HEADLINE_CAP, DETAIL_CAP = 99, 99.9
TARGET_BENEFIT = 1 - 1 / math.sqrt(TARGET)
METHOD_V2 = {
    'version': VERSION_V2, 'scope': 'invested_assets', 'cash': 'excluded',
    'formula': 'DR=sum(w*sigma)/sqrt(w^T Sigma w); benefit=1-1/DR; score=100*benefit/(1-1/sqrt(target))',
    'scale': 'benefit_over_target_benefit_clip_0_100', 'target_streams': TARGET,
    'estimator': 'ledoit_wolf_2003_constant_correlation_on_sample_covariance_ddof1',
    'shrinkage': {'target': 'constant_correlation', 'intensity': 'ledoit_wolf_2003_analytic_clip_0_1',
                  'moments': 'ml_divide_by_T', 'scale': 'times_T_over_T_minus_1'},
    'stream': 'v2_group_representative_history',
    'weights': 'saved_v2_weights_every_positive_group_required', 'windows': list(WINDOWS), 'primary_window': PRIMARY,
    'minimum_observations': 36, 'max_lag_months': MAX_LAG,
    'car_business': {'series': BASKET_ID, 'names': BASKET_NAMES, 'aggregation': 'equal_weight_all_names_required',
                     'blocks': sorted(risk_proxies.INSPECT_METHODS)},
    'risk_share': 'euler_w_i_times_cov_w_i_over_variance', 'annual_volatility': 'monthly_std_times_sqrt12',
    'proxy_comparison': {'ids': COMPARISON_IDS, 'sample': 'common_months_of_all_ids_and_other_groups'},
    'volatility': {'multipliers': MULTIPLIERS, 'sample': 'main_scenario_months'},
    'stress': {'worst_months': WORST_MONTHS, 'rule': 'lowest_portfolio_return_earlier_date_on_tie',
               'contribution': 'mean_of_w_i_times_r_i_over_selected_months', 'car_writeoff_fractions': WRITEOFF_FRACTIONS},
    'display': {'headline': 'floor_capped_until_target', 'detail': 'one_decimal_floor_capped_until_target',
                'headline_cap': HEADLINE_CAP, 'detail_cap': DETAIL_CAP},
    'tolerances': {'weight_sum': WEIGHT_TOLERANCE, 'psd': METHOD['psd_tolerance'],
                   'variance_floor': METHOD['variance_floor'], 'integer_snap': EPS, 'hedge_count': HEDGE_TOLERANCE},
}
IGNORED_V2 = {'calculated_at', 'result_fingerprint'}


def _identity(v2):
    return isinstance(v2, dict) and all(isinstance(v2.get(key), str) for key in (
        'as_of_date', 'result_fingerprint', 'method_fingerprint', 'history_fingerprint'))


def _source_v2(v2):
    return dict(result_fingerprint=v2['result_fingerprint'], method_fingerprint=v2['method_fingerprint'],
                history_fingerprint=v2['history_fingerprint'], score=v2.get('score'), status=v2.get('status'))


def _display_v2(points, streams):
    """Integer for the compact headline, one decimal (rounded down) for details; 100 only at the target."""
    if streams >= TARGET - EPS:
        return {'headline': 100, 'detail': 100.0}
    return {'headline': min(HEADLINE_CAP, int(math.floor(points + EPS))),
            'detail': min(DETAIL_CAP, math.floor(points * 10 + TOLERANCE) / 10)}


def _shrunk_covariance(x):
    """Ledoit-Wolf (2003) covariance shrunk toward the constant-correlation target.

    `x` is T x n complete monthly rows. Returns (covariance, intensity, mean correlation) with the ddof=1 scale of
    `np.cov` (the shrunk ML matrix times T/(T-1); DR does not depend on that common factor), or None when the
    inputs cannot be used (fewer than 2 rows, a non-positive variance, non-finite values). The diagonal stays the
    sample variances, so each stream keeps its own volatility. Intensity: the paper's analytic estimate
    kappa/T clipped to [0, 1], all moments divided by T; with a single stream there is nothing to shrink
    (intensity 0.0, mean correlation None) and the result is the plain sample variance.
    """
    t, n = x.shape
    if t < 2:
        return None
    centered = x - x.mean(axis=0)
    sample = centered.T @ centered / t
    sample = (sample + sample.T) / 2
    variance = np.diag(sample).copy()
    if not np.isfinite(sample).all() or (variance <= 0).any():
        return None
    scale = t / (t - 1)
    if n < 2:
        return sample * scale, 0., None
    sigma = np.sqrt(variance)
    outer = np.outer(sigma, sigma)
    mean_correlation = float((np.sum(sample / outer) - n) / (n * (n - 1)))
    target = mean_correlation * outer
    np.fill_diagonal(target, variance)
    squares = centered ** 2
    pi_matrix = squares.T @ squares / t - sample ** 2
    theta = (centered ** 3).T @ centered / t - variance[:, None] * sample
    np.fill_diagonal(theta, 0.)
    rho = np.trace(pi_matrix) + mean_correlation * np.sum(np.outer(1 / sigma, sigma) * theta)
    gamma = float(np.sum((sample - target) ** 2))
    # gamma is zero up to rounding when the sample already equals the target (always so for two streams): no shrinkage
    kappa = (pi_matrix.sum() - rho) / gamma if gamma > 1e-24 * float(np.sum(sample ** 2)) else 0.
    intensity = float(max(0., min(1., kappa / t))) if np.isfinite(kappa) else 0.
    return (intensity * target + (1 - intensity) * sample) * scale, intensity, mean_correlation


def _stats(data, weights):
    """Covariance statistics of complete rows; a reason string when the inputs cannot be used."""
    cols = list(data.columns)
    x = data.to_numpy(dtype=float)
    w = np.array([weights[c] for c in cols], dtype=float)
    if not np.isfinite(x).all() or not np.isfinite(w).all():
        return 'degenerate_covariance'
    shrunk = _shrunk_covariance(x)
    if shrunk is None:
        return 'degenerate_covariance'
    cov, intensity, mean_correlation = np.atleast_2d(shrunk[0]), shrunk[1], shrunk[2]
    if not np.isfinite(cov).all():
        return 'degenerate_covariance'
    sigma = np.sqrt(np.diag(cov))
    variance, standalone = float(w @ cov @ w), float(w @ sigma)
    if (sigma <= 0).any() or variance <= standalone ** 2 * METHOD_V2['tolerances']['variance_floor']:
        return 'degenerate_covariance'
    eigenvalues = np.linalg.eigvalsh(cov)
    if eigenvalues[0] < -METHOD_V2['tolerances']['psd'] * max(eigenvalues[-1], 1e-300):
        return 'not_positive_semidefinite'
    ratio = standalone / math.sqrt(variance)
    streams = ratio ** 2
    if abs(streams - round(streams)) <= EPS:
        streams = float(round(streams))
        ratio = math.sqrt(streams)
    points = min(100., max(0., 100 * (1 - 1 / ratio) / TARGET_BENEFIT))
    shares = w * (cov @ w) / variance
    return dict(cols=cols, w=w, x=x, ratio=float(ratio), streams=float(streams), points=float(points),
                shares={c: float(s) for c, s in zip(cols, shares)},
                annual={c: float(s * math.sqrt(12) * 100) for c, s in zip(cols, sigma)},
                portfolio=float(math.sqrt(variance) * math.sqrt(12) * 100), min_eigenvalue=float(eigenvalues[0]),
                shrinkage=dict(target='constant_correlation', intensity=float(intensity),
                               mean_correlation=None if mean_correlation is None else float(mean_correlation)))


def _empty_window(months, cols, reason=None):
    return dict(months=months, status='unavailable', reason=reason, observations=0, window_start=None, window_end=None,
                streams=len(cols), effective_streams=None, diversification_ratio=None, volatility_reduction_pct=None,
                progress_points=None, progress_display=None, flags=[], min_eigenvalue=None, capital_weights={},
                risk_share={}, annual_volatility_pct={}, annual_portfolio_volatility_pct=None, shrinkage=None)


def _window_v2(frame, cols, weights, months, cutoff):
    """DR window on the last `months` calendar rows; (record, complete-rows frame or None)."""
    out = _empty_window(months, cols)
    if not cols:
        return dict(out, reason='no_streams'), None
    sub = frame[cols].iloc[-months:]
    data = sub.dropna()
    out['observations'] = len(data)
    if len(data) < METHOD_V2['minimum_observations']:
        return dict(out, reason='insufficient_common_history'), None
    floor = cutoff - pd.offsets.MonthEnd(MAX_LAG)
    stale = [c for c in cols if sub[c].last_valid_index() is None or sub[c].last_valid_index() < floor]
    if stale:
        return dict(out, reason='stale_series:' + ','.join(stale)), None
    if data.index[-1] < floor:
        return dict(out, reason='stale_common_history'), None
    out.update(window_start=data.index[0].date().isoformat(), window_end=data.index[-1].date().isoformat())
    stats = _stats(data, weights)
    if isinstance(stats, str):
        return dict(out, reason=stats), None
    lagged, short = data.index[-1] < cutoff, len(data) < months
    flags = (['lagged_one_month'] if lagged else []) + (['short_history'] if short else [])
    if stats['streams'] > len(cols) + HEDGE_TOLERANCE:
        flags.append('hedge_driven_count')
    return dict(out, status='provisional' if lagged or short else 'modeled',
                effective_streams=stats['streams'], diversification_ratio=stats['ratio'],
                volatility_reduction_pct=float(100 * (1 - 1 / stats['ratio'])), progress_points=stats['points'],
                progress_display=_display_v2(stats['points'], stats['streams']), flags=flags,
                min_eigenvalue=stats['min_eigenvalue'], capital_weights={c: float(weights[c]) for c in cols},
                risk_share=stats['shares'], annual_volatility_pct=stats['annual'],
                annual_portfolio_volatility_pct=stats['portfolio'], shrinkage=stats['shrinkage']), data


def _item(stats, status):
    if isinstance(stats, str):
        return dict(status='unavailable', reason=stats, effective_streams=None, progress_points=None,
                    progress_display=None, car_risk_share=None, annual_portfolio_volatility_pct=None)
    return dict(status=status, reason=None, effective_streams=stats['streams'], progress_points=stats['points'],
                progress_display=_display_v2(stats['points'], stats['streams']),
                car_risk_share=stats['shares'][CAR_ID], annual_portfolio_volatility_pct=stats['portfolio'])


def _volatility(data, weights, status):
    items = {}
    for multiplier in MULTIPLIERS:
        scaled = data.copy()
        scaled[CAR_ID] = scaled[CAR_ID] * multiplier
        stats = _stats(scaled, weights)
        item = _item(stats, status)
        item['car_series_annual_volatility_pct'] = None if isinstance(stats, str) else stats['annual'][CAR_ID]
        items[str(multiplier)] = item
    usable = [i for i in items.values() if i['status'] != 'unavailable']
    return dict(status=status if usable else 'unavailable', reason=None if usable else 'degenerate_covariance',
                multipliers=list(MULTIPLIERS), items=items)


def _comparison(base, other, weights, block, check, cutoff, main_data, parent_status):
    out = dict(status='unavailable', reason=None, members=list(COMPARISON_IDS), common_observations=0,
               window_start=None, window_end=None, same_sample_as_main=None, items={}, range=None)
    if not check['integrity']:
        return dict(out, reason='invalid_car_proxies_block')
    problems = {}
    for name in COMPARISON_IDS:
        info = check['series'].get(name)
        if info is None:
            problems[name] = 'missing'
        elif not info['ok']:
            problems[name] = info['reason'] or 'unusable'
    if problems:
        items = {name: dict(status='unavailable', reason=problems[name]) if name in problems
                 else dict(status='not_compared', reason='comparison_incomplete') for name in COMPARISON_IDS}
        return dict(out, status='incomplete', reason='incomplete_proxy_set', items=items)
    series = series_map(block)
    wide = base[other].copy()
    for name in COMPARISON_IDS:
        wide[name] = series[name].reindex(base.index)
    sample = wide.iloc[-PRIMARY:].dropna()
    out.update(common_observations=len(sample))
    if len(sample) < METHOD_V2['minimum_observations']:
        return dict(out, reason='insufficient_common_history')
    if sample.index[-1] < cutoff - pd.offsets.MonthEnd(MAX_LAG):
        return dict(out, reason='stale_common_history')
    complete = len(sample) == PRIMARY and sample.index[-1] == cutoff
    status = 'modeled' if complete and parent_status == 'modeled' else 'provisional'
    items = {}
    for name in COMPARISON_IDS:
        data = sample[other].assign(**{CAR_ID: sample[name]})[sorted(weights)]
        items[name] = _item(_stats(data, weights), status)
    usable = {n: i for n, i in items.items() if i['status'] != 'unavailable'}
    out.update(window_start=sample.index[0].date().isoformat(), window_end=sample.index[-1].date().isoformat(),
               same_sample_as_main=bool(main_data is not None and list(sample.index) == list(main_data.index)),
               items=items)
    if len(usable) != len(COMPARISON_IDS):
        return dict(out, status='incomplete', reason='degenerate_covariance')
    low = min(usable, key=lambda n: usable[n]['progress_points'])
    high = max(usable, key=lambda n: usable[n]['progress_points'])
    return dict(out, status=status, range=dict(low_id=low, high_id=high, low_display=usable[low]['progress_display'],
                                               high_display=usable[high]['progress_display']))


def _stress(data, weights, status, car_weight_pct_nav):
    cols = list(data.columns)
    w = np.array([weights[c] for c in cols], dtype=float)
    x = data.to_numpy(dtype=float)
    returns = x @ w
    order = sorted(range(len(returns)), key=lambda i: (float(returns[i]), data.index[i]))[:WORST_MONTHS]
    worst = dict(window_start=data.index[0].date().isoformat(), window_end=data.index[-1].date().isoformat(),
                 count=WORST_MONTHS,
                 months=[dict(date=data.index[i].date().isoformat(), portfolio_return=float(returns[i])) for i in order],
                 mean_portfolio_return=float(np.mean(returns[order])),
                 contributions={c: float(np.mean(w[j] * x[order, j])) for j, c in enumerate(cols)})
    writeoff = None if car_weight_pct_nav is None else dict(
        weight_pct_nav=car_weight_pct_nav,
        scenarios=[dict(loss_fraction=f, nav_loss_pct=float(car_weight_pct_nav * f)) for f in WRITEOFF_FRACTIONS],
        assumptions=['rest_of_assets_unchanged', 'no_extra_liabilities_or_secondary_losses_or_taxes'])
    return dict(status=status, reason=None, worst_months=worst, car_writeoff=writeoff)


def _provenance(block, name):
    return block['series'][name].get('provenance') or 'imported:' + str(block.get('fingerprint'))


def _record_v2(v2, retrospective, **fields):
    calculated = v2.get('calculated_at')
    result = dict(version=VERSION_V2, unit='points', scope=METHOD_V2['scope'], as_of_date=v2['as_of_date'],
                  calculated_at=datetime.now(timezone.utc).isoformat(), retrospective=bool(retrospective),
                  data_vintage=dict(source_v2_calculated_at=calculated if isinstance(calculated, str) else None,
                                    car_proxies_cutoff=None, series={}),
                  status='unavailable', reason=None, warnings=[], progress_points=None, progress_display=None,
                  method=copy.deepcopy(METHOD_V2), method_fingerprint=fingerprint(METHOD_V2),
                  source_v2=_source_v2(v2), car_proxies=None, car_proxies_fingerprint=None, coverage=None,
                  windows={}, sensitivity=None, stress=None)
    result.update(fields)
    return seal_result(result)


def _derive_v2(v2, proxies, retrospective):
    def fail(reason, **more):  # reads `retrospective` as it stands when called (raised once the block is known)
        return _record_v2(v2, retrospective, reason=reason, warnings=[reason.split(':')[0]], **more)
    if v2.get('status') == 'not_applicable':
        return _record_v2(v2, retrospective, status='not_applicable', reason='no_invested_assets')
    if not _applicable(v2):
        return fail('source_v2_unavailable')
    groups = [(g['id'], g['weight']) for g in v2['groups']]
    if not all(isinstance(w, (int, float)) and not isinstance(w, bool) and math.isfinite(w) and w >= 0 for _, w in groups) \
            or abs(sum(w for _, w in groups) - 1) > WEIGHT_TOLERANCE:
        return fail('invalid_weights')
    weights = {g: float(w) for g, w in groups if w > 0}
    invested_pct_nav = float(v2['coverage']['invested_pct_nav'])
    cash_pct_nav = float(v2['coverage']['cash_pct_nav'])
    base = monthly_window(build_group_history(v2['histories'], weights, v2['configuration']['group_definitions']),
                          v2['as_of_date'])
    cutoff = completed_month_end(v2['as_of_date'])
    keep = {}
    car_weight = weights.get(CAR_ID, 0.)
    frame, check, block = base, None, None
    if car_weight > 0:
        if proxies is not None and not isinstance(proxies, dict):
            proxies = {'unreadable': True}  # valid JSON that is no block: same marker as an unreadable file, so it replays
        if isinstance(proxies, dict):
            block = copy.deepcopy(proxies)
            keep = dict(car_proxies=block, car_proxies_fingerprint=block.get('fingerprint')
                        if isinstance(block.get('fingerprint'), str) else None)
        if proxies is None:
            return fail('car_proxies_missing')
        check = inspect_block(proxies, v2['as_of_date'])
        if not check['integrity']:
            return fail('invalid_car_proxies_block', **keep)
        main_check = check['series'].get(BASKET_ID)
        if main_check is None or not main_check['ok']:
            excluded = proxies.get('excluded')
            collected = excluded.get(BASKET_ID) if isinstance(excluded, dict) else None
            reason = (main_check['reason'] or 'unusable') if main_check is not None else collected or 'missing'
            return fail('car_basket_unavailable:' + str(reason), **keep)
        basket = series_map(proxies)[BASKET_ID]
        frame = base.assign(**{CAR_ID: basket.reindex(base.index)})
    missing = sorted(g for g in weights if g not in frame)
    covered = []
    for g in sorted(weights):
        row = dict(id=g, weight_pct_invested=100 * weights[g], weight_pct_nav=weights[g] * invested_pct_nav)
        if g in frame:
            covered.append(dict(row, representative='listed_remarketers_proxy' if g == CAR_ID else 'v2_group_history'))
    excluded = [dict(id=g, weight_pct_invested=100 * weights[g], weight_pct_nav=weights[g] * invested_pct_nav,
                     reason='unclassified' if g == 'unknown' else 'no_return_history') for g in missing]
    car_proxy = None
    vintage = dict(source_v2_calculated_at=v2.get('calculated_at') if isinstance(v2.get('calculated_at'), str) else None,
                   car_proxies_cutoff=None, series={})
    if block is not None:
        car_proxy = dict(id=BASKET_ID, names=list(BASKET_NAMES), last_month=block['series'][BASKET_ID]['last_month'],
                         provenance=_provenance(block, BASKET_ID),
                         assumption='business_behaves_like_listed_remarketers_basket')
        vintage = dict(vintage, car_proxies_cutoff=block['cutoff_month'],
                       series={n: dict(last_month=i['last_month'], provenance=_provenance(block, n))
                               for n, i in sorted(block['series'].items())})
        retrospective = bool(retrospective) or (isinstance(block.get('as_of_date'), str)
                                                and block['as_of_date'] > v2['as_of_date'])
    coverage = dict(invested_pct_nav=invested_pct_nav, cash_pct_nav=cash_pct_nav, groups=covered,
                    covered_pct_invested=sum(r['weight_pct_invested'] for r in covered), excluded=excluded,
                    excluded_pct_invested=sum(r['weight_pct_invested'] for r in excluded), car_proxy=car_proxy)
    common = dict(data_vintage=vintage, coverage=coverage, **keep)
    if missing:
        return fail('no_history:' + ','.join(missing), **common)
    cols = sorted(weights)
    windows, frames = {}, {}
    for months in WINDOWS:
        windows[f'm{months}'], frames[months] = _window_v2(frame, cols, weights, months, cutoff)
    main = windows[f'm{PRIMARY}']
    parent = ['source_v2_provisional'] + list(v2.get('warnings') or []) if v2['status'] == 'provisional' else []
    warnings = ([] if car_proxy is None else ['car_proxy_assumption']) + parent
    if main['status'] == 'unavailable':
        stub = dict(status='unavailable', reason='main_unavailable')
        windows[f'm{WINDOWS[1]}'] = _empty_window(WINDOWS[1], cols, 'main_unavailable')
        return _record_v2(v2, retrospective, status='unavailable', reason=main['reason'],
                          warnings=warnings + [main['reason'].split(':')[0]], windows=windows,
                          sensitivity=dict(proxy_comparison=dict(stub), volatility=dict(stub)), stress=dict(stub),
                          **common)
    status = 'provisional' if main['status'] == 'provisional' or parent else 'modeled'
    main_data = frames[PRIMARY]
    if car_weight > 0:
        other = [c for c in cols if c != CAR_ID]
        sensitivity = dict(proxy_comparison=_comparison(base, other, weights, proxies, check, cutoff, main_data, status),
                           volatility=_volatility(main_data, weights, status))
        writeoff = car_weight * invested_pct_nav
    else:
        na = dict(status='not_applicable', reason='no_car_business_weight')
        sensitivity, writeoff = dict(proxy_comparison=dict(na), volatility=dict(na)), None
    return _record_v2(v2, retrospective, status=status, progress_points=main['progress_points'],
                      progress_display=main['progress_display'], warnings=warnings + main['flags'],
                      windows=windows, sensitivity=sensitivity,
                      stress=_stress(main_data, weights, status, None if writeoff is None else float(writeoff)),
                      **common)


def derive_risk_progress_v2(v2, proxies, *, retrospective=False):
    """Headline record from a saved v2 record and a frozen car proxy block (or None).

    None only when `v2` carries no identity. Every other failure is an explicit unavailable record; the car
    business is never given another proxy, and a bad block is kept in the record so the failure replays.
    `retrospective` marks a recomputation made later than the snapshot (also set when the block postdates it).
    The block-date rule is enforced on replay; a caller-asserted True cannot be proven or disproven there
    (a re-sealed record can carry any recorded fact), so it is an assertion, not a guarantee.
    """
    if not _identity(v2):
        return None
    try:
        return _derive_v2(v2, proxies, retrospective)
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, IndexError, np.linalg.LinAlgError):
        return _record_v2(v2, retrospective, reason='invalid_inputs', warnings=['invalid_inputs'])


def _equal(a, b):
    """Replay comparison: ints and strings exact, floats within 1e-8 absolute, containers recursive.

    Stricter than `same_value` on purpose: an int must stay an int (`observations`, counters).
    """
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, int) or isinstance(b, int):
        return isinstance(a, int) and isinstance(b, int) and a == b
    if isinstance(a, float) and isinstance(b, float):
        return math.isclose(a, b, rel_tol=0, abs_tol=TOLERANCE)
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_equal(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_equal(x, y) for x, y in zip(a, b))
    return type(a) is type(b) and a == b if a is not None and b is not None else a is b


def validate_saved_risk_progress_v2(result, data, v2, expected_date=None, *, v2_validated=False):
    """Integrity plus full recomputation from the saved v2 record and the block embedded in the record."""
    try:
        if not isinstance(result, dict) or result.get('version') != VERSION_V2 or result.get('unit') != 'points' \
                or result.get('scope') != METHOD_V2['scope'] or not isinstance(result.get('retrospective'), bool):
            return False
        if result.get('result_fingerprint') != fingerprint({k: v for k, v in result.items() if k != 'result_fingerprint'}):
            return False
        if not v2_validated and not validate_saved_allocation_v2(v2, data, expected_date, replay=True):
            return False
        if result['as_of_date'] != v2['as_of_date'] or (expected_date and result['as_of_date'] != expected_date):
            return False
        if result.get('method') != METHOD_V2 or result.get('method_fingerprint') != fingerprint(METHOD_V2):
            return False
        if result.get('source_v2') != _source_v2(v2):
            return False
        datetime.fromisoformat(result['calculated_at'])
        if result['status'] not in {'modeled', 'provisional', 'unavailable', 'not_applicable'} or (
                result['status'] in {'unavailable', 'not_applicable'}
                and (result['progress_points'] is not None or result['progress_display'] is not None)):
            return False
        fresh = derive_risk_progress_v2(v2, result.get('car_proxies'), retrospective=result['retrospective'])
        if fresh is None:
            return False
        return _equal({k: v for k, v in fresh.items() if k not in IGNORED_V2},
                      {k: v for k, v in result.items() if k not in IGNORED_V2})
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return False


if __name__ == '__main__':
    raise SystemExit(main())
