"""Capital diversity, independent of volatility and of legacy DR-squared checks."""
from itertools import combinations
import json
import math

import numpy as np
import pandas as pd

from analytics.holy_grail import completed_month_end, fingerprint

VERSION = 'capital_diversification_v1'
MAX_CALIBRATION = (50 - 20.25) / .18


def display_score(score):
    nearest = round(score)
    return math.floor(nearest if abs(score - nearest) <= 1e-8 else score)


def score_components(weights, correlations, sectors, coefficient):
    """Score already aggregated economic weights; absent correlations earn no bonus.

    Sector shares are conditional on each equity market. Unknown sector mass is
    assigned to its largest known sector, never treated as an extra sector.
    """
    if not math.isfinite(coefficient) or not 0 < coefficient < MAX_CALIBRATION:
        raise ValueError('Calibration violates the approved concentration anchor')
    if any(not math.isfinite(v) or v < 0 for v in weights.values()):
        raise ValueError('Invalid economic weights')
    if abs(sum(weights.values()) - 1) > 1e-8:
        raise ValueError('Economic weights must sum to one')
    diversity = 0.0
    for left, right in combinations(sorted(weights), 2):
        rho = correlations.get((left, right), correlations.get((right, left), 1.0))
        if not math.isfinite(rho) or not -1 <= rho <= 1:
            raise ValueError('Invalid correlation')
        diversity += 2 * weights[left] * weights[right] * (1 - max(0, rho))
    breadth = 0.0
    for group, profile in sectors.items():
        values = list(profile.values())
        if len(values)>11 or any(not math.isfinite(v) or v < 0 for v in values) or sum(values) > 1 + 1e-8:
            raise ValueError('Invalid sector profile')
        if values and sum(values) > 0:
            values[values.index(max(values))] += max(0, 1 - sum(values))
            b = max(0, (1 - sum(v*v for v in values)) / (1 - 1/11))
            breadth += weights.get(group, 0)**2 * b
    raw = coefficient * diversity + 25 * breadth
    score = min(100.0, max(0.0, raw))
    return dict(diversity=diversity, breadth=breadth, raw_score=raw,
                score=score, display_score=display_score(score))


def monthly_window(frame, as_of_date):
    frame = frame.copy()
    frame.index = pd.to_datetime(frame.index).tz_localize(None).normalize()
    if frame.index.has_duplicates or not frame.index.is_month_end.all() or frame.columns.has_duplicates:
        raise ValueError('Histories must have unique month ends and series')
    frame = frame.apply(pd.to_numeric, errors='raise')
    if np.isinf(frame.to_numpy(dtype=float)).any():
        raise ValueError('Non-finite return history')
    cutoff = completed_month_end(as_of_date)
    return frame.reindex(pd.date_range(end=cutoff, periods=60, freq='ME'))


def pair_correlations(frame, groups, as_of_date, *, business=(), business_correlation=.25):
    frame = monthly_window(frame, as_of_date)
    pairs = []
    for left, right in combinations(sorted(groups), 2):
        pair = dict(left=left, right=right, correlation=None, observations=0,
                    last_month=None, months=[], kind='missing')
        if (left in business) != (right in business):
            pair.update(correlation=business_correlation, kind='modeled', observations=None)
        elif left in frame and right in frame:
            common = frame[[left, right]].dropna()
            pair.update(observations=len(common), months=[d.date().isoformat() for d in common.index],
                        last_month=common.index[-1].date().isoformat() if len(common) else None)
            if len(common) >= 36 and (common.std() > 0).all():
                rho = float(common.iloc[:, 0].corr(common.iloc[:, 1]))
                if math.isfinite(rho):
                    pair.update(correlation=min(1., max(-1., rho)), kind='measured')
        pairs.append(pair)
    return pairs


def correlation_map(pairs):
    return {(p['left'], p['right']): p['correlation'] for p in pairs if p['correlation'] is not None}


def history_payload(frame):
    return json.loads(frame.to_json(date_format='iso', double_precision=15))


def history_frame(payload):
    frame = pd.DataFrame(payload, dtype=float)
    frame.index = pd.to_datetime(frame.index)
    return frame


def freeze_calibration(frame, reference, sectors, *, profiles, as_of_date='2026-09-30', business=(), provenance=None):
    """Freeze a practical reference once; later quarters reuse its coefficient."""
    if as_of_date != '2026-09-30':
        raise ValueError('Version one calibration date is fixed')
    frame = monthly_window(frame, as_of_date)
    public = set(reference) - set(business)
    if any(g not in frame or frame[g].notna().sum() != 60 for g in public):
        raise ValueError('Calibration requires 60 complete public observations')
    payload = history_payload(frame[sorted(public)])
    # Compute from precisely the serialized observations used for future replay.
    pairs = pair_correlations(history_frame(payload), reference, as_of_date, business=business)
    if any(p['correlation'] is None for p in pairs):
        raise ValueError('Calibration correlation is unavailable')
    components = score_components(reference, correlation_map(pairs), sectors, 1)
    if components['diversity'] <= 0:
        raise ValueError('Degenerate reference')
    coefficient = (100 - 25 * components['breadth']) / components['diversity']
    score = score_components(reference, correlation_map(pairs), sectors, coefficient)
    result = dict(version=VERSION, as_of_date=as_of_date, coefficient=coefficient,
                  reference=reference, sectors=sectors, profiles=profiles, histories=payload,
                  history_provenance=provenance or {},
                  business=list(business), business_correlation=.25, sensitivity_correlation=.75,
                  reference_score=score['score'], reference_components=components)
    result['fingerprint'] = fingerprint(result)
    return result


def validate_calibration(calibration):
    try:
        if calibration['version'] != VERSION or calibration['fingerprint'] != fingerprint(
                {k:v for k,v in calibration.items() if k != 'fingerprint'}):
            return False
        fresh = freeze_calibration(history_frame(calibration['histories']), calibration['reference'],
                                   calibration['sectors'], profiles=calibration['profiles'],
                                   as_of_date=calibration['as_of_date'], business=calibration['business'],
                                   provenance=calibration['history_provenance'])
        return (math.isclose(fresh['coefficient'], calibration['coefficient'], rel_tol=0, abs_tol=1e-10)
                and fresh['business_correlation'] == calibration['business_correlation']
                and fresh['sensitivity_correlation'] == calibration['sensitivity_correlation']
                and math.isclose(calibration['reference_score'], 100, rel_tol=0, abs_tol=1e-8))
    except (ValueError, TypeError, KeyError, AttributeError, ZeroDivisionError, OverflowError):
        return False
