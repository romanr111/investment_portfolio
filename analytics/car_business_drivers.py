"""Public driver panel for the car-business correlation bound.

Powers the diagnostic described in the car-business bound plan. The panel
feeds `analytics.car_business_bound` only; it never writes to
`DIVERSIFICATION_DATA` and is never a score input on its own.

The two physical drivers are the US used-vehicle CPI (BLS series
CUSR0000SETA02) and the USD/UAH exchange rate. The optional listed-proxy
block (auto-remarketing equities) supplies the conservative high bound.

The BLS flat-file fetcher is injected into `collect_return_history` through
its designed `fetch_fred` hook (FRED blocks this environment's egress with a
bot wall, but the series is a BLS CPI component). Market series keep the
collector's default yfinance path - it works here because yfinance ships
curl_cffi - so no second fetch path is added to the collector itself.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pandas as pd

from analytics.allocation_score import monthly_window
from analytics.holy_grail_data import collect_return_history

PHYSICAL_DRIVERS = (
    {"series": "fred:CUSR0000SETA02", "symbol": "CUSR0000SETA02", "provider": "fred",
     "currency": "USD", "collection_priority": 1},
    {"series": "fx:UAHX", "symbol": "UAH=X", "provider": "yfinance",
     "currency": "USD", "collection_priority": 2},
)
# Roma approved the listed high-bound block (open decision 1, 2026-10-30).
# Two tickers keep k at four per the plan's driver cap. KAR/Openlane is
# unavailable on Yahoo (delisted quote); RB Global (Ritchie Bros + IAA) is
# the other large auto-remarketing auctioneer and carries a full history.
LISTED_DRIVERS = (
    {"series": "eq:CPRT", "symbol": "CPRT", "provider": "yfinance",
     "currency": "USD", "collection_priority": 3},
    {"series": "eq:RBA", "symbol": "RBA", "provider": "yfinance",
     "currency": "USD", "collection_priority": 4},
)
BLS_FILE_URL = "https://download.bls.gov/pub/time.series/cu/cu.data.14.USTransportation"
BLS_CONTACT_UA = "romanrud111@gmail.com (car-bound diagnostic)"


def _curl(url: str, user_agent: str, timeout: int = 60) -> str:
    result = subprocess.run(
        ["curl", "-sS", "--max-time", str(timeout), "-A", user_agent, url],
        capture_output=True, text=True, check=True)
    body = result.stdout
    if not body:
        raise ValueError("empty response")
    return body


def _fetch_fred_bls_flatfile(symbol: str, start: str, end: str) -> dict:
    """FRED-compatible fetcher backed by the BLS flat file for the same series.

    FRED blocks this environment's egress with a bot wall, but the series is a
    BLS CPI component, so the authoritative flat file supplies the identical
    monthly values (FRED's Sep 2026 print 182.176 matches).
    """
    body = _curl(BLS_FILE_URL, BLS_CONTACT_UA)
    periods, values = [], []
    for line in body.splitlines():
        parts = line.split()
        if len(parts) < 4 or parts[0] != symbol:
            continue
        year, month = parts[1], parts[2]
        if not (month.startswith("M") and month[1:].isdigit()):
            continue
        value = float(parts[3])
        stamp = pd.Timestamp(int(year), int(month[1:]), 1)
        periods.append(stamp)
        values.append(value)
    if not periods:
        raise ValueError(f"BLS flat file has no rows for {symbol}")
    prices = pd.Series(values, index=pd.DatetimeIndex(periods), dtype=float)
    prices = prices.sort_index()
    return {"prices": prices, "currency": "USD", "frequency": "monthly",
            "source": "bls_flat_file", "publication_dates": "not_supplied"}


def collect_driver_panel(as_of_date: str, *, cache_dir: str, allow_network: bool = True,
                         include_listed: bool = True) -> pd.DataFrame:
    """Monthly percentage changes of the public drivers over the standard window.

    Returns a frame aligned by `monthly_window` (60 completed month-ends). A
    series that fails to collect is dropped by the collector and reported in
    the returned frame's column set; the bound step treats a missing column as
    panel-incomplete for the blocks that need it.
    """
    exposures = list(PHYSICAL_DRIVERS) + (list(LISTED_DRIVERS) if include_listed else [])
    frame, provenance, flags = collect_return_history(
        exposures, as_of_date=as_of_date, cache_dir=Path(cache_dir),
        allow_network=allow_network, fetch_fred=_fetch_fred_bls_flatfile)
    frame = monthly_window(frame, as_of_date)
    frame.attrs["provenance"] = provenance
    frame.attrs["flags"] = sorted(flags)
    return frame