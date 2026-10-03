from calendar import monthrange
from copy import deepcopy
from datetime import date, datetime, time, timezone
import json
from pathlib import Path
import re
from typing import Any, Iterable, Optional


MATERIALITY_USD = 100.0
QUANTITY_TOLERANCE = 1e-8
STABLECOINS = {"USDT", "USDC", "BUSD", "DAI", "PAX", "EURI"}
_SNAPSHOT_DATE_RE = re.compile(r"^combined_data_(\d{4}-\d{2}-\d{2})_")


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _position_status(start_quantity: float, end_quantity: float) -> str:
    if abs(start_quantity) <= QUANTITY_TOLERANCE:
        return "new" if abs(end_quantity) > QUANTITY_TOLERANCE else "unchanged"
    if abs(end_quantity) <= QUANTITY_TOLERANCE:
        return "closed"
    if end_quantity > start_quantity + QUANTITY_TOLERANCE:
        return "increased"
    if end_quantity < start_quantity - QUANTITY_TOLERANCE:
        return "decreased"
    return "unchanged"


def modified_dietz_return(
    *,
    start_value: float,
    end_value: float,
    cash_flows: Iterable[tuple[datetime, float]],
    period_start: datetime,
    period_end: datetime,
) -> Optional[float]:
    period_seconds = (period_end - period_start).total_seconds()
    if period_seconds <= 0:
        raise ValueError("Modified Dietz period_end must be after period_start.")

    total_flows = 0.0
    weighted_flows = 0.0
    for occurred_at, amount in cash_flows:
        if occurred_at < period_start or occurred_at > period_end:
            raise ValueError("Modified Dietz cash flow is outside the calculation period.")
        flow = float(amount)
        weight = (period_end - occurred_at).total_seconds() / period_seconds
        total_flows += flow
        weighted_flows += weight * flow

    denominator = float(start_value) + weighted_flows
    if abs(denominator) <= 1e-12:
        return None
    return (float(end_value) - float(start_value) - total_flows) / denominator


def classify_internal_transfer_legs(
    events: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Mark matching on-chain deposit and withdrawal legs as internal transfers."""
    normalized = [dict(event) for event in events]
    legs_by_transfer: dict[tuple[str, str], list[int]] = {}
    for index, event in enumerate(normalized):
        transfer_id = event.get("transfer_id")
        if not transfer_id or event.get("event_type") not in {"deposit", "withdrawal"}:
            continue
        key = (str(transfer_id), str(event.get("asset", "")).upper())
        legs_by_transfer.setdefault(key, []).append(index)

    for indices in legs_by_transfer.values():
        deposits = [
            index for index in indices if normalized[index]["event_type"] == "deposit"
        ]
        withdrawals = [
            index for index in indices if normalized[index]["event_type"] == "withdrawal"
        ]
        if len(deposits) != 1 or len(withdrawals) != 1:
            continue
        deposit = normalized[deposits[0]]
        withdrawal = normalized[withdrawals[0]]
        if abs(
            float(deposit.get("quantity", 0.0))
            - float(withdrawal.get("quantity", 0.0))
        ) > QUANTITY_TOLERANCE:
            continue
        deposit["event_type"] = "internal_transfer"
        withdrawal["event_type"] = "internal_transfer"

    return normalized


def calculate_crypto_performance(
    *,
    start_value_usd: float,
    end_value_usd: float,
    events: Iterable[dict[str, Any]],
    period_start: datetime,
    period_end: datetime,
    reconciliation_complete: bool,
) -> dict[str, Any]:
    cash_flows: list[tuple[datetime, float]] = []
    rewards_usd = 0.0
    fees_usd = 0.0
    coverage_complete = reconciliation_complete
    for event in events:
        occurred_at = _timestamp(event["occurred_at"])
        if occurred_at < period_start or occurred_at > period_end:
            continue
        asset = str(event.get("asset", "")).upper()
        if asset in STABLECOINS:
            continue
        event_type = str(event.get("event_type", "")).lower()
        if event_type not in {"buy", "sell", "deposit", "withdrawal", "reward", "fee"}:
            continue
        usd_value = event.get("usd_value")
        if usd_value is None:
            coverage_complete = False
            continue
        value = abs(float(usd_value))
        if event_type in {"buy", "deposit"}:
            cash_flows.append((occurred_at, value))
        elif event_type in {"sell", "withdrawal"}:
            cash_flows.append((occurred_at, -value))
        elif event_type == "reward":
            rewards_usd += value
        elif event_type == "fee":
            fees_usd += value
        if event_type != "fee" and abs(float(event.get("fee_quantity") or 0.0)) > 0:
            fee_usd = event.get("fee_usd")
            if fee_usd is None:
                coverage_complete = False
            else:
                fees_usd += abs(float(fee_usd))

    return_pct = None
    return_method = "unavailable"
    if coverage_complete:
        calculated = modified_dietz_return(
            start_value=start_value_usd,
            end_value=end_value_usd,
            cash_flows=cash_flows,
            period_start=period_start,
            period_end=period_end,
        )
        if calculated is not None:
            return_pct = calculated * 100
            return_method = "modified_dietz"
    return {
        "return_pct": return_pct,
        "net_flow_usd": (
            sum(amount for _, amount in cash_flows) if coverage_complete else None
        ),
        "income_usd": rewards_usd - fees_usd if coverage_complete else None,
        "return_method": return_method,
        "coverage": "complete" if coverage_complete else "partial",
    }


def classify_lending_positions(
    savings_positions: Iterable[dict[str, dict[str, tuple[float, float]]]],
) -> dict[str, Any]:
    stablecoin_positions = []
    volatile_earn = []
    for platform_group in savings_positions:
        for platform, positions in platform_group.items():
            for raw_asset, values in positions.items():
                asset = str(raw_asset).upper()
                principal, expected_apy = values
                if asset in STABLECOINS:
                    stablecoin_positions.append(
                        {
                            "account": platform,
                            "asset": asset,
                            "principal_usd": float(principal),
                            "expected_apy": float(expected_apy),
                            "status": "current",
                        }
                    )
                else:
                    volatile_earn.append(
                        {
                            "account": platform,
                            "asset": asset,
                            "quantity": float(principal),
                            "expected_apy": float(expected_apy),
                            "principal_bucket": "Crypto Coins",
                        }
                    )
    return {
        "stablecoin_principal_usd": sum(
            position["principal_usd"] for position in stablecoin_positions
        ),
        "stablecoin_positions": stablecoin_positions,
        "volatile_earn": volatile_earn,
    }


def calculate_lending_performance(
    *,
    start_principal_usd: Optional[float],
    end_principal_usd: float,
    events: Iterable[dict[str, Any]],
    period_start: datetime,
    period_end: datetime,
    source_coverage_complete: bool = True,
) -> dict[str, Any]:
    deposits_usd = 0.0
    withdrawals_usd = 0.0
    rewards_usd = 0.0
    fees_usd = 0.0
    cash_flows: list[tuple[datetime, float]] = []
    coverage_complete = start_principal_usd is not None and source_coverage_complete
    volatile_rewards: dict[str, dict[str, Any]] = {}

    for event in events:
        occurred_at = _timestamp(event["occurred_at"])
        if occurred_at < period_start or occurred_at > period_end:
            continue
        event_type = str(event["event_type"]).lower()
        asset = str(event.get("asset", "")).upper()
        usd_value = event.get("usd_value")
        if event_type not in {
            "lending_subscription",
            "lending_redemption",
            "reward",
            "fee",
        }:
            continue
        if asset and asset not in STABLECOINS:
            if event_type == "reward":
                reward = volatile_rewards.setdefault(
                    asset,
                    {
                        "asset": asset,
                        "quantity": 0.0,
                        "usd_value": 0.0,
                        "coverage": "complete",
                    },
                )
                reward["quantity"] += abs(float(event.get("quantity") or 0.0))
                if usd_value is None:
                    reward["usd_value"] = None
                    reward["coverage"] = "partial"
                elif reward["usd_value"] is not None:
                    reward["usd_value"] += abs(float(usd_value))
            continue
        if usd_value is None:
            coverage_complete = False
            continue
        value = abs(float(usd_value))
        if event_type == "lending_subscription":
            deposits_usd += value
            cash_flows.append((occurred_at, value))
        elif event_type == "lending_redemption":
            withdrawals_usd += value
            cash_flows.append((occurred_at, -value))
        elif event_type == "reward":
            rewards_usd += value
        elif event_type == "fee":
            fees_usd += value

    return_value = None
    return_method = "unavailable"
    if coverage_complete and start_principal_usd is not None:
        return_value = modified_dietz_return(
            start_value=start_principal_usd,
            end_value=end_principal_usd,
            cash_flows=cash_flows,
            period_start=period_start,
            period_end=period_end,
        )
        if return_value is not None:
            return_value *= 100
            return_method = "modified_dietz"

    return {
        "start_principal_usd": start_principal_usd,
        "end_principal_usd": float(end_principal_usd),
        "deposits_usd": deposits_usd if coverage_complete else None,
        "withdrawals_usd": withdrawals_usd if coverage_complete else None,
        "income_usd": rewards_usd - fees_usd if coverage_complete else None,
        "return_pct": return_value,
        "return_method": return_method,
        "coverage": "complete" if coverage_complete else "partial",
        "volatile_rewards": [
            volatile_rewards[asset] for asset in sorted(volatile_rewards)
        ],
    }


def _amount_usd(record: dict[str, Any]) -> Optional[float]:
    if record.get("amount_usd") not in (None, ""):
        return round(float(record["amount_usd"]), 2)
    if record.get("amount") not in (None, "") and record.get("fx_rate_to_usd") not in (
        None,
        "",
    ):
        return round(float(record["amount"]) * float(record["fx_rate_to_usd"]), 2)
    return None


def calculate_car_assets(
    *,
    assets: Iterable[dict[str, Any]],
    events: Iterable[dict[str, Any]],
    valuations: Iterable[dict[str, Any]],
    as_of_date: date,
) -> list[dict[str, Any]]:
    event_rows = list(events)
    valuation_rows = list(valuations)
    positions = []

    for asset in assets:
        asset_id = str(asset["asset_id"])
        asset_events = sorted(
            (
                event
                for event in event_rows
                if str(event.get("asset_id")) == asset_id
                and date.fromisoformat(str(event["occurred_at"])[:10]) <= as_of_date
            ),
            key=lambda event: event["occurred_at"],
        )
        purchase_cost = 0.0
        capitalized_costs = 0.0
        operating_expenses = 0.0
        sale_proceeds = 0.0
        selling_costs = 0.0
        impairment = 0.0
        sale_date = None
        amount_coverage_complete = True

        for event in asset_events:
            amount = _amount_usd(event)
            if amount is None:
                if str(event.get("event_type", "")).lower() in {
                    "purchase",
                    "capitalized_cost",
                    "operating_expense",
                    "sale_proceeds",
                    "selling_cost",
                    "impairment",
                }:
                    amount_coverage_complete = False
                continue
            event_type = str(event["event_type"]).lower()
            if event_type == "purchase":
                purchase_cost += abs(amount)
            elif event_type == "capitalized_cost":
                capitalized_costs += abs(amount)
            elif event_type == "operating_expense":
                operating_expenses += abs(amount)
            elif event_type == "sale_proceeds":
                sale_proceeds += abs(amount)
                sale_date = date.fromisoformat(str(event["occurred_at"])[:10])
            elif event_type == "selling_cost":
                selling_costs += abs(amount)
            elif event_type == "impairment":
                impairment += abs(amount)

        capitalized_cost = purchase_cost + capitalized_costs
        if capitalized_cost <= 0 and asset.get("legacy_carrying_value_usd") not in (
            None,
            "",
        ):
            capitalized_cost = float(asset["legacy_carrying_value_usd"])

        applicable_valuations = [
            valuation
            for valuation in valuation_rows
            if str(valuation.get("asset_id")) == asset_id
            and date.fromisoformat(str(valuation["as_of_date"])[:10]) <= as_of_date
        ]
        latest_valuation = max(
            applicable_valuations,
            key=lambda valuation: valuation["as_of_date"],
            default=None,
        )

        sold = sale_proceeds > 0
        carrying_value = max(capitalized_cost - impairment, 0.0)
        if latest_valuation is not None:
            carrying_value = float(latest_valuation["value_usd"])
        if sold:
            carrying_value = 0.0

        net_proceeds = sale_proceeds - selling_costs if sold else None
        realized_profit = (
            net_proceeds - capitalized_cost if net_proceeds is not None else None
        )
        all_in_profit = (
            realized_profit - operating_expenses
            if realized_profit is not None
            else None
        )
        roi_pct = (
            realized_profit / capitalized_cost * 100
            if realized_profit is not None and capitalized_cost > 0
            else None
        )
        purchase_date = (
            date.fromisoformat(str(asset["purchase_date"])[:10])
            if asset.get("purchase_date")
            else None
        )
        holding_days = (
            (sale_date - purchase_date).days
            if sale_date is not None and purchase_date is not None
            else None
        )

        positions.append(
            {
                "asset_id": asset_id,
                "name": asset.get("name") or asset_id,
                "status": "sold" if sold else asset.get("status", "active"),
                "capitalized_cost_usd": capitalized_cost,
                "operating_expenses_usd": operating_expenses,
                "carrying_value_usd": carrying_value,
                "net_proceeds_usd": net_proceeds,
                "realized_profit_usd": realized_profit,
                "all_in_profit_usd": all_in_profit,
                "roi_pct": roi_pct,
                "holding_days": holding_days,
                "return_pct": None,
                "return_method": "unavailable",
                "coverage": (
                    "complete"
                    if purchase_date is not None
                    and capitalized_cost > 0
                    and amount_coverage_complete
                    else "partial"
                ),
            }
        )

    return positions


def normalize_p2p_positions(
    rows: Iterable[dict[str, Any]], *, as_of_date: Optional[date] = None
) -> list[dict[str, Any]]:
    latest_by_account: dict[str, dict[str, Any]] = {}
    for row in rows:
        row_date = date.fromisoformat(str(row["as_of_date"])[:10])
        if as_of_date is not None and row_date > as_of_date:
            continue
        account = str(row["account"])
        status = str(row.get("status", "winding_down")).lower()
        if status not in {"winding_down", "closed"}:
            raise ValueError(f"Unsupported P2P status for {account}: {status}")
        current = latest_by_account.get(account)
        if current is None or str(row["as_of_date"]) > str(current["as_of_date"]):
            latest_by_account[account] = row

    positions = []
    for account, row in sorted(latest_by_account.items()):
        status = str(row.get("status", "winding_down")).lower()
        balance = float(row.get("balance_usd") or 0.0)
        if status == "closed" and abs(balance) > 1e-8:
            raise ValueError(f"Closed P2P position {account} must have zero balance.")
        if status == "closed" and not row.get("closed_at"):
            raise ValueError(f"Closed P2P position {account} must include closed_at.")
        positions.append(
            {
                "account": account,
                "balance_usd": balance,
                "as_of_date": row["as_of_date"],
                "status": status,
                "closed_at": row.get("closed_at") or None,
                "return_pct": None,
                "return_method": "unavailable",
                "coverage": "complete",
            }
        )
    return positions


def _snapshot_payload(snapshot: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not snapshot:
        return {}
    return snapshot.get("data", snapshot)


def select_contract_start_snapshot(
    snapshot_dir: Path, as_of_date: date, grace_days: int = 5
) -> Optional[dict[str, Any]]:
    period_start, _, _ = _quarter_bounds(as_of_date)
    start_date = period_start.date().toordinal()
    lower_cutoff = start_date - grace_days
    upper_cutoff = start_date + grace_days
    candidates = []
    for path in snapshot_dir.glob("combined_data_*.json"):
        match = _SNAPSHOT_DATE_RE.match(path.name)
        if not match:
            continue
        try:
            snapshot_date = date.fromisoformat(match.group(1))
        except ValueError:
            continue
        if lower_cutoff <= snapshot_date.toordinal() <= upper_cutoff:
            candidates.append((snapshot_date, path.name, path))

    for _, _, path in sorted(candidates, reverse=True):
        try:
            with path.open(encoding="utf-8") as handle:
                snapshot = json.load(handle)
        except (OSError, json.JSONDecodeError):
            continue
        payload = _snapshot_payload(snapshot)
        has_v2_positions = (
            payload.get("DATA_CONTRACT_VERSION") == 2 and "POSITION_DATA" in payload
        )
        legacy_crypto = payload.get("CRYPTO_DATA", {})
        has_legacy_positions = bool(
            legacy_crypto.get("Token_Quantities")
            or legacy_crypto.get("Crypto_Market_Values")
        )
        if has_v2_positions or has_legacy_positions:
            return {"path": path, "data": snapshot}
    return None


def _quarter_bounds(as_of_date: date) -> tuple[datetime, datetime, str]:
    quarter = (as_of_date.month - 1) // 3 + 1
    start_month = (quarter - 1) * 3 + 1
    end_month = start_month + 2
    start_date = date(as_of_date.year, start_month, 1)
    end_date = date(
        as_of_date.year,
        end_month,
        monthrange(as_of_date.year, end_month)[1],
    )
    return (
        datetime.combine(start_date, time.min, timezone.utc),
        datetime.combine(end_date, time.max, timezone.utc),
        f"{as_of_date.year}-Q{quarter}",
    )


def _snapshot_crypto_positions(
    snapshot: Optional[dict[str, Any]],
) -> tuple[dict[str, float], dict[str, float]]:
    payload = _snapshot_payload(snapshot)
    positions = payload.get("POSITION_DATA", {}).get("crypto", [])
    if positions:
        quantities = {
            str(position["asset"]).upper(): float(position.get("quantity", 0.0))
            for position in positions
        }
        values = {
            str(position["asset"]).upper(): float(position.get("value_usd", 0.0))
            for position in positions
        }
        return quantities, values

    legacy_crypto = payload.get("CRYPTO_DATA", {})
    quantities = {
        str(asset).upper(): float(quantity)
        for asset, quantity in legacy_crypto.get("Token_Quantities", {}).items()
    }
    values = {
        str(asset).upper(): float(value)
        for asset, value in legacy_crypto.get("Crypto_Market_Values", {}).items()
    }
    return quantities, values


def recover_crypto_positions(
    live_quantities: dict[str, float],
    live_values_usd: dict[str, float],
    latest_snapshot: Optional[dict[str, Any]],
    *,
    balance_sources: Optional[dict[str, str]] = None,
) -> tuple[dict[str, float], dict[str, float], str]:
    snapshot_quantities, snapshot_values = _snapshot_crypto_positions(latest_snapshot)
    # A nonempty aggregate is not automatically complete: when a balance source
    # failed or had its balances dropped by filters, live data covers only part
    # of the portfolio and must not be labeled "live".
    sources_failed = balance_sources is not None and any(
        source not in (None, "", "ok") for source in balance_sources.values()
    )
    if (
        live_quantities
        and not sources_failed
        and all(asset in live_values_usd for asset in live_quantities)
    ):
        return dict(live_quantities), dict(live_values_usd), "live"
    if not live_quantities and snapshot_quantities:
        return snapshot_quantities, snapshot_values, "stale"
    if live_quantities:
        recovered_values = {
            asset: float(live_values_usd.get(asset, snapshot_values.get(asset, 0.0)))
            for asset in live_quantities
        }
        if sources_failed:
            # Keep the snapshot holdings of assets the live fetch could not
            # see; losing a failed exchange's balances would understate the
            # portfolio even though its accounts were not actually empty.
            recovered_quantities = dict(live_quantities)
            for asset, quantity in snapshot_quantities.items():
                if asset not in recovered_quantities:
                    recovered_quantities[asset] = float(quantity)
                    recovered_values[asset] = float(snapshot_values.get(asset, 0.0))
            return recovered_quantities, recovered_values, "partial"
        return dict(live_quantities), recovered_values, "partial"
    return {}, {}, "partial"


def _snapshot_lending_principal(snapshot: Optional[dict[str, Any]]) -> Optional[float]:
    payload = _snapshot_payload(snapshot)
    positions = payload.get("POSITION_DATA", {}).get("crypto_lending", [])
    if positions:
        return sum(float(position.get("principal_usd", 0.0)) for position in positions)
    group_interest = payload.get("FIXED_INCOME_DATA", {}).get(
        "group_weighted_interest", {}
    )
    legacy_lending = group_interest.get("Crypto Landing")
    if isinstance(legacy_lending, (list, tuple)) and legacy_lending:
        return float(legacy_lending[0])
    return None


def build_portfolio_contract(
    *,
    ledger,
    live_crypto_quantities: dict[str, float],
    live_crypto_market_values: dict[str, float],
    savings_positions: Iterable[dict[str, dict[str, tuple[float, float]]]],
    legacy_other_assets_usd: float,
    legacy_p2p_balance_usd: float,
    as_of_date: date,
    start_snapshot: Optional[dict[str, Any]] = None,
    crypto_freshness: str = "live",
    crypto_balance_sources: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    period_start, quarter_end, quarter_key = _quarter_bounds(as_of_date)
    # Cap the performance period at the as-of date: when the pipeline runs
    # before the last day of the quarter, weighting cash flows against the
    # future calendar quarter end would assume a horizon that has not elapsed
    # and understate the recorded return.
    period_end = min(
        quarter_end, datetime.combine(as_of_date, time.max, timezone.utc)
    )
    events = classify_internal_transfer_legs(ledger.load_crypto_events())
    import_state = ledger.load_import_state()
    start_quantities, start_values = _snapshot_crypto_positions(start_snapshot)
    boundary_complete = bool(start_quantities or start_values)
    if not boundary_complete:
        start_quantities = dict(live_crypto_quantities)
        start_values = dict(live_crypto_market_values)

    source_coverage = {
        source: str(details.get("coverage", "complete"))
        for source, details in import_state.items()
        if isinstance(details, dict)
    }
    crypto_activity = aggregate_crypto_quarter(
        events=events,
        start_quantities=start_quantities,
        end_quantities=live_crypto_quantities,
        start_values_usd=start_values,
        end_values_usd=live_crypto_market_values,
        period_start=period_start,
        period_end=period_end,
        source_coverage=source_coverage,
    )
    if not boundary_complete:
        for row in crypto_activity:
            row["coverage"] = "partial"
            for field in ("buys_usd", "sells_usd", "rewards_usd", "fees_usd"):
                row[field] = None

    classified_lending = classify_lending_positions(savings_positions)
    quarter_events = [
        event
        for event in events
        if period_start <= _timestamp(event["occurred_at"]) <= period_end
    ]
    crypto_performance = calculate_crypto_performance(
        start_value_usd=sum(start_values.values()),
        end_value_usd=sum(float(value) for value in live_crypto_market_values.values()),
        events=quarter_events,
        period_start=period_start,
        period_end=period_end,
        reconciliation_complete=(
            boundary_complete
            and all(row.get("coverage") == "complete" for row in crypto_activity)
        ),
    )
    lending_performance = calculate_lending_performance(
        start_principal_usd=_snapshot_lending_principal(start_snapshot),
        end_principal_usd=classified_lending["stablecoin_principal_usd"],
        events=quarter_events,
        period_start=period_start,
        period_end=period_end,
        source_coverage_complete=all(
            import_state.get(str(position.get("account", "")).lower(), {})
            .get("lending", {})
            .get("coverage")
            == "complete"
            for position in classified_lending["stablecoin_positions"]
        ),
    )

    car_assets = ledger.load_car_assets()
    if car_assets:
        cars = calculate_car_assets(
            assets=car_assets,
            events=ledger.load_car_events(),
            valuations=ledger.load_car_valuations(),
            as_of_date=as_of_date,
        )
        car_quality = "complete" if all(
            car["coverage"] == "complete" for car in cars
        ) else "partial"
    else:
        cars = [
            {
                "asset_id": "legacy-other-bets",
                "name": "Other Bets",
                "status": "legacy",
                "capitalized_cost_usd": None,
                "operating_expenses_usd": None,
                "carrying_value_usd": float(legacy_other_assets_usd),
                "net_proceeds_usd": None,
                "realized_profit_usd": None,
                "all_in_profit_usd": None,
                "roi_pct": None,
                "holding_days": None,
                "return_pct": None,
                "return_method": "unavailable",
                "coverage": "partial",
            }
        ]
        car_quality = "legacy"

    p2p_rows = ledger.load_p2p_positions()
    p2p_positions = (
        normalize_p2p_positions(p2p_rows, as_of_date=as_of_date) if p2p_rows else []
    )
    if p2p_positions:
        p2p_quality = "complete"
    else:
        p2p_positions = [
            {
                "account": "legacy",
                "balance_usd": float(legacy_p2p_balance_usd),
                "as_of_date": as_of_date.isoformat(),
                "status": "legacy",
                "closed_at": None,
                "return_pct": None,
                "return_method": "unavailable",
                "coverage": "partial",
            }
        ]
        p2p_quality = "legacy"

    crypto_positions = [
        {
            "asset": asset,
            "quantity": float(quantity),
            "value_usd": float(live_crypto_market_values.get(asset, 0.0)),
            "status": "current",
        }
        for asset, quantity in live_crypto_quantities.items()
    ]
    sold_cars = [car for car in cars if car["status"] == "sold"]
    return {
        "DATA_CONTRACT_VERSION": 2,
        "POSITION_DATA": {
            "as_of_date": as_of_date.isoformat(),
            "crypto": crypto_positions,
            "crypto_lending": classified_lending["stablecoin_positions"],
            "crypto_earn_volatile": classified_lending["volatile_earn"],
            "other_assets": cars,
            "p2p": p2p_positions,
        },
        "ACTIVITY_DATA": {
            "quarters": {
                quarter_key: {
                    "period_start": period_start.date().isoformat(),
                    "period_end": period_end.date().isoformat(),
                    "crypto": crypto_activity,
                    "crypto_performance": crypto_performance,
                    "crypto_lending": lending_performance,
                    "sold_cars": sold_cars,
                }
            }
        },
        "PERFORMANCE_DATA": {
            "buckets": {
                "Crypto Coins": {
                    "return_pct": crypto_performance["return_pct"],
                    "net_flow_usd": crypto_performance["net_flow_usd"],
                    "income_usd": crypto_performance["income_usd"],
                    "return_method": crypto_performance["return_method"],
                    "data_quality": crypto_performance["coverage"],
                },
                "Crypto Lending": {
                    "return_pct": lending_performance["return_pct"],
                    "net_flow_usd": (
                        lending_performance["deposits_usd"]
                        - lending_performance["withdrawals_usd"]
                        if lending_performance["deposits_usd"] is not None
                        else None
                    ),
                    "income_usd": lending_performance["income_usd"],
                    "return_method": lending_performance["return_method"],
                    "data_quality": lending_performance["coverage"],
                },
                "Other Bets": {
                    "return_pct": None,
                    "net_flow_usd": None,
                    "return_method": "unavailable",
                    "data_quality": car_quality,
                },
                "P2P Lending": {
                    "return_pct": None,
                    "net_flow_usd": None,
                    "return_method": "unavailable",
                    "data_quality": p2p_quality,
                },
            }
        },
        "DATA_QUALITY": {
            "crypto": {
                "coverage": crypto_performance["coverage"],
                "freshness": crypto_freshness,
                "sources": import_state,
                "balance_sources": (
                    dict(crypto_balance_sources) if crypto_balance_sources else None
                ),
            },
            "crypto_lending": {"coverage": lending_performance["coverage"]},
            "other_assets": {"coverage": car_quality},
            "p2p": {"coverage": p2p_quality},
        },
    }


def upgrade_legacy_combined_data(
    combined_data: dict[str, Any],
    *,
    ledger,
    as_of_date: date,
    start_snapshot: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Add the v2 contract to an archived legacy combined_data payload."""
    upgraded = deepcopy(combined_data)
    crypto = combined_data.get("CRYPTO_DATA", {})
    quantities = {
        str(asset).upper(): float(quantity)
        for asset, quantity in crypto.get("Token_Quantities", {}).items()
    }
    market_values = {
        str(asset).upper(): float(value)
        for asset, value in crypto.get("Crypto_Market_Values", {}).items()
    }

    fixed_income = combined_data.get("FIXED_INCOME_DATA", {})
    raw_lending = fixed_income.get("fixed_income_full_data", {}).get(
        "Crypto Landing", {}
    )
    lending_positions = {}
    for platform, positions in raw_lending.items():
        normalized_positions = {}
        for asset, values in positions.items():
            if str(asset).upper() in {"", "NONE"}:
                continue
            if not isinstance(values, (list, tuple)) or len(values) < 2:
                continue
            normalized_positions[str(asset).upper()] = (
                float(values[0]),
                float(values[1]),
            )
        if normalized_positions:
            lending_positions[str(platform)] = normalized_positions

    group_interest = fixed_income.get("group_weighted_interest", {})
    p2p_group = group_interest.get("p2p_lending", (0.0, 0.0))
    legacy_p2p = (
        float(p2p_group[0])
        if isinstance(p2p_group, (list, tuple)) and p2p_group
        else 0.0
    )
    other_assets = combined_data.get("OTHER_ASSETS", {})
    legacy_other = float(other_assets.get("Other Bets", 0.0) or 0.0)

    contract = build_portfolio_contract(
        ledger=ledger,
        live_crypto_quantities=quantities,
        live_crypto_market_values=market_values,
        savings_positions=[lending_positions] if lending_positions else [],
        legacy_other_assets_usd=legacy_other,
        legacy_p2p_balance_usd=legacy_p2p,
        as_of_date=as_of_date,
        start_snapshot=start_snapshot,
        crypto_freshness="snapshot",
    )
    upgraded.update(contract)
    return upgraded


def project_legacy_values(contract: dict[str, Any]) -> dict[str, float]:
    positions = contract["POSITION_DATA"]
    return {
        "crypto_value_usd": sum(
            float(position.get("value_usd", 0.0)) for position in positions["crypto"]
        ),
        "crypto_lending_value_usd": sum(
            float(position.get("principal_usd", 0.0))
            for position in positions["crypto_lending"]
        ),
        "p2p_value_usd": sum(
            float(position.get("balance_usd", 0.0)) for position in positions["p2p"]
        ),
        "other_assets_value_usd": sum(
            float(position.get("carrying_value_usd", 0.0))
            for position in positions["other_assets"]
        ),
    }


def aggregate_crypto_quarter(
    *,
    events: Iterable[dict[str, Any]],
    start_quantities: dict[str, float],
    end_quantities: dict[str, float],
    start_values_usd: dict[str, float],
    end_values_usd: dict[str, float],
    period_start: datetime,
    period_end: datetime,
    source_coverage: Optional[dict[str, str]] = None,
    materiality_usd: float = MATERIALITY_USD,
) -> list[dict[str, Any]]:
    in_period = [
        event
        for event in events
        if period_start <= _timestamp(event["occurred_at"]) <= period_end
    ]
    assets = set(start_quantities) | set(end_quantities)
    assets.update(str(event["asset"]).upper() for event in in_period)
    rows = []

    for asset in assets:
        start_quantity = float(start_quantities.get(asset, 0.0))
        end_quantity = float(end_quantities.get(asset, 0.0))
        start_value = float(start_values_usd.get(asset, 0.0))
        end_value = float(end_values_usd.get(asset, 0.0))
        if max(abs(start_value), abs(end_value)) < materiality_usd:
            continue

        buys_quantity = 0.0
        sells_quantity = 0.0
        rewards_quantity = 0.0
        fees_quantity = 0.0
        external_transfers_quantity = 0.0
        internal_transfers_quantity = 0.0
        buys_usd = 0.0
        sells_usd = 0.0
        rewards_usd = 0.0
        fees_usd = 0.0
        value_coverage_complete = True
        sources = set()

        for event in in_period:
            event_asset = str(event["asset"]).upper()
            fee_asset = str(event.get("fee_asset") or "").upper()
            if event_asset != asset and fee_asset != asset:
                continue
            sources.add(str(event.get("source", "manual")))
            event_type = str(event["event_type"]).lower()
            quantity = float(event.get("quantity") or 0.0)
            usd_value = event.get("usd_value")

            if event_asset == asset:
                if event_type == "buy":
                    buys_quantity += quantity
                    if usd_value is None:
                        value_coverage_complete = False
                    else:
                        buys_usd += float(usd_value)
                elif event_type == "sell":
                    sells_quantity += quantity
                    if usd_value is None:
                        value_coverage_complete = False
                    else:
                        sells_usd += float(usd_value)
                elif event_type == "reward":
                    rewards_quantity += quantity
                    if usd_value is None:
                        value_coverage_complete = False
                    else:
                        rewards_usd += float(usd_value)
                elif event_type in {"deposit", "withdrawal"}:
                    sign = 1.0 if event_type == "deposit" else -1.0
                    external_transfers_quantity += sign * quantity
                elif event_type == "internal_transfer":
                    internal_transfers_quantity += quantity
                elif event_type == "fee":
                    fees_quantity += quantity
                    if usd_value is None:
                        value_coverage_complete = False
                    else:
                        fees_usd += float(usd_value)

            if fee_asset == asset:
                fee_quantity = abs(float(event.get("fee_quantity") or 0.0))
                fees_quantity += fee_quantity
                if event.get("fee_usd") is not None:
                    fees_usd += abs(float(event["fee_usd"]))
                elif fee_quantity > 0:
                    value_coverage_complete = False

        net_change = (
            buys_quantity
            - sells_quantity
            + rewards_quantity
            - fees_quantity
            + external_transfers_quantity
        )
        unexplained = end_quantity - start_quantity - net_change
        reconciliation_complete = abs(unexplained) <= QUANTITY_TOLERANCE
        source_complete = all(
            (source_coverage or {}).get(source, "complete") == "complete"
            for source in sources
        )
        coverage = (
            "complete"
            if reconciliation_complete and source_complete and value_coverage_complete
            else "partial"
        )
        rows.append(
            {
                "asset": asset,
                "start_quantity": start_quantity,
                "end_quantity": end_quantity,
                "start_value_usd": start_value,
                "end_value_usd": end_value,
                "buys_quantity": buys_quantity,
                "buys_usd": buys_usd if value_coverage_complete else None,
                "sells_quantity": sells_quantity,
                "sells_usd": sells_usd if value_coverage_complete else None,
                "rewards_quantity": rewards_quantity,
                "rewards_usd": rewards_usd if value_coverage_complete else None,
                "fees_quantity": fees_quantity,
                "fees_usd": fees_usd if value_coverage_complete else None,
                "external_transfers_quantity": external_transfers_quantity,
                "internal_transfers_quantity": internal_transfers_quantity,
                "net_change_quantity": net_change,
                "unexplained_quantity": 0.0 if reconciliation_complete else unexplained,
                "status": _position_status(start_quantity, end_quantity),
                "coverage": coverage,
            }
        )

    return sorted(rows, key=lambda row: (-row["end_value_usd"], row["asset"]))
