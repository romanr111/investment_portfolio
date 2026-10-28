"""Collect risk inputs and enrich saved portfolio data without changing balances."""
from datetime import date, datetime, timezone
import io
import json
import math
from pathlib import Path
import time
import hashlib

import pandas as pd

from analytics.holy_grail import completed_month_end, fingerprint
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


def _number(value):
    if isinstance(value, bool):
        return None
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


def bound_exposure_record(records, identifier, fallback, source_identity=None):
    """Index-keyed evidence is usable only when bound to the same economic holding."""
    record = records.get(identifier)
    positional = identifier.split(':', 1)[0] in {'crypto_lending', 'p2p', 'other_assets'}
    if record is not None and (not positional or (source_identity and record.get('source_identity') == source_identity)):
        return record
    return records.get(fallback, {})


def _source_identity(row, keys):
    if all(isinstance(row.get(key), str) and row[key].strip() for key in keys):
        return {key: row[key] for key in keys}
    return None


def extract_exposures(data, as_of_date, config):
    """Use the canonical saved values; aliases and rationale overrides stay private."""
    positions, flags = [], set()
    mappings = config.get("mappings", {})
    qualifications = config.get("qualifications", {})

    def add(identifier, category, value, *, symbol=None, proxy=None, risks=(), source_identity=None):
        amount = _number(value)
        if amount is None:
            flags.add("invalid_valuation")
            return
        if amount == 0:
            return
        mapping = bound_exposure_record(mappings, identifier, "category:" + category, source_identity)
        if 'valid_from' in mapping or 'valid_until' in mapping:
            try:
                start = date.fromisoformat(mapping.get('valid_from', date.min.isoformat()))
                end = date.fromisoformat(mapping.get('valid_until', date.max.isoformat()))
                if start > end:
                    raise ValueError('Reversed mapping validity')
                if not start <= date.fromisoformat(as_of_date) <= end:
                    flags.add('mapping_outside_validity')
                    mapping = {}
            except (ValueError, TypeError):
                flags.add('invalid_mapping_dates')
                mapping = {}
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
            "qualification": bound_exposure_record(qualifications, identifier, category, source_identity) or {"status": "draft"},
            "source_identity": source_identity,
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
            add(f"{key}:{index}", category, row.get(amount_key), proxy="HYG", risks=risks,
                source_identity=_source_identity(row, ("account", "asset") if key == "crypto_lending" else ("account",)))
            if row.get("status") == "legacy" or row.get("coverage") == "partial":
                flags.add("partial_valuations")
    other_rows = contract.get("other_assets")
    if other_rows is None:
        other_rows = [{"carrying_value_usd": value} for value in data.get("OTHER_ASSETS", {}).values()]
    for index, row in enumerate(other_rows):
        add(f"other_assets:{index}", "Other Bets", row.get("carrying_value_usd"),
            proxy="CUSR0000SETA02", risks=["resale_execution_risk_unmodeled", "local_market_risk_unmodeled"],
            source_identity=_source_identity(row, ("asset_id",)))
        if row.get("status") == "legacy" or row.get("coverage") == "partial":
            flags.add("partial_valuations")
    cash = _number(data.get("CASH_DATA", {}).get("Total"))
    if cash is None:
        flags.add("invalid_cash_valuation")
        cash = 0.0
    if data.get("CASH_DATA", {}).get("Cash_Equivalents"):
        flags.add("cash_equivalent_counterparty_risk")
    # Inspect liabilities before net cash combines accounts with positive balances.
    cash_components = list((data.get("CASH_DATA", {}).get("Breakdown") or {}).values())
    cash_components.append(ib.get("Net_cash", 0))
    if any(_number(value) is not None and _number(value) < 0 for value in cash_components):
        flags.add("unsupported_borrowing")
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
    if remainder > max(1.0, abs(total) * 1e-6):
        add("unallocated", "Unmapped", remainder)
        flags.add("unreconciled_positions")
    return positions, cash, flags


def enrich_combined_data(data, *, as_of_date=None, config=None, monthly_returns=None,
                         allow_network=True, cache_dir=CACHE_DIR, source_provenance=None,
                         previous_combined_data=None):
    """Return an enriched copy. An analytics failure never changes financial values."""
    output = dict(data)
    as_of_date = _date(as_of_date or data.get("POSITION_DATA", {}).get("as_of_date")
                       or data.get("DATA_METADATA", {}).get("last_updated") or date.today().isoformat())
    try:
        settings = load_config() if config is None else config
    except (OSError, ValueError, TypeError):
        settings = None
    if isinstance(settings, dict) and 'allocation' not in settings:
        return output

    from copy import deepcopy
    from analytics.allocation_inputs import allocation_history_requests, allocation_settings, _seal
    from analytics.allocation_v2_inputs import calculate_allocation_score_v2, comparison_basis, _compare_basis

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
            returns, provenance, collection_flags = collect_return_history(
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
        saved['comparison'] = _compare_basis(saved, basis) if basis else {
            'status': 'unavailable', 'reason': 'previous_v2_invalid_or_absent'}
        _seal(saved)
    output['DIVERSIFICATION_DATA']['allocation_score_v2'] = saved
    return output


def enrich_snapshot_file(source_path, output_path, *, config=None, cache_dir=CACHE_DIR, allow_network=True,
                         monthly_returns=None, source_provenance=None, previous_combined_data=None):
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
                                    allow_network=allow_network, monthly_returns=monthly_returns,
                                    source_provenance=source_provenance, previous_combined_data=previous_combined_data)
    if (enriched.get('DIVERSIFICATION_DATA') is not data.get('DIVERSIFICATION_DATA')
            and 'allocation_score_v2' in enriched.get('DIVERSIFICATION_DATA', {})):
        from copy import deepcopy
        result = deepcopy(payload)
        target = result['data'] if 'data' in result else result
        target.setdefault('DIVERSIFICATION_DATA', {})['allocation_score_v2'] = enriched['DIVERSIFICATION_DATA']['allocation_score_v2']
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
