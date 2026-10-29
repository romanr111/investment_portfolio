"""Private inputs and scenario construction for capital diversification v2."""
from copy import deepcopy
from datetime import date, datetime, timezone
import math
import re

import pandas as pd

from analytics.allocation_inputs import GROUPS, FATAL_FLAGS, BALANCE_FLAGS, profile_for, _seal
from analytics.allocation_score import history_payload, history_frame, monthly_window
from analytics.allocation_score_v2 import VERSION, SECTORS, evaluate_scenarios, _same
from analytics.diversification_inputs import quality_inputs_fingerprint
from analytics.holy_grail import completed_month_end, fingerprint

METHOD = {
    'version': VERSION, 'target_groups': 6, 'correlation_exponent': 2,
    'correlation_clip': 'positive', 'sector_coefficient': 25,
    'sector_cap': 'min(equity_breadth,1-between)', 'sector_count': 11,
    'sectors': sorted(SECTORS), 'category_boundaries': [50, 80],
    'windows': [60, 36], 'business_correlations': [.25, .75],
    'minimum_observations': 36, 'max_unknown_pct': 5,
    'max_missing_pair_points': 5, 'rounding': 'floor_with_integer_noise_1e-8',
    'group_definitions': {g: {'label': label, 'representative': representative}
                          for g, (label, representative) in GROUPS.items()},
}


def _assessment(scenarios, business):
    available = {key: value for key, value in scenarios.items() if value['score'] is not None}
    categories = {key: value['category'] for key, value in available.items()}
    business_dependent = business and any(
        all(k in categories for k in (f'm{window}_r025', f'm{window}_r075')) and
        categories[f'm{window}_r025'] != categories[f'm{window}_r075'] for window in (60, 36))
    window_dependent = any(
        all(k in categories for k in (f'm60{suffix}', f'm36{suffix}')) and
        categories[f'm60{suffix}'] != categories[f'm36{suffix}']
        for suffix in (('_r025', '_r075') if business else ('',)))
    combined = len(set(categories.values())) > 1 and not (business_dependent or window_dependent)
    scores = [value['score'] for value in available.values()]
    displays = [value['display_score'] for value in available.values()]
    return dict(business_dependent=business_dependent, window_dependent=window_dependent,
                combined_dependent=combined, available=len(available), expected=len(scenarios),
                missing=[key for key in scenarios if key not in available],
                min_score=min(scores) if scores else None, max_score=max(scores) if scores else None,
                min_display=min(displays) if displays else None, max_display=max(displays) if displays else None)


def _risk_facts(positions, profiles, settings, total, as_of_date, cutoff):
    """Summarize model exposures and reviewed evidence without inventing FX facts."""
    from analytics.holy_grail_data import bound_exposure_record
    from analytics.diversification_quality import reviewed_record
    records = settings.get('diversification', {}).get('exposures', {})
    by_position = {p['position_id']: p['definition'] for p in profiles}
    categories = {}
    duration_details = {}
    unknown = dict(duration_pct_nav=0., counterparty_pct_nav=0., liquidity_pct_nav=0.,
                   economic_fx_pct_nav=0., business_geography_pct_nav=0.)
    evidence = []
    for position in positions:
        value = float(position['value_usd'])
        profile = by_position.get(position['id'], {})
        amounts = {}
        for component in profile.get('components', []):
            group, amount = component['group'], value * component['share']
            if group.startswith('treasury_'):
                amounts[group] = amounts.get(group, 0.) + amount
            elif group.startswith('credit_'):
                amounts['credit_lending'] = amounts.get('credit_lending', 0.) + amount
            elif group == 'car_business':
                amounts['business'] = amounts.get('business', 0.) + amount
        record = bound_exposure_record(records, position['id'], 'category:' + position['category'],
                                       position.get('source_identity'))
        reviewed = reviewed_record({'risk_record': record}, as_of_date, review_cutoff=cutoff)
        interest_value = sum(amount for key, amount in amounts.items() if key.startswith('treasury_') or key == 'credit_lending')
        duration = reviewed.get('rate_duration')
        if interest_value and (isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration < 0):
            unknown['duration_pct_nav'] += interest_value / total * 100
        if amounts.get('credit_lending') and reviewed.get('counterparty_complete') is not True:
            unknown['counterparty_pct_nav'] += amounts['credit_lending'] / total * 100
        if reviewed.get('fx_monetary') is not True and reviewed.get('fx_monetary') is not False:
            unknown['economic_fx_pct_nav'] += value / total * 100
        if amounts.get('business') and reviewed.get('business_geography') != 'Ukraine':
            unknown['business_geography_pct_nav'] += amounts['business'] / total * 100
        liquidity = reviewed.get('liquidation_days')
        if isinstance(liquidity, bool) or not isinstance(liquidity, (int, float)) or not math.isfinite(liquidity) or liquidity < 0:
            unknown['liquidity_pct_nav'] += value / total * 100
        if reviewed:
            evidence.append({'position_id': position['id'], 'record': deepcopy(reviewed)})
            if interest_value and not isinstance(duration, bool) and isinstance(duration, (int, float)) and math.isfinite(duration) and duration >= 0:
                maturity = reviewed.get('maturity')
                try:
                    maturity = date.fromisoformat(maturity).isoformat() if maturity else None
                    if maturity and maturity < as_of_date: maturity = None
                except (ValueError, TypeError):
                    maturity = None
                key = (float(duration), maturity or '')
                duration_details[key] = duration_details.get(key, 0.) + interest_value
            if 'ai' in reviewed.get('themes', []): amounts['confirmed_ai_theme'] = value
            if reviewed.get('fx_monetary') is True: amounts['economic_fx'] = value
            if reviewed.get('counterparty_groups'): amounts['counterparty'] = value
            if amounts.get('business') and reviewed.get('business_geography') == 'Ukraine':
                amounts['business_ukraine'] = amounts['business']
            days = reviewed.get('liquidation_days')
            if not isinstance(days, bool) and isinstance(days, (int, float)) and math.isfinite(days) and days > 30:
                amounts['illiquidity'] = value
        for category, amount in amounts.items():
            categories[category] = categories.get(category, 0.) + min(value, amount)
    facts = [dict(id=key, affected_pct_nav=amount / total * 100) for key, amount in sorted(categories.items()) if amount > 0]
    details = [dict(rate_duration=duration, maturity=maturity or None, affected_pct_nav=amount / total * 100)
               for (duration, maturity), amount in sorted(duration_details.items())]
    return facts, evidence, unknown, details


def _group_history(histories, weights, definitions):
    frozen = history_frame(histories)
    frame = pd.DataFrame(index=frozen.index)
    for group in weights:
        symbol = definitions.get(group, {}).get('representative')
        series = 'yf:' + symbol if symbol else None
        if series in frozen:
            frame[group] = frozen[series]
    return history_frame(history_payload(frame))


def _compare_basis(result, basis):
    """Rebuild the saved previous basis; structural tamper raises, drift downgrades."""
    try:
        if basis['method_fingerprint'] != result['method_fingerprint']:
            raise ValueError('different_method')
        if basis.get('source_reference_verification') != 'unverified_without_original' or any(
                not isinstance(basis.get(key), str) or not re.fullmatch('[0-9a-f]{64}', basis[key])
                for key in ('source_result_fingerprint', 'source_content_fingerprint')):
            raise ValueError('invalid_previous_inputs')
        from analytics.holy_grail_data import extract_exposures
        source = basis['source_inputs']
        if quality_inputs_fingerprint(source) != basis['source_inputs_fingerprint']:
            raise ValueError('invalid_previous_inputs')
        positions, cash, flags = extract_exposures(source, basis['as_of_date'], basis['configuration']['extraction_settings'])
        if not _same(positions, basis['positions']) or not _same(cash, basis['cash_value']) or not flags.issubset(set(basis['input_flags']) | {'unsupported_borrowing'}):
            raise ValueError('invalid_previous_inputs')
        rebuilt = calculate_allocation_score_v2(source, positions, cash, history_frame(basis['histories']),
                                                 basis['configuration'], basis['as_of_date'], basis['input_flags'])
        # Bounded compare catches tampered saved values; exact compare below detects
        # cross-version recomputation noise and downgrades the comparison instead.
        weights = {g['id']: g['weight'] for g in rebuilt.get('groups', [])}
        if basis['method_definition'] != basis['configuration']['method_definition'] or not (
                _same(weights, basis['weights']) and _same(rebuilt.get('sectors'), basis['sectors'])
                and _same(rebuilt.get('score'), basis['score'])):
            raise ValueError('invalid_previous_inputs')
        if basis['as_of_date'] > result['as_of_date'] or datetime.fromisoformat(basis['calculated_at']) >= datetime.fromisoformat(result['calculated_at']):
            raise ValueError('invalid_previous_date')
        if not (_same(weights, basis['weights'], tol=0.) and _same(rebuilt.get('sectors'), basis['sectors'], tol=0.)
                and _same(rebuilt.get('score'), basis['score'], tol=0.)):
            return dict(status='unavailable', previous_basis=basis, reason='previous_rebuild_unstable')
        weights = basis['weights']
        key = 'm60_r025' if weights.get('car_business', 0) > 0 else 'm60'
        definitions = basis['method_definition']['group_definitions']
        old = evaluate_scenarios(weights, basis['sectors'], _group_history(basis['histories'], weights, definitions), basis['as_of_date'])[key]
        new = evaluate_scenarios(weights, basis['sectors'], _group_history(result['histories'], weights, definitions), result['as_of_date'])[key]
        if old['score'] is None or new['score'] is None or any(p['kind'] == 'missing' for p in old['pairs'] + new['pairs']):
            raise ValueError('missing_comparison_history')
        a, b, d = old['score'], new['score'], result['score']
        if d is None or abs(a - basis['score']) > 1e-8:
            raise ValueError('invalid_previous_score')
        return dict(status='available', previous_basis=basis, market_relationship_change=b-a,
                    positions_and_profiles_change=d-b, total_change=d-a)
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as error:
        return dict(status='unavailable', previous_basis=basis, reason=str(error) if str(error) in {
            'different_method', 'invalid_previous_date', 'missing_comparison_history', 'invalid_previous_score'} else 'invalid_previous_inputs')


def comparison_basis(previous):
    if not isinstance(previous, dict):
        return None
    data = previous.get('data', previous)
    if not isinstance(data, dict) or not isinstance(data.get('DIVERSIFICATION_DATA'), dict):
        return None
    old = data['DIVERSIFICATION_DATA'].get('allocation_score_v2')
    if not validate_saved_allocation_v2(old, data, replay=True) or old['score'] is None:
        return None
    keys = ('IB_DATA', 'CRYPTO_DATA', 'POSITION_DATA', 'CASH_DATA', 'TOTAL_ASSETS',
            'FIXED_INCOME_DATA', 'OTHER_ASSETS', 'DATA_QUALITY', 'DATA_METADATA', 'ENHANCED_STOCKS')
    source_inputs = {key: deepcopy(data[key]) for key in keys if key in data}
    return dict(as_of_date=old['as_of_date'], calculated_at=old['calculated_at'], score=old['score'],
                weights={group['id']: group['weight'] for group in old['groups']}, sectors=deepcopy(old['sectors']),
                histories=deepcopy(old['histories']), method_fingerprint=old['method_fingerprint'],
                method_definition=deepcopy(old['configuration']['method_definition']),
                configuration=deepcopy(old['configuration']), positions=deepcopy(old['positions']),
                cash_value=old['cash_value'], input_flags=deepcopy(old['input_flags']), source_inputs=source_inputs,
                source_inputs_fingerprint=quality_inputs_fingerprint(source_inputs),
                source_reference_verification='unverified_without_original',
                source_result_fingerprint=old['result_fingerprint'], source_content_fingerprint=fingerprint(data))


def calculate_allocation_score_v2(data, positions, cash, returns, config, as_of_date, flags=(), provenance=None):
    """Build a new record; failures remain explicitly unavailable."""
    try:
        holdings_fingerprint = quality_inputs_fingerprint(data)
    except (ValueError, TypeError, OverflowError):
        holdings_fingerprint = None
    result = dict(version=VERSION, unit='points', scope='invested_assets', as_of_date=as_of_date,
                  calculated_at=datetime.now(timezone.utc).isoformat(), status='unavailable',
                  score=None, display_score=None, category=None, warnings=[], scenarios={},
                  coverage={}, holdings_fingerprint=holdings_fingerprint,
                  comparison={'status': 'unavailable', 'reason': 'previous_v2_not_provided'})
    try:
        config = deepcopy(config)
        config.pop('calibration', None)
        config.setdefault('evidence_review_cutoff', datetime.now(timezone.utc).date().isoformat())
        config.setdefault('group_definitions', deepcopy(METHOD['group_definitions']))
        config.setdefault('method_definition', deepcopy(METHOD))
        if config['method_definition'] != METHOD or config['group_definitions'] != config['method_definition']['group_definitions']:
            raise ValueError('invalid_method_definition')
        flags = set(flags)
        if isinstance(data.get('TOTAL_ASSETS'), bool) or isinstance(cash, bool) or any(isinstance(p.get('value_usd'), bool) for p in positions):
            raise ValueError('invalid_valuation')
        # Validate before pandas serialization, which otherwise converts infinity to null.
        dates = pd.to_datetime(returns.index).tz_localize(None).normalize()
        if dates.isna().any() or (dates > completed_month_end(as_of_date)).any():
            raise ValueError('invalid_history')
        source_histories = history_payload(monthly_window(returns, as_of_date))
        result.update(configuration=config, configuration_fingerprint=fingerprint(config),
                      method_fingerprint=fingerprint(METHOD), positions=deepcopy(positions),
                      cash_value=cash, input_flags=sorted(flags), source_provenance=deepcopy(provenance or {}),
                      histories=source_histories, history_fingerprint=fingerprint(source_histories))
        total = float(data['TOTAL_ASSETS'])
        cash = float(cash)
        values = [float(p['value_usd']) for p in positions]
        if not math.isfinite(total) or total <= 0 or not math.isfinite(cash) or cash < 0 or any(not math.isfinite(v) or v < 0 for v in values):
            raise ValueError('invalid_valuation')
        if abs(sum(values) + cash - total) > max(1., total * 1e-6):
            raise ValueError('unreconciled_valuations')
        breakdown = data.get('CASH_DATA', {}).get('Breakdown', {}) or {}
        excluded = {'debt', 'manual_reconciliation'}
        cash_items = [v for k, v in breakdown.items() if k not in excluded]
        cash_items.append(data.get('IB_DATA', {}).get('Net_cash', 0))
        if any(isinstance(value, bool) or not math.isfinite(float(value)) for value in list(breakdown.values()) + cash_items):
            raise ValueError('invalid_cash_valuation')
        if any(float(v) < 0 for v in cash_items):
            flags.add('unsupported_borrowing')
        elif any(float(v) < 0 for k, v in breakdown.items() if k in excluded):
            flags.discard('unsupported_borrowing')
            flags.add('cash_liabilities_outside_scope')
        if flags & FATAL_FLAGS:
            raise ValueError(sorted(flags & FATAL_FLAGS)[0])
        quantities = [r.get('quantity') for r in data.get('POSITION_DATA', {}).get('crypto', [])]
        for rows in data.get('ENHANCED_STOCKS', {}).values():
            if isinstance(rows, dict):
                quantities.extend(r.get('quantity') for r in rows.values() if isinstance(r, dict))
        if any(float(v) < 0 for v in quantities if v is not None) or any(
                p.get('unsupported_risk') or p['category'] == 'Short Selling' or
                p['id'] in config.get('unsupported_ids', []) for p in positions):
            raise ValueError('unsupported_risk')
        invested = sum(values)
        result.update(cash_value=cash, input_flags=sorted(flags),
                      coverage=dict(cash_pct_nav=cash / total * 100, invested_pct_nav=invested / total * 100))
        if not invested:
            result['status'] = 'not_applicable'
            return _seal(result)
        amounts, sector_amounts, profiles = {}, {}, []
        unknown = modeled = 0.
        for position, value in zip(positions, values):
            if value == 0:
                continue
            profile = profile_for(position, config, as_of_date)
            if profile is None:
                unknown += value
                amounts['unknown'] = amounts.get('unknown', 0.) + value
                continue
            profiles.append(dict(position_id=position['id'], definition=profile))
            if position.get('kind') == 'proxy' or any(c['group'] == 'car_business' for c in profile['components']):
                modeled += value
            for component in profile['components']:
                group = component['group']
                amount = value * component['share']
                amounts[group] = amounts.get(group, 0.) + amount
                if group.startswith('equity_'):
                    sector = sector_amounts.setdefault(group, {})
                    for name, share in component.get('sectors', {}).items():
                        sector[name] = sector.get(name, 0.) + amount * share
        weights = {group: amount / invested for group, amount in amounts.items() if amount > 0}
        risk_facts, risk_evidence, risk_unknown, risk_details = _risk_facts(
            positions, profiles, config.get('extraction_settings', {}), total, as_of_date, config['evidence_review_cutoff'])
        sectors = {group: {name: amount / amounts[group] for name, amount in values.items()}
                   for group, values in sector_amounts.items()}
        # Keep source observations as serialized data, then calculate only from that serialization.
        group_history = _group_history(source_histories, weights, config['group_definitions'])
        scenarios = evaluate_scenarios(weights, sectors, group_history, as_of_date)
        business = weights.get('car_business', 0) > 0
        main = scenarios['m60_r025' if business else 'm60']
        warnings = []
        if unknown: warnings.append('unknown_profiles')
        if flags & BALANCE_FLAGS: warnings.append('partial_or_cached_valuations')
        if 'cash_liabilities_outside_scope' in flags: warnings.append('cash_liabilities_outside_scope')
        if any(sum(row.values()) < 1 - 1e-8 for row in sectors.values()): warnings.append('unknown_sectors')
        if main['status'] == 'provisional': warnings.append('partial_pair_history')
        result.update(groups=[dict(id=g, weight=weights[g]) for g in sorted(weights)], sectors=sectors,
                      profiles=profiles, risk_facts=risk_facts, risk_evidence=risk_evidence,
                      risk_unknown=risk_unknown, risk_details=risk_details,
                      histories=source_histories, history_fingerprint=fingerprint(source_histories),
                      scenarios=scenarios, assessment=_assessment(scenarios, business), warnings=warnings)
        result['coverage'].update(unknown_pct_invested=unknown / invested * 100,
                                  modeled_pct_invested=modeled / invested * 100,
                                  missing_pair_max_points=main['missing_pair_max_points'])
        if unknown / invested > .05 + 1e-12 or main['score'] is None:
            result['warnings'].append('insufficient_coverage')
            return _seal(result)
        result.update(status='provisional' if warnings else main['status'], score=main['score'],
                      display_score=main['display_score'], category=main['category'])
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as error:
        code = str(error) if str(error) in FATAL_FLAGS | {'unsupported_risk', 'invalid_valuation', 'unreconciled_valuations'} else 'invalid_inputs'
        result.update(status='unavailable', score=None, display_score=None, category=None, warnings=[code])
    return _seal(result)


def validate_saved_allocation_v2(result, data, expected_date=None, *, replay=True):
    """Validate integrity and reconstruct the saved calculation from frozen inputs."""
    try:
        if not isinstance(result, dict) or result.get('version') != VERSION or result.get('unit') != 'points' or result.get('scope') != 'invested_assets':
            return False
        if result.get('result_fingerprint') != fingerprint({k: v for k, v in result.items() if k != 'result_fingerprint'}):
            return False
        if result.get('holdings_fingerprint') != quality_inputs_fingerprint(data):
            return False
        if expected_date and result['as_of_date'] != expected_date:
            return False
        datetime.fromisoformat(result['as_of_date'])
        datetime.fromisoformat(result['calculated_at'])
        if result['status'] not in {'modeled', 'provisional', 'unavailable', 'not_applicable'}:
            return False
        if result['status'] in {'unavailable', 'not_applicable'} and result['score'] is not None:
            return False
        if result.get('configuration_fingerprint') != fingerprint(result['configuration']):
            return False
        if result['configuration'].get('evidence_review_cutoff') != datetime.fromisoformat(result['calculated_at']).date().isoformat():
            return False
        if result.get('method_fingerprint') != fingerprint(METHOD) or result['configuration'].get('method_definition') != METHOD:
            return False
        if result['configuration'].get('group_definitions') != result['configuration']['method_definition']['group_definitions']:
            return False
        if result['status'] != 'not_applicable' and result.get('history_fingerprint') != fingerprint(result['histories']):
            return False
        # A sealed value alone cannot establish semantic consistency. Until an
        # independent structural-only validator exists, always perform replay.
        from analytics.holy_grail_data import bound_exposure_record, extract_exposures
        positions, cash, extracted_flags = extract_exposures(
            data, result['as_of_date'], result['configuration']['extraction_settings'])
        if not _same(positions, result['positions']) or not _same(cash, result['cash_value']):
            return False
        records = result['configuration']['extraction_settings'].get('diversification', {}).get('exposures', {})
        risky_ids = []
        for position in positions:
            record = bound_exposure_record(records, position['id'], 'category:' + position['category'],
                                           position.get('source_identity'))
            if position.get('unsupported_risk') or record.get('leveraged') or record.get('nonlinear_risk'):
                risky_ids.append(position['id'])
        if sorted(set(risky_ids)) != result['configuration'].get('unsupported_ids', []):
            return False
        if not extracted_flags.issubset(set(result['input_flags']) | {'unsupported_borrowing'}):
            return False
        fresh = calculate_allocation_score_v2(data, positions, cash, history_frame(result.get('histories', {})),
                                             result['configuration'], result['as_of_date'],
                                             result['input_flags'], result['source_provenance'])
        comparison = result.get('comparison', {})
        if 'previous_basis' in comparison:
            if comparison.get('reason') == 'invalid_previous_inputs':
                return False
            recomputed = _compare_basis(result, comparison['previous_basis'])
            # Instability of the previous-basis rebuild is environment-specific
            # float noise: it must not invalidate the record.
            if comparison.get('reason') == 'previous_rebuild_unstable':
                if recomputed.get('status') != 'available' and recomputed.get('reason') != 'previous_rebuild_unstable':
                    return False
            elif recomputed.get('reason') == 'previous_rebuild_unstable':
                if comparison.get('status') != 'available':
                    return False
            elif not _same(comparison, recomputed):
                return False
        elif comparison != fresh['comparison'] and comparison != {'status': 'unavailable', 'reason': 'previous_v2_invalid_or_absent'}:
            return False
        ignored = {'calculated_at', 'result_fingerprint', 'comparison'}
        return _same({k: v for k, v in fresh.items() if k not in ignored},
                     {k: v for k, v in result.items() if k not in ignored})
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return False
