"""Frozen capital_diversification_v1: score, calibration and the saved-record validator.

Records written by this method are still displayed; nothing new is written with it.
"""
from itertools import combinations
import math

from analytics.holy_grail.allocation_score_v2 import same_value
from analytics.holy_grail.correlation import (correlation_map, history_frame, history_payload,
                                              monthly_window, pair_correlations)
from analytics.holy_grail.evidence import quality_inputs_fingerprint
from analytics.holy_grail.fingerprint import fingerprint

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


def validate_saved_allocation(result, data, expected_date=None, *, replay=True):
    """Integrity plus main/sensitivity replay from frozen, dated inputs."""
    try:
        if not isinstance(result,dict) or result.get('version')!=VERSION:
            return False
        if result.get('result_fingerprint')!=fingerprint({k:v for k,v in result.items() if k!='result_fingerprint'}):
            return False
        if result['holdings_fingerprint']!=quality_inputs_fingerprint(data): return False
        if expected_date and result['as_of_date']!=expected_date: return False
        if result['status']=='unavailable': return True
        if result['configuration_fingerprint']!=fingerprint(result['configuration']): return False
        if not isinstance(result['configuration'].get('group_definitions'),dict): return False
        cal=result['configuration']['calibration']
        if cal.get('fingerprint')!=fingerprint({k:v for k,v in cal.items() if k!='fingerprint'}): return False
        if result['status']=='not_applicable': return result['score'] is None
        if result['history_fingerprint']!=fingerprint(result['histories']): return False
        if not replay: return result['status'] in {'modeled','provisional'}
        if not validate_calibration(cal): return False
        # Group histories were already converted to USD; preserve their exact months.
        weights={g['id']:g['weight'] for g in result['groups']}
        pairs=pair_correlations(history_frame(result['histories']),weights,result['as_of_date'],business=['car_business'])
        for p in pairs:
            if 'unknown' in (p['left'],p['right']):p.update(correlation=None,kind='missing',observations=0,months=[],last_month=None)
        # pair names, month dates and kinds stay exact; recomputed numbers are bounded
        if not same_value(pairs,result['pairs']): return False
        expected=score_components(weights,correlation_map(pairs),result['sectors'],result['configuration']['calibration']['coefficient'])
        if weights.get('car_business',0)>0:
            sensitivity=[dict(p,correlation=cal['sensitivity_correlation']) if p['kind']=='modeled' else p for p in pairs]
            alternate=score_components(weights,correlation_map(sensitivity),result['sectors'],cal['coefficient'])
            if (not math.isclose(result['sensitivity_score'],alternate['score'],rel_tol=0,abs_tol=1e-8)
                    or result['sensitivity_display_score']!=alternate['display_score']): return False
        elif result['sensitivity_score'] is not None or result['sensitivity_display_score'] is not None:
            return False
        return all(math.isclose(result[k],v,rel_tol=0,abs_tol=1e-8) for k,v in expected.items())
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError):
        return False
