"""Automatic collection of the car-business basket (CPRT/KMX/OPLN) for risk_progress_v2.

Normal collection only: it reuses the history collector (Yahoo fetch, month-end rules, immutable cache) and
freezes the result with the imported price indexes into one car_proxies_v3 block. Replay, offline and view
code never call it; they receive the frozen block.
"""
import pandas as pd

from analytics.holy_grail import market_history
from analytics.holy_grail.car import risk_proxies
from analytics.holy_grail.fingerprint import completed_month_end
from analytics.holy_grail.paths import CACHE_DIR

SERIES_PREFIX = 'car_basket:'
SOURCE_KEYS = ('provider', 'currency', 'retrieved_at', 'source_revision', 'status', 'error_type')


def collect_basket(as_of_date, *, cache_dir=CACHE_DIR, allow_network=True, fetch_market=None):
    """(monthly basket returns or None, per-symbol sources, exclusion reason or None).

    Equal-weight mean of the three names on the same month, no forward fill: a month missing for any name is
    absent, and a missing name gives no basket at all (never a mean of two).
    """
    exposures = [dict(series=SERIES_PREFIX + name, symbol=name, provider='yfinance', collection_priority=0,
                      value_usd=0.) for name in risk_proxies.BASKET]
    frame, provenance, _ = market_history.collect_return_history(
        exposures, as_of_date=as_of_date, cache_dir=cache_dir, allow_network=allow_network, fetch_market=fetch_market)
    sources = {name: {k: v for k, v in provenance.get(SERIES_PREFIX + name, {'status': 'unavailable'}).items()
                      if k in SOURCE_KEYS} for name in risk_proxies.BASKET}
    columns = [SERIES_PREFIX + name for name in risk_proxies.BASKET]
    missing = [name for name, column in zip(risk_proxies.BASKET, columns) if column not in frame.columns]
    if missing:
        return None, sources, 'collection_failed:' + ','.join(missing)
    basket = frame[columns].mean(axis=1, skipna=False)  # gaps stay NaN; the block builder windows and drops them
    return basket[basket.index <= completed_month_end(as_of_date)], sources, None


def collect_car_proxies_block(as_of_date, imported_block=None, *, cache_dir=CACHE_DIR, allow_network=True,
                              fetch_market=None):
    """Frozen car_proxies_v3 block; `imported_block` (an earlier v1/v2 block) only supplies the price indexes."""
    basket, sources, reason = collect_basket(as_of_date, cache_dir=cache_dir, allow_network=allow_network,
                                             fetch_market=fetch_market)
    return risk_proxies.build_block_v3(as_of_date, basket_returns=basket, basket_sources=sources,
                                       basket_excluded=reason, imported_block=imported_block)
