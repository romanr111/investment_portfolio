"""Offline what-if scenarios on a copied snapshot: no writes, no network, no orders.

`--what-if ID=+USD` mutates a copy of a saved snapshot (the position matched by
id, the cash total by the net delta), reruns the same frozen offline
enrichment on that copy and prints before/after limit states with the v2
score. The mutation and the derived result live in a temporary directory that
is removed afterwards; the original snapshot is only read. Every input is
validated before the copy is mutated, so a rejected delta changes nothing.
"""
import json
import math
import re
import tempfile
from copy import deepcopy
from pathlib import Path

from analytics.allocation_inputs import allocation_settings, profile_for
from analytics.allocation_score import history_frame
from analytics.holy_grail_data import (CACHE_DIR, CONFIG_PATH, CASH_EQUIVALENTS, DATA_DIR,
                                       extract_exposures, enrich_snapshot_file, load_config)
from analytics.concentration_v1 import VERSION as CONCENTRATION_VERSION, build_block, unavailable_block


class WhatIfError(ValueError):
    """Rejected inputs or a failed run; the original snapshot was not changed."""


DELTA = re.compile(r'([^=\s]+)=([+-])(\d+(?:\.\d+)?)')
V2 = 'capital_diversification_v2'
IB_CATEGORIES = ('Stocks', 'China Stocks', 'Bonds', 'Precious Metals', 'Commodities', 'REIT', 'Short Selling')
PRIVATE_ROWS = {'crypto_lending': ('Crypto Landing', 'principal_usd'),
                'p2p': ('p2p_lending', 'balance_usd'),
                'other_assets': (None, 'carrying_value_usd')}


def parse_deltas(texts):
    """`ID=value` USD deltas; the sign is mandatory (a re-buy is not a sale)."""
    deltas = []
    for text in texts:
        match = DELTA.fullmatch(text.strip())
        if not match:
            raise WhatIfError('Invalid --what-if value "' + text + '"; use ID=+USD or ID=-USD')
        identifier, sign = match.group(1), match.group(2)
        if any(delta['id'] == identifier for delta in deltas):
            raise WhatIfError('Repeated --what-if position ' + identifier)
        deltas.append({'id': identifier, 'usd': float(sign + match.group(3))})
    if not deltas:
        raise WhatIfError('No --what-if deltas provided')
    return deltas


def latest_snapshot(data_dir=DATA_DIR):
    """Newest dated combined snapshot; pass --snapshot to pin another file."""
    directory = Path(data_dir) / 'snapshots'
    paths = [path for path in directory.glob('combined_data_*.json')
             if path.is_file() and path.name not in {'combined_data_latest.json', 'final_data.json'}]
    if not paths:
        raise WhatIfError('No dated combined_data snapshot found under data/snapshots; pass --snapshot')
    return max(paths, key=lambda path: path.name)


def validated(settings, positions, deltas, as_of_date):
    """Check every delta id against saved positions and economic profiles."""
    config = allocation_settings(settings)
    by_id = {}
    for position in positions:
        by_id.setdefault(position['id'], position)
    for delta in deltas:
        identifier = delta['id']
        if identifier == 'unallocated':
            continue  # remainder deltas only move cash; no economic profile exists
        if identifier.startswith('crypto:') and identifier.split(':', 1)[1] in CASH_EQUIVALENTS:
            raise WhatIfError('Cash-like position ' + identifier + ' is not priced; shift cash instead')
        position = by_id.get(identifier)
        if position is not None:
            try:
                profiled = profile_for(position, config, as_of_date) is not None
            except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
                profiled = False
            if not profiled:
                raise WhatIfError('Position ' + identifier + ' has no economic profile in the saved configuration')
            continue
        # A fully sold position may still be re-bought when its dated profile or
        # the explicit category model covers the id.
        profiled = identifier.startswith('crypto:') and as_of_date >= '2026-09-30'
        if identifier.startswith('ib:'):
            profiled = identifier in config['profiles']
        if not profiled:
            raise WhatIfError('Position ' + identifier + ' not found in the saved positions')
    return config


def _apply_symbol(ib, symbol, amount):
    values = ib.setdefault('IB_DATA', {}) if isinstance(ib, dict) else {}
    for category in IB_CATEGORIES:
        rows = values.get(category)
        if isinstance(rows, dict) and symbol in rows:
            rows[symbol] = float(rows[symbol]) + amount
            return
    values.setdefault('Stocks', {})[symbol] = amount


def _apply_crypto(data, symbol, amount):
    rows = (data.get('POSITION_DATA') or {}).get('crypto')
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict) and row.get('asset') == symbol:
                row['value_usd'] = float(row.get('value_usd') or 0) + amount
                return
        rows.append({'asset': symbol, 'value_usd': amount})
        return
    saved = (data.get('CRYPTO_DATA') or {}).get('Crypto_Market_Values') or {}
    saved[symbol] = float(saved.get(symbol) or 0) + amount


def _apply_private_row(data, family, index, amount):
    income_key, amount_field = PRIVATE_ROWS[family]
    contract = data.setdefault('POSITION_DATA', {})
    if not isinstance(contract.get(family), list):
        if income_key:
            saved = (data.get('FIXED_INCOME_DATA') or {}).get('group_weighted_interest', {}).get(income_key, [0])
            value = saved[0] if isinstance(saved, (list, tuple)) else saved
            contract[family] = [{amount_field: value}]
        else:
            contract[family] = [{amount_field: value} for value in (data.get('OTHER_ASSETS') or {}).values()]
        # Materialized legacy fallback rows keep the same ids in the same order.
    rows = contract[family]
    if index >= len(rows):
        raise WhatIfError('Position ' + family + ':' + str(index) + ' not found in the saved positions')
    rows[index][amount_field] = float(rows[index].get(amount_field) or 0) + amount


def apply_deltas(data, deltas):
    """Move positions by id and the cash total by the net delta; TOTAL_ASSETS stays."""
    for delta in deltas:
        identifier, amount = delta['id'], delta['usd']
        if identifier == 'unallocated':
            continue  # the remainder delta is already a cash shift
        if identifier.startswith('ib:'):
            _apply_symbol(data, identifier[3:], amount)
        elif identifier.startswith('crypto:'):
            _apply_crypto(data, identifier.split(':', 1)[1], amount)
        else:
            family, index = identifier.split(':', 1)
            if family not in PRIVATE_ROWS:
                raise WhatIfError('Unsupported --what-if position id ' + identifier)
            _apply_private_row(data, family, int(index), amount)
    total = -sum(delta['usd'] for delta in deltas)
    cash = data.setdefault('CASH_DATA', {})
    cash['Total'] = float(cash.get('Total') or 0) + total
    return data


def score_state(data):
    """Whitelisted v2 score readout for one saved or recomputed quality dict."""
    record = (data.get('DIVERSIFICATION_DATA') or {}).get('allocation_score_v2')
    record = record if isinstance(record, dict) else {}
    return {'status': record.get('status'), 'score': record.get('score'),
            'display_score': record.get('display_score'), 'category': record.get('category'),
            'assessment': record.get('assessment'), 'warnings': list(record.get('warnings') or []),
            'input_flags': list(record.get('input_flags') or []),
            'coverage': dict((record.get('coverage') or {})),
            'comparison': record.get('comparison')}


def limit_value(facts, limit):
    if limit == 'issuer_pct_equities':
        return (facts.get('largest_issuer') or {}).get('pct_equities')
    if limit == 'issuer_pct_nav':
        return (facts.get('largest_issuer') or {}).get('pct_nav')
    if limit == 'top4_pct_equities':
        return (facts.get('top4_issuers') or {}).get('pct_equities')
    if limit == 'core_min_pct_equities':
        return facts.get('core_pct_equities')
    if limit == 'country_pct_equities_china':
        for key, value in (facts.get('country_pct_equities') or {}).items():
            if str(key).lower() == 'china':
                return value
        return None
    return None


def _decision_state(breach, decisions, as_of_date):
    record = decisions.get(breach.get('decision_id')) if breach.get('decision_id') else None
    if record is None:
        return {'decision_id': breach.get('decision_id'), 'state': 'unresolved'}
    review_by = str(record.get('review_by') or '')
    resolved = bool(review_by and review_by >= as_of_date)
    return {'decision_id': breach.get('decision_id'), 'decision': record.get('decision'),
            'decided_at': record.get('decided_at'), 'review_by': review_by, 'resolved': resolved}


def concentration_state(block, decisions, as_of_date):
    """Per-limit value/breach/decision readout with the block's own warnings."""
    if not isinstance(block, dict) or block.get('version') != CONCENTRATION_VERSION:
        return {'status': 'absent'}
    if block.get('status') == 'unavailable':
        return {'status': 'unavailable', 'warnings': list(block.get('warnings') or [])}
    facts = block.get('facts') or {}
    limits = block.get('limits') or {}
    breached = {}
    for breach in block.get('breaches') or []:
        if isinstance(breach, dict) and isinstance(breach.get('limit'), str):
            breached.setdefault(breach['limit'], breach)
    try:
        states = {}
        for key, limit in limits.items():
            if key == 'thesis_pct_equities':
                states[key] = {name: _limit_state(
                    (facts.get('thesis_pct_equities') or {}).get(name), value, breached.get(key, {}),
                    _decision_state(breached.get(key, {}), decisions, as_of_date))
                    for name, value in sorted((limit or {}).items())}
                continue
            states[key] = _limit_state(limit_value(facts, key), limit, breached.get(key, {}),
                                       _decision_state(breached.get(key, {}), decisions, as_of_date))
        largest = facts.get('largest_issuer') or {}
    except (AttributeError, KeyError, TypeError):
        return {'status': 'unavailable', 'warnings': ['concentration_state_invalid']}
    return {'status': 'scored', 'warnings': list(block.get('warnings') or []),
            'largest_issuer': largest, 'top4_issuers': facts.get('top4_issuers'),
            'business_pct_invested': facts.get('business_pct_invested'),
            'score_excluding_car': facts.get('score_excluding_car'),
            'unknown_lookthrough_pct_equities': facts.get('unknown_lookthrough_pct_equities'),
            'limits': states}


def _limit_state(value, limit, breach, decision):
    value = value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None
    result = {'value': value, 'limit': limit, 'min': limit == 'core_min_pct_equities',
              'breached': bool(breach)}
    if breach:
        result['breach_value'] = breach.get('value')
        result['decision'] = decision
    return result


def run(deltas_text, *, snapshot=None, config_path=CONFIG_PATH, cache_dir=None, data_dir=DATA_DIR):
    """Validate, mutate a copied payload, re-enrich it offline and print the states."""
    deltas = parse_deltas(deltas_text)
    source = Path(snapshot) if snapshot else latest_snapshot(data_dir)
    try:
        payload = json.loads(source.read_text(encoding='utf-8'))
        settings = load_config(config_path)
    except (OSError, ValueError, TypeError) as error:
        raise WhatIfError('Cannot read snapshot or settings (' + type(error).__name__ + '); nothing was changed')
    data = payload.get('data', payload)
    try:
        stamp = data.get('POSITION_DATA', {}).get('as_of_date') or payload.get('as_of_date') or \
            data.get('DATA_METADATA', {}).get('last_updated')
        from datetime import date
        as_of_date = date.fromisoformat(str(stamp)[:10]).isoformat()
    except (ValueError, TypeError) as error:
        raise WhatIfError('Snapshot carries no valid as_of_date; nothing was changed')
    try:
        positions, cash, flags = extract_exposures(data, as_of_date, settings)
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        raise WhatIfError('Cannot read saved positions (' + type(error).__name__ + '); nothing was changed')
    config = validated(settings, positions, deltas, as_of_date)
    saved = deepcopy(payload)
    target = saved['data'] if 'data' in saved else saved
    (target.setdefault('DIVERSIFICATION_DATA', {})).pop('concentration_v1', None)
    apply_deltas(target, deltas)

    saved_v2 = (data.get('DIVERSIFICATION_DATA') or {}).get('allocation_score_v2')
    if not (isinstance(saved_v2, dict) and saved_v2.get('version') == V2 and
            isinstance(saved_v2.get('histories'), dict) and saved_v2['histories']):
        saved_v2 = {}
    try:
        frozen_histories = history_frame(saved_v2['histories']) if saved_v2 else None
        if frozen_histories is not None and frozen_histories.empty:
            frozen_histories = None
    except (ValueError, TypeError, KeyError) as error:
        frozen_histories = None

    decisions_before = ((saved_v2.get('configuration') or {}).get('concentration_decisions')
                        if isinstance(saved_v2, dict) else None) or {}
    before_block = (data.get('DIVERSIFICATION_DATA') or {}).get('concentration_v1') \
        if isinstance(data.get('DIVERSIFICATION_DATA'), dict) else None
    try:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copy_path = root / 'in' / 'mutated.json'
            out_path = root / 'out' / 'derived.json'
            copy_path.parent.mkdir(); out_path.parent.mkdir()
            copy_path.write_text(json.dumps(saved, ensure_ascii=False, allow_nan=False), encoding='utf-8')
            result = enrich_snapshot_file(copy_path, out_path, config=settings,
                                          cache_dir=cache_dir or CACHE_DIR, allow_network=False,
                                          monthly_returns=frozen_histories)
    except WhatIfError:
        raise
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise WhatIfError('Offline recomputation failed (' + type(error).__name__ + '); nothing was changed')
    after_data = result.get('data', result)
    after = deepcopy(after_data.get('DIVERSIFICATION_DATA') or {})
    after_v2 = after.get('allocation_score_v2') or {}
    after_block = after.get('concentration_v1')
    if not (isinstance(after_block, dict) and after_block.get('version') == CONCENTRATION_VERSION):
        try:
            after_block = build_block(after_v2.get('positions') or [], config, target.get('TOTAL_ASSETS'),
                                      as_of_date, v2_result=after_v2 if after_v2.get('version') == V2 else None)
        except NotImplementedError:
            after_block = unavailable_block(as_of_date, ['concentration_block_unavailable'])
        except (ValueError, TypeError, KeyError, OverflowError, AttributeError):
            after_block = unavailable_block(as_of_date, ['concentration_block_invalid'])
    decisions_after = ((after_v2.get('configuration') or {}).get('concentration_decisions') or {})
    return {'snapshot': str(source), 'as_of_date': as_of_date,
            'deltas': [{'id': delta['id'], 'usd': delta['usd']} for delta in deltas],
            'cash_delta_usd': round(-sum(delta['usd'] for delta in deltas), 2) or 0.0,
            'before': {'allocation_score_v2': score_state(data),
                       'concentration_v1': concentration_state(before_block, decisions_before, as_of_date)},
            'after': {'allocation_score_v2': score_state({'DIVERSIFICATION_DATA': {'allocation_score_v2': after_v2}}),
                      'concentration_v1': concentration_state(after_block, decisions_after, as_of_date)}}