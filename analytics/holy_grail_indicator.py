"""Saved, risk-equivalent indicator independent of the legacy policy score."""
from copy import deepcopy
from datetime import date, timedelta
import math

import numpy as np
import pandas as pd

from analytics.holy_grail import completed_month_end, fingerprint
from analytics.diversification_quality import _sample_risk, COUNT_VERSION
from analytics.diversification_inputs import quality_inputs_fingerprint

VERSION = 'holy_grail_indicator_v1'
ROLES = ('direct', 'model', 'reserve', 'cash', 'uncovered')
MODEL_NOTES = {
    'yf:HYG': 'Кредитний проксі lending/P2P; не моделює конкретні дефолти платформ або depeg.',
    'yf:SHV': 'SHV: модель US Treasuries зі строком до погашення 0-1 рік; total return ETF з виплатами, не історія конкретної облігації. Не замінює довгі Treasury, зокрема TLT.',
    'fred:CUSR0000SETA02': 'Ціни уживаних авто США; не фактична дохідність Car Resale в Україні.',
}


def reconciliation_tolerance(total):
    return max(1., abs(float(total)) * 1e-6)


def reserve_confirmed(record, as_of):
    """A named, dated USD Treasury confirmation cannot persist indefinitely."""
    try:
        confirmed = date.fromisoformat(record['as_of_date'])
        end = date.fromisoformat(record['maturity']) if record.get('maturity') else confirmed + timedelta(days=int(record['max_remaining_days']))
        return (record.get('kind') == 'us_treasury' and record.get('currency') == 'USD'
                and bool(record.get('source', '').strip()) and confirmed <= date.fromisoformat(as_of) <= end
                and 0 <= (end - confirmed).days <= 365)
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def _seal(result):
    result['result_fingerprint'] = fingerprint({k:v for k,v in result.items() if k != 'result_fingerprint'})
    return result


def calculate_indicator(data, positions, cash, returns, settings, as_of_date, flags=(), provenance=None):
    """Use canonical valuations; unknown quality checks never gate this statistic."""
    result = dict(version=VERSION, count_version=COUNT_VERSION, as_of_date=as_of_date,
                  status='unavailable', effective_streams=None, direct_only_effective_streams=None,
                  recent_effective_streams=None, direct_only_recent_effective_streams=None,
                  target_range=[15,20], observation_count=0, modeled_exposure_count=0,
                  return_window_start=None, return_window_end=None, coverage={k:0. for k in ROLES},
                  models=[], top_correlations=[], uncovered=[], warnings=[],
                  holdings_fingerprint=quality_inputs_fingerprint(data))
    try:
        config = deepcopy(settings.get('indicator', {}))
        if not isinstance(config, dict) or not isinstance(config.get('reserves', {}), dict):
            raise ValueError('invalid_inputs')
        config['mappings'] = deepcopy(settings.get('mappings', {}))
        result['configuration'] = config
        result['configuration_fingerprint'] = fingerprint(config)
        result['source_provenance'] = deepcopy(provenance or {})
        result['history_fingerprint'] = fingerprint(returns.to_json(date_format='iso'))
        total = float(data['TOTAL_ASSETS']); cash = float(cash)
        values = [float(e['value_usd']) for e in positions]
        if not math.isfinite(total) or total <= 0 or not math.isfinite(cash) or cash < 0 or any(not math.isfinite(v) or v < 0 for v in values):
            raise ValueError('invalid_valuation')
        if abs(sum(values) + cash - total) > reconciliation_tolerance(total):
            raise ValueError('unreconciled_valuations')
        equivalents = sum(float(v) for v in (data.get('CASH_DATA', {}).get('Cash_Equivalents') or {}).values())
        if not math.isfinite(equivalents) or equivalents < 0 or equivalents > cash + .02:
            raise ValueError('invalid_cash_partition')
        if 'unreconciled_positions' in flags:
            raise ValueError('unreconciled_valuations')
        if 'invalid_valuation' in flags or 'invalid_cash_valuation' in flags:
            raise ValueError('invalid_valuation')
        records = settings.get('diversification', {}).get('exposures', {})
        def unsupported(e):
            r = records.get(e['id'], records.get('category:'+e['category'], {}))
            return e.get('unsupported_risk') or e.get('category') == 'Short Selling' or r.get('leveraged') or r.get('nonlinear_risk')
        if any(unsupported(e) for e in positions):
            raise ValueError('unsupported_risk')
        result['reconciliation_delta_usd'] = total - cash - sum(values)
        result['warnings'].extend(sorted(set(flags) & {'mapping_outside_validity','invalid_mapping_dates'}))
        cutoff = completed_month_end(as_of_date)
        frame = returns.copy()
        frame.index = pd.to_datetime(frame.index).tz_localize(None).normalize()
        if frame.index.has_duplicates or frame.columns.has_duplicates or not frame.index.is_month_end.all():
            raise ValueError('invalid_monthly_history')
        frame = frame.loc[(frame.index <= cutoff) & (frame.index.to_period('M') >= cutoff.to_period('M') - 59)]
        frame = frame.sort_index().apply(pd.to_numeric, errors='coerce').replace([np.inf,-np.inf],np.nan)
        grouped, direct, labels, representatives = {}, {}, {}, []
        coverage = result['coverage']; coverage['cash'] = cash / total * 100
        for e in positions:
            value = float(e['value_usd'])
            if value == 0: continue
            record = config.get('reserves', {}).get(e['id'], {})
            if reserve_confirmed(record, as_of_date):
                coverage['reserve'] += value / total * 100
                continue
            if record:
                result['warnings'].append('reserve_confirmation_expired_or_invalid')
            series = e.get('series')
            usable = series in frame and frame[series].notna().sum() >= 36 and frame[series].dropna().std() > 0
            if not usable:
                coverage['uncovered'] += value / total * 100
                result['uncovered'].append(dict(category=e['category'], share_pct=value / total * 100,
                    reason='missing_or_short_history'))
                continue
            canonical = next((s for s in representatives if frame[s].equals(frame[series])), None)
            if canonical is None:
                canonical = series; representatives.append(series)
            grouped[canonical] = grouped.get(canonical, 0.) + value / total
            if e.get('kind') == 'proxy':
                coverage['model'] += value / total * 100
                note = MODEL_NOTES.get(series, 'Наближена модель; не фактична дохідність позиції.')
                item = next((m for m in result['models'] if m['series']==series), None)
                if item is None:
                    item = dict(series=series, description=note, share_pct=0.)
                    result['models'].append(item)
                item['share_pct'] += value / total * 100
                labels[canonical] = {'yf:HYG':'Кредитний проксі lending/P2P',
                    'yf:SHV':'US Treasuries 0-1 рік (SHV)',
                    'fred:CUSR0000SETA02':'Модель Car Resale'}.get(series, 'Модель активу')
            else:
                coverage['direct'] += value / total * 100
                direct[canonical] = direct.get(canonical, 0.) + value / total
                labels.setdefault(canonical, str(e.get('symbol') or e['category']))
        result['modeled_exposure_count'] = len(grouped)
        if not grouped:
            if coverage['uncovered'] > 1e-9: raise ValueError('insufficient_common_history')
            result['status'] = 'not_applicable'
            return _seal(result)
        aligned = frame[list(grouped)].dropna()
        result['observation_count'] = len(aligned)
        if len(aligned) < 36: raise ValueError('insufficient_common_history')
        stats = _sample_risk(aligned, list(grouped.values()))
        if stats is None: raise ValueError('degenerate_covariance')
        result['effective_streams'] = stats['effective_streams']
        result['return_window_start'] = aligned.index[0].date().isoformat()
        result['return_window_end'] = aligned.index[-1].date().isoformat()
        if direct:
            d = _sample_risk(aligned[list(direct)], list(direct.values()))
            result['direct_only_effective_streams'] = d['effective_streams'] if d else None
        end = aligned.index[-1]
        recent = aligned.loc[aligned.index.to_period('M') >= end.to_period('M') - 35]
        if len(recent) == 36:
            r = _sample_risk(recent, list(grouped.values()))
            result['recent_effective_streams'] = r['effective_streams'] if r else None
            if direct:
                d = _sample_risk(recent[list(direct)], list(direct.values()))
                result['direct_only_recent_effective_streams'] = d['effective_streams'] if d else None
        else: result['warnings'].append('incomplete_recent_window')
        selected = [s for s,w in grouped.items() if w >= .01]
        corr = aligned[selected].corr()
        pairs = [dict(left=labels[a],right=labels[b],correlation=float(corr.loc[a,b]))
                 for i,a in enumerate(selected) for b in selected[i+1:] if corr.loc[a,b] > 0]
        result['top_correlations'] = sorted(pairs,key=lambda p:(-p['correlation'],p['left'],p['right']))[:3]
        if stats['effective_streams'] > len(grouped) + 1e-9: result['warnings'].append('hedge_driven_count')
        if len(aligned) < 60: result['warnings'].append('short_common_history')
        if aligned.index[-1] != cutoff: result['warnings'].append('history_lags_positions')
        if coverage['uncovered'] > 1e-9: result['warnings'].append('uncovered_positions')
        if set(flags) & {'stale_valuations','partial_valuations','valuation_date_mismatch','valuation_date_unverified'}:
            result['warnings'].append('partial_or_cached_valuations')
        result['warnings'] = sorted(set(result['warnings']))
        result['status'] = 'provisional' if result['warnings'] else 'modeled'
    except (ValueError, TypeError, KeyError, OverflowError) as error:
        # Only our own enumerated reason codes may be serialized.
        known = {'invalid_valuation','unreconciled_valuations','invalid_cash_partition','unsupported_risk',
                 'invalid_monthly_history','insufficient_common_history','degenerate_covariance'}
        result['effective_streams'] = None
        result['warnings'] = [str(error) if str(error) in known else 'invalid_inputs']
    return _seal(result)


def validate_saved_indicator(indicator, data, expected_date=None):
    """Historical config is frozen; validation never reads today's private config."""
    if not isinstance(indicator,dict) or indicator.get('version') != VERSION: return False
    if indicator.get('count_version') != COUNT_VERSION: return False
    if indicator.get('result_fingerprint') != fingerprint({k:v for k,v in indicator.items() if k != 'result_fingerprint'}): return False
    if indicator.get('holdings_fingerprint') != quality_inputs_fingerprint(data): return False
    if expected_date and indicator.get('as_of_date') != expected_date: return False
    if indicator.get('configuration_fingerprint') != fingerprint(indicator.get('configuration')): return False
    return indicator.get('status') in {'modeled','provisional','not_applicable','unavailable'}
