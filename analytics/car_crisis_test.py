"""Crisis-behaviour test of the used-vehicle price index against portfolio groups (H1-H3).

Offline: reads the raw files recorded by `analytics.car_category_data` plus a long
monthly-returns CSV. The Manheim index is a wholesale used-vehicle price index, a
category proxy: it is not the return of any individual flipping business.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from analytics import car_category_data as data

# (start, end, shock type). The start is the month-end before the episode.
EPISODES = {'gfc_2008_09': ('2008-06-30', '2009-12-31', 'demand'),
            'covid_2020': ('2020-01-31', '2020-12-31', 'demand'),
            'rates_2022': ('2021-12-31', '2023-06-30', 'rates')}
STRESS_QUANTILE = .2
DRAWDOWN_BAND = .05
MIN_OBS = 36

# Volumes reported by industry, kept as cited constants (not recomputed here).
USED_VOLUMES = [
    dict(episode='2007_2008', used_change=-0.12, used_basis='US retail used 41.4M -> 36.5M (Manheim, 2009 report)',
         new_window=('2007-12-31', '2008-12-31'),
         source='https://press.manheim.com/2009-01-24-2009-Used-Car-Market-Report-Fundamental-Transformations-Taking-Hold-In-Remarketing-Industry'),
    dict(episode='2008_2009_franchised', used_change=-0.03, new_change=-0.21,
         used_basis='franchised dealers, used vs new units 2009 (Manheim, 2010 report)',
         source='https://press.manheim.com/2010-02-13-2010-Used-Car-Market-Report-Examines-Long-Term-Structural-Shifts-in-Automotive-Industry-Critical-Role-of-Marketing'),
    dict(episode='2019_2020', used_change=round(36.7 / 40.0 - 1, 4), new_window=('2019-12-31', '2020-12-31'),
         used_basis='US total used 40.0M -> 36.7M (Cox via Auto Remarketing, secondary)',
         source='https://www.autoremarketing.com/?p=57463'),
]
# Gross margin on purchased vehicles resold as-is, before overheads (Copart 10-K lines).
COPART_PURCHASED_MARGIN = {'FY2008': .191, 'FY2009': .170, 'FY2010': .199, 'FY2021': .136, 'FY2022': .097,
                           'FY2023': .085, 'FY2024': .083, 'FY2025': .111, 'FY2026': .115}


def _pair(a, b):
    return pd.concat([a, b], axis=1).dropna()


def correlation(a, b):
    pair = _pair(a, b)
    if len(pair) < 12 or (pair.std() == 0).any():
        return dict(r=None, n=len(pair))
    return dict(r=round(float(pair.iloc[:, 0].corr(pair.iloc[:, 1])), 4), n=len(pair))


def levels(returns):
    return (1 + returns.fillna(0)).cumprod()


def lag_table(price, equity, lags=range(-6, 7)):
    """Positive lag: the price series reacts later than the equity series."""
    return {int(lag): correlation(price, equity.shift(lag)) for lag in lags}


def quarterly_returns(level):
    quarter = level.groupby(level.index.to_period('Q')).last()
    return quarter.pct_change()


def stress_months(equity):
    return equity[equity <= equity.quantile(STRESS_QUANTILE)].index


def conditional_stats(price, equity):
    pair = _pair(price, equity)
    pair.columns = ['price', 'equity']
    stress = pair[pair['equity'] <= pair['equity'].quantile(STRESS_QUANTILE)]

    def beta(frame):
        return round(float(np.polyfit(frame['equity'], frame['price'], 1)[0]), 4) if len(frame) > 5 else None

    return dict(n=len(pair), stress_n=len(stress),
                mean_price_in_stress=round(float(stress['price'].mean()), 4),
                share_price_negative_in_stress=round(float((stress['price'] < 0).mean()), 4),
                corr_all=correlation(pair['price'], pair['equity'])['r'],
                corr_stress=correlation(stress['price'], stress['equity'])['r'],
                beta_down=beta(pair[pair['equity'] < 0]), beta_up=beta(pair[pair['equity'] > 0]))


def stress_overlap(price_level, equity_level):
    """P(one in its worst quintile of 3-month returns | the other is), against the 20% base rate."""
    p3 = (price_level / price_level.shift(3) - 1)
    e3 = (equity_level / equity_level.shift(3) - 1)
    pair = _pair(p3, e3)
    pair.columns = ['price', 'equity']
    p_stress = pair['price'] <= pair['price'].quantile(STRESS_QUANTILE)
    e_stress = pair['equity'] <= pair['equity'].quantile(STRESS_QUANTILE)
    return dict(n=len(pair), base_rate=STRESS_QUANTILE,
                price_stress_given_equity_stress=round(float(p_stress[e_stress].mean()), 4),
                equity_stress_given_price_stress=round(float(e_stress[p_stress].mean()), 4))


def _months(a, b):
    return (b.year - a.year) * 12 + b.month - a.month


def episode_metrics(level, start, end):
    """Peak-to-trough inside the window and months to regain the pre-episode peak (within the band)."""
    window = level.loc[pd.Timestamp(start):pd.Timestamp(end)]
    prior_peak = float(level.loc[:pd.Timestamp(start)].max())
    trough_date = window.idxmin()
    after = level.loc[trough_date:]
    recovered = after[after >= prior_peak * (1 - DRAWDOWN_BAND)]
    return dict(change=round(float(window.iloc[-1] / window.iloc[0] - 1), 4),
                trough=trough_date.date().isoformat(), trough_change_from_start=round(float(window.min() / window.iloc[0] - 1), 4),
                months_trough_to_recovery=_months(trough_date, recovered.index[0]) if len(recovered) else None)


def episode_table(levels_by_name, spy_level):
    out = {}
    for name, (start, end, shock) in EPISODES.items():
        row = dict(shock=shock, window=[start, end])
        for label, level in levels_by_name.items():
            row[label] = episode_metrics(level.dropna(), start, end)
        row['spy'] = episode_metrics(spy_level.dropna(), start, end)
        for label in levels_by_name:
            a, b = row[label]['trough'], row['spy']['trough']
            row[f'{label}_trough_minus_spy_trough_months'] = _months(pd.Timestamp(b), pd.Timestamp(a))
        out[name] = row
    return out


def volume_table(raw_dir):
    units = data.new_vehicle_units(raw_dir)
    yearly = units.groupby(units.index.year).sum()
    rows = []
    for item in USED_VOLUMES:
        row = {k: v for k, v in item.items() if k != 'new_window'}
        if 'new_window' in item:
            a, b = (pd.Timestamp(d).year for d in item['new_window'])
            row['new_change'] = round(float(yearly[b] / yearly[a] - 1), 4)
        row['used_falls_less_than_new'] = row['used_change'] > row['new_change']
        rows.append(row)
    return rows


def group_table(price, long_returns, equity):
    stress = stress_months(equity.dropna())
    out = {}
    for group in long_returns.columns:
        series = long_returns[group]
        full, in_stress = correlation(price, series), correlation(price.loc[price.index.intersection(stress)],
                                                                  series.loc[series.index.intersection(stress)])
        out[group] = dict(first_month=series.first_valid_index().date().isoformat(),
                          corr_full=full, corr_in_spy_stress_months=in_stress,
                          covers_2008=bool(series.first_valid_index() <= pd.Timestamp('2008-06-30')))
    return out


def run(raw_dir, long_returns_csv):
    raw = Path(raw_dir)
    manheim = data.manheim_frame(raw / 'manheim.xlsx')[data.MANHEIM_INDEX]
    bls_file = raw / 'bls_cu_transport.txt'
    bls = data.bls_frame(bls_file)['CUSR0000SETA02'] if bls_file.exists() else None
    auto1 = data.auto1_series(raw / 'auto1_index.html')
    longr = pd.read_csv(long_returns_csv, index_col=0, parse_dates=True)
    spy = longr['equity_us']
    price_ret = manheim.pct_change()
    price_level = manheim
    spy_level = levels(spy)
    pair_start = max(price_ret.first_valid_index(), spy.first_valid_index())
    subperiods = {'1997_2007': ('1997-01-31', '2007-12-31'), '2008_2012': ('2008-01-31', '2012-12-31'),
                  '2013_2019': ('2013-01-31', '2019-12-31'), '2020_2026': ('2020-01-31', '2026-09-30')}
    q_price, q_spy = quarterly_returns(price_level), quarterly_returns(spy_level)
    q_price.index, q_spy.index = q_price.index.to_timestamp(how='end'), q_spy.index.to_timestamp(how='end')
    return dict(
        generated_for='category proxy (wholesale used-vehicle price index), not a business return',
        sample=dict(price_first=price_ret.first_valid_index().date().isoformat(), pair_start=pair_start.date().isoformat(),
                    last=price_ret.last_valid_index().date().isoformat()),
        raw_manifest=data.manifest(raw), long_returns_sha256=data.sha256(long_returns_csv),
        h1_volumes=volume_table(raw),
        h2_prices=dict(
            lag_corr_manheim_vs_spy=lag_table(price_ret, spy),
            lag_corr_bls_used_cpi_vs_spy=None if bls is None else lag_table(bls.pct_change(), spy),
            lag_corr_auto1_vs_spy=lag_table(auto1.pct_change(), spy),
            lag0_by_subperiod={k: correlation(price_ret.loc[a:b], spy.loc[a:b]) for k, (a, b) in subperiods.items()},
            quarterly_nonoverlapping_corr=correlation(q_price, q_spy),
            conditional_on_spy_worst_quintile=conditional_stats(price_ret, spy),
            conditional_on_spy_worst_quintile_ex_2020=conditional_stats(
                price_ret[~((price_ret.index >= '2020-01-31') & (price_ret.index <= '2020-12-31'))],
                spy[~((spy.index >= '2020-01-31') & (spy.index <= '2020-12-31'))]),
            three_month_stress_overlap=stress_overlap(price_level, spy_level),
            episodes=episode_table(dict(manheim=price_level), spy_level),
            groups_vs_manheim=group_table(price_ret, longr, spy)),
        h3_spreads=dict(copart_purchased_vehicle_gross_margin=COPART_PURCHASED_MARGIN,
                        note='as-is resale before overheads, 10-K lines; gfc margins held, 2022-24 compressed'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', required=True)
    parser.add_argument('--long-returns', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--fetch-manheim-url', help='download all raw files into the (new) --raw directory first')
    parser.add_argument('--as-of', help='snapshot as_of_date for the long asset history (with --fetch-manheim-url)')
    parser.add_argument('--bls-contact', help='contact (e.g. an email you choose) for the BLS User-Agent; without it the BLS CPI file is skipped')
    args = parser.parse_args()
    if args.fetch_manheim_url:
        from analytics.allocation_inputs import GROUPS
        data.fetch_raw(args.raw, args.fetch_manheim_url, args.bls_contact)
        symbols = {g: rep for g, (_, rep) in GROUPS.items() if rep and not rep.endswith('.L')}
        data.long_group_returns(args.as_of, symbols).to_csv(args.long_returns)
    result = run(args.raw, args.long_returns)
    Path(args.out).write_text(json.dumps(result, indent=1, default=str), encoding='utf-8')
    print(json.dumps(result['h2_prices']['conditional_on_spy_worst_quintile'], indent=1))


if __name__ == '__main__':
    main()
