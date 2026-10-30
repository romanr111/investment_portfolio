"""Financial derivations for sections of the generated portfolio snapshot."""

from datetime import date
import math
from typing import Any, Optional


CATEGORIES = (
    "Stocks",
    "Bonds",
    "Other Bets",
    "Crypto Lending",
    "Precious Metals",
    "Crypto Coins",
    "Commodities",
    "Cash",
    "P2P Lending",
    "REIT",
)


def _number(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _sum_mapping(mapping: Any) -> Optional[float]:
    if not isinstance(mapping, dict):
        return None
    values = [_number(value) for value in mapping.values()]
    if any(value is None for value in values):
        return None
    return sum(values)


def _group_principal(data: dict, names: tuple[str, ...]) -> Optional[float]:
    fixed_income = data.get("FIXED_INCOME_DATA")
    if not isinstance(fixed_income, dict):
        return None
    groups = fixed_income.get("group_weighted_interest")
    if not isinstance(groups, dict):
        return None
    for name in names:
        if name not in groups:
            continue
        value = groups[name]
        if isinstance(value, (list, tuple)):
            value = value[0] if value else None
        return _number(value)
    return None


def _group_rate(data: dict, names: tuple[str, ...]) -> Optional[float]:
    fixed_income = data.get("FIXED_INCOME_DATA")
    groups = fixed_income.get("group_weighted_interest") if isinstance(fixed_income, dict) else None
    if not isinstance(groups, dict):
        return None
    for name in names:
        if name not in groups:
            continue
        value = groups[name]
        if isinstance(value, (list, tuple)):
            return _number(value[1]) if len(value) > 1 else None
    return None


def _category_values(data: Optional[dict]) -> dict[str, Optional[float]]:
    if not isinstance(data, dict):
        return {category: None for category in CATEGORIES}

    ib_data = data.get("IB_DATA")
    ib_data = ib_data if isinstance(ib_data, dict) else {}

    if "Total Stocks Value" in ib_data:
        stocks = _number(ib_data.get("Total Stocks Value"))
    elif "Stocks" in ib_data or "China Stocks" in ib_data:
        regular = _sum_mapping(ib_data.get("Stocks", {}))
        china = _sum_mapping(ib_data.get("China Stocks", {}))
        stocks = None if regular is None or china is None else regular + china
    else:
        stocks = None

    bonds = _sum_mapping(ib_data["Bonds"]) if "Bonds" in ib_data else None
    metals_key = "Precious Metals" if "Precious Metals" in ib_data else "Gold"
    metals = _sum_mapping(ib_data[metals_key]) if metals_key in ib_data else None
    commodities = (
        _sum_mapping(ib_data["Commodities"]) if "Commodities" in ib_data else None
    )

    crypto_data = data.get("CRYPTO_DATA")
    if isinstance(crypto_data, dict) and "Total_Crypto_Value" in crypto_data:
        crypto = _number(crypto_data.get("Total_Crypto_Value"))
    elif isinstance(crypto_data, dict) and "Crypto_Market_Values" in crypto_data:
        crypto = _sum_mapping(crypto_data.get("Crypto_Market_Values"))
    else:
        crypto = None

    cash_data = data.get("CASH_DATA")
    cash = (
        _number(cash_data.get("Total"))
        if isinstance(cash_data, dict) and "Total" in cash_data
        else None
    )
    other_assets = data.get("OTHER_ASSETS")
    if isinstance(other_assets, dict):
        other = (
            _number(other_assets.get("Other Bets"))
            if "Other Bets" in other_assets
            else _sum_mapping(other_assets)
        )
    else:
        other = None

    values = {
        "Stocks": stocks,
        "Bonds": bonds,
        "Other Bets": other,
        "Crypto Lending": _group_principal(
            data, ("Crypto Lending", "Crypto Landing")
        ),
        "Precious Metals": metals,
        "Crypto Coins": crypto,
        "Commodities": commodities,
        "Cash": cash,
        "P2P Lending": _group_principal(data, ("P2P Lending", "p2p_lending")),
        "REIT": _sum_mapping(ib_data["REIT"]) if "REIT" in ib_data else None,
    }
    # ASSET_ALLOCATION.allocations is the published per-category amount
    # (src/data_source.py). Prefer it so the sheet cannot diverge from what the
    # sheets sync publishes; the derivation above is the fallback when the
    # publication is absent.
    allocation = data.get("ASSET_ALLOCATION")
    saved = allocation.get("allocations") if isinstance(allocation, dict) else None
    if isinstance(saved, dict):
        for category, entry in saved.items():
            if category not in values or not isinstance(entry, dict):
                continue
            amount = entry.get("value")
            if isinstance(amount, (int, float)) and not isinstance(amount, bool):
                values[category] = float(amount)
    return values


def _category_total(values: dict[str, Optional[float]]) -> Optional[float]:
    if any(value is None for value in values.values()):
        return None
    total = sum(value for value in values.values() if value is not None)
    return total if total != 0 else None


def category_rows(combined_data: dict) -> list[dict[str, Any]]:
    """Return category amounts and weights using tracked total assets as denominator."""
    values = _category_values(combined_data)
    total_assets = _number(combined_data.get("TOTAL_ASSETS"))
    rows = []
    for category in CATEGORIES:
        value = values[category]
        weight = (
            value / total_assets
            if value is not None and total_assets is not None and total_assets > 0
            else None
        )
        rows.append(
            {
                "category": category,
                "value": value,
                "weight": weight,
                "state": "Available" if value is not None else "Unknown",
            }
        )
    return rows


def _date_value(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def snapshot_comparison(
    current: dict,
    previous: Optional[dict],
    current_date: Optional[str] = None,
    previous_date: Optional[str] = None,
) -> dict[str, Any]:
    """Compare balance snapshots by category without describing changes as profit."""
    current_values = _category_values(current)
    previous_values = _category_values(previous)
    current_total = _category_total(current_values)
    previous_total = _category_total(previous_values)
    rows = []

    for category in CATEGORIES:
        current_value = current_values[category]
        previous_value = previous_values[category]
        current_weight = (
            current_value / current_total
            if current_value is not None and current_total is not None
            else None
        )
        previous_weight = (
            previous_value / previous_total
            if previous_value is not None and previous_total is not None
            else None
        )

        if previous is None:
            state, change = "No baseline", None
        elif current_value is None or previous_value is None:
            state, change = "Incomplete", None
        elif previous_value == 0 and current_value > 0:
            state, change = "new", current_value
        elif previous_value > 0 and current_value == 0:
            state, change = "closed", None
        else:
            state = "Available"
            change = current_value - previous_value

        movement = (
            current_value - previous_value
            if current_value is not None and previous_value is not None
            else None
        )
        change_pp = (
            (current_weight - previous_weight) * 100
            if current_weight is not None and previous_weight is not None
            else None
        )
        rows.append(
            {
                "category": category,
                "previous": previous_value,
                "current": current_value,
                "change": change,
                "previous_weight": previous_weight,
                "current_weight": current_weight,
                "change_pp": change_pp,
                "state": state,
                "movement": movement,
            }
        )

    rows.sort(
        key=lambda row: abs(row["movement"] or 0),
        reverse=True,
    )
    changes = [row["change"] for row in rows if row["change"] is not None]
    has_incomplete_rows = any(row["state"] == "Incomplete" for row in rows)
    current_day = _date_value(current_date)
    previous_day = _date_value(previous_date)
    interval_days = (
        (current_day - previous_day).days
        if current_day is not None and previous_day is not None
        else None
    )
    complete = previous is not None and not has_incomplete_rows
    closed_adjustment = (
        -sum(row["previous"] for row in rows if row["state"] == "closed")
        if complete else None
    )
    current_tracked = _number(current.get("TOTAL_ASSETS"))
    previous_tracked = _number(previous.get("TOTAL_ASSETS")) if previous else None
    balance_change = (
        current_tracked - previous_tracked
        if complete and current_total is not None and previous_total is not None
        and current_tracked is not None and previous_tracked is not None else None
    )

    return {
        "current_date": current_date,
        "previous_date": previous_date,
        "interval_days": interval_days,
        "previous_total": previous_total,
        "current_total": current_total,
        "balance_change_total": balance_change,
        "closed_balance_adjustment": closed_adjustment,
        "reconciliation_difference": (
            balance_change - sum(changes) - closed_adjustment
            if balance_change is not None else None
        ),
        "change_total": (
            sum(changes)
            if previous is not None and not has_incomplete_rows
            else None
        ),
        "rows": rows,
        "state": (
            "No baseline"
            if previous is None
            else "Incomplete"
            if has_incomplete_rows
            else "Available"
        ),
        "label": "Balance change - not investment profit",
        "external_contributions": None,
        "attribution_state": "Unavailable - complete reconciled activity data not supplied",
    }


def income_breakdown(combined_data: dict, *, fixed_only: bool = False) -> dict[str, Any]:
    """Separate estimated income components from transaction receipts."""
    fixed_income = combined_data.get("FIXED_INCOME_DATA")
    fixed_income = fixed_income if isinstance(fixed_income, dict) else {}
    stock_source = fixed_income.get("stocks_principal_and_interest", {})
    stock_source = stock_source if isinstance(stock_source, dict) else {}
    stock_principal = _number(stock_source.get("total_principal"))
    stock_rate_points = _number(stock_source.get("weighted_interest"))
    stock_rate = (
        stock_rate_points / 100 if stock_rate_points is not None else None
    )
    stock_annual = _number(fixed_income.get("stocks_yearly"))
    if stock_annual is None and stock_principal is not None and stock_rate is not None:
        stock_annual = _number(stock_principal * stock_rate)

    definitions = (
        ("Stocks", stock_principal, stock_rate, stock_annual, "Estimated"),
        (
            "Bonds",
            _group_principal(combined_data, ("Bonds",)),
            _group_rate(combined_data, ("Bonds",)),
            None,
            "Manual estimate",
        ),
        (
            "Crypto Lending",
            _group_principal(combined_data, ("Crypto Lending", "Crypto Landing")),
            _group_rate(combined_data, ("Crypto Lending", "Crypto Landing")),
            None,
            "Manual estimate",
        ),
        (
            "P2P Lending",
            _group_principal(combined_data, ("P2P Lending", "p2p_lending")),
            _group_rate(combined_data, ("P2P Lending", "p2p_lending")),
            None,
            "Manual estimate",
        ),
    )

    if fixed_only:
        definitions = definitions[1:]

    items = []
    for source, principal, annual_rate, annual_income, state in definitions:
        if annual_income is None and principal is not None and annual_rate is not None:
            annual_income = _number(principal * annual_rate)
        if annual_income is None:
            state = "Unavailable"
        yield_value = (
            annual_income / principal
            if annual_income is not None and principal is not None and principal > 0
            else None
        )
        if yield_value is not None and not math.isfinite(yield_value * 100):
            yield_value = None
        items.append(
            {
                "source": source,
                "principal": principal,
                "annual_rate": annual_rate,
                "annual_income": annual_income,
                "annual_yield": yield_value,
                "monthly_average": annual_income / 12 if annual_income is not None else None,
                "state": state,
            }
        )

    available = [item["annual_income"] for item in items if item["annual_income"] is not None]
    annual_total = sum(available) if available else None
    valid_basis = all(
        item["annual_income"] is not None
        and item["principal"] is not None
        and item["principal"] >= 0
        and (item["principal"] != 0 or item["annual_income"] == 0)
        for item in items
    )
    annual_principal = (
        sum(item["principal"] for item in items) if valid_basis else None
    )
    if annual_principal is not None and not math.isfinite(annual_principal):
        annual_principal = None
    annual_yield = (
        annual_total / annual_principal
        if annual_total is not None
        and math.isfinite(annual_total)
        and annual_principal is not None
        and annual_principal > 0
        else None
    )
    if annual_yield is not None and not math.isfinite(annual_yield * 100):
        annual_yield = None
    receipts = combined_data.get("INCOME_RECEIPTS")
    if isinstance(receipts, dict):
        receipt_view = {
            "state": receipts.get("state", "Incomplete"),
            "coverage_start": receipts.get("coverage_start"),
            "coverage_end": receipts.get("coverage_end"),
            "rows": receipts.get("rows", []),
            "message": receipts.get("message", "Receipt coverage supplied by transaction data."),
        }
    else:
        receipt_view = {
            "state": "Unavailable",
            "coverage_start": None,
            "coverage_end": None,
            "rows": [],
            "message": "No supported transaction data for actual income receipts.",
        }

    return {
        "items": items,
        "annual_income": annual_total,
        "annual_principal": annual_principal,
        "annual_yield": annual_yield,
        "monthly_average": annual_total / 12 if annual_total is not None else None,
        "state": "Estimated" if len(available) == len(items) else "Incomplete",
        "receipts": receipt_view,
    }


def _position_row(
    symbol: str,
    category: str,
    raw_value: Any,
    details: Optional[dict],
    total_assets: Optional[float],
    ib_total: Optional[float],
    account: str,
    source: str,
) -> dict[str, Any]:
    details = details if isinstance(details, dict) else {}
    value = _number(raw_value)
    pnl = _number(details.get("unrealized_pnl"))
    pnl_percent_points = _number(details.get("unrealized_pnl_percentage"))
    pnl_currency = details.get("currency") or details.get("trading_currency")
    if pnl_currency:
        pnl_state = "Native currency"
    elif pnl is not None:
        pnl_state = "Native currency unavailable"
    else:
        pnl_state = "Unavailable - cost basis not supplied"
    # Producers carry no currency code for positions without one; show the
    # explicit state in the currency column instead of a fabricated code.
    if pnl_currency is None and pnl is not None:
        pnl_currency = pnl_state
    name = details.get("name")
    return {
        "asset": f"{name} ({symbol})" if name else symbol,
        "symbol": symbol,
        "category": category,
        "account": details.get("account_label") or account,
        "value_usd": value,
        "pct_total_assets": (
            value / total_assets
            if value is not None and total_assets is not None and total_assets > 0
            else None
        ),
        "pct_ib_portfolio": (
            value / ib_total
            if source == "IB" and value is not None and ib_total is not None and ib_total > 0
            else None
        ),
        "unrealized_pnl_amount": pnl,
        "pnl_currency": pnl_currency or "Unknown",
        "pnl_state": pnl_state,
        "pnl_pct": pnl_percent_points / 100 if pnl_percent_points is not None else None,
        "trading_currency": details.get("trading_currency") or pnl_currency or "Unknown",
        "underlying_geography": details.get("underlying_geography")
        or details.get("geography")
        or "Unknown",
        "provider": details.get("provider")
        or details.get("platform")
        or ("IB" if source == "IB" else "Unknown"),
        "source": source,
        "state": "Available" if value is not None else "Unknown",
    }


def _simple_position(
    symbol: str,
    category: str,
    value: Any,
    total_assets: Optional[float],
    account: str,
    source: str,
) -> dict[str, Any]:
    return _position_row(
        symbol, category, value, None, total_assets, None, account, source
    )


def holdings_table(
    combined_data: dict, tiny_threshold_usd: float = 100.0
) -> dict[str, Any]:
    """Build detailed positions while keeping tiny nonzero values visible."""
    if tiny_threshold_usd < 0:
        raise ValueError("tiny_threshold_usd must be non-negative")

    total_assets = _number(combined_data.get("TOTAL_ASSETS"))
    ib_data = combined_data.get("IB_DATA")
    ib_data = ib_data if isinstance(ib_data, dict) else {}
    ib_total = _number(ib_data.get("IB_Portfolio_Value"))
    enhanced = combined_data.get("ENHANCED_STOCKS")
    enhanced = enhanced if isinstance(enhanced, dict) else {}
    rows: list[dict[str, Any]] = []

    ib_categories = (
        ("Stocks", "Stocks"),
        ("China Stocks", "Stocks"),
        ("Bonds", "Bonds"),
        ("Precious Metals", "Precious Metals"),
        ("Commodities", "Commodities"),
        ("REIT", "REIT"),
    )
    for source_category, display_category in ib_categories:
        positions = ib_data.get(source_category)
        if not isinstance(positions, dict):
            continue
        details_by_symbol = enhanced.get(source_category, {})
        for symbol, value in positions.items():
            details = details_by_symbol.get(symbol, {}) if isinstance(details_by_symbol, dict) else {}
            rows.append(
                _position_row(
                    str(symbol),
                    display_category,
                    value,
                    details,
                    total_assets,
                    ib_total,
                    "IB",
                    "IB",
                )
            )

    crypto_data = combined_data.get("CRYPTO_DATA")
    if isinstance(crypto_data, dict):
        market_values = crypto_data.get("Crypto_Market_Values")
        crypto_total = _number(crypto_data.get("Total_Crypto_Value"))
        if isinstance(market_values, dict) and market_values:
            crypto_rows = [
                _simple_position(
                    str(symbol), "Crypto Coins", value, total_assets, "Crypto", "Crypto"
                )
                for symbol, value in market_values.items()
            ]
            rows.extend(crypto_rows)
            item_total = _sum_mapping(market_values)
            if crypto_total is not None and item_total is not None:
                residual = crypto_total - item_total
                if not math.isclose(residual, 0.0, abs_tol=0.005):
                    rows.append(
                        _simple_position(
                            "Unitemized crypto value",
                            "Crypto Coins",
                            residual,
                            total_assets,
                            "Crypto",
                            "Crypto",
                        )
                    )
        elif crypto_total is not None:
            rows.append(
                _simple_position(
                    "Crypto total", "Crypto Coins", crypto_total, total_assets, "Crypto", "Crypto"
                )
            )

    fixed_income = combined_data.get("FIXED_INCOME_DATA")
    fixed_income = fixed_income if isinstance(fixed_income, dict) else {}
    for label, names in (
        ("Crypto Lending", ("Crypto Lending", "Crypto Landing")),
        ("P2P Lending", ("P2P Lending", "p2p_lending")),
    ):
        principal = _group_principal(combined_data, names)
        if principal is not None:
            rows.append(
                _simple_position(
                    label, label, principal, total_assets, label, "Manual estimate"
                )
            )

    cash_data = combined_data.get("CASH_DATA")
    if isinstance(cash_data, dict) and "Total" in cash_data:
        cash_total = _number(cash_data.get("Total"))
        if cash_total is not None:
            rows.append(
                _simple_position("Cash total", "Cash", cash_total, total_assets, "Cash", "Cash")
            )

    other_assets = combined_data.get("OTHER_ASSETS")
    if isinstance(other_assets, dict):
        if "Other Bets" in other_assets:
            other_positions = {"Other Bets": other_assets["Other Bets"]}
        else:
            other_positions = other_assets
        for name, value in other_positions.items():
            rows.append(
                _simple_position(
                    str(name), "Other Bets", value, total_assets, "Manual estimate", "Manual estimate"
                )
            )

    category_order = {category: index for index, category in enumerate(CATEGORIES)}
    rows.sort(
        key=lambda row: (
            category_order.get(row["category"], len(category_order)),
            -(row["value_usd"] or 0.0),
            row["symbol"],
        )
    )
    for row in rows:
        value = row["value_usd"]
        row["tiny"] = (
            value is not None and value != 0 and abs(value) < tiny_threshold_usd
        )

    tiny_rows = [row for row in rows if row["tiny"]]
    known_values = [row["value_usd"] for row in rows if row["value_usd"] is not None]
    return {
        "rows": rows,
        "tiny_rows": tiny_rows,
        "regular_rows": [row for row in rows if not row["tiny"]],
        "tiny_total": sum(row["value_usd"] for row in tiny_rows),
        "tiny_threshold_usd": tiny_threshold_usd,
        "tiny_threshold_note": f"Positions below USD {tiny_threshold_usd:g} are grouped; detail remains listed.",
        "total_value": math.fsum(known_values) if known_values else None,
        "reconciliation_delta": (
            total_assets - math.fsum(known_values)
            if total_assets is not None and len(known_values) == len(rows)
            else None
        ),
    }


def liquidity_ladder(combined_data: dict, config: Optional[dict] = None) -> dict[str, Any]:
    """Report only explicitly classified liquidity, spending, and liabilities."""
    config = config if isinstance(config, dict) else {}

    def configured_amount(key: str) -> Optional[float]:
        amount = _number(config.get(key))
        return amount if amount is not None and amount >= 0 else None

    cash_available = configured_amount("cash_available_now_usd")
    assets_for_sale = configured_amount("assets_for_sale_usd")
    restricted_assets = configured_amount("restricted_assets_usd")
    spending = _number(config.get("essential_monthly_spending_usd"))
    spending_valid = spending is not None and spending > 0
    liabilities_present = "liabilities_usd" in config
    liabilities = configured_amount("liabilities_usd") if liabilities_present else None
    liabilities_known = liabilities is not None
    gross_assets = _number(combined_data.get("TOTAL_ASSETS"))
    net_worth = (
        gross_assets - liabilities
        if gross_assets is not None and liabilities_known
        else None
    )

    return {
        "cash_available_now": cash_available,
        "cash_available_state": "Known" if cash_available is not None else "Unknown",
        "assets_for_sale": assets_for_sale,
        "assets_for_sale_state": "Known" if assets_for_sale is not None else "Unknown",
        "restricted_assets": restricted_assets,
        "restricted_assets_state": "Known" if restricted_assets is not None else "Unknown",
        "unclassified_cash": _number(combined_data.get("CASH_DATA", {}).get("Total"))
        if isinstance(combined_data.get("CASH_DATA"), dict)
        else None,
        "essential_monthly_spending": spending if spending_valid else None,
        "spending_state": (
            "Known" if spending_valid else "Invalid - must be positive" if spending is not None else "Unknown"
        ),
        "runway_months": cash_available / spending if cash_available is not None and spending_valid else None,
        "runway_state": "Available" if cash_available is not None and spending_valid else "Unavailable",
        "gross_tracked_assets": gross_assets,
        "liabilities": liabilities,
        "liabilities_state": (
            "Confirmed zero" if liabilities_known and liabilities == 0 else "Known" if liabilities_known else "Unknown"
        ),
        "net_worth_after_known_liabilities": net_worth,
        "net_worth_state": "Known" if net_worth is not None else "Unknown liabilities or gross assets",
    }


def fire_progress(combined_data: dict, config: Optional[dict] = None) -> dict[str, Any]:
    """Use the saved portfolio value for FIRE; income principal is a separate basis.

    Legacy eligibility configuration no longer filters the portfolio. Existing
    result keys remain aliases for the full portfolio to preserve callers.
    """
    config = config if isinstance(config, dict) else {}
    eligible_value = _number(combined_data.get("TOTAL_ASSETS"))
    eligible_state = "Available" if eligible_value is not None else "Unavailable"

    if "fire_target_usd" in config:
        target_candidate = _number(config.get("fire_target_usd"))
    else:
        target_candidate = _number(combined_data.get("FINANCIAL_FREEDOM_GOAL_TARGET"))
    target = (
        target_candidate
        if target_candidate is not None and target_candidate > 0
        else None
    )
    if target is None:
        state = "Target not configured"
    elif eligible_value is None:
        state = "Portfolio value unavailable"
    else:
        state = "Available"
    remaining = (
        max(target - eligible_value, 0)
        if target is not None and eligible_value is not None
        else None
    )
    progress = (
        eligible_value / target
        if target is not None and eligible_value is not None
        else None
    )

    liquidity = liquidity_ladder(combined_data, config)
    income = income_breakdown(combined_data)
    monthly_income = (
        income["monthly_average"] if income["state"] == "Estimated" else None
    )
    spending = liquidity["essential_monthly_spending"]
    income_coverage = (
        monthly_income / spending
        if monthly_income is not None and spending is not None and spending > 0
        else None
    )

    return {
        "eligible_value": eligible_value,
        "category_values": _category_values(combined_data),
        "target": target,
        "remaining": remaining,
        "progress_fraction": progress,
        "progress_bar_fraction": min(progress, 1.0) if progress is not None else None,
        "included_categories": list(CATEGORIES),
        "excluded_categories": [],
        "eligible_value_state": eligible_state,
        "income_coverage_fraction": income_coverage,
        "income_coverage_state": (
            "Estimated" if income_coverage is not None else "Unavailable"
        ),
        "state": state,
    }


def targets_and_deviations(
    combined_data: dict, config: Optional[dict] = None
) -> list[dict[str, Any]]:
    """Compare actual category weights with explicitly configured target weights."""
    config = config if isinstance(config, dict) else {}
    targets = config.get("allocation_targets_pct", {})
    targets = targets if isinstance(targets, dict) else {}
    rows = []
    for category in category_rows(combined_data):
        raw_target = _number(targets.get(category["category"]))
        if raw_target is not None and 0 <= raw_target <= 100:
            target_weight = raw_target / 100
            deviation = (
                (category["weight"] - target_weight) * 100
                if category["weight"] is not None
                else None
            )
            basis = "Actual weight vs configured target"
            state = "Available" if deviation is not None else "Actual weight unavailable"
        else:
            target_weight = None
            deviation = None
            basis = "Target not configured"
            state = "Unconfigured"
        rows.append(
            {
                "category": category["category"],
                "value": category["value"],
                "actual_weight": category["weight"],
                "target_weight": target_weight,
                "deviation_pp": deviation,
                "deviation_pp_basis": basis,
                "state": state,
            }
        )
    return rows


def concentration_views(combined_data: dict) -> dict[str, Any]:
    """Group the same holdings by known provider, trading currency, and geography."""
    holdings = holdings_table(combined_data)
    total = holdings["total_value"]
    dimensions = ("provider", "trading_currency", "underlying_geography")
    views: dict[str, list[dict[str, Any]]] = {}
    reconciles: dict[str, bool] = {}

    for dimension in dimensions:
        amounts: dict[str, float] = {}
        unknown_count = 0
        for holding in holdings["rows"]:
            amount = holding["value_usd"]
            category = holding.get(dimension) or "Unknown"
            if amount is None:
                unknown_count += 1
                continue
            amounts[category] = amounts.get(category, 0.0) + amount
        rows = [
            {
                "category": category,
                "amount": amount,
                "weight": amount / total if total is not None and total > 0 else None,
                **({"unknown_rows": unknown_count} if category == "Unknown" else {}),
            }
            for category, amount in amounts.items()
        ]
        rows.sort(key=lambda row: row["amount"], reverse=True)
        if "Unknown" not in amounts:
            rows.append(
                {
                    "category": "Unknown",
                    "amount": 0.0,
                    "weight": 0.0 if total is not None and total > 0 else None,
                    "unknown_rows": unknown_count,
                }
            )
        amount_total = sum(row["amount"] for row in rows)
        views[dimension] = rows
        reconciles[dimension] = total is not None and math.isclose(
            amount_total, total, rel_tol=1e-9, abs_tol=0.01
        )

    return {
        **views,
        "total_value": total,
        "reconciles": reconciles,
        "unknown_value_rows": sum(
            row["value_usd"] is None for row in holdings["rows"]
        ),
    }


def source_statuses(
    combined_data: dict, max_age_seconds: float = 300.0
) -> dict[str, Any]:
    """Expose data freshness separately from estimates and unsupported coverage."""
    metadata = combined_data.get("DATA_METADATA")
    metadata = metadata if isinstance(metadata, dict) else {}
    source = str(metadata.get("source") or "").lower()
    age = _number(metadata.get("age_seconds"))
    if "cache" in source or (age is not None and age > max_age_seconds):
        overall_key = "Cached"
    elif source in {"live_api_calls", "live", "current"}:
        overall_key = "Current"
    else:
        overall_key = "Unknown"

    overall = overall_key
    if overall_key == "Cached" and age is not None:
        overall = f"Cached - data age {int(age)}s"
    fixed_income = combined_data.get("FIXED_INCOME_DATA")
    groups = fixed_income.get("group_weighted_interest") if isinstance(fixed_income, dict) else None
    has_manual_rates = isinstance(groups, dict) and any(
        isinstance(value, (list, tuple)) and len(value) > 1
        for value in groups.values()
    )
    receipts = combined_data.get("INCOME_RECEIPTS")

    return {
        "overall_key": overall_key,
        "overall": overall,
        "portfolio": overall,
        "investment_income": "Manual estimate" if has_manual_rates else "Unknown",
        "actual_receipts": (
            receipts.get("state", "Incomplete")
            if isinstance(receipts, dict)
            else "Incomplete"
        ),
        "valuation_date": combined_data.get("as_of_date")
        or metadata.get("last_updated", "Unknown"),
        "last_successful_refresh": metadata.get("last_updated", "Unknown"),
        "source": metadata.get("source", "Unknown"),
        "data_age_seconds": age,
    }
