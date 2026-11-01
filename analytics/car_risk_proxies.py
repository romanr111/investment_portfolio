"""Frozen block of retrospective used-vehicle proxy series for the risk-progress car scenarios.

The owner's car business has no return series, so risk progress tests it with public series
that stand in for "the business behaves like X": wholesale and retail price indexes (US, EU)
and a basket of listed remarketers. Each series becomes monthly simple returns. The block
freezes them with the SHA-256 of the raw files, so a run replays offline and proves its data
vintage. These are category proxies, never the return of any individual business.
"""
import argparse
import json
import math
from pathlib import Path

import pandas as pd

from analytics import car_category_data as data
from analytics.holy_grail import completed_month_end, fingerprint

VERSION = 'car_proxies_v1'
PROXIES = {
    'manheim_wholesale': dict(label='Manheim Used Vehicle Value Index (US wholesale, SA)', channel='wholesale_price',
                              source='manheim.xlsx', confidence='high'),
    'bls_used_retail': dict(label='BLS CPI used cars and trucks (US retail, SA)', channel='retail_price',
                            source='bls_cu_transport.txt', confidence='high'),
    'auto1_wholesale_eu': dict(label='AUTO1 Group Price Index (EU wholesale, SA)', channel='wholesale_price',
                               source='auto1_index.html', confidence='medium (scraped page)'),
    'listed_remarketers': dict(label='Equal-weight CPRT/KMX/OPLN total return (listed remarketers)', channel='equity',
                               source='proxy_csv', confidence='market-priced'),
}
BLS_SERIES = 'CUSR0000SETA02'
BASKET = ('CPRT', 'KMX', 'OPLN')
METHOD = {'version': VERSION, 'proxies': {k: dict(v) for k, v in PROXIES.items()}, 'returns': 'monthly_simple',
          'history_months': 120, 'minimum_months': 36, 'max_lag_months': 1, 'basket': 'equal_weight_all_names_required',
          'basket_names': list(BASKET)}
LIMITATIONS = [
    'Category proxies, not the return of any individual business.',
    'Price indexes move far less than a leveraged inventory business; the listed basket is priced like equities.',
    'Manheim history is revised; AUTO1 is scraped from a web page; the sha256 of each raw file names the vintage.',
]
LATEST_BLOCK = Path(__file__).resolve().parents[1] / 'data' / 'car_category' / 'proxies_latest.json'


def load_block(path=LATEST_BLOCK):
    """None when no block file exists; an unreadable file becomes an invalid block, never a silent absence."""
    path = Path(path)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {'unreadable': True}


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
    used = {meta['source'] for meta in PROXIES.values()}
    manifest = {k: v for k, v in data.manifest(raw_dir).items() if k in used}
    block = dict(version=VERSION, as_of_date=as_of_date, cutoff_month=completed.date().isoformat(), method=METHOD,
                 series=series, excluded=excluded,
                 sources=dict(raw=manifest, proxy_csv_sha256=data.sha256(proxy_csv)), limitations=LIMITATIONS)
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
        if not block['series'] or set(block['series']) - set(PROXIES) or pd.Timestamp(block['cutoff_month']) > completed:
            return False
        mapped = series_map(block)
        for name, item in block['series'].items():
            values = mapped[name]
            if len(values) < METHOD['minimum_months'] or not values.index.is_month_end.all() or values.index.max() > completed:
                return False
            if values.index.max() < completed - pd.offsets.MonthEnd(METHOD['max_lag_months']):
                return False
            if not all(math.isfinite(v) for v in values) or item['last_month'] != values.index.max().date().isoformat():
                return False
        return True
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return False


def _report(block_path):
    block = json.loads(Path(block_path).read_text(encoding='utf-8'))
    print(f"car_proxies_v1 as of {block['as_of_date']} cutoff {block['cutoff_month']} fingerprint {block['fingerprint'][:12]}")
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
    build.add_argument('--raw', required=True, help='directory with manheim.xlsx, bls_cu_transport.txt, auto1_index.html')
    build.add_argument('--proxy-csv', required=True, help='monthly returns of the listed names (yf:CPRT, ...)')
    build.add_argument('--as-of', required=True)
    build.add_argument('--out', required=True)
    report = sub.add_parser('report', help='print the series in a block file')
    report.add_argument('--block', required=True)
    args = parser.parse_args()
    if args.command == 'build':
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
