"""Dated economic profiles and frozen inputs for the capital diversity score.

Only this adapter reads private configuration. Renderers validate and display a
saved result against its own frozen inputs, without consulting today's config.
"""
from copy import deepcopy
from datetime import date
import json
import math

from analytics.holy_grail.fingerprint import fingerprint
from analytics.holy_grail.paths import PROFILE_PATH

# profile_for labels category-model profiles with the config's method_version. The fallback is the historical
# v1 label, kept byte-for-byte; allocation_settings always sets method_version, so the pipeline does not reach it.
_FALLBACK_METHOD_LABEL = 'capital_diversification_v1'

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
    config['concentration_round_decimals'] = 1
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
        return dict(as_of_date='2026-09-30', source=config.get('method_version', _FALLBACK_METHOD_LABEL)+': explicit category model',
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


def allocation_history_requests(positions, config, as_of_date, extra_groups=(), extra_symbols=()):
    """Representatives of the held groups, plus `extra_groups` and `extra_symbols` (risk_progress_v3 factors and
    proxy baskets); v2 stores every collected column and scores only its weighted groups."""
    groups = set(extra_groups)
    for position in positions:
        profile = profile_for(position, config, as_of_date)
        if profile:
            groups.update(c['group'] for c in profile['components'])
    symbols = [GROUPS[g][1] for g in sorted(groups) if GROUPS[g][1]]
    symbols += [s for s in sorted(set(extra_symbols)) if s not in symbols]
    return [dict(series='yf:'+s, symbol=s, provider='yfinance', value_usd=0, collection_priority=0) for s in symbols]


def seal_result(result):
    result['result_fingerprint'] = fingerprint({k:v for k,v in result.items() if k != 'result_fingerprint'})
    return result
