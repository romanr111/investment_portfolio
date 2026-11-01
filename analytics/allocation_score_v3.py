"""Capital diversification v3: the v2 formula with the car pairs taken from a category price index.

Everything except the car_business pairs is the saved, replayed v2 record: weights, sectors,
the other pair correlations and the 0.75 stress scenario. The car pairs come from the frozen
`car_category` block (analytics.car_category): the correlation of a used-vehicle price index
with each group, scaled by the index loading R = 1. R = 1 is a conditional scenario assumption
(the business inherits the index's price channel), not a bound on the business, so the result is
a category proxy and never a measurement of the owner's business.
"""
from copy import deepcopy
from datetime import datetime, timezone

import pandas as pd

from analytics import car_category
from analytics.allocation_inputs import _seal
from analytics.allocation_score import correlation_map, monthly_window
from analytics.allocation_score_v2 import TOLERANCE, _same, category, score_components_v2
from analytics.allocation_v2_inputs import _group_history, validate_saved_allocation_v2
from analytics.holy_grail import completed_month_end, fingerprint

VERSION = 'capital_diversification_v3'
CAR = car_category.CAR
WINDOWS = (60, 36)
# Headline judgment call: per group the largest of three different correlation measures (window,
# window with a one-month price lag, long-history equity-stress months). Their samples differ, so a
# pair's observations count and measure are stored, not a common window. The wider cat_upper90
# (largest per-measure Fisher endpoint, nominal per estimate) and the 0.75 stress stay as scenarios.
HEADLINE = 'm60_cat_point'
BASES = {'cat_point': 'point', 'cat_upper90': 'upper90'}
METHOD_V3 = {
    'version': VERSION, 'source_version': 'capital_diversification_v2', 'category_method': car_category.METHOD,
    'windows': list(WINDOWS), 'category_scenarios': list(BASES), 'stress_scenarios': ['r075'],
    'headline_scenario': HEADLINE, 'car_group': CAR, 'pair_kind': 'category',
    'max_missing_pair_points': 5, 'minimum_observations': 36,
}
IGNORED = {'calculated_at', 'result_fingerprint'}


def _weights(v2):
    return {group['id']: group['weight'] for group in v2['groups']}


def _measures(v2, block):
    weights = _weights(v2)
    frame = monthly_window(_group_history(v2['histories'], weights, v2['configuration']['group_definitions']),
                           v2['as_of_date'])
    out = {}
    for months in WINDOWS:
        window = frame.iloc[-months:]
        out[f'm{months}'] = {group: car_category.group_measures(block, window, group, months)
                             for group in sorted(weights) if group not in (CAR, 'unknown') and group in window}
    return out


def _scenario(v2, months, assign, basis):
    """Template pairs of the saved base scenario with the car pairs replaced by `assign(group)`."""
    weights = _weights(v2)
    pairs = deepcopy(v2['scenarios'][f'm{months}_r025']['pairs'])
    for pair in pairs:
        if CAR not in (pair['left'], pair['right']):
            continue
        other = pair['right'] if pair['left'] == CAR else pair['left']
        if other == 'unknown':
            continue
        value = assign(other)
        if value is None:
            pair.update(correlation=None, kind='missing', observations=0, months=[], last_month=None)
        else:
            pair.update(correlation=value['correlation'], kind=value['kind'],
                        observations=value['observations'], months=[], last_month=None)
            if value.get('sample'):
                pair['sample'] = value['sample']
    correlations = correlation_map(pairs)
    components = score_components_v2(weights, correlations, v2['sectors'])
    optimistic = dict(correlations)
    optimistic.update({(p['left'], p['right']): 0. for p in pairs if p['correlation'] is None})
    impact = score_components_v2(weights, optimistic, v2['sectors'])['score'] - components['score']
    if impact < -TOLERANCE:
        raise ValueError('Invalid missing-pair bound')
    last = completed_month_end(v2['as_of_date']).date().isoformat()
    scenario = dict(window_months=months, business_correlation=None, car_basis=basis, status='modeled',
                    reason=None, pairs=pairs, components=components, score=components['score'],
                    display_score=components['display_score'], category=category(components['score']),
                    missing_pair_max_points=max(0., impact))
    # Same status rules as v2. Category pairs carry the index window, not an exact-window count.
    if months == 36 and any(p['kind'] == 'missing' or (p['kind'] == 'measured' and p['observations'] != 36)
                            for p in pairs):
        scenario.update(status='unavailable', reason='incomplete_window', score=None, display_score=None, category=None)
    elif impact > 5 + TOLERANCE:
        scenario.update(status='unavailable', reason='insufficient_pair_coverage', score=None,
                        display_score=None, category=None)
    elif any(p['kind'] == 'missing' or (p['kind'] == 'measured' and
             (p['observations'] < months or p['last_month'] != last)) for p in pairs):
        scenario['status'] = 'provisional'
    return scenario


def _assessment(scenarios):
    available = {key: value for key, value in scenarios.items() if value['score'] is not None}
    categories = {key: value['category'] for key, value in available.items()}
    suffixes = tuple(BASES) + ('r075',)

    def differs(left, right):
        return left in categories and right in categories and categories[left] != categories[right]

    business_dependent = any(differs(f'm{w}_{a}', f'm{w}_{b}') for w in WINDOWS for a in suffixes for b in suffixes)
    window_dependent = any(differs(f'm60_{s}', f'm36_{s}') for s in suffixes)
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
                  assessment=_assessment({}), coverage=deepcopy(v2['coverage']), method=deepcopy(METHOD_V3),
                  method_fingerprint=fingerprint(METHOD_V3), car_category=None,
                  source_v2=dict(result_fingerprint=v2['result_fingerprint'],
                                 method_fingerprint=v2['method_fingerprint'], score=v2['score']))
    result.update(fields)
    return _seal(result)


def _unavailable(v2, warning):
    return _record(v2, warnings=[warning])


def _applicable(v2):
    return (isinstance(v2, dict) and v2.get('status') in {'modeled', 'provisional'}
            and all(f'm{w}_{s}' in v2.get('scenarios', {}) for w in WINDOWS for s in ('r025', 'r075'))
            and _weights(v2).get(CAR, 0) > 0)


def derive_allocation_score_v3(v2, block):
    """Build the v3 record from a saved v2 record and a frozen category block.

    Returns None when there is nothing to derive (no block supplied, v2 not usable, or no car
    business); an unusable block yields an explicit unavailable record, never a silent fallback.
    """
    if block is None or not _applicable(v2):
        return None
    try:
        if not car_category.validate_block(block, v2['as_of_date']):
            return _unavailable(v2, 'invalid_car_category_block')
        measures = _measures(v2, block)
        scenarios = {}
        for months in WINDOWS:
            by_group = measures[f'm{months}']
            for name, field in BASES.items():
                def assign(group, by_group=by_group, field=field):
                    measure = by_group.get(group)
                    if not measure or measure[field] is None:
                        return None
                    upper = field == 'upper90'
                    return dict(correlation=measure[field], kind='category',
                                observations=measure['upper_n' if upper else 'n'],
                                sample=measure['upper_selected' if upper else 'selected'])
                scenarios[f'm{months}_{name}'] = _scenario(v2, months, assign, name)
            stress = deepcopy(v2['scenarios'][f'm{months}_r075'])
            stress['car_basis'] = 'assumption'
            scenarios[f'm{months}_r075'] = stress
        headline = scenarios[HEADLINE]
        warnings = [w for w in v2['warnings'] if w != 'partial_pair_history']
        if headline['status'] == 'provisional':
            warnings.append('partial_pair_history')
        if any(p['kind'] == 'missing' and CAR in (p['left'], p['right']) and 'unknown' not in (p['left'], p['right'])
               for p in headline['pairs']):
            warnings.append('category_pair_unmeasured')
        if pd.Timestamp(block['cutoff_month']) < completed_month_end(v2['as_of_date']):
            warnings.append('category_index_lagged')
        coverage = dict(v2['coverage'], missing_pair_max_points=headline['missing_pair_max_points'])
        fields = dict(scenarios=scenarios, measures=measures, assessment=_assessment(scenarios), coverage=coverage,
                      warnings=warnings, car_category=deepcopy(block))
        if headline['score'] is None:
            fields['warnings'] = warnings + ['insufficient_coverage']
        else:
            fields.update(status='provisional' if warnings else headline['status'], score=headline['score'],
                          display_score=headline['display_score'], category=headline['category'])
        return _record(v2, **fields)
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return _unavailable(v2, 'invalid_inputs')


def validate_saved_allocation_v3(result, data, v2, expected_date=None, *, v2_validated=False):
    """Integrity plus full recomputation from the saved v2 record and the frozen block."""
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
        if result.get('method') != METHOD_V3 or result.get('method_fingerprint') != fingerprint(METHOD_V3):
            return False
        if result.get('source_v2') != dict(result_fingerprint=v2['result_fingerprint'],
                                           method_fingerprint=v2['method_fingerprint'], score=v2['score']):
            return False
        datetime.fromisoformat(result['calculated_at'])
        if result['status'] not in {'modeled', 'provisional', 'unavailable'} or (
                result['status'] == 'unavailable' and result['score'] is not None):
            return False
        block = result.get('car_category')
        if block is None:
            fresh = _unavailable(v2, 'invalid_car_category_block') if _applicable(v2) else None
            if fresh is not None and result['warnings'] != fresh['warnings']:
                fresh = _unavailable(v2, 'invalid_inputs')
        else:
            fresh = derive_allocation_score_v3(v2, block)
        if fresh is None:
            return False
        return _same({k: v for k, v in fresh.items() if k not in IGNORED},
                     {k: v for k, v in result.items() if k not in IGNORED})
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return False
