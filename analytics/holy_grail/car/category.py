"""Car-category correlation tracker: frozen input block, per-group measures, report.

The category is "buy damaged vehicles, repair, resell". Its public price channel is the
Manheim used-vehicle price index (US wholesale, seasonally adjusted). The block freezes
that index plus long asset histories so the measures replay offline and deterministically.

Every correlation is the index's correlation scaled by R (index loading, fixed at 1.0):
rho(business, group) = R * rho(index, group). R = 1 is a conditional scenario assumption:
the business inherits the standardized index's price channel, which is not a bound on the
business. Deal-level noise would lower the loading but needs the owner's own deals to
calibrate (docs/car-deal-ledger.md); financing, liquidity, repair, FX, tax and local
channels are outside the index and unbounded here. The result is a category proxy, never
the owner's returns.
"""
import json
import math
from pathlib import Path

import pandas as pd

from analytics.holy_grail.car import category_data as data
from analytics.holy_grail.fingerprint import completed_month_end, fingerprint
from analytics.holy_grail.paths import CAR_CATEGORY_BLOCK as LATEST_BLOCK

VERSION = 'car_category_v2'
CAR = 'car_business'
METHOD = {
    'version': VERSION, 'index': 'manheim_used_vehicle_value_index_sa',
    'measures': ['monthly', 'lagged_1m', 'stress_quintile'], 'selection': 'max',
    'upper_selection': 'max_over_measures',
    'stress_group': 'equity_us', 'stress_quantile': 0.2, 'min_stress_observations': 20,
    'minimum_observations': 36, 'upper_confidence_z': 1.645, 'index_loading_R': 1.0,
    'max_index_lag_months': 1,
}
LIMITATIONS = [
    'Category price index (US wholesale), not the return of any individual business.',
    'Index loading R is fixed at 1: a conditional price-channel assumption, not a measurement or a bound on the business.',
    'Financing, liquidity, FX, customs and local-war channels are not in the index.',
    'Manheim history is revised; the sha256 of each raw file identifies the vintage used.',
    'Crisis coverage before 2011-2017 is incomplete for China, EM and crypto groups.',
]
MIN_INDEX_RETURNS = 120


def load_block(path=LATEST_BLOCK):
    """None when no block file exists; an unreadable file becomes an invalid block, never a silent absence."""
    path = Path(path)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {'unreadable': True}


def _series(mapping):
    series = pd.Series({pd.Timestamp(k): float(v) for k, v in mapping.items()}).sort_index()
    return series


def index_series(block):
    return _series(block['index']['returns'])


def long_frame(block):
    return pd.DataFrame({group: _series(values) for group, values in block['long_returns'].items()})


def _clean(series):
    return {d.date().isoformat(): float(v) for d, v in series.dropna().items()}


def build_block(raw_dir, long_returns_csv, as_of_date):
    """Freeze the index and long asset histories used by the tracker (no network)."""
    raw = Path(raw_dir)
    completed = completed_month_end(as_of_date)
    levels = data.manheim_frame(raw / 'manheim.xlsx')[data.MANHEIM_INDEX]
    levels = levels[levels.index <= completed]
    # Manheim publishes about a week into the next month: one month of lag is allowed, flagged downstream.
    cutoff = levels.index[-1]
    if cutoff < completed - pd.offsets.MonthEnd(METHOD['max_index_lag_months']):
        raise ValueError('Manheim file is more than one month behind the completed month of the snapshot')
    returns = levels.pct_change().dropna()
    long = pd.read_csv(long_returns_csv, index_col=0, parse_dates=True)
    long = long[long.index <= cutoff].dropna(axis=1, how='all')
    if METHOD['stress_group'] not in long:
        raise ValueError('Long asset history lacks the stress group')
    block = dict(version=VERSION, as_of_date=as_of_date, cutoff_month=cutoff.date().isoformat(), method=METHOD,
                 index=dict(name=METHOD['index'], unit='monthly_simple_return', returns=_clean(returns)),
                 long_returns={g: _clean(long[g]) for g in long.columns},
                 sources=dict(raw=data.manifest(raw), long_returns_sha256=data.sha256(long_returns_csv)),
                 limitations=LIMITATIONS)
    block['fingerprint'] = fingerprint(block)
    return block


def validate_block(block, as_of_date):
    """Integrity and look-ahead gate for a frozen block."""
    try:
        if not isinstance(block, dict) or block.get('version') != VERSION or block.get('method') != METHOD:
            return False
        if block.get('fingerprint') != fingerprint({k: v for k, v in block.items() if k != 'fingerprint'}):
            return False
        completed = completed_month_end(as_of_date)
        cutoff = pd.Timestamp(block['cutoff_month'])
        if not cutoff.is_month_end or not completed - pd.offsets.MonthEnd(METHOD['max_index_lag_months']) <= cutoff <= completed:
            return False
        if index_series(block).index.max() != cutoff:
            return False
        frames = [index_series(block)] + [_series(v) for v in block['long_returns'].values()]
        for series in frames:
            if series.empty or not series.index.is_month_end.all() or series.index.max() > cutoff:
                return False
            if not all(math.isfinite(v) for v in series):
                return False
        return len(frames[0]) >= MIN_INDEX_RETURNS and METHOD['stress_group'] in block['long_returns']
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return False


def _pearson(left, right, minimum):
    pair = pd.concat([left, right], axis=1).dropna()
    if len(pair) < max(minimum, 4) or (pair.std() <= 0).any():
        return None
    r = float(pair.iloc[:, 0].corr(pair.iloc[:, 1]))
    return dict(r=r, n=len(pair)) if math.isfinite(r) else None


def _fisher_upper(r, n, z):
    if n <= 3:
        return None
    r = max(-.999999, min(.999999, r))
    return math.tanh(math.atanh(r) + z / math.sqrt(n - 3))


def group_measures(block, window_frame, group, months):
    """Correlation of one group with the category index, three ways, then two separate envelopes.

    The monthly and lagged measures use the window; the stress measure uses every month of the
    long history in which US equities were in their worst quintile, so its `n` is not the window.
    `point` is R times the largest correlation; `upper90` is R times the largest of the per-measure
    Fisher upper endpoints (z=1.645: nominal per-estimate, one-sided 95%), which can come from a
    different measure and sample than the point (`upper_selected`, `upper_n`). Neither is a
    confidence statement about a score or about the business.
    """
    method = METHOD
    price = index_series(block)
    series = window_frame[group]
    base = min(months, method['minimum_observations'])
    found = dict(monthly=_pearson(series, price.reindex(series.index), base),
                 lagged_1m=_pearson(series, price.shift(-1).reindex(series.index), base - 1))
    stress = None
    long = long_frame(block)
    if group in long:
        reference = long[method['stress_group']].dropna()
        reference = reference[reference.index >= price.index[0]]
        stress_months = reference[reference <= reference.quantile(method['stress_quantile'])].index
        stress = _pearson(long[group].reindex(stress_months), price.reindex(stress_months),
                          method['min_stress_observations'])
    found['stress_quintile'] = stress
    available = {name: m for name, m in found.items() if m is not None}
    out = dict(found, selected=None, point=None, upper90=None, n=None, upper_selected=None, upper_n=None)
    if available:
        name = max(available, key=lambda key: (available[key]['r'], key))
        chosen, loading = available[name], method['index_loading_R']
        out.update(selected=name, n=chosen['n'], point=loading * chosen['r'])
        uppers = {key: _fisher_upper(m['r'], m['n'], method['upper_confidence_z']) for key, m in available.items()}
        uppers = {key: value for key, value in uppers.items() if value is not None}
        if uppers:
            top = max(uppers, key=lambda key: (uppers[key], key))
            out.update(upper_selected=top, upper_n=available[top]['n'], upper90=min(1., loading * uppers[top]))
    return out
