"""Collect risk inputs and enrich saved portfolio data without changing balances."""
from datetime import date, datetime, timezone
import io
import json
import math
from pathlib import Path
import time
import hashlib

import pandas as pd

from analytics.holy_grail import calculate_progress, completed_month_end, fingerprint, holdings_fingerprint
from src.portfolio_ledger.contract import CASH_EQUIVALENTS

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
CONFIG_PATH = DATA_DIR / "holy_grail_config.json"
CACHE_DIR = DATA_DIR / "holy_grail_history"


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
        return prices.resample("ME").last()
    values = prices.resample("ME").last()
    timestamps = pd.Series(prices.index, index=prices.index).where(prices.notna()).resample("ME").last()
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


def _fetch_market(symbol, start, end):
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
    market = fetch_market or _fetch_market
    fred = fetch_fred or _fetch_fred
    histories, provenance, flags = {}, {}, set()
    deadline = time.monotonic() + 60
    attempted = set()
    # A bounded cold refresh should cover the largest valuations first.
    for exposure in sorted(exposures, key=lambda item: -float(item.get("value_usd", 0))):
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


def _number(value):
    try:
        result = float(value)
    except (ValueError, TypeError):
        return None
    return result if math.isfinite(result) else None


def _date(value):
    return date.fromisoformat(str(value)[:10]).isoformat()


def load_config(path=CONFIG_PATH):
    if not Path(path).exists():
        return {}
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Holy Grail configuration must be a JSON object")
    return value


def extract_exposures(data, as_of_date, config):
    """Use the canonical saved values; aliases and rationale overrides stay private."""
    positions, flags = [], set()
    mappings = config.get("mappings", {})
    qualifications = config.get("qualifications", {})

    def add(identifier, category, value, *, symbol=None, proxy=None, risks=()):
        amount = _number(value)
        if amount is None:
            flags.add("invalid_valuation")
            return
        if amount == 0:
            return
        mapping = mappings.get(identifier, mappings.get("category:" + category, {}))
        provider = mapping.get("provider", "fred" if proxy == "CUSR0000SETA02" else "yfinance")
        market_symbol = mapping.get("symbol", proxy or symbol)
        is_proxy = mapping.get("kind", "proxy" if proxy else "direct") == "proxy"
        prefix = "fred:" if provider == "fred" else "yf:"
        positions.append({
            "id": identifier, "category": category, "value_usd": amount,
            "series": prefix + market_symbol if market_symbol else None,
            "symbol": market_symbol, "provider": provider,
            "currency": mapping.get("currency"),
            "kind": "proxy" if is_proxy else "direct",
            "weak_proxy": bool(mapping.get("weak_proxy", is_proxy)),
            "risk_flags": sorted(set(risks) | set(mapping.get("risk_flags", []))),
            "qualification": qualifications.get(identifier, qualifications.get(category, {"status": "draft"})),
        })

    ib = data.get("IB_DATA", {})
    for category in ("Stocks", "China Stocks", "Bonds", "Precious Metals", "Commodities", "REIT", "Short Selling"):
        for symbol, value in (ib.get(category) or {}).items():
            # Never treat a broker-specific contract id as a Yahoo ticker.
            market_symbol = None if str(symbol).startswith("IBCID") else str(symbol).replace(" ", "-")
            if market_symbol and market_symbol.isdigit():
                market_symbol = market_symbol.zfill(4) + ".HK"
            add("ib:" + str(symbol), category, value, symbol=market_symbol)

    contract = data.get("POSITION_DATA", {})
    crypto_rows = contract.get("crypto")
    if crypto_rows is None:
        crypto_rows = [{"asset": symbol, "value_usd": value} for symbol, value in
                       data.get("CRYPTO_DATA", {}).get("Crypto_Market_Values", {}).items()]
    for row in crypto_rows:
        symbol = row.get("asset", "")
        if symbol in CASH_EQUIVALENTS:
            continue
        add("crypto:" + symbol, "Crypto Coins", row.get("value_usd"), symbol=symbol + "-USD")
    income = data.get("FIXED_INCOME_DATA", {}).get("group_weighted_interest", {})
    for category, key, amount_key, income_key in (
        ("Crypto Lending", "crypto_lending", "principal_usd", "Crypto Landing"),
        ("P2P Lending", "p2p", "balance_usd", "p2p_lending"),
    ):
        rows = contract.get(key)
        if rows is None:
            saved = income.get(income_key, [0])
            rows = [{amount_key: saved[0] if isinstance(saved, (list, tuple)) else saved}]
        for index, row in enumerate(rows):
            if row.get("asset") in CASH_EQUIVALENTS:
                continue
            risks = ["counterparty_risk_unmodeled", "liquidity_risk_unmodeled"]
            if category == "Crypto Lending":
                risks.append("depeg_risk_unmodeled")
            add(f"{key}:{index}", category, row.get(amount_key), proxy="HYG", risks=risks)
            if row.get("status") == "legacy" or row.get("coverage") == "partial":
                flags.add("partial_valuations")
    other_rows = contract.get("other_assets")
    if other_rows is None:
        other_rows = [{"carrying_value_usd": value} for value in data.get("OTHER_ASSETS", {}).values()]
    for index, row in enumerate(other_rows):
        add(f"other_assets:{index}", "Other Bets", row.get("carrying_value_usd"),
            proxy="CUSR0000SETA02", risks=["resale_execution_risk_unmodeled", "local_market_risk_unmodeled"])
        if row.get("status") == "legacy" or row.get("coverage") == "partial":
            flags.add("partial_valuations")
    cash = _number(data.get("CASH_DATA", {}).get("Total"))
    if cash is None:
        flags.add("invalid_cash_valuation")
        cash = 0.0
    if data.get("CASH_DATA", {}).get("Cash_Equivalents"):
        flags.add("cash_equivalent_counterparty_risk")
    quality = data.get("DATA_QUALITY", {})
    for key in ("crypto", "cash"):
        if quality.get(key, {}).get("freshness") in {"stale", "partial", "snapshot_fallback"}:
            flags.add("stale_valuations")
    for group in ("crypto", "crypto_lending", "p2p", "other_assets"):
        for row in contract.get(group, []):
            if row.get("as_of_date") and _date(row["as_of_date"]) != as_of_date:
                flags.add("valuation_date_mismatch")
    stamps = (contract.get("as_of_date"), data.get("DATA_METADATA", {}).get("last_updated"))
    if not any(stamps):
        flags.add("valuation_date_unverified")
    for stamp in stamps:
        if stamp and _date(stamp) != as_of_date:
            flags.add("valuation_date_mismatch")
    total = _number(data.get("TOTAL_ASSETS"))
    if total is None:
        raise ValueError("Missing portfolio total")
    remainder = total - cash - sum(row["value_usd"] for row in positions)
    if remainder > max(0.02, total * 1e-6):
        add("unallocated", "Unmapped", remainder)
        flags.add("unreconciled_positions")
    return positions, cash, flags


def enrich_combined_data(data, *, as_of_date=None, config=None, monthly_returns=None,
                         allow_network=True, cache_dir=CACHE_DIR):
    """Return an enriched copy. An analytics failure never changes financial values."""
    output = dict(data)
    as_of_date = _date(as_of_date or data.get("POSITION_DATA", {}).get("as_of_date")
                       or data.get("DATA_METADATA", {}).get("last_updated") or date.today().isoformat())
    positions, cash, flags, provenance = [], 0., set(), {}
    settings = {}
    returns = monthly_returns if monthly_returns is not None else pd.DataFrame()
    try:
        settings = load_config() if config is None else config
        positions, cash, flags = extract_exposures(data, as_of_date, settings)
        provenance = {}
        returns = monthly_returns
        if returns is None:
            returns, provenance, collection_flags = collect_return_history(
                positions, as_of_date=as_of_date, cache_dir=cache_dir, allow_network=allow_network)
            flags.update(collection_flags)
        summary = calculate_progress(
            positions, returns, as_of_date=as_of_date, total_assets=float(data["TOTAL_ASSETS"]),
            cash_value=cash, input_flags=flags, config_hash=fingerprint(settings),
        )
        summary["retrospective"] = as_of_date < datetime.now(timezone.utc).date().isoformat()
        summary["source_provenance"] = provenance
        summary["history_fingerprint"] = fingerprint(returns.to_json(date_format="iso"))
        summary["holdings_fingerprint"] = holdings_fingerprint(data)
        output["HOLY_GRAIL_DATA"] = summary
    except Exception as error:
        # Do not serialize exception messages: upstream failures may contain URLs or identifiers.
        output["HOLY_GRAIL_DATA"] = {
            "method_version": "holy_grail_progress_v1", "as_of_date": as_of_date,
            "status": "unavailable", "effective_streams": None,
            "estimated_progress_pct": None, "target_achieved": False,
            "constraints": ["analytics_failed", type(error).__name__],
        }
    from analytics.diversification_inputs import enrich_quality
    output['DIVERSIFICATION_DATA'] = enrich_quality(data,positions,cash,returns,settings,as_of_date,flags,provenance)
    return output


def enrich_snapshot_file(source_path, output_path, *, config=None, cache_dir=CACHE_DIR, allow_network=True):
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
    as_of = _date(payload.get("as_of_date") or data.get("DATA_METADATA", {}).get("last_updated"))
    enriched = enrich_combined_data(data, as_of_date=as_of, config=config, cache_dir=cache_dir,
                                    allow_network=allow_network)
    result = dict(payload, data=enriched) if "data" in payload else enriched
    result["holy_grail_enrichment"] = {
        "source_snapshot_sha256": hashlib.sha256(raw).hexdigest(),
        "calculated_at": datetime.now(timezone.utc).isoformat(), "retrospective": True,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
    return result
