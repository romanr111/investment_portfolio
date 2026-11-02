"""Capital diversification v4: the v2 formula with the car pairs taken from a channel composite of proxies.

Everything except the car_business pairs is the saved, replayed v2 record: weights, sectors, the other
pair correlations and the 0.75 stress scenario. Each car pair is a 50/50 blend of two channels measured on
the frozen `car_proxies` block (analytics.car_risk_proxies): the mean same-month correlation of the
used-vehicle price indexes with the group, and the correlation of the listed remarketer basket with it.
Weighting channels, not series, keeps a channel with more published indexes from outvoting the other.
The result is a proxy scenario, never a measurement of the owner's business.
"""
from copy import deepcopy
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from analytics.allocation_inputs import _seal
from analytics.allocation_score import monthly_window
from analytics.allocation_score_v2 import _same
from analytics.allocation_score_v3 import CAR, WINDOWS, _scenario, _weights
from analytics.allocation_v2_inputs import _group_history, validate_saved_allocation_v2
from analytics.car_risk_proxies import series_map, validate_block
from analytics.holy_grail import completed_month_end, fingerprint

VERSION = 'capital_diversification_v4'
HEADLINE = 'm60_composite'
CHANNELS = {'price': ['manheim_wholesale', 'bls_used_retail', 'auto1_wholesale_eu', 'ukraine_vehicle_cpi'],
            'equity': ['listed_remarketers']}
CHANNEL_WEIGHTS = {'price': .5, 'equity': .5}
SCENARIOS = ('composite', 'price_channel', 'equity_channel', 'r075')
METHOD_V4 = {
    'version': VERSION, 'source_version': 'capital_diversification_v2', 'proxy_block': 'car_proxies',
    'channels': CHANNELS, 'channel_weights': CHANNEL_WEIGHTS, 'within_channel': 'arithmetic_mean',
    'measure': 'same_month_pearson_on_v2_window', 'windows': list(WINDOWS), 'scenarios': list(SCENARIOS),
    'stress_scenarios': ['r075'], 'headline_scenario': HEADLINE, 'car_group': CAR, 'pair_kind': 'proxy_composite',
    'max_missing_pair_points': 5, 'minimum_observations': 36,
}
IGNORED = {'calculated_at', 'result_fingerprint'}


def _correlation(left, right):
    """Pearson on the common months; None below the minimum or when undefined."""
    joined = pd.concat([left, right], axis=1).dropna()
    if len(joined) < METHOD_V4['minimum_observations']:
        return None
    value = float(np.corrcoef(joined.to_numpy(dtype=float), rowvar=False)[0, 1])
    return dict(r=value, n=len(joined)) if np.isfinite(value) else None


def _measures(v2, block):
    """Per window and group: each proxy's correlation, the two channel means and the composite."""
    weights = _weights(v2)
    frame = monthly_window(_group_history(v2['histories'], weights, v2['configuration']['group_definitions']),
                           v2['as_of_date'])
    proxies = series_map(block)
    out = {}
    for months in WINDOWS:
        window = frame.iloc[-months:]
        by_group = {}
        for group in sorted(weights):
            if group in (CAR, 'unknown') or group not in window:
                continue
            per_proxy = {name: _correlation(window[group], series.reindex(window.index))
                         for name, series in proxies.items()}
            entry = dict(proxies=per_proxy)
            for channel, names in CHANNELS.items():
                usable = [per_proxy[n] for n in names if per_proxy.get(n)]
                entry[channel] = (dict(r=sum(u['r'] for u in usable) / len(usable), n=min(u['n'] for u in usable),
                                       series=len(usable)) if usable else None)
            entry['composite'] = (dict(r=sum(CHANNEL_WEIGHTS[c] * entry[c]['r'] for c in CHANNELS),
                                       n=min(entry[c]['n'] for c in CHANNELS))
                                  if all(entry[c] for c in CHANNELS) else None)
            by_group[group] = entry
        out[f'm{months}'] = by_group
    return out


def _assessment(scenarios):
    available = {key: value for key, value in scenarios.items() if value['score'] is not None}
    categories = {key: value['category'] for key, value in available.items()}

    def differs(left, right):
        return left in categories and right in categories and categories[left] != categories[right]

    business_dependent = any(differs(f'm{w}_{a}', f'm{w}_{b}') for w in WINDOWS for a in SCENARIOS for b in SCENARIOS)
    window_dependent = any(differs(f'm60_{s}', f'm36_{s}') for s in SCENARIOS)
    scores = [value['score'] for value in available.values()]
    displays = [value['display_score'] for value in available.values()]
    return dict(business_dependent=business_dependent, window_dependent=window_dependent,
                combined_dependent=len(set(categories.values())) > 1 and not (business_dependent or window_dependent),
                available=len(available), expected=len(scenarios),
                missing=[key for key in scenarios if key not in available],
                min_score=min(scores) if scores else None, max_score=max(scores) if scores else None,
                min_display=min(displays) if displays else None, max_display=max(displays) if displays else None)


def _record(v2, **fields):
    result = dict(version=VERSION, unit='points', scope='invested_assets', as_of_date=v2['as_of_date'],
                  calculated_at=datetime.now(timezone.utc).isoformat(), status='unavailable', score=None,
                  display_score=None, category=None, warnings=[], scenarios={}, measures={},
                  assessment=_assessment({}), coverage=deepcopy(v2['coverage']), method=deepcopy(METHOD_V4),
                  method_fingerprint=fingerprint(METHOD_V4), car_proxies=None,
                  source_v2=dict(result_fingerprint=v2['result_fingerprint'],
                                 method_fingerprint=v2['method_fingerprint'], score=v2['score']))
    result.update(fields)
    return _seal(result)


def _unavailable(v2, warning, **fields):
    return _record(v2, warnings=[warning], **fields)


def _applicable(v2):
    return (isinstance(v2, dict) and v2.get('status') in {'modeled', 'provisional'}
            and all(f'm{w}_{s}' in v2.get('scenarios', {}) for w in WINDOWS for s in ('r025', 'r075'))
            and _weights(v2).get(CAR, 0) > 0)


def _composite_scenario(v2, months, by_group, field):
    def assign(group):
        measure = (by_group.get(group) or {}).get(field)
        if not measure:
            return None
        return dict(correlation=measure['r'], kind=METHOD_V4['pair_kind'], observations=measure['n'], sample=field)

    scenario = _scenario(v2, months, assign, field)
    # A car pair on fewer months than the window is partial history, as for a measured pair.
    if scenario['status'] == 'modeled' and any(
            p['kind'] == METHOD_V4['pair_kind'] and p['observations'] < months for p in scenario['pairs']):
        scenario['status'] = 'provisional'
    return scenario


def derive_allocation_score_v4(v2, block):
    """Build the v4 record from a saved v2 record and a frozen car proxy block.

    Returns None when there is nothing to derive (no block supplied, v2 not usable, or no car
    business); an unusable block yields an explicit unavailable record, never a silent fallback.
    """
    if block is None or not _applicable(v2):
        return None
    try:
        if not validate_block(block, v2['as_of_date']):
            return _unavailable(v2, 'invalid_car_proxies_block')
        if not all(set(names) & set(block['series']) for names in CHANNELS.values()):
            return _unavailable(v2, 'car_channel_missing', car_proxies=deepcopy(block))
        measures = _measures(v2, block)
        scenarios = {}
        for months in WINDOWS:
            for field in ('composite', 'price', 'equity'):
                name = field if field == 'composite' else f'{field}_channel'
                scenarios[f'm{months}_{name}'] = _composite_scenario(v2, months, measures[f'm{months}'], field)
            stress = deepcopy(v2['scenarios'][f'm{months}_r075'])
            stress['car_basis'] = 'assumption'
            scenarios[f'm{months}_r075'] = stress
        headline = scenarios[HEADLINE]
        warnings = [w for w in v2['warnings'] if w != 'partial_pair_history']
        if headline['status'] == 'provisional':
            warnings.append('partial_pair_history')
        if any(p['kind'] == 'missing' and CAR in (p['left'], p['right']) and 'unknown' not in (p['left'], p['right'])
               for p in headline['pairs']):
            warnings.append('car_proxy_pair_unmeasured')
        if pd.Timestamp(block['cutoff_month']) < completed_month_end(v2['as_of_date']):
            warnings.append('car_proxies_lagged')
        coverage = dict(v2['coverage'], missing_pair_max_points=headline['missing_pair_max_points'])
        fields = dict(scenarios=scenarios, measures=measures, assessment=_assessment(scenarios), coverage=coverage,
                      warnings=warnings, car_proxies=deepcopy(block))
        if headline['score'] is None:
            fields['warnings'] = warnings + ['insufficient_coverage']
        else:
            fields.update(status='provisional' if warnings else headline['status'], score=headline['score'],
                          display_score=headline['display_score'], category=headline['category'])
        return _record(v2, **fields)
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return _unavailable(v2, 'invalid_inputs')


def validate_saved_allocation_v4(result, data, v2, expected_date=None, *, v2_validated=False):
    """Integrity plus full recomputation from the saved v2 record and the embedded proxy block."""
    try:
        if not isinstance(result, dict) or result.get('version') != VERSION or result.get('unit') != 'points' \
                or result.get('scope') != 'invested_assets':
            return False
        if result.get('result_fingerprint') != fingerprint({k: v for k, v in result.items() if k != 'result_fingerprint'}):
            return False
        if not v2_validated and not validate_saved_allocation_v2(v2, data, expected_date, replay=True):
            return False
        if result['as_of_date'] != v2['as_of_date'] or (expected_date and result['as_of_date'] != expected_date):
            return False
        if result.get('method') != METHOD_V4 or result.get('method_fingerprint') != fingerprint(METHOD_V4):
            return False
        if result.get('source_v2') != dict(result_fingerprint=v2['result_fingerprint'],
                                           method_fingerprint=v2['method_fingerprint'], score=v2['score']):
            return False
        datetime.fromisoformat(result['calculated_at'])
        if result['status'] not in {'modeled', 'provisional', 'unavailable'} or (
                result['status'] == 'unavailable' and result['score'] is not None):
            return False
        block = result.get('car_proxies')
        if block is None:
            fresh = _unavailable(v2, 'invalid_car_proxies_block') if _applicable(v2) else None
            if fresh is not None and result['warnings'] != fresh['warnings']:
                fresh = _unavailable(v2, 'invalid_inputs')
        else:
            fresh = derive_allocation_score_v4(v2, block)
        if fresh is None:
            return False
        return _same({k: v for k, v in fresh.items() if k not in IGNORED},
                     {k: v for k, v in result.items() if k not in IGNORED})
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return False
