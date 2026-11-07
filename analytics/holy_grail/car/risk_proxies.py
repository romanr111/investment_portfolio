"""Frozen block of retrospective used-vehicle proxy series for the risk-progress car scenarios.

The owner's car business has no return series, so risk progress tests it with public series
that stand in for "the business behaves like X": wholesale and retail price indexes (US, EU,
Ukraine) and a basket of listed remarketers. Each series becomes monthly simple returns. The block
freezes them with the SHA-256 of the raw files, so a run replays offline and proves its data
vintage. These are category proxies, never the return of any individual business.
"""
import argparse
import json
import math
from pathlib import Path

import pandas as pd

from analytics.holy_grail.car import category_data as data
from analytics.holy_grail.fingerprint import completed_month_end, fingerprint
from analytics.holy_grail.paths import CAR_PROXIES_BLOCK as LATEST_BLOCK

VERSION = 'car_proxies_v2'
PROXIES_V1 = {
    'manheim_wholesale': dict(label='Manheim Used Vehicle Value Index (US wholesale, SA)', channel='wholesale_price',
                              source='manheim.xlsx', confidence='high'),
    'bls_used_retail': dict(label='BLS CPI used cars and trucks (US retail, SA)', channel='retail_price',
                            source='bls_cu_transport.txt', confidence='high'),
    'auto1_wholesale_eu': dict(label='AUTO1 Group Price Index (EU wholesale, SA)', channel='wholesale_price',
                               source='auto1_index.html', confidence='medium (scraped page)'),
    'listed_remarketers': dict(label='Equal-weight CPRT/KMX/OPLN total return (listed remarketers)', channel='equity',
                               source='proxy_csv', confidence='market-priced'),
}
PROXIES = dict(PROXIES_V1, ukraine_vehicle_cpi=dict(
    label='Ukrstat CPI purchase of vehicles (Ukraine retail, USD at NBU monthly mean rate)', channel='retail_price',
    source='ukrstat_cpi_07_1.csv', fx_source='nbu_usd_uah_daily.json',
    confidence='medium (official CPI, new and used vehicles mixed)'))
BLS_SERIES = 'CUSR0000SETA02'
BASKET = ('CPRT', 'KMX', 'OPLN')
METHOD_V1 = {'version': 'car_proxies_v1', 'proxies': {k: dict(v) for k, v in PROXIES_V1.items()},
             'returns': 'monthly_simple', 'history_months': 120, 'minimum_months': 36, 'max_lag_months': 1,
             'basket': 'equal_weight_all_names_required', 'basket_names': list(BASKET)}
METHOD = dict(METHOD_V1, version=VERSION, proxies={k: dict(v) for k, v in PROXIES.items()},
              ukraine_usd='uah_index_times_previous_over_current_nbu_monthly_mean_rate')
# Saved records embed the block they used, so every released method stays readable.
# `validate_block` and risk_progress_v1 keep reading exactly these two versions.
METHODS = {METHOD_V1['version']: METHOD_V1, VERSION: METHOD}
# car_proxies_v3 (normal collection): the listed basket is collected automatically, the price indexes are
# imported from an earlier v1/v2 block with their own dates. Read by `inspect_block` only.
VERSION_V3 = 'car_proxies_v3'
PROXIES_V3 = {k: dict(v) for k, v in PROXIES.items()}
PROXIES_V3['listed_remarketers'] = dict(PROXIES['listed_remarketers'], source='yfinance_auto_adjust')
# `history_months` (120) is inherited and applies to the imported series; the collected basket uses `basket_history_months`.
METHOD_V3 = dict(METHOD, version=VERSION_V3, proxies=PROXIES_V3, basket_history_months=60,
                 basket_collection='yfinance_auto_adjusted_monthly_usd_total_return',
                 basket_aggregation='mean_skipna_false_on_same_month',
                 provenance=['auto_collected', 'imported:<block_fingerprint>'])
INSPECT_METHODS = {VERSION: METHOD, VERSION_V3: METHOD_V3}
IMPORT_METHODS = dict(METHODS, **{VERSION_V3: METHOD_V3})
MAIN_SERIES = 'listed_remarketers'
LIMITATIONS = [
    'Category proxies, not the return of any individual business.',
    'Price indexes move far less than a leveraged inventory business; the listed basket is priced like equities.',
    'Manheim history is revised; AUTO1 is scraped from a web page; the sha256 of each raw file names the vintage.',
    'The Ukrstat index mixes new and used vehicles bought by households (no national car sub-item is published).',
]


def load_block(path=LATEST_BLOCK):
    """None when no block file exists; an unreadable file, or valid JSON that is not an object, becomes an invalid
    block, never a silent absence."""
    path = Path(path)
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {'unreadable': True}
    return value if isinstance(value, dict) else {'unreadable': True}


class MissingBasketNames(ValueError):
    """The proxy CSV lacks one of the named basket constituents."""


def _returns(name, raw, proxy_csv):
    raw = Path(raw)
    if name == 'manheim_wholesale':
        return data.manheim_frame(raw / 'manheim.xlsx')[data.MANHEIM_INDEX].pct_change(fill_method=None)
    if name == 'bls_used_retail':
        return data.bls_frame(raw / 'bls_cu_transport.txt')[BLS_SERIES].pct_change(fill_method=None)
    if name == 'auto1_wholesale_eu':
        return data.auto1_series(raw / 'auto1_index.html').pct_change(fill_method=None)
    if name == 'ukraine_vehicle_cpi':
        cpi = data.ukrstat_cpi_series(raw / PROXIES[name]['source'])
        rate = data.nbu_monthly_rate(raw / PROXIES[name]['fx_source'])
        # A UAH price relative times the USD value of a hryvnia this month versus last month.
        return cpi / 100 * (rate.shift(1) / rate).reindex(cpi.index) - 1
    frame = pd.read_csv(proxy_csv, index_col=0)
    frame.index = pd.to_datetime(frame.index).tz_localize(None).normalize()
    frame.columns = [c[3:] if c.startswith('yf:') else c for c in frame.columns]
    if frame.columns.duplicated().any():
        raise ValueError('duplicate basket columns in the proxy CSV')
    missing = [name for name in BASKET if name not in frame.columns]
    if missing:
        raise MissingBasketNames(f'proxy CSV lacks {missing}')
    return frame[list(BASKET)].mean(axis=1, skipna=False)  # only the named constituents; other columns are ignored


def _clean(series):
    return {d.date().isoformat(): float(v) for d, v in series.dropna().items()}


def series_map(block):
    return {name: pd.Series({pd.Timestamp(k): float(v) for k, v in item['returns'].items()}).sort_index()
            for name, item in block['series'].items()}


def build_block(raw_dir, proxy_csv, as_of_date):
    """Freeze the proxy returns (no network). A stale or short series is left out and named in `excluded`."""
    completed = completed_month_end(as_of_date)
    series, excluded = {}, {}
    for name, meta in PROXIES.items():
        try:
            returns = _returns(name, raw_dir, proxy_csv).dropna()
        except MissingBasketNames:
            excluded[name] = 'missing_basket_names'
            continue
        except (KeyError, ValueError, OSError):
            excluded[name] = 'source_unreadable'
            continue
        returns = returns[returns.index <= completed].iloc[-METHOD['history_months']:]
        if len(returns) < METHOD['minimum_months']:
            excluded[name] = 'insufficient_history'
        elif returns.index[-1] < completed - pd.offsets.MonthEnd(METHOD['max_lag_months']):
            excluded[name] = 'stale'
        else:
            series[name] = dict(meta, returns=_clean(returns), last_month=returns.index[-1].date().isoformat())
    if not series:
        raise ValueError('No usable proxy series')
    used = {meta[key] for meta in PROXIES.values() for key in ('source', 'fx_source') if key in meta}
    manifest = {k: v for k, v in data.manifest(raw_dir).items() if k in used}
    block = dict(version=VERSION, as_of_date=as_of_date, cutoff_month=completed.date().isoformat(), method=METHOD,
                 series=series, excluded=excluded,
                 sources=dict(raw=manifest, proxy_csv_sha256=data.sha256(proxy_csv)), limitations=LIMITATIONS)
    block['fingerprint'] = fingerprint(block)
    return block


def _inspect(block, as_of_date, methods):
    """Block integrity and per-series freshness, reported separately (a stale series never breaks integrity)."""
    out = dict(integrity=False, reason=None, series={}, excluded={})
    try:
        method = methods.get(block.get('version')) if isinstance(block, dict) else None
        if method is None:
            return dict(out, reason='unknown_version')
        if block.get('method') != method:
            return dict(out, reason='method_mismatch')
        if block.get('fingerprint') != fingerprint({k: v for k, v in block.items() if k != 'fingerprint'}):
            return dict(out, reason='fingerprint_mismatch')
        completed = completed_month_end(as_of_date)
        if not isinstance(block['series'], dict) or set(block['series']) - set(method['proxies']):
            return dict(out, reason='unknown_series')
        if pd.Timestamp(block['cutoff_month']) > completed:
            return dict(out, reason='future_cutoff')
        floor = completed - pd.offsets.MonthEnd(method['max_lag_months'])
        mapped = series_map(block)
        series = {}
        for name, item in block['series'].items():
            values = mapped[name]
            if (not len(values) or not values.index.is_month_end.all() or values.index.max() > completed
                    or not all(math.isfinite(v) for v in values)
                    or item['last_month'] != values.index.max().date().isoformat()):
                return dict(out, reason='invalid_series:' + name)
            if method['version'] == VERSION_V3 and (
                    item['observations'] != len(values) or not isinstance(item['observations'], int)
                    or not (item['provenance'] == 'auto_collected' or str(item['provenance']).startswith('imported:'))):
                return dict(out, reason='invalid_series:' + name)
            reason = ('insufficient_history' if len(values) < method['minimum_months']
                      else 'stale' if values.index.max() < floor else None)
            series[name] = dict(ok=reason is None, reason=reason, observations=len(values),
                                last_month=values.index.max().date().isoformat())
        excluded = block.get('excluded')
        return dict(out, integrity=True, series=series, excluded=dict(excluded) if isinstance(excluded, dict) else {})
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return dict(out, integrity=False, reason='malformed_block', series={})


def inspect_block(block, as_of_date):
    """Narrow gate of risk_progress_v2 for car_proxies_v2/v3 blocks.

    `integrity` covers version, method, fingerprint, calendar and finite month-end values; every series is then
    judged on its own (>= 36 months, last month within one month of the cutoff). The main basket decides the
    headline, an auxiliary series only the comparison. `validate_block` (v1/v2 replay) is left unchanged.
    """
    return _inspect(block, as_of_date, INSPECT_METHODS)


def import_series(block, as_of_date):
    """Auxiliary series of an earlier v1/v2/v3 block: (series, info). Months after the new cutoff are cut off."""
    # Integrity is judged against the block's own date; the new cutoff only trims later months.
    check = _inspect(block, block.get('as_of_date') if isinstance(block, dict) else None, IMPORT_METHODS)
    if not check['integrity']:
        return {}, dict(rejected=check['reason'])
    completed = completed_month_end(as_of_date)
    series, trimmed = {}, []
    for name, values in series_map(block).items():
        if name == MAIN_SERIES:
            continue
        kept = values[values.index <= completed]
        if len(kept) < len(values):
            trimmed.append(name)
        if not len(kept):
            continue
        series[name] = dict(PROXIES_V3[name], returns=_clean(kept), last_month=kept.index[-1].date().isoformat(),
                            observations=len(kept), provenance='imported:' + block['fingerprint'])
    return series, dict(fingerprint=block['fingerprint'], version=block['version'], as_of_date=block['as_of_date'],
                        trimmed_series=sorted(trimmed))


def build_block_v3(as_of_date, *, basket_returns, basket_sources, basket_excluded=None, imported_block=None):
    """Freeze the auto-collected basket plus imported auxiliary series (no network).

    A basket that exists but is short or stale stays in `series` (inspect_block names the reason); one with
    no usable months is left out and named in `excluded`. The block exists even without a main series.
    """
    completed = completed_month_end(as_of_date)
    series, excluded = {}, {}
    returns = basket_returns
    if returns is not None:
        # The window is the last N calendar months; a gap is dropped, never filled with an older month.
        first = completed - pd.offsets.MonthEnd(METHOD_V3['basket_history_months'])
        returns = returns[(returns.index > first) & (returns.index <= completed)].dropna()
    if returns is not None and len(returns):
        series[MAIN_SERIES] = dict(PROXIES_V3[MAIN_SERIES], returns=_clean(returns),
                                   last_month=returns.index[-1].date().isoformat(), observations=len(returns),
                                   provenance='auto_collected')
    else:
        excluded[MAIN_SERIES] = basket_excluded or 'no_common_months'
    imported, info = import_series(imported_block, as_of_date) if imported_block is not None else ({}, None)
    series.update(imported)
    block = dict(version=VERSION_V3, as_of_date=pd.Timestamp(as_of_date).date().isoformat(),
                 cutoff_month=completed.date().isoformat(), method=METHOD_V3, series=series, excluded=excluded,
                 sources=dict(basket=dict(symbols=basket_sources), imported=info),
                 limitations=LIMITATIONS + ['The listed basket is collected automatically (Yahoo Finance, '
                                            'auto-adjusted closes, USD); imported price indexes keep their own dates.'])
    block['fingerprint'] = fingerprint(block)
    return block


def validate_block(block, as_of_date):
    """Integrity and look-ahead gate for a frozen block."""
    try:
        method = METHODS.get(block.get('version')) if isinstance(block, dict) else None
        if method is None or block.get('method') != method:
            return False
        if block.get('fingerprint') != fingerprint({k: v for k, v in block.items() if k != 'fingerprint'}):
            return False
        completed = completed_month_end(as_of_date)
        if not block['series'] or set(block['series']) - set(method['proxies']) or pd.Timestamp(block['cutoff_month']) > completed:
            return False
        mapped = series_map(block)
        for name, item in block['series'].items():
            values = mapped[name]
            if len(values) < method['minimum_months'] or not values.index.is_month_end.all() or values.index.max() > completed:
                return False
            if values.index.max() < completed - pd.offsets.MonthEnd(method['max_lag_months']):
                return False
            if not all(math.isfinite(v) for v in values) or item['last_month'] != values.index.max().date().isoformat():
                return False
        return True
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return False


def _report(block_path):
    block = json.loads(Path(block_path).read_text(encoding='utf-8'))
    print(f"{block['version']} as of {block['as_of_date']} cutoff {block['cutoff_month']} fingerprint {block['fingerprint'][:12]}")
    for name, values in series_map(block).items():
        print(f"  {name}: {len(values)} months {values.index[0].date()}..{values.index[-1].date()} "
              f"annual vol {values.std() * math.sqrt(12) * 100:.1f}% ({block['series'][name]['channel']}, "
              f"{block['series'][name]['confidence']})")
    for name, reason in block['excluded'].items():
        print(f'  {name}: excluded ({reason})')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    build = sub.add_parser('build', help='freeze the proxy series into one block file (offline, never overwrites)')
    build.add_argument('--raw', required=True, help='directory with manheim.xlsx, bls_cu_transport.txt, auto1_index.html, '
                                                    'ukrstat_cpi_07_1.csv, nbu_usd_uah_daily.json')
    build.add_argument('--proxy-csv', required=True, help='monthly returns of the listed names (yf:CPRT, ...)')
    build.add_argument('--as-of', required=True)
    build.add_argument('--out', required=True)
    report = sub.add_parser('report', help='print the series in a block file')
    report.add_argument('--block', required=True)
    ukraine = sub.add_parser('fetch-ukraine', help='download the Ukrstat vehicle CPI and NBU USD rates into a raw '
                                                   'directory (network, never overwrites)')
    ukraine.add_argument('--raw', required=True)
    ukraine.add_argument('--as-of', required=True)
    args = parser.parse_args()
    if args.command == 'fetch-ukraine':
        try:
            for name, item in data.fetch_ukraine(args.raw, args.as_of).items():
                print(f"{name}: {item['bytes']} bytes sha256 {item['sha256'][:12]}")
        except (ValueError, OSError) as error:
            raise SystemExit(f'Not fetched: {error}')
    elif args.command == 'build':
        target = Path(args.out)
        if target.exists():
            raise SystemExit('Output exists; choose a new path.')
        try:
            block = build_block(args.raw, args.proxy_csv, args.as_of)
        except (ValueError, OSError, KeyError) as error:
            raise SystemExit(f'Block not built: {error}')
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('x', encoding='utf-8') as handle:
            json.dump(block, handle, ensure_ascii=False, allow_nan=False)
        print(f"block written: {target} fingerprint {block['fingerprint'][:12]}")
        _report(target)
    else:
        _report(args.block)


if __name__ == '__main__':
    main()
