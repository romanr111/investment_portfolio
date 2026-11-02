"""Enrich saved portfolio data with the diversification records without changing balances."""
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path

import pandas as pd

from analytics.holy_grail import concentration_v1, market_history
from analytics.holy_grail.allocation_inputs import (allocation_history_requests, allocation_settings,
                                                    seal_result, FATAL_FLAGS)
from analytics.holy_grail.allocation_score_v3 import derive_allocation_score_v3
from analytics.holy_grail.allocation_v2_inputs import calculate_allocation_score_v2, comparison_basis, compare_basis
from analytics.holy_grail.exposures import bound_exposure_record, extract_exposures, iso_date
from analytics.holy_grail.paths import CACHE_DIR, CONFIG_PATH, DATA_DIR
from analytics.holy_grail.risk_progress import derive_risk_progress_v1


def load_config(path=CONFIG_PATH):
    if not Path(path).exists():
        return {}
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Holy Grail configuration must be a JSON object")
    return value


def enrich_combined_data(data, *, as_of_date=None, config=None, monthly_returns=None,
                         allow_network=True, cache_dir=CACHE_DIR, source_provenance=None,
                         previous_combined_data=None, car_category=None, car_proxies=None):
    """Return an enriched copy. An analytics failure never changes financial values.

    `car_category` is an explicit frozen block (analytics.holy_grail.car.category): given, a v3 record is
    derived beside v2; omitted, no v3 record is written (nothing is looked up implicitly).
    `car_proxies` is the same kind of explicit block (analytics.holy_grail.car.risk_proxies): given, a
    risk_progress_v1 record with car-business scenarios is derived beside v2; omitted, none is written.
    """
    output = dict(data)
    as_of_date = iso_date(as_of_date or data.get("POSITION_DATA", {}).get("as_of_date")
                       or data.get("DATA_METADATA", {}).get("last_updated") or date.today().isoformat())
    try:
        settings = load_config() if config is None else config
    except (OSError, ValueError, TypeError):
        settings = None
    if isinstance(settings, dict) and 'allocation' not in settings:
        return output

    from copy import deepcopy

    existing = data.get('DIVERSIFICATION_DATA')
    output['DIVERSIFICATION_DATA'] = deepcopy(existing) if isinstance(existing, dict) else {}
    requested = settings.get('allocation') if isinstance(settings, dict) else None
    method = requested.get('method_version', 'capital_diversification_v2') if isinstance(requested, dict) else None
    try:
        allocation_config = allocation_settings(settings)
    except (ValueError, TypeError, KeyError, OSError, AttributeError):
        output['DIVERSIFICATION_DATA']['allocation_score_v2'] = {
            'version': 'capital_diversification_v2', 'status': 'unavailable', 'score': None,
            'warnings': ['invalid_method_version' if method not in (None, 'capital_diversification_v2')
                         else 'invalid_allocation_config']}
        return output

    positions, cash, flags, provenance = [], 0., set(), source_provenance or {}
    returns = monthly_returns if monthly_returns is not None else pd.DataFrame()
    try:
        positions, cash, flags = extract_exposures(data, as_of_date, settings)
        if monthly_returns is None:
            requests = allocation_history_requests(positions, allocation_config, as_of_date)
            returns, provenance, collection_flags = market_history.collect_return_history(
                requests, as_of_date=as_of_date, cache_dir=cache_dir, allow_network=allow_network)
            flags.update(collection_flags)
        risky_ids = [p['id'] for p in positions if p.get('unsupported_risk')]
        for p in positions:
            record = bound_exposure_record(settings.get('diversification', {}).get('exposures', {}),
                p['id'], 'category:' + p['category'], p.get('source_identity'))
            if record.get('leveraged') or record.get('nonlinear_risk'):
                risky_ids.append(p['id'])
        allocation_config['unsupported_ids'] = sorted(set(risky_ids))
    except Exception:
        # A failed extraction or collection must never become a successful all-cash result.
        flags.add('invalid_inputs')
        allocation_config['unsupported_ids'] = []
    allocation_config['extraction_settings'] = deepcopy(settings)
    saved = calculate_allocation_score_v2(
        data, positions, cash, returns, allocation_config, as_of_date, flags, provenance)
    if previous_combined_data is not None:
        basis = comparison_basis(previous_combined_data)
        saved['comparison'] = compare_basis(saved, basis) if basis else {
            'status': 'unavailable', 'reason': 'previous_v2_invalid_or_absent'}
        seal_result(saved)
    output['DIVERSIFICATION_DATA']['allocation_score_v2'] = saved
    # v3 is derived from this very v2 record; a stale one from an earlier run can never match it.
    output['DIVERSIFICATION_DATA'].pop('allocation_score_v3', None)
    if car_category is not None:
        derived = derive_allocation_score_v3(saved, car_category)
        if derived is not None:
            output['DIVERSIFICATION_DATA']['allocation_score_v3'] = derived
    # Risk progress is derived from this very v2 record too; a stale one can never match it.
    output['DIVERSIFICATION_DATA'].pop('risk_progress_v1', None)
    if car_proxies is not None:
        progress = derive_risk_progress_v1(saved, car_proxies)
        if progress is not None:
            output['DIVERSIFICATION_DATA']['risk_progress_v1'] = progress
    # Concentration facts measured beside the score on the same frozen inputs;
    # a failed build stays explicit instead of silently omitting the block.
    try:
        # Mirror the score's own failure modes: the record's reconciled input
        # flags and, when the score itself is unavailable, its failure reason.
        blocking = set(saved.get('input_flags') or ()) & (FATAL_FLAGS | {'unsupported_risk'})
        if saved.get('status') == 'unavailable' and saved.get('warnings'):
            blocking |= set(saved['warnings']) & (FATAL_FLAGS | {'unsupported_risk'})
        if blocking:
            concentration = concentration_v1.unavailable_block(as_of_date, [sorted(blocking)[0]])
        else:
            concentration = concentration_v1.build_block(
                positions, allocation_config, float(data['TOTAL_ASSETS']), as_of_date, v2_result=saved)
            concentration_v1.match_decisions(
                concentration, allocation_config.get('concentration_decisions'), as_of_date,
                allocation_config)
    except Exception as error:
        reason = str(error) or error.__class__.__name__
        concentration = concentration_v1.unavailable_block(as_of_date, [reason])
    output['DIVERSIFICATION_DATA']['concentration_v1'] = concentration
    return output


def enrich_snapshot_file(source_path, output_path, *, config=None, cache_dir=CACHE_DIR, allow_network=True,
                         monthly_returns=None, source_provenance=None, previous_combined_data=None,
                         car_category=None, car_proxies=None):
    """Create a derived artifact without changing original snapshots or latest pointers."""
    source = Path(source_path).resolve()
    destination = Path(output_path).resolve()
    snapshot_dir = (DATA_DIR / "snapshots").resolve()
    if (destination == source or destination.parent == source.parent
            or destination == snapshot_dir or snapshot_dir in destination.parents
            or destination.name in {"combined_data_latest.json", "final_data.json"}):
        raise ValueError("Derived results must be outside the source and automatic snapshot directories")
    if destination.exists():
        raise FileExistsError("The derived result already exists; choose a new output path")
    raw = source.read_bytes()
    payload = json.loads(raw)
    data = payload.get("data", payload)
    as_of = iso_date(payload.get("as_of_date") or data.get("DATA_METADATA", {}).get("last_updated"))
    enriched = enrich_combined_data(data, as_of_date=as_of, config=config, cache_dir=cache_dir,
                                    allow_network=allow_network, monthly_returns=monthly_returns,
                                    source_provenance=source_provenance, previous_combined_data=previous_combined_data,
                                    car_category=car_category, car_proxies=car_proxies)
    if (enriched.get('DIVERSIFICATION_DATA') is not data.get('DIVERSIFICATION_DATA')
            and 'allocation_score_v2' in enriched.get('DIVERSIFICATION_DATA', {})):
        from copy import deepcopy
        result = deepcopy(payload)
        target = result['data'] if 'data' in result else result
        target_dd = target.setdefault('DIVERSIFICATION_DATA', {})
        target_dd['allocation_score_v2'] = enriched['DIVERSIFICATION_DATA']['allocation_score_v2']
        # The derived v3 belongs to this very v2; an older one in the source cannot match it.
        target_dd.pop('allocation_score_v3', None)
        if 'allocation_score_v3' in enriched['DIVERSIFICATION_DATA']:
            target_dd['allocation_score_v3'] = deepcopy(enriched['DIVERSIFICATION_DATA']['allocation_score_v3'])
        target_dd.pop('risk_progress_v1', None)
        if 'risk_progress_v1' in enriched['DIVERSIFICATION_DATA']:
            target_dd['risk_progress_v1'] = deepcopy(enriched['DIVERSIFICATION_DATA']['risk_progress_v1'])
        if 'concentration_v1' in enriched['DIVERSIFICATION_DATA']:
            target_dd['concentration_v1'] = deepcopy(enriched['DIVERSIFICATION_DATA']['concentration_v1'])
        result['allocation_score_v2_enrichment'] = {
            'source_snapshot_sha256': hashlib.sha256(raw).hexdigest(),
            'calculated_at': datetime.now(timezone.utc).isoformat(), 'retrospective': True,
        }
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('x', encoding='utf-8') as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        return result
    # With no allocation settings, no analytics were calculated or replaced.
    result = payload
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
    return result
