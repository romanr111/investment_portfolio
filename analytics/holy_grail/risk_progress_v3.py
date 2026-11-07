"""Risk progress v3: the Holy Grail headline for an individual long-only investor (100 = 7 independent streams).

A sibling record derived offline from a saved, replayed capital_diversification_v2 record, like risk_progress_v2
(`analytics.holy_grail.risk_progress`). It adds what an individual investor can hold outside the broker:

- declared private streams (real estate, land, Ukrainian deposits and government bonds, P2P loans), modeled from
  public literature parameters with their country and location;
- listed proxy baskets (infrastructure, private equity, private credit funds, timberland), measured like the car
  business basket.

The declarations live in the private config (`private_streams`) and are frozen inside the v2 record's configuration.
The parameters live in the public model file `analytics/models/private_streams_v1.json`; the fingerprint of its
behaviour-bearing values is part of the method and the parameters used are embedded in the record.

Streams
  measured : a v2 group representative history (after reclassification), the car basket, a proxy basket.
  modeled  : r = beta'F + sigma_res*(sqrt(s_c) g_country + sqrt(s_k) h_class_country + sqrt(s_l) k_location)
             F = the equity_us, treasury_medium and commodities representatives, plus EUR/USD for rows that declare
             corr_fx_eur. There is no idiosyncratic term: one (class, country, location) is one stream, so splitting
             a holding never adds a stream. Rows of countries in `no_country_factor` (US, other) have no country
             factor; without a location the location share folds into the class share.
  UA link  : g_UA = rho*e/sigma_e + sqrt(1-rho^2) u_UA, e = the value-weighted residual of the measured Ukrainian
             streams (the reviewed car business, Ukrainian proxy holdings) against the other measured columns.
Covariance : Sigma = A blockdiag(Sigma_shrunk(measured), I) A' (positive semidefinite by construction).
Score      : DR = sum(w sigma)/sqrt(w' Sigma w); points = 100*(1-1/DR)/(1-1/sqrt(7)) clipped; 100 only at 7 streams.

The central parameters give the headline. Favorable and adverse vary only the dependence parameters (correlations,
residual shares, rho); a separate x0.5/x2 total modeled volatility sensitivity is reported. Neither is a confidence
interval. Balances, totals and the v2 record are never changed; a failure is an explicit unavailable record and
never falls back to another method.
"""
import copy
from datetime import date, datetime, timezone
import json
import math
from pathlib import Path
import re

import numpy as np
import pandas as pd

from analytics.holy_grail import risk_progress as rp
from analytics.holy_grail.allocation_inputs import GROUPS, seal_result
from analytics.holy_grail.allocation_v2_inputs import build_group_history, validate_saved_allocation_v2
from analytics.holy_grail.correlation import history_frame, monthly_window
from analytics.holy_grail.exposures import is_positional
from analytics.holy_grail.fingerprint import completed_month_end, fingerprint
from analytics.holy_grail.paths import PRIVATE_MODEL_PATH

VERSION_V3 = 'risk_progress_v3'
MODEL_VERSION = 'private_streams_v1'
TARGET_V3 = 7
TARGET_BENEFIT_V3 = 1 - 1 / math.sqrt(TARGET_V3)
TRIPLET = ('low', 'central', 'high')
SCENARIOS = {'favorable': 'low', 'central': 'central', 'adverse': 'high'}
FACTORS = ('equity', 'bonds', 'commodity', 'fx_eur')
CORRELATION_KEYS = {'equity': 'corr_equity', 'bonds': 'corr_bonds', 'commodity': 'corr_commodity',
                    'fx_eur': 'corr_fx_eur'}
SHARE_KEYS = ('s_c', 's_k', 's_l')
VOLATILITY_MULTIPLIERS = [0.5, 2.0]
R2_CAP = 0.95
STALE_DAYS = 365
OTHER = 'other'
PROXY_PREFIX = 'proxy:'
PRIVATE_PREFIX = 'private:'
FX_COLUMN = 'fx_eur'
DOCUMENTATION_KEYS = ('basis', 'sources', 'access_non_accredited', 'notes')
MODEL_ROW_KEYS = frozenset({'vol_annual', 'share_scenarios', 'cash_eligible'}
                           | set(CORRELATION_KEYS.values()) | set(DOCUMENTATION_KEYS))
ENTRY_REQUIRED = frozenset({'id', 'class', 'country', 'value_usd', 'valuation_as_of'})
ENTRY_OPTIONAL = frozenset({'location', 'currency', 'debt_usd', 'nav_source', 'held_from', 'valuation_source',
                            'reviewed_at', 'primary_residence'})
RECLASSIFY_KEYS = frozenset({'class', 'country', 'location', 'source_identity'})
IGNORED_V3 = {'calculated_at', 'result_fingerprint'}
_COUNTRY = re.compile(r'[A-Z]{2}')


class _Unavailable(Exception):
    """A declaration or input that cannot be scored; the message is the record's reason."""


# ---------------------------------------------------------------------------------------------------- model file
def _number(value, low=-math.inf, high=math.inf):
    return (not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
            and low <= value <= high)


def _check_triplet(value, low, high):
    if (not isinstance(value, dict) or set(value) != set(TRIPLET) or not all(_number(value[k], low, high) for k in TRIPLET)
            or not value['low'] <= value['central'] <= value['high']):
        raise ValueError('invalid_triplet')


def country_code(value):
    """Upper-case ISO alpha-2 code, or 'other'; None when the value is neither."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.lower() == OTHER:
        return OTHER
    return text.upper() if _COUNTRY.fullmatch(text.upper()) else None


def load_model(path=PRIVATE_MODEL_PATH):
    """The public parameter file, validated; raises ValueError (or OSError) when it cannot be used."""
    model = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(model, dict) or model.get('version') != MODEL_VERSION:
        raise ValueError('model_version')
    factors = model.get('factors')
    if not isinstance(factors, dict) or set(factors) != set(FACTORS):
        raise ValueError('model_factors')
    for name in FACTORS[:3]:
        group = factors[name].get('group') if isinstance(factors[name], dict) else None
        if group not in GROUPS or not GROUPS[group][1]:
            raise ValueError('model_factors')
    if not isinstance(factors['fx_eur'], dict) or not isinstance(factors['fx_eur'].get('symbol'), str):
        raise ValueError('model_factors')
    no_country = model.get('no_country_factor')
    if not isinstance(no_country, list) or any(country_code(c) != c for c in no_country):
        raise ValueError('model_no_country_factor')
    _check_triplet(model.get('car_link_rho'), 0., .99)
    proxies, rows = model.get('proxies'), model.get('rows')
    if not isinstance(proxies, dict) or not isinstance(rows, dict) or not rows:
        raise ValueError('model_tables')
    for name, proxy in proxies.items():
        symbols = proxy.get('symbols') if isinstance(proxy, dict) else None
        if (not isinstance(name, str) or ':' in name or not isinstance(symbols, list) or not symbols
                or len(set(symbols)) != len(symbols) or not all(isinstance(s, str) and s for s in symbols)):
            raise ValueError('model_proxies')
    for key, row in rows.items():
        cls, _, country = key.partition(':')
        if not cls or cls in proxies or country_code(country) != country or not isinstance(row, dict):
            raise ValueError('model_rows')
        if set(row) - MODEL_ROW_KEYS:
            raise ValueError('model_rows')
        _check_triplet(row.get('vol_annual'), 1e-6, 3.)
        for factor in FACTORS:
            if factor != 'fx_eur' or 'corr_fx_eur' in row:
                _check_triplet(row.get(CORRELATION_KEYS[factor]), -1., 1.)
        scenarios = row.get('share_scenarios')
        if not isinstance(scenarios, dict) or set(scenarios) != set(TRIPLET):
            raise ValueError('model_shares')
        for triple in scenarios.values():
            if (not isinstance(triple, dict) or set(triple) != set(SHARE_KEYS)
                    or not all(_number(triple[k], 0., 1.) for k in SHARE_KEYS)
                    or abs(sum(triple.values()) - 1) > 1e-6):
                raise ValueError('model_shares')
        if not isinstance(row.get('cash_eligible', False), bool):
            raise ValueError('model_rows')
    return model


def _model_parameters(model):
    """The behaviour-bearing parameters only; prose, sources and labels never enter the method fingerprint."""
    return dict(
        version=model['version'], factors=copy.deepcopy(model['factors']),
        no_country_factor=list(model['no_country_factor']), car_link_rho=copy.deepcopy(model['car_link_rho']),
        proxies={name: dict(symbols=list(proxy['symbols'])) for name, proxy in sorted(model['proxies'].items())},
        rows={key: {field: copy.deepcopy(value) for field, value in sorted(row.items())
                    if field not in DOCUMENTATION_KEYS}
              for key, row in sorted(model['rows'].items())})


def method_v3(model):
    """The method definition; the model enters through its version and parameter fingerprint."""
    return {
        'version': VERSION_V3, 'scope': 'invested_assets_plus_declared_private_streams',
        'cash': 'excluded_except_declared_cash_eligible_deposits',
        'formula': rp.METHOD_V2['formula'], 'scale': rp.METHOD_V2['scale'], 'target_streams': TARGET_V3,
        'estimator': rp.METHOD_V2['estimator'], 'shrinkage': copy.deepcopy(rp.METHOD_V2['shrinkage']),
        'shrinkage_block': 'measured_streams_v2_groups_proxies_and_factors_jointly',
        'streams': {'measured': 'v2_group_representative_after_reclassification',
                    'proxy': 'equal_weight_basket_all_names_required',
                    'modeled': 'r=beta*F+sigma_res*(sqrt(s_c)*g_country+sqrt(s_k)*h_class_country+sqrt(s_l)*k_location)',
                    'identity': 'class_country_location',
                    'location': 'whitespace_collapsed_casefold_diversified_dash_or_empty_is_none'},
        'loadings': 'beta=Sigma_F^-1*(sigma_F*rho*vol_central*multiplier); rho_scaled_to_r2_cap; residual=vol^2-beta*Sigma_F*beta',
        'ua_link': 'g_UA=rho*e/sigma_e+sqrt(1-rho^2)*u_UA; e=value_weighted_residual_of_measured_ua_streams_vs_other_measured',
        'scenarios': {'headline': 'central', 'favorable': 'low', 'adverse': 'high',
                      'varies': ['correlations', 'residual_shares', 'car_link_rho'],
                      'volatility_multipliers': list(VOLATILITY_MULTIPLIERS),
                      'unreviewed_business_geography': 'ukraine_in_adverse_only'},
        'weights': 'capital_over_invested_plus_declared_private',
        'private_rules': {'leverage': 'unavailable', 'primary_residence': 'excluded',
                          'held_from_after_snapshot': 'excluded', 'valuation_stale_days': STALE_DAYS,
                          'cash_nav_source': 'cash_eligible_rows_only_capped_by_v2_cash',
                          'reclassify_positional': 'source_identity_required'},
        'private_gain': 'sequential_v2_groups_then_modeled_then_proxy_primary_window_central',
        'windows': list(rp.WINDOWS), 'primary_window': rp.PRIMARY,
        'minimum_observations': rp.METHOD_V2['minimum_observations'], 'max_lag_months': rp.MAX_LAG,
        'car_business': copy.deepcopy(rp.METHOD_V2['car_business']),
        'risk_share': rp.METHOD_V2['risk_share'], 'annual_volatility': rp.METHOD_V2['annual_volatility'],
        'display': copy.deepcopy(rp.METHOD_V2['display']),
        'tolerances': dict(rp.METHOD_V2['tolerances'], correlation_r2_cap=R2_CAP),
        'model': {'path': 'analytics/models/private_streams_v1.json',
                  'version': model.get('version') if isinstance(model, dict) else None,
                  'parameters_fingerprint': (fingerprint(_model_parameters(model))
                                             if isinstance(model, dict) else None)},
    }


try:
    MODEL, MODEL_ERROR = load_model(), None
except (OSError, ValueError, TypeError, KeyError, AttributeError) as _error:
    MODEL, MODEL_ERROR = None, type(_error).__name__
METHOD_V3 = method_v3(MODEL)
_DEFAULT = object()


def _model_used(model, row_keys, proxy_classes):
    """The parameters a record used (documentation fields left in the public file)."""
    return dict(version=model['version'], factors=copy.deepcopy(model['factors']),
                no_country_factor=list(model['no_country_factor']), car_link_rho=dict(model['car_link_rho']),
                proxies={c: dict(symbols=list(model['proxies'][c]['symbols'])) for c in sorted(proxy_classes)},
                rows={k: {f: copy.deepcopy(v) for f, v in model['rows'][k].items() if f not in DOCUMENTATION_KEYS}
                      for k in sorted(row_keys)})


def history_needs(settings, model=_DEFAULT):
    """(extra groups, extra symbols) the declared private streams need collected; empty when none are declared.

    Never raises: a malformed declaration collects nothing extra and is rejected later by the record itself.
    """
    model = MODEL if model is _DEFAULT else model
    try:
        declared = settings.get('private_streams') if isinstance(settings, dict) else None
        if not isinstance(model, dict) or not isinstance(declared, dict):
            return (), ()
        specs = [e for e in declared.get('entries') or [] if isinstance(e, dict)]
        specs += [r for r in (declared.get('reclassify') or {}).values() if isinstance(r, dict)]
        classes = {(s.get('class'), country_code(s.get('country'))) for s in specs}
        rows = [model['rows'][f'{c}:{k}'] for c, k in classes if f'{c}:{k}' in model['rows']]
        groups = tuple(model['factors'][f]['group'] for f in FACTORS[:3]) if rows else ()
        symbols = {model['factors']['fx_eur']['symbol']} if any('corr_fx_eur' in r for r in rows) else set()
        symbols.update(s for c, _ in classes if c in model['proxies'] for s in model['proxies'][c]['symbols'])
        return groups, tuple(sorted(symbols))
    except (TypeError, KeyError, AttributeError):
        return (), ()


# ---------------------------------------------------------------------------------------------- private inputs
def _iso(value, reason, required=True):
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise _Unavailable(reason)
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise _Unavailable(reason) from None


def _location(value, reason):
    if value is None:
        return None
    if not isinstance(value, str):
        raise _Unavailable(reason)
    text = ' '.join(value.split()).casefold()
    return None if text in ('', 'diversified', '-') else text


def _kind(model, cls, country, reason):
    if not isinstance(cls, str) or not cls or country is None:
        raise _Unavailable(reason)
    if f'{cls}:{country}' in model['rows']:
        return 'modeled'
    if cls in model['proxies']:
        return 'proxy'
    raise _Unavailable('class_not_in_model')


def _private(v2, model):
    """Declared entries and reclassified positions: (items, excluded counts, flags, cash_total). Raises _Unavailable."""
    settings = v2['configuration'].get('extraction_settings')
    declared = settings.get('private_streams') if isinstance(settings, dict) else None
    excluded = dict(primary_residence=0, not_yet_held=0, zero_value=0)
    if declared is None:
        return [], excluded, set(), 0.
    bad = 'invalid_private_streams'
    if not isinstance(declared, dict) or not set(declared) <= {'entries', 'reclassify'}:
        raise _Unavailable(bad)
    entries, reclassify = declared.get('entries', []), declared.get('reclassify', {})
    if not isinstance(entries, list) or not isinstance(reclassify, dict):
        raise _Unavailable(bad)
    as_of = date.fromisoformat(v2['as_of_date'])
    items, flags, seen, cash_total = [], set(), set(), 0.
    for entry in entries:
        if not isinstance(entry, dict) or not ENTRY_REQUIRED <= set(entry) <= ENTRY_REQUIRED | ENTRY_OPTIONAL:
            raise _Unavailable(bad)
        ident, value, debt = entry['id'], entry['value_usd'], entry.get('debt_usd', 0)
        nav, residence = entry.get('nav_source', 'outside'), entry.get('primary_residence', False)
        if (not isinstance(ident, str) or not ident.strip() or ident in seen or not _number(value, 0.)
                or not _number(debt, 0.) or nav not in ('outside', 'cash') or not isinstance(residence, bool)
                or any(k in entry and not isinstance(entry[k], str) for k in ('currency', 'valuation_source'))):
            raise _Unavailable(bad)
        seen.add(ident)
        valued, held = _iso(entry['valuation_as_of'], bad), _iso(entry.get('held_from'), bad, False)
        _iso(entry.get('reviewed_at'), bad, False)
        country = country_code(entry['country'])
        kind = _kind(model, entry['class'], country, bad)
        location = _location(entry.get('location'), bad)
        if residence:
            excluded['primary_residence'] += 1
            continue
        if debt > 0:
            raise _Unavailable('unsupported_leverage')
        if held is not None and held > as_of:
            excluded['not_yet_held'] += 1
            continue
        if value == 0:
            excluded['zero_value'] += 1
            continue
        if nav == 'cash':
            if kind != 'modeled' or not model['rows'][f"{entry['class']}:{country}"].get('cash_eligible', False):
                raise _Unavailable(bad)
            cash_total += float(value)
        if (as_of - valued).days > STALE_DAYS:
            flags.add('stale_private_valuation')
        if valued > as_of:
            flags.add('private_valuation_after_snapshot')
        items.append(dict(source='entry', cls=entry['class'], country=country, location=location, kind=kind,
                          amount=float(value), components=[]))
    cash = float(v2['cash_value'])
    if cash_total > cash + max(1., cash * 1e-6):
        raise _Unavailable('cash_entries_exceed_cash')
    positions = {p['id']: p for p in v2['positions']}
    profiles = {p['position_id']: p['definition'] for p in v2.get('profiles') or []}
    for pid, spec in sorted(reclassify.items()):
        wrong = 'invalid_reclassify'
        if not isinstance(spec, dict) or not {'class', 'country'} <= set(spec) <= RECLASSIFY_KEYS:
            raise _Unavailable(wrong)
        position = positions.get(pid)
        identity = spec.get('source_identity')
        # The same binding rule as exposure evidence: an index-keyed id must name the holding's (non-empty) identity.
        if position is None or (identity is not None and identity != position.get('source_identity')) or (
                is_positional(pid) and not identity):
            raise _Unavailable(wrong)
        country = country_code(spec['country'])
        kind = _kind(model, spec['class'], country, wrong)
        location = _location(spec.get('location'), wrong)
        value = float(position['value_usd'])
        if value <= 0:
            excluded['zero_value'] += 1
            continue
        profile = profiles.get(pid)
        components = ([(c['group'], value * float(c['share'])) for c in profile['components']] if profile
                      else [('unknown', value)])
        items.append(dict(source='reclassify', cls=spec['class'], country=country, location=location, kind=kind,
                          amount=value, components=components))
    return items, excluded, flags, cash_total


def _stream_id(item):
    if item['kind'] == 'proxy':
        return PROXY_PREFIX + item['cls']
    return f"{PRIVATE_PREFIX}{item['cls']}:{item['country']}:{item['location'] or '-'}"


def _universe(v2, items, kinds):
    """Capital per stream (USD) for the included private kinds; positions reclassified to a left-out kind stay put."""
    invested = sum(float(p['value_usd']) for p in v2['positions'])
    amounts = {g['id']: float(g['weight']) * invested for g in v2['groups'] if g['weight'] > 0}
    for item in items:
        if item['kind'] not in kinds:
            continue
        for group, amount in item['components']:
            amounts[group] = amounts.get(group, 0.) - amount
        key = _stream_id(item)
        amounts[key] = amounts.get(key, 0.) + item['amount']
    tolerance = max(1., invested) * 1e-9
    if any(a < -tolerance for a in amounts.values()):
        raise _Unavailable('invalid_reclassify')
    return {k: a for k, a in amounts.items() if a > tolerance}


def _car_ukraine(v2, invested_pct_nav):
    """(reviewed, unreviewed) shares of the car business located in Ukraine, from the v2 risk facts."""
    car = next((float(g['weight']) for g in v2['groups'] if g['id'] == rp.CAR_ID), 0.) * invested_pct_nav
    if car <= 0:
        return 0., 0.
    facts = {f.get('id'): float(f.get('affected_pct_nav') or 0.) for f in v2.get('risk_facts') or []}
    unknown = float((v2.get('risk_unknown') or {}).get('business_geography_pct_nav') or 0.)
    reviewed = min(1., facts.get('business_ukraine', 0.) / car)
    return reviewed, min(1. - reviewed, unknown / car)


def _state(amounts, items, car_ua, model):
    """Streams (sorted ids) with capital weights and the measured Ukrainian weights per scenario."""
    total = sum(amounts.values())
    meta = {_stream_id(i): i for i in items if i['kind'] == 'modeled'}
    streams = []
    for key in sorted(amounts):
        w = amounts[key] / total
        if key.startswith(PRIVATE_PREFIX):
            item = meta[key]
            streams.append(dict(id=key, kind='modeled', cls=item['cls'], country=item['country'],
                                location=item['location'], row=f"{item['cls']}:{item['country']}", w=w))
        else:
            streams.append(dict(id=key, kind='proxy' if key.startswith(PROXY_PREFIX) else 'measured', col=key, w=w))
    ua = {}
    for item in items:
        key = _stream_id(item)
        if item['kind'] == 'proxy' and item['country'] == 'UA' and key in amounts:
            ua[key] = ua.get(key, 0.) + item['amount'] / total
    ua_adverse = dict(ua)
    if rp.CAR_ID in amounts:
        car_w = amounts[rp.CAR_ID] / total
        if car_ua[0] > 0:
            ua[rp.CAR_ID] = car_w * car_ua[0]
        if sum(car_ua) > 0:
            ua_adverse[rp.CAR_ID] = car_w * sum(car_ua)
    return dict(streams=streams, ua={'default': ua, 'adverse': ua_adverse})


# -------------------------------------------------------------------------------------------------- covariance
def _shares(row, key, has_country, has_location):
    triple = row['share_scenarios'][key]
    s_c, s_k, s_l = (float(triple[k]) for k in SHARE_KEYS)
    if not has_country:
        s_c, s_k = 0., s_k + s_c
    if not has_location:
        s_k, s_l = s_k + s_l, 0.
    return s_c, s_k, s_l


def _loadings(row, key, sig_f, factor_names, multiplier):
    """Factor betas (one per factor column) and the residual monthly volatility of a modeled row."""
    use = [j for j, f in enumerate(factor_names) if f != 'fx_eur' or 'corr_fx_eur' in row]
    sf = sig_f[np.ix_(use, use)]
    scale = np.sqrt(np.diag(sf))
    correlation = sf / np.outer(scale, scale)
    vol = float(row['vol_annual']['central']) * multiplier / math.sqrt(12)
    rho = np.array([float(row[CORRELATION_KEYS[factor_names[j]]][key]) for j in use])
    explained = float(rho @ np.linalg.solve(correlation, rho))
    if explained > R2_CAP:
        rho = rho * math.sqrt(R2_CAP / explained)
    beta_used = np.linalg.solve(sf, scale * rho * vol)
    residual = vol ** 2 - float(beta_used @ sf @ beta_used)
    beta = np.zeros(len(factor_names))
    beta[use] = beta_used
    return beta, math.sqrt(max(residual, 0.))


def _stream_covariance(cov_m, ctx, state, scenario, multiplier):
    """Sigma over the state's streams from the shrunk measured block, and each modeled stream's loadings."""
    key = SCENARIOS[scenario]
    model, mcols, fcols, names = ctx['model'], ctx['mcols'], ctx['fcols'], ctx['factor_names']
    index = {c: i for i, c in enumerate(mcols)}
    fidx = [index[c] for c in fcols]
    sig_f = cov_m[np.ix_(fidx, fidx)]
    no_country = set(model['no_country_factor'])
    streams = state['streams']
    latent = []
    for s in streams:
        if s['kind'] != 'modeled':
            continue
        if s['country'] not in no_country:
            latent.append(('u', s['country']))
        latent.append(('h', s['cls'], s['country']))
        if s['location']:
            latent.append(('k', s['country'], s['location']))
    latent = list(dict.fromkeys(latent))
    position = {name: len(mcols) + i for i, name in enumerate(latent)}
    nz = len(mcols) + len(latent)
    sig_z = np.zeros((nz, nz))
    sig_z[:len(mcols), :len(mcols)] = cov_m
    sig_z[len(mcols):, len(mcols):] = np.eye(len(latent))
    country_rows = {}
    for name in latent:
        if name[0] != 'u':
            continue
        row = np.zeros(nz)
        row[position[name]] = 1.
        ua = state['ua']['adverse' if scenario == 'adverse' else 'default']
        rho = float(model['car_link_rho'][key]) if name[1] == 'UA' and ua else 0.
        if rho > 0:
            c = np.zeros(len(mcols))
            for col, weight in ua.items():
                c[index[col]] += weight
            c /= c.sum()
            ua_idx = {index[col] for col in ua}
            others = [i for i in range(len(mcols)) if i not in ua_idx]
            e = c.copy()
            if others:
                e[others] -= np.linalg.solve(cov_m[np.ix_(others, others)], cov_m[others, :] @ c)
            spread = float(e @ cov_m @ e)
            if spread > 0:
                row[:len(mcols)] = rho * e / math.sqrt(spread)
                row[position[name]] = math.sqrt(1 - rho ** 2)
        country_rows[name[1]] = row
    a = np.zeros((len(streams), nz))
    loadings = {}
    for i, s in enumerate(streams):
        if s['kind'] != 'modeled':
            a[i, index[s['col']]] = 1.
            continue
        row = model['rows'][s['row']]
        beta, residual = _loadings(row, key, sig_f, names, multiplier)
        a[i, fidx] += beta
        has_country = s['country'] not in no_country
        s_c, s_k, s_l = _shares(row, key, has_country, bool(s['location']))
        if has_country:
            a[i] += residual * math.sqrt(s_c) * country_rows[s['country']]
        a[i, position[('h', s['cls'], s['country'])]] += residual * math.sqrt(s_k)
        if s['location']:
            a[i, position[('k', s['country'], s['location'])]] += residual * math.sqrt(s_l)
        loadings[s['id']] = dict(beta={n: float(b) for n, b in zip(names, beta)},
                                 residual_annual=float(residual * math.sqrt(12)),
                                 shares=dict(country=s_c, class_country=s_k, location=s_l))
    sigma = a @ sig_z @ a.T
    return (sigma + sigma.T) / 2, loadings


def _stats(cov_m, ctx, state, scenario='central', multiplier=1.):
    sigma, loadings = _stream_covariance(cov_m, ctx, state, scenario, multiplier)
    w = np.array([s['w'] for s in state['streams']], dtype=float)
    stats = rp.dr_stats(sigma, w, [s['id'] for s in state['streams']], TARGET_BENEFIT_V3)
    return stats if isinstance(stats, str) else dict(stats, loadings=loadings)


def _item(stats, status):
    if isinstance(stats, str):
        return dict(status='unavailable', reason=stats, effective_streams=None, progress_points=None,
                    progress_display=None)
    return dict(status=status, reason=None, effective_streams=stats['streams'], progress_points=stats['points'],
                progress_display=rp.display_points(stats['points'], stats['streams'], TARGET_V3))


def _empty_window(months, count, reason=None):
    return dict(months=months, status='unavailable', reason=reason, observations=0, window_start=None,
                window_end=None, streams=count, effective_streams=None, diversification_ratio=None,
                volatility_reduction_pct=None, progress_points=None, progress_display=None, flags=[],
                min_eigenvalue=None, capital_weights={}, risk_share={}, annual_volatility_pct={},
                annual_portfolio_volatility_pct=None, shrinkage=None)


def _window(frame, ctx, state, months, cutoff):
    """Headline statistics on the last `months` calendar rows: (record, shrunk measured covariance or None)."""
    streams = state['streams']
    out = _empty_window(months, len(streams))
    data, reason = rp.measured_window(frame, ctx['mcols'], months, cutoff)
    out['observations'] = len(data)
    if reason:
        return dict(out, reason=reason), None
    out.update(window_start=data.index[0].date().isoformat(), window_end=data.index[-1].date().isoformat())
    x = data.to_numpy(dtype=float)
    shrunk = rp.shrunk_covariance(x) if np.isfinite(x).all() else None
    if shrunk is None:
        return dict(out, reason='degenerate_covariance'), None
    cov_m = np.atleast_2d(shrunk[0])
    stats = _stats(cov_m, ctx, state)
    if isinstance(stats, str):
        return dict(out, reason=stats), None
    lagged, short = data.index[-1] < cutoff, len(data) < months
    flags = (['lagged_one_month'] if lagged else []) + (['short_history'] if short else [])
    if stats['streams'] > len(streams) + rp.HEDGE_TOLERANCE:
        flags.append('hedge_driven_count')
    return dict(out, status='provisional' if lagged or short else 'modeled', effective_streams=stats['streams'],
                diversification_ratio=stats['ratio'], volatility_reduction_pct=float(100 * (1 - 1 / stats['ratio'])),
                progress_points=stats['points'],
                progress_display=rp.display_points(stats['points'], stats['streams'], TARGET_V3), flags=flags,
                min_eigenvalue=stats['min_eigenvalue'], capital_weights={s['id']: float(s['w']) for s in streams},
                risk_share=stats['shares'], annual_volatility_pct=stats['annual'],
                annual_portfolio_volatility_pct=stats['portfolio'],
                shrinkage=dict(target='constant_correlation', intensity=float(shrunk[1]),
                               mean_correlation=None if shrunk[2] is None else float(shrunk[2]))), \
        dict(cov=cov_m, stats=stats)


def _scenarios(cov_m, ctx, state, status):
    if not any(s['kind'] == 'modeled' for s in state['streams']):
        na = dict(status='not_applicable', reason='no_modeled_streams')
        return dict(na, items={}, volatility={}, range=None)
    items = {name: _item(_stats(cov_m, ctx, state, name), status) for name in SCENARIOS}
    volatility = {str(m): _item(_stats(cov_m, ctx, state, 'central', m), status) for m in VOLATILITY_MULTIPLIERS}
    usable = [i for i in items.values() if i['status'] != 'unavailable']
    if len(usable) != len(items):
        return dict(status='incomplete', reason='degenerate_covariance', items=items, volatility=volatility, range=None)
    return dict(status=status, reason=None, items=items, volatility=volatility,
                range=dict(low_display=items['adverse']['progress_display'],
                           high_display=items['favorable']['progress_display']))


def _gain(cov_m, ctx, states, status):
    """Sequential points: the v2 groups alone, plus modeled streams, plus proxy streams (the headline)."""
    if states['base'] is None:
        return dict(status='unavailable', reason='baseline_no_history', items={}, modeled_points=None,
                    proxy_points=None, total_points=None)
    items = {name: _item(_stats(cov_m, ctx, states[name]), status) for name in ('base', 'with_modeled', 'full')}
    if any(i['status'] == 'unavailable' for i in items.values()):
        return dict(status='incomplete', reason='degenerate_covariance', items=items, modeled_points=None,
                    proxy_points=None, total_points=None)
    p = {n: i['progress_points'] for n, i in items.items()}
    return dict(status=status, reason=None, items=items, modeled_points=p['with_modeled'] - p['base'],
                proxy_points=p['full'] - p['with_modeled'], total_points=p['full'] - p['base'])


def _source_of(stream):
    if stream['kind'] == 'modeled':
        return 'private:' + stream['country']
    if stream['kind'] == 'proxy':
        return 'proxy'
    return 'car_business' if stream['id'] == rp.CAR_ID else 'listed'


def _by_source(streams, shares):
    capital, risk = {}, {}
    for s in streams:
        source = _source_of(s)
        capital[source] = capital.get(source, 0.) + 100 * s['w']
        risk[source] = risk.get(source, 0.) + 100 * shares[s['id']]
    return dict(capital_pct=dict(sorted(capital.items())), risk_pct=dict(sorted(risk.items())))


# ----------------------------------------------------------------------------------------------------- records
def _record_v3(v2, retrospective, method, **fields):
    calculated = v2.get('calculated_at')
    result = dict(version=VERSION_V3, unit='points', scope=method['scope'], as_of_date=v2['as_of_date'],
                  calculated_at=datetime.now(timezone.utc).isoformat(), retrospective=bool(retrospective),
                  data_vintage=dict(source_v2_calculated_at=calculated if isinstance(calculated, str) else None,
                                    car_proxies_cutoff=None, series={}),
                  status='unavailable', reason=None, warnings=[], progress_points=None, progress_display=None,
                  method=copy.deepcopy(method), method_fingerprint=fingerprint(method),
                  source_v2=rp.source_v2_summary(v2), model=None, car_proxies=None, car_proxies_fingerprint=None,
                  private=None, coverage=None, windows={}, scenarios=None, private_gain=None, sources=None,
                  locations=None)
    result.update(fields)
    return seal_result(result)


def _frame(v2, groups, proxy_classes, fx_symbol, model):
    """Monthly measured columns: group representatives, proxy baskets (all names required) and EUR/USD."""
    as_of = v2['as_of_date']
    group_frame = build_group_history(v2['histories'], {g: 1. for g in groups},
                                      v2['configuration']['group_definitions'])
    frozen = history_frame(v2['histories'])
    extra = pd.DataFrame(index=group_frame.index)
    for cls in sorted(proxy_classes):
        names = ['yf:' + s for s in model['proxies'][cls]['symbols']]
        if all(n in frozen for n in names):
            extra[PROXY_PREFIX + cls] = frozen[names].mean(axis=1, skipna=False).reindex(group_frame.index)
    if fx_symbol and 'yf:' + fx_symbol in frozen:
        extra[FX_COLUMN] = frozen['yf:' + fx_symbol].reindex(group_frame.index)
    return monthly_window(pd.concat([group_frame, extra], axis=1), as_of)


def _derive(v2, proxies, model, retrospective):
    method = method_v3(model)

    def make(**fields):
        return _record_v3(v2, retrospective, method, **fields)

    def fail(reason, **more):
        return make(reason=reason, warnings=[reason.split(':')[0]], **more)
    if v2.get('status') == 'not_applicable':
        return make(status='not_applicable', reason='no_invested_assets')
    if not isinstance(model, dict):
        cause = MODEL_ERROR if model is MODEL and MODEL_ERROR else type(model).__name__
        return fail('private_model_invalid' + (':' + cause if cause else ''))
    if not rp.v2_applicable(v2):
        return fail('source_v2_unavailable')
    groups = [(g['id'], g['weight']) for g in v2['groups']]
    if not all(_number(w, 0.) for _, w in groups) or abs(sum(w for _, w in groups) - 1) > rp.WEIGHT_TOLERANCE:
        return fail('invalid_weights')
    invested_pct_nav = float(v2['coverage']['invested_pct_nav'])
    cash_pct_nav = float(v2['coverage']['cash_pct_nav'])
    try:
        items, excluded, private_flags, cash_total = _private(v2, model)
        amounts = {kinds: _universe(v2, items, kinds) for kinds in
                   (frozenset(), frozenset({'modeled'}), frozenset({'modeled', 'proxy'}))}
    except _Unavailable as error:
        return fail(str(error))
    full_amounts = amounts[frozenset({'modeled', 'proxy'})]
    row_keys = {f"{i['cls']}:{i['country']}" for i in items if i['kind'] == 'modeled'}
    proxy_classes = {i['cls'] for i in items if i['kind'] == 'proxy'}
    uses_fx = any('corr_fx_eur' in model['rows'][k] for k in row_keys)
    private = dict(declared=bool(items) or any(excluded.values()),
                   entries=sum(1 for i in items if i['source'] == 'entry'),
                   reclassified=sum(1 for i in items if i['source'] == 'reclassify'), excluded=excluded)
    keep = dict(model=_model_used(model, row_keys, proxy_classes), private=private)
    names = [f for f in FACTORS if row_keys and (f != 'fx_eur' or uses_fx)]
    fcols = [model['factors'][f]['group'] if f != 'fx_eur' else FX_COLUMN for f in names]
    base_groups = set(amounts[frozenset()])
    measured_groups = {k for k in full_amounts if not k.startswith((PROXY_PREFIX, PRIVATE_PREFIX))}
    wanted = base_groups | measured_groups | {c for c in fcols if c != FX_COLUMN}
    base = _frame(v2, wanted, proxy_classes, model['factors']['fx_eur']['symbol'] if uses_fx else None, model)
    cutoff = completed_month_end(v2['as_of_date'])
    frame, check, block = base, None, None
    if full_amounts.get(rp.CAR_ID, 0.) > 0 or rp.CAR_ID in base_groups:
        frame, check, block, car_keep, reason = rp.car_basket_frame(v2, base, proxies)
        keep.update(car_keep)
        if reason:
            return fail(reason, **keep)
    car_ua = _car_ukraine(v2, invested_pct_nav)
    states = {name: _state(amounts[kinds], items, car_ua, model) for name, kinds in (
        ('base', frozenset()), ('with_modeled', frozenset({'modeled'})), ('full', frozenset({'modeled', 'proxy'})))}
    measured = sorted(s['col'] for s in states['full']['streams'] if s['kind'] != 'modeled')
    missing = sorted(c for c in measured + fcols if c not in frame)
    total = sum(full_amounts.values())
    invested = sum(float(p['value_usd']) for p in v2['positions'])
    stream_rows = [dict(id=s['id'], kind=_source_of(s), cls=s.get('cls'), country=s.get('country'),
                        location=s.get('location'), weight_pct_universe=100 * s['w'])
                   for s in states['full']['streams']]
    by_kind = {k: sum(i['amount'] for i in items if i['kind'] == k) for k in ('modeled', 'proxy')}
    car_proxy = None
    vintage = dict(source_v2_calculated_at=v2.get('calculated_at') if isinstance(v2.get('calculated_at'), str) else None,
                   car_proxies_cutoff=None, series={})
    if block is not None:
        car_proxy = dict(id=rp.BASKET_ID, names=list(rp.BASKET_NAMES), last_month=block['series'][rp.BASKET_ID]['last_month'],
                         provenance=rp.block_provenance(block, rp.BASKET_ID),
                         assumption='business_behaves_like_listed_remarketers_basket')
        vintage = dict(vintage, car_proxies_cutoff=block['cutoff_month'],
                       series={n: dict(last_month=i['last_month'], provenance=rp.block_provenance(block, n))
                               for n, i in sorted(block['series'].items())})
        retrospective = bool(retrospective) or (isinstance(block.get('as_of_date'), str)
                                                and block['as_of_date'] > v2['as_of_date'])
    nav = invested * 100. / invested_pct_nav if invested and invested_pct_nav else None
    cash_source_pct_nav = 100. * cash_total / nav if nav is not None else 0.
    coverage = dict(invested_pct_nav=invested_pct_nav, cash_pct_nav=cash_pct_nav,
                    cash_source_pct_nav=cash_source_pct_nav,
                    universe_over_invested=total / invested,
                    private_pct_universe=100 * (by_kind['modeled'] + by_kind['proxy']) / total,
                    modeled_pct_universe=100 * by_kind['modeled'] / total,
                    proxy_pct_universe=100 * by_kind['proxy'] / total,
                    reclassified_pct_invested=100 * sum(i['amount'] for i in items if i['source'] == 'reclassify') / invested,
                    streams=stream_rows, car_proxy=car_proxy)
    locations = {}
    for s in states['full']['streams']:
        if s['kind'] == 'modeled' and s['location']:
            locations.setdefault(s['country'], set()).add(s['location'])
    common = dict(data_vintage=vintage, coverage=coverage, locations={c: len(v) for c, v in sorted(locations.items())},
                  **keep)
    if missing:
        return fail('no_history:' + ','.join(missing), **common)
    base_ready = all(s['col'] in frame for s in states['base']['streams'])
    mcols = sorted(set(measured) | set(fcols) | {s['col'] for s in states['base']['streams'] if s['col'] in frame})
    ctx = dict(model=model, mcols=mcols, fcols=fcols, factor_names=names)
    windows, covariances = {}, {}
    for months in rp.WINDOWS:
        windows[f'm{months}'], covariances[months] = _window(frame, ctx, states['full'], months, cutoff)
    main = windows[f'm{rp.PRIMARY}']
    parent = ['source_v2_provisional'] + list(v2.get('warnings') or []) if v2['status'] == 'provisional' else []
    warnings = (([] if car_proxy is None else ['car_proxy_assumption'])
                + (['modeled_private_assumptions'] if row_keys else [])
                + (['listed_proxy_assumption'] if proxy_classes else []) + sorted(private_flags)
                + (['ua_link_unreviewed'] if car_ua[1] > 0 and any(k.endswith(':UA') for k in row_keys) else [])
                + parent)
    if main['status'] == 'unavailable':
        stub = dict(status='unavailable', reason='main_unavailable')
        windows[f'm{rp.WINDOWS[1]}'] = _empty_window(rp.WINDOWS[1], len(states['full']['streams']), 'main_unavailable')
        return make(status='unavailable', reason=main['reason'], warnings=warnings + [main['reason'].split(':')[0]],
                    windows=windows, scenarios=dict(stub), private_gain=dict(stub), **common)
    status = ('provisional' if main['status'] == 'provisional' or parent or 'stale_private_valuation' in private_flags
              else 'modeled')
    cov_m = covariances[rp.PRIMARY]['cov']
    if items:
        gain = _gain(cov_m, ctx, dict(states, base=states['base'] if base_ready else None), status)
    else:
        gain = dict(status='not_applicable', reason='no_private_streams', items={}, modeled_points=None,
                    proxy_points=None, total_points=None)
    return make(status=status, progress_points=main['progress_points'], progress_display=main['progress_display'],
                warnings=warnings + main['flags'], windows=windows,
                scenarios=_scenarios(cov_m, ctx, states['full'], status), private_gain=gain,
                sources=dict(_by_source(states['full']['streams'], main['risk_share']),
                             loadings=covariances[rp.PRIMARY]['stats']['loadings']), **common)


def derive_risk_progress_v3(v2, proxies, *, model=_DEFAULT, retrospective=False):
    """Headline record from a saved v2 record, a frozen car proxy block (or None) and the public model.

    None only when `v2` carries no identity. Every other failure is an explicit unavailable record; nothing falls
    back to v2. `model` defaults to the tracked parameter file; replay always uses that default.
    """
    if not rp.has_v2_identity(v2):
        return None
    model = MODEL if model is _DEFAULT else model
    try:
        return _derive(v2, proxies, model, retrospective)
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, IndexError, ZeroDivisionError,
            np.linalg.LinAlgError) as error:
        return _record_v3(v2, retrospective, method_v3(model),
                          reason='invalid_inputs:' + type(error).__name__, warnings=['invalid_inputs'])


def validate_saved_risk_progress_v3(result, data, v2, expected_date=None, *, v2_validated=False):
    """Integrity plus full recomputation from the saved v2 record, the embedded block and the tracked model."""
    try:
        if not isinstance(result, dict) or result.get('version') != VERSION_V3 or result.get('unit') != 'points' \
                or result.get('scope') != METHOD_V3['scope'] or not isinstance(result.get('retrospective'), bool):
            return False
        if result.get('result_fingerprint') != fingerprint({k: v for k, v in result.items() if k != 'result_fingerprint'}):
            return False
        if result.get('method') != METHOD_V3 or result.get('method_fingerprint') != fingerprint(METHOD_V3):
            return False
        if not v2_validated and not validate_saved_allocation_v2(v2, data, expected_date, replay=True):
            return False
        if result['as_of_date'] != v2['as_of_date'] or (expected_date and result['as_of_date'] != expected_date):
            return False
        if result.get('source_v2') != rp.source_v2_summary(v2):
            return False
        datetime.fromisoformat(result['calculated_at'])
        if result['status'] not in {'modeled', 'provisional', 'unavailable', 'not_applicable'} or (
                result['status'] in {'unavailable', 'not_applicable'}
                and (result['progress_points'] is not None or result['progress_display'] is not None)):
            return False
        fresh = derive_risk_progress_v3(v2, result.get('car_proxies'), retrospective=result['retrospective'])
        if fresh is None:
            return False
        return rp.replay_equal({k: v for k, v in fresh.items() if k not in IGNORED_V3},
                               {k: v for k, v in result.items() if k not in IGNORED_V3})
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return False
