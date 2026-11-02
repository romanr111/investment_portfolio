"""Monthly USD return histories for the economic-group representatives: provider fetch, month-end rules, cache."""
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import time

import pandas as pd

from analytics.holy_grail.fingerprint import completed_month_end, fingerprint
from analytics.holy_grail.paths import CACHE_DIR


def _month_prices(prices, *, monthly=False):
    prices = prices.copy()
    prices.index = pd.to_datetime(prices.index).tz_localize(None).normalize()
    prices = pd.to_numeric(prices, errors="coerce").sort_index()
    if prices.index.has_duplicates or (prices.dropna() <= 0).any():
        raise ValueError("Invalid price history")
    if monthly:
        prices.index = prices.index.to_period("M").to_timestamp("M")
        if prices.index.has_duplicates:
            raise ValueError("Duplicate reference periods")
        return prices.resample(pd.offsets.MonthEnd()).last()
    values = prices.resample(pd.offsets.MonthEnd()).last()
    timestamps = pd.Series(prices.index, index=prices.index).where(prices.notna()).resample(pd.offsets.MonthEnd()).last()
    # A quote early in a month is not a complete month's closing price.
    age = (values.index.to_series() - timestamps).dt.days
    return values.where(age <= 7)


def monthly_usd_returns(prices, currency, as_of_date, *, fx_prices=None, monthly=False):
    """Convert already adjusted prices once, without forward-filling observations."""
    cutoff = completed_month_end(as_of_date)
    closes = _month_prices(prices.loc[pd.to_datetime(prices.index).date <= cutoff.date()], monthly=monthly)
    unit = 0.01 if currency in {"GBp", "GBX"} else 1.0
    currency = "GBP" if unit == 0.01 else str(currency or "").upper()
    if currency != "USD":
        if fx_prices is None or not currency:
            raise ValueError("Historical currency conversion is missing")
        fx = _month_prices(fx_prices.loc[pd.to_datetime(fx_prices.index).date <= cutoff.date()])
        closes = closes * unit * fx.reindex(closes.index)
    return closes.pct_change(fill_method=None).replace([float("inf"), -float("inf")], float("nan"))


def fetch_yfinance_history(symbol, start, end):
    import yfinance as yf
    ticker = yf.Ticker(symbol)
    frame = ticker.history(start=start, end=end, interval="1d", auto_adjust=True,
                           actions=False, timeout=8, raise_errors=True)
    metadata = ticker.history_metadata or {}
    return {"prices": frame["Close"], "currency": metadata.get("currency"), "frequency": "daily"}


def _fetch_fred(symbol, start, end):
    import requests
    response = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv",
                            params={"id": symbol}, timeout=8)
    response.raise_for_status()
    frame = pd.read_csv(io.StringIO(response.text))
    if symbol not in frame.columns:
        raise ValueError("Economic history response is not a data series")
    return {"prices": pd.Series(pd.to_numeric(frame[symbol], errors="coerce").values,
                                 index=pd.to_datetime(frame.iloc[:, 0])),
            "currency": "USD", "frequency": "monthly", "publication_dates": "not_supplied"}


def _cached_prices(provider, symbol, as_of_date, cache_dir, allow_network, fetcher):
    """Keep immutable retrievals and an atomic cache entry for each requested month."""
    cutoff = completed_month_end(as_of_date)
    folder = Path(cache_dir) / fingerprint([provider, symbol])[:24]
    cached = folder / (cutoff.strftime("%Y-%m") + ".json")
    record = None
    if cached.exists():
        try:
            record = json.loads(cached.read_text(encoding="utf-8"))
            prices = pd.Series(record["prices"], dtype=float)
            prices.index = pd.to_datetime(prices.index)
            closes = _month_prices(prices, monthly=record.get("frequency") == "monthly")
            if cutoff in closes.index and pd.notna(closes.loc[cutoff]):
                return prices, record
        except (ValueError, KeyError, TypeError):
            record = None
    if not allow_network:
        if record is None:
            raise FileNotFoundError("History is not cached")
        return prices, record
    failure = folder / (cutoff.strftime("%Y-%m") + "_failure.json")
    today = datetime.now(timezone.utc).date().isoformat()
    if failure.exists() and json.loads(failure.read_text()).get("date") == today:
        if record is not None:
            return prices, record
        raise ValueError("History collection already failed today")
    try:
        start = (cutoff.to_period("M") - 61).start_time.date().isoformat()
        end = (cutoff + pd.Timedelta(days=1)).date().isoformat()
        fetched = fetcher(symbol, start, end)
        prices = fetched["prices"].copy()
        prices.index = pd.to_datetime(prices.index).tz_localize(None).normalize()
        prices = pd.to_numeric(prices, errors="coerce").dropna().sort_index()
        prices = prices.loc[(prices.index >= start) & (prices.index <= cutoff)]
        if prices.empty:
            raise ValueError("No price observations returned")
        now = datetime.now(timezone.utc)
        record = {key: value for key, value in fetched.items() if key != "prices"}
        record.update(provider=provider, symbol=symbol, retrieved_at=now.isoformat(),
                      prices={stamp.date().isoformat(): float(value) for stamp, value in prices.items()})
        record["source_revision"] = fingerprint(record["prices"])
        text = json.dumps(record, allow_nan=False)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / (cutoff.strftime("%Y-%m") + "_" + now.strftime("%Y%m%dT%H%M%S%fZ") + ".json")).write_text(text)
        temporary = cached.with_suffix(".tmp")
        temporary.write_text(text)
        temporary.replace(cached)
        return prices, record
    except Exception as error:
        folder.mkdir(parents=True, exist_ok=True)
        failure.write_text(json.dumps({"date": today, "error_type": type(error).__name__}))
        if record is not None:
            return prices, record
        raise


def collect_return_history(exposures, *, as_of_date, cache_dir=CACHE_DIR, allow_network=True,
                           fetch_market=None, fetch_fred=None):
    """Collect unique series, retain per-source provenance, and degrade independently."""
    market = fetch_market or fetch_yfinance_history
    fred = fetch_fred or _fetch_fred
    histories, provenance, flags = {}, {}, set()
    deadline = time.monotonic() + 60
    attempted = set()
    # Refresh the main indicator's representatives before optional legacy
    # individual histories, then cover the largest valuations first.
    for exposure in sorted(exposures, key=lambda item: (item.get('collection_priority',1), -float(item.get("value_usd", 0)))):
        series, symbol = exposure.get("series"), exposure.get("symbol")
        if not series or not symbol or series in attempted:
            continue
        attempted.add(series)
        provider = exposure.get("provider", "yfinance")
        try:
            network = allow_network and time.monotonic() < deadline
            prices, record = _cached_prices(provider, symbol, as_of_date, cache_dir, network,
                                            fred if provider == "fred" else market)
            currency = exposure.get("currency") or record.get("currency")
            fx = None
            normalized_currency = "GBP" if currency in {"GBp", "GBX"} else str(currency or "").upper()
            fx_record = None
            if normalized_currency != "USD":
                if not normalized_currency:
                    raise ValueError("Quote currency is unknown")
                fx, fx_record = _cached_prices("yfinance", normalized_currency + "USD=X", as_of_date,
                                               cache_dir, network, market)
            histories[series] = monthly_usd_returns(prices, currency, as_of_date, fx_prices=fx,
                                                     monthly=record.get("frequency") == "monthly")
            provenance[series] = {key: value for key, value in record.items() if key != "prices"}
            if fx_record:
                provenance[series]["fx_source"] = {k: v for k, v in fx_record.items() if k != "prices"}
            if provider == "fred":
                flags.add("publication_vintage_unverified")
        except Exception as error:
            provenance[series] = {"status": "unavailable", "error_type": type(error).__name__}
            flags.add("history_collection_incomplete")
    return pd.DataFrame(histories), provenance, flags
