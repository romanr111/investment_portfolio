"""Turn a saved combined_data record into dated economic exposures (no network, no scoring)."""
from datetime import date
import math

from src.portfolio_ledger.contract import CASH_EQUIVALENTS


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (ValueError, TypeError):
        return None
    return result if math.isfinite(result) else None


def iso_date(value):
    return date.fromisoformat(str(value)[:10]).isoformat()


POSITIONAL_PREFIXES = frozenset({'crypto_lending', 'p2p', 'other_assets'})


def is_positional(identifier):
    """Ids of these kinds are list indexes; a record keyed by one must also name the holding's source identity."""
    return identifier.split(':', 1)[0] in POSITIONAL_PREFIXES


def bound_exposure_record(records, identifier, fallback, source_identity=None):
    """Index-keyed evidence is usable only when bound to the same economic holding."""
    record = records.get(identifier)
    positional = is_positional(identifier)
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
            if row.get("as_of_date") and iso_date(row["as_of_date"]) != as_of_date:
                flags.add("valuation_date_mismatch")
    stamps = (contract.get("as_of_date"), data.get("DATA_METADATA", {}).get("last_updated"))
    if not any(stamps):
        flags.add("valuation_date_unverified")
    for stamp in stamps:
        if stamp and iso_date(stamp) != as_of_date:
            flags.add("valuation_date_mismatch")
    total = _number(data.get("TOTAL_ASSETS"))
    if total is None:
        raise ValueError("Missing portfolio total")
    remainder = total - cash - sum(row["value_usd"] for row in positions)
    if remainder > max(1.0, abs(total) * 1e-6):
        add("unallocated", "Unmapped", remainder)
        flags.add("unreconciled_positions")
    return positions, cash, flags
