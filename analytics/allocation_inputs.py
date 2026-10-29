"""Dated economic profiles and frozen inputs for the capital diversity score.

Only this adapter reads private configuration. Renderers validate and display a
saved result against its own frozen inputs, without consulting today's config.
"""
from copy import deepcopy
from datetime import date
from pathlib import Path
import json
import math

from analytics.allocation_score import (VERSION, correlation_map, history_frame,
    pair_correlations, score_components, validate_calibration)
from analytics.allocation_score_v2 import _same
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
    for key in ('concentration_limits', 'linked_theses', 'concentration_decisions'):
        if key in config and not isinstance(config[key], dict):
            raise ValueError('Invalid ' + key + ' settings')
        config.setdefault(key, {})
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
        if not _same(pairs,result['pairs']): return False
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
