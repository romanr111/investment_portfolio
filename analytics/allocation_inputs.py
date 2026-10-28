"""Dated economic profiles and frozen inputs for the capital diversity score.

Only this adapter reads private configuration. Renderers validate and display a
saved result against its own frozen inputs, without consulting today's config.
"""
from copy import deepcopy
from datetime import date
from pathlib import Path
import json
import math

import pandas as pd

from analytics.allocation_score import (VERSION, correlation_map, history_frame,
    history_payload, monthly_window, pair_correlations, score_components, validate_calibration)
from analytics.holy_grail import fingerprint
from analytics.diversification_inputs import quality_inputs_fingerprint

GROUPS = {
    'equity_us': ('Акції США', 'SPY'),
    'equity_developed': ('Акції розвинених ринків поза США', 'EFA'),
    'equity_china': ('Акції Китаю', 'MCHI'),
    'equity_emerging': ('Акції інших emerging markets', 'EMXC'),
    'treasury_short': ('US Treasury 0-1 рік', 'SHV'),
    'treasury_medium': ('US Treasury понад 1-10 років', 'IEF'),
    'treasury_long': ('US Treasury понад 10 років', 'TLT'),
    'credit_ig_usd': ('Investment grade кредит USD', 'LQD'),
    'credit_hy_usd': ('High yield кредит USD / lending', 'HYG'),
    'credit_hy_eur': ('High yield кредит EUR', 'IHYG.L'),
    'gold': ('Золото', 'IAU'), 'silver': ('Срібло', 'SLV'),
    'commodities': ('Товарні активи', 'DBC'), 'crypto': ('Крипторинок', 'BTC-USD'),
    'car_business': ('Car Resale: український бізнес', None),
}
SECTORS = {'Information Technology','Financials','Communication Services','Health Care',
           'Consumer Discretionary','Industrials','Consumer Staples','Energy','Utilities',
           'Real Estate','Materials'}
PROFILE_PATH = Path(__file__).with_name('models') / 'economic_profiles_v1.json'
FATAL_FLAGS = {'invalid_valuation','invalid_cash_valuation','unreconciled_positions',
               'unreconciled_valuations','unsupported_borrowing','invalid_inputs'}
BALANCE_FLAGS = {'partial_valuations','stale_valuations','valuation_date_mismatch','valuation_date_unverified'}


def allocation_settings(settings):
    """Explicit opt-in uses the pinned shipped model; private overrides stay local."""
    config = deepcopy(settings['allocation'])
    if not isinstance(config, dict):
        raise ValueError('Invalid allocation settings')
    method = config.get('method_version', 'capital_diversification_v2')
    if method != 'capital_diversification_v2':
        raise ValueError('Unknown allocation method')
    config['method_version'] = method
    public = json.loads(PROFILE_PATH.read_text()) if PROFILE_PATH.exists() else {}
    config['profiles'] = dict(public, **config.get('profiles', {}))
    return config


def profile_for(position, config, as_of_date):
    """No regional inference from broker bucket or quote currency."""
    identifier = position['id']
    profile = config.get('profiles', {}).get(identifier)
    if profile is None and position['category'] in {'Crypto Lending','P2P Lending','Crypto Coins'}:
        group = 'crypto' if position['category'] == 'Crypto Coins' else 'credit_hy_usd'
        return dict(as_of_date='2026-09-30', source=config.get('method_version', VERSION)+': explicit category model',
                    components=[dict(group=group, share=1)]) if as_of_date >= '2026-09-30' else None
    if profile is None:
        return None
    profile = deepcopy(profile)
    stamp = date.fromisoformat(profile['as_of_date'])
    as_of = date.fromisoformat(as_of_date)
    if stamp > as_of or (profile.get('valid_until') and as_of > date.fromisoformat(profile['valid_until'])):
        return None
    if profile.get('source_identity') is not None and profile['source_identity'] != position.get('source_identity'):
        return None
    if not isinstance(profile.get('source'), str) or not profile['source'].strip():
        raise ValueError('Profile requires dated evidence')
    components = profile['components']
    if not components or any(c['group'] not in GROUPS for c in components):
        raise ValueError('Unknown economic group')
    for component in components:
        share = component['share']
        if isinstance(share, bool) or not math.isfinite(share) or share < 0:
            raise ValueError('Invalid profile weight')
        sectors = component.get('sectors', {})
        if any(k not in SECTORS or isinstance(v,bool) or not math.isfinite(v) or v < 0 for k,v in sectors.items()):
            raise ValueError('Invalid GICS profile')
        if sectors and not component['group'].startswith('equity_'):
            raise ValueError('Only equities have a sector bonus')
        if sum(sectors.values()) > 1+1e-8:
            if not profile.get('complete_sector_profile') or abs(sum(sectors.values())-1) > .001+1e-10:
                raise ValueError('Incomplete/invalid sector normalization')
            component['sectors'] = {k:v/sum(sectors.values()) for k,v in sectors.items()}
    total = sum(c['share'] for c in components)
    if abs(total-1) > 1e-8:
        if not profile.get('complete_profile') or abs(total-1) > .001+1e-10:
            raise ValueError('Missing profile components')
        for c in components:
            c['share'] /= total
    return profile


def allocation_history_requests(positions, config, as_of_date):
    groups = set()
    for position in positions:
        profile = profile_for(position, config, as_of_date)
        if profile:
            groups.update(c['group'] for c in profile['components'])
    return [dict(series='yf:'+GROUPS[g][1], symbol=GROUPS[g][1], provider='yfinance',
                 value_usd=0, collection_priority=0) for g in sorted(groups) if GROUPS[g][1]]


def _seal(result):
    result['result_fingerprint'] = fingerprint({k:v for k,v in result.items() if k != 'result_fingerprint'})
    return result


def calculate_allocation_score(data, positions, cash, returns, config, as_of_date, flags=(), provenance=None):
    """One persisted calculation with complete private replay inputs."""
    result = dict(version=VERSION, scope='invested_assets', as_of_date=as_of_date,
                  status='unavailable', score=None, raw_score=None, display_score=None,
                  sensitivity_score=None, sensitivity_display_score=None, warnings=[],
                  groups=[], pairs=[], sectors={}, profiles=[], coverage={},
                  holdings_fingerprint=quality_inputs_fingerprint(data))
    try:
        config = deepcopy(config)
        if not validate_calibration(config['calibration']):
            raise ValueError('invalid_calibration')
        config['group_definitions'] = {g:dict(label=label,representative=symbol)
                                       for g,(label,symbol) in GROUPS.items()}
        result.update(configuration=config, configuration_fingerprint=fingerprint(config),
                      calibration_fingerprint=config['calibration']['fingerprint'],
                      source_provenance=deepcopy(provenance or {}))
        total = float(data['TOTAL_ASSETS']); cash = float(cash)
        flags = set(flags)
        breakdown = data.get('CASH_DATA',{}).get('Breakdown',{}) or {}
        excluded_cash_keys = {'debt','manual_reconciliation'}
        investment_cash = [v for k,v in breakdown.items() if k not in excluded_cash_keys]
        investment_cash.append(data.get('IB_DATA',{}).get('Net_cash',0))
        has_margin = any(float(v)<0 for v in investment_cash)
        excluded_liability = any(float(v)<0 for k,v in breakdown.items() if k in excluded_cash_keys)
        if has_margin:
            flags.add('unsupported_borrowing')
        elif excluded_liability:
            # These typed ledger rows belong to the Cash scope explicitly
            # excluded by this score. Preserve the stricter legacy diagnostics.
            flags.discard('unsupported_borrowing')
            flags.add('cash_liabilities_outside_scope')
        values = [float(p['value_usd']) for p in positions]
        if (not math.isfinite(total) or total <= 0 or not math.isfinite(cash) or cash < 0
                or any(not math.isfinite(v) or v < 0 for v in values)):
            raise ValueError('invalid_valuation')
        if abs(sum(values)+cash-total) > max(1., total*1e-6):
            raise ValueError('unreconciled_valuations')
        if set(flags) & FATAL_FLAGS:
            raise ValueError(sorted(set(flags)&FATAL_FLAGS)[0])
        risk_records = config.get('unsupported_ids', [])
        quantities = [r.get('quantity') for r in data.get('POSITION_DATA',{}).get('crypto',[])]
        for rows in data.get('ENHANCED_STOCKS',{}).values():
            if isinstance(rows,dict):
                quantities.extend(r.get('quantity') for r in rows.values() if isinstance(r,dict))
        if any(float(v)<0 for v in quantities if v is not None):
            raise ValueError('unsupported_risk')
        if any(p.get('unsupported_risk') or p['category']=='Short Selling' or p['id'] in risk_records for p in positions):
            raise ValueError('unsupported_risk')
        invested = sum(values)
        result['coverage'] = dict(cash_pct_nav=cash/total*100, invested_pct_nav=invested/total*100,
                                  unknown_pct_invested=0., missing_pair_max_points=0.)
        frozen_frame = monthly_window(returns, as_of_date)
        if invested == 0:
            result.update(status='not_applicable')
            return _seal(result)
        amounts, sector_amounts = {}, {}
        unknown, model_value = 0., 0.
        for position, value in zip(positions, values):
            if value == 0:
                continue
            profile = profile_for(position, config, as_of_date)
            if profile is None:
                unknown += value
                amounts['unknown'] = amounts.get('unknown',0.)+value
                continue
            result['profiles'].append(dict(position_id=position['id'], definition=profile))
            model_value += value if position.get('kind')=='proxy' or any(c['group']=='car_business' for c in profile['components']) else 0.
            for c in profile['components']:
                g=c['group'];amount=value*c['share']
                amounts[g]=amounts.get(g,0.)+amount
                if g.startswith('equity_'):
                    counts=sector_amounts.setdefault(g,{})
                    for k,s in c.get('sectors',{}).items(): counts[k]=counts.get(k,0.)+amount*s
            if 'ai' in profile.get('themes',[]):
                result['warnings'].append('confirmed_ai_theme')
        weights={g:v/invested for g,v in amounts.items() if v > 0}
        sectors={g:{k:v/amounts[g] for k,v in rows.items()} for g,rows in sector_amounts.items()}
        group_frame=pd.DataFrame(index=frozen_frame.index)
        for g in weights:
            series='yf:'+GROUPS[g][1] if g in GROUPS and GROUPS[g][1] else None
            if series in frozen_frame: group_frame[g]=frozen_frame[series]
        group_frame=history_frame(history_payload(group_frame))
        pairs=pair_correlations(group_frame,weights,as_of_date,business=['car_business'])
        # Unknown profiles cannot receive the business-model independence bonus.
        for p in pairs:
            if 'unknown' in (p['left'],p['right']): p.update(correlation=None,kind='missing',observations=0,months=[],last_month=None)
        coefficient=config['calibration']['coefficient']
        uncertainty=2*coefficient*sum(weights[p['left']]*weights[p['right']] for p in pairs if p['correlation'] is None)
        result['coverage'].update(unknown_pct_invested=unknown/invested*100, missing_pair_max_points=uncertainty,
                                  modeled_pct_invested=model_value/invested*100)
        result.update(groups=[dict(id=g,weight=weights[g]) for g in sorted(weights)],sectors=sectors,pairs=pairs,
                      histories=history_payload(group_frame),history_fingerprint=fingerprint(history_payload(group_frame)),
                      positions=deepcopy(positions),cash_value=cash,input_flags=sorted(flags),
                      window_start=frozen_frame.index[0].date().isoformat(),window_end=frozen_frame.index[-1].date().isoformat())
        if unknown/invested > .05+1e-12 or uncertainty > 5+1e-10:
            raise ValueError('insufficient_coverage')
        components=score_components(weights,correlation_map(pairs),sectors,coefficient)
        sensitivity=[dict(p,correlation=.75) if p['kind']=='modeled' else p for p in pairs]
        business=weights.get('car_business',0)>0
        result.update(components)
        if business:
            alternate=score_components(weights,correlation_map(sensitivity),sectors,coefficient)
            result.update(sensitivity_score=alternate['score'],sensitivity_display_score=alternate['display_score'])
        warnings=result['warnings']
        if unknown: warnings.append('unknown_profiles')
        if uncertainty: warnings.append('unknown_correlations')
        if set(flags)&BALANCE_FLAGS: warnings.append('partial_or_cached_valuations')
        if 'cash_liabilities_outside_scope' in flags: warnings.append('cash_liabilities_outside_scope')
        if any(p['kind']=='measured' and (p['observations']<60 or p['last_month']!=result['window_end']) for p in pairs):
            warnings.append('partial_pair_history')
        if any(sum(s.values()) < 1-1e-8 for s in sectors.values()): warnings.append('unknown_sectors')
        result.update(status='provisional' if warnings else 'modeled',warnings=sorted(set(warnings)))
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError) as error:
        code=str(error) if str(error) in (FATAL_FLAGS|{'invalid_calibration','unsupported_risk','insufficient_coverage'}) else 'invalid_inputs'
        result.update(status='unavailable',score=None,raw_score=None,display_score=None,
                      sensitivity_score=None,sensitivity_display_score=None,warnings=[code])
    return _seal(result)


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
        if pairs!=result['pairs']: return False
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
