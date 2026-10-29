"""Pure capital-diversity calculation for the version 2 methodology."""
from itertools import combinations
import math
from numbers import Real

VERSION = 'capital_diversification_v2'
SECTORS = frozenset({'Information Technology', 'Financials', 'Communication Services',
                     'Health Care', 'Consumer Discretionary', 'Industrials',
                     'Consumer Staples', 'Energy', 'Utilities', 'Real Estate', 'Materials'})
TOLERANCE = 1e-8


def _number(value):
    return isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(value)


def _same(a, b, tol=TOLERANCE):
    """Bounded equality for recomputed values replayed across environments.

    Numbers (absolute-tolerance close), dicts (same key set), lists and tuples
    (same length, element-wise) compare recursively; bool, None and everything
    else - strings such as fingerprints, categories, status, dates, and
    configuration values - compare exactly.
    """
    if isinstance(a, Real) and isinstance(b, Real) and not isinstance(a, bool) and not isinstance(b, bool):
        return math.isclose(a, b, rel_tol=0, abs_tol=tol)
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if a is None or b is None:
        return a is b
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_same(a[k], b[k], tol) for k in a)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_same(x, y, tol) for x, y in zip(a, b))
    return a == b


def display_score(score):
    if not _number(score) or score < -TOLERANCE or score > 100 + TOLERANCE:
        raise ValueError('Invalid score')
    score = min(100., max(0., score))
    nearest = round(score)
    return math.floor(nearest if abs(score - nearest) <= TOLERANCE else score)


def category(score):
    if not _number(score) or score < -TOLERANCE or score > 100 + TOLERANCE:
        raise ValueError('Invalid score')
    nearest = round(score)
    score = nearest if abs(score - nearest) <= TOLERANCE else score
    return 'concentrated' if score < 50 else 'partly_diversified' if score < 80 else 'well_diversified'


def score_components_v2(weights, correlations, sectors_by_group):
    """Calculate from aggregated group weights and conditional equity sector shares.

    Missing correlations conservatively represent perfect similarity. Unknown
    equity sector weight is assigned to the largest known global sector.
    """
    if not weights or any(not _number(v) or v < 0 for v in weights.values()):
        raise ValueError('Invalid economic weights')
    if abs(sum(weights.values()) - 1) > TOLERANCE:
        raise ValueError('Economic weights must sum to one')
    for pair, rho in correlations.items():
        if not isinstance(pair, tuple) or len(pair) != 2 or not _number(rho) or not -1 <= rho <= 1:
            raise ValueError('Invalid correlation')
        reverse = correlations.get((pair[1], pair[0]), rho)
        if reverse != rho:
            raise ValueError('Conflicting correlations')
    amounts = {}
    equity_weight = sum(w for g, w in weights.items() if g.startswith('equity_'))
    for group, sectors in sectors_by_group.items():
        if group not in weights or not group.startswith('equity_') or not isinstance(sectors, dict):
            raise ValueError('Invalid sector group')
        if any(k not in SECTORS or not _number(v) or v < 0 for k, v in sectors.items()):
            raise ValueError('Invalid sector profile')
        if sum(sectors.values()) > 1 + TOLERANCE:
            raise ValueError('Invalid sector profile')
        for sector, share in sectors.items():
            amounts[sector] = amounts.get(sector, 0.) + weights[group] * share
    breadth = 0.
    if equity_weight > 0 and amounts and max(amounts.values()) > 0:
        largest = min(amounts, key=lambda s: (-amounts[s], s))
        amounts[largest] += max(0., equity_weight - sum(amounts.values()))
        breadth = (1 - sum((amount / equity_weight) ** 2 for amount in amounts.values())) / (1 - 1 / 11)
        if breadth < -TOLERANCE or breadth > 1 + TOLERANCE:
            raise ValueError('Invalid sector breadth')
        breadth = min(1., max(0., breadth))
    concentration = sum(w * w for w in weights.values())
    for left, right in combinations(sorted(weights), 2):
        rho = correlations.get((left, right), correlations.get((right, left), 1.))
        concentration += 2 * weights[left] * weights[right] * max(0., rho) ** 2
    effective = 1 / concentration
    between = min(1., max(0., (effective - 1) / 5))
    bonus = 25 * min(equity_weight * breadth, 1 - between)
    score = 100 * between + bonus
    if score < -TOLERANCE or score > 100 + TOLERANCE:
        raise ValueError('Invalid computed score')
    score = min(100., max(0., score))
    return dict(score=score, display_score=display_score(score), concentration=concentration,
                effective_groups=effective, between_fraction=between, equity_weight=equity_weight,
                sector_breadth=breadth, sector_bonus=bonus)


def evaluate_scenarios(weights, sectors_by_group, history, as_of_date):
    """Evaluate the fixed windows using frozen, group-keyed monthly returns."""
    import pandas as pd
    from analytics.allocation_score import monthly_window, pair_correlations, correlation_map
    from analytics.holy_grail import completed_month_end

    dates = pd.to_datetime(history.index).tz_localize(None).normalize()
    if dates.isna().any() or (dates > completed_month_end(as_of_date)).any():
        raise ValueError("Return history extends beyond the completed month")
    # Validate before dropping zero positions, then exclude them from pair requirements.
    score_components_v2(weights, {}, sectors_by_group)
    weights = {group: weight for group, weight in weights.items() if weight > 0}
    sectors_by_group = {group: profile for group, profile in sectors_by_group.items() if group in weights}
    frame = monthly_window(history, as_of_date)
    business = weights.get('car_business', 0) > 0
    scenarios = {}
    for months in (60, 36):
        for assumption in ((.25, .75) if business else (None,)):
            key = f'm{months}' + (f'_r{int(assumption * 100):03d}' if business else '')
            pairs = pair_correlations(frame.iloc[-months:], weights, as_of_date,
                                      business=['car_business'],
                                      business_correlation=assumption if business else .25)
            for pair in pairs:
                if 'unknown' in (pair['left'], pair['right']):
                    pair.update(correlation=None, kind='missing', observations=0,
                                months=[], last_month=None)
            correlations = correlation_map(pairs)
            components = score_components_v2(weights, correlations, sectors_by_group)
            optimistic = dict(correlations)
            optimistic.update({(p['left'], p['right']): 0. for p in pairs if p['correlation'] is None})
            impact = score_components_v2(weights, optimistic, sectors_by_group)['score'] - components['score']
            if impact < -TOLERANCE:
                raise ValueError('Invalid missing-pair bound')
            scenario = dict(window_months=months, business_correlation=assumption,
                            status='modeled', reason=None, pairs=pairs, components=components,
                            score=components['score'], display_score=components['display_score'],
                            category=category(components['score']), missing_pair_max_points=max(0., impact))
            if months == 36 and any(p['kind'] == 'missing' or
                                    (p['kind'] == 'measured' and p['observations'] != 36) for p in pairs):
                scenario.update(status='unavailable', reason='incomplete_window', score=None,
                                display_score=None, category=None)
            elif impact > 5 + TOLERANCE:
                scenario.update(status='unavailable', reason='insufficient_pair_coverage', score=None,
                                display_score=None, category=None)
            elif any(p['kind'] == 'missing' or (p['kind'] == 'measured' and
                     (p['observations'] < months or p['last_month'] != frame.index[-1].date().isoformat())) for p in pairs):
                scenario['status'] = 'provisional'
            scenarios[key] = scenario
    return scenarios
