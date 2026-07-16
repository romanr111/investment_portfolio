"""Position-level analysis: activity classification and ratio calculations."""

from dataclasses import dataclass
from typing import List, Optional, Tuple

from .config import (
    CHINA_EQUITY_SYMBOLS,
    CHINESE_STOCKS,
    CORE_SYMBOLS,
    EXCLUDED_FROM_EQUITY,
    HKD_TO_USD_RATE,
    SPECIAL_ASSET_TICKERS,
)
from .flex_xml_parser import PositionRecord, SnapshotData

INCREASED = "Збільшив"
DECREASED = "Зменшив"
UNCHANGED = "Без змін"
NEW_POSITION = "Нова позиція"
ELIMINATED = "Закрита позиція"

ICON_NEW = "🆕"
ICON_INCREASED = "➕"
ICON_DECREASED = "➖"
ICON_UNCHANGED = ""
ICON_ELIMINATED = "✖"


@dataclass
class PositionAnalysis:
    symbol: str
    activity: str
    avg_entry_price: float
    avg_exit_price: float
    weight: float
    price_change_pct: float
    is_special_asset: bool
    is_china_equity: bool


@dataclass
class AggregateBills:
    total_value: float
    weighted_avg_price: float


def is_special_asset(symbol: str) -> bool:
    return symbol in SPECIAL_ASSET_TICKERS


def is_excluded_from_equity(symbol: str, asset_category: str = "") -> bool:
    if symbol in EXCLUDED_FROM_EQUITY:
        return True
    if asset_category == "BILL":
        return True
    return False


def aggregate_bills(
    start: SnapshotData, end: SnapshotData
) -> Tuple[Optional[AggregateBills], Optional[AggregateBills]]:
    """Aggregate all BILL positions into a single ``BILLS`` entry."""

    def _aggregate(snap: SnapshotData) -> Optional[AggregateBills]:
        total_value = 0.0
        weighted_price_sum = 0.0
        total_nominal = 0.0
        for rec in snap.positions.values():
            if rec.asset_category != "BILL":
                continue
            total_value += rec.position_value
            weighted_price_sum += rec.cost_basis_price * rec.shares
            total_nominal += rec.shares
        if total_nominal <= 0:
            return None
        return AggregateBills(
            total_value=total_value,
            weighted_avg_price=weighted_price_sum / total_nominal,
        )

    return _aggregate(start), _aggregate(end)


def usd_value(record: Optional[PositionRecord]) -> float:
    if record is None:
        return 0.0
    if record.symbol in CHINESE_STOCKS:
        return record.position_value * HKD_TO_USD_RATE
    return record.position_value


def price_change_pct(cost_basis: float, mark_price: float) -> float:
    if cost_basis > 0 and mark_price > 0:
        return ((mark_price - cost_basis) / cost_basis) * 100
    return 0.0


def sell_trades_for(
    snap: SnapshotData, symbol: str
) -> Tuple[float, float]:
    """Return (total_sell_quantity, weighted_avg_sell_price) for a symbol."""
    total_qty = 0.0
    weighted_sum = 0.0
    for trade in snap.trades:
        if trade.symbol != symbol:
            continue
        is_sell = trade.buy_sell == "SELL" or trade.quantity < 0
        if not is_sell:
            continue
        qty = abs(trade.quantity)
        total_qty += qty
        weighted_sum += qty * trade.trade_price
    avg = weighted_sum / total_qty if total_qty > 0 else 0.0
    return total_qty, avg


def equity_total_value(snap: SnapshotData) -> float:
    """Sum USD values of equity (non-excluded, non-BILL) positions."""
    total = 0.0
    for symbol, rec in snap.positions.items():
        if is_excluded_from_equity(symbol, rec.asset_category):
            continue
        total += usd_value(rec)
    return total


def special_assets_value(snap: SnapshotData) -> float:
    """Sum USD values of special assets (bonds, metals, commodities, BILLS)."""
    total = 0.0
    for symbol, rec in snap.positions.items():
        if symbol in SPECIAL_ASSET_TICKERS or rec.asset_category == "BILL":
            total += usd_value(rec)
    return total


def analyze_position(
    symbol: str,
    start_snap: SnapshotData,
    end_snap: SnapshotData,
    total_value_for_weight: float,
    start_total_value_for_weight: float = 0.0,
) -> Optional[PositionAnalysis]:
    """Classify a single position's activity between two snapshots.

    ``total_value_for_weight`` is the end-period total used for open/new
    positions. ``start_total_value_for_weight`` is the start-period total
    used for closed (eliminated) positions; if 0, falls back to the
    end-period total for backward compatibility.
    """
    start_rec = start_snap.positions.get(symbol)
    end_rec = end_snap.positions.get(symbol)

    if start_rec is None and end_rec is None:
        return None

    activity = ""
    avg_entry = 0.0
    avg_exit = 0.0
    price_pct = 0.0
    special = is_special_asset(symbol)
    china_eq = symbol in CHINA_EQUITY_SYMBOLS

    is_closed = False

    if start_rec and end_rec:
        if start_rec.shares > 0:
            pct_change = (
                (end_rec.shares - start_rec.shares) / start_rec.shares * 100
            )
        else:
            pct_change = 0.0
        if pct_change > 0:
            activity = (
                f"{ICON_INCREASED} {INCREASED} (+{int(round(abs(pct_change)))}%)"
            )
        elif pct_change < 0:
            activity = (
                f"{ICON_DECREASED} {DECREASED} "
                f"(-{int(round(abs(pct_change)))}%)"
            )
        else:
            activity = f"{ICON_UNCHANGED} {UNCHANGED}"
        avg_entry = end_rec.cost_basis_price
        price_pct = price_change_pct(end_rec.cost_basis_price, end_rec.mark_price)
    elif start_rec and not end_rec:
        activity = f"{ICON_ELIMINATED} {ELIMINATED}"
        avg_entry = start_rec.cost_basis_price
        _, avg_exit = sell_trades_for(end_snap, symbol)
        if avg_entry > 0 and avg_exit > 0:
            price_pct = ((avg_exit - avg_entry) / avg_entry) * 100
        is_closed = True
    elif end_rec and not start_rec:
        activity = f"{ICON_NEW} {NEW_POSITION}"
        avg_entry = end_rec.cost_basis_price
        price_pct = price_change_pct(end_rec.cost_basis_price, end_rec.mark_price)

    weight = 0.0
    if is_closed and start_rec:
        denom = start_total_value_for_weight or total_value_for_weight
        if denom > 0:
            weight = (usd_value(start_rec) / denom) * 100
    elif end_rec and total_value_for_weight > 0:
        weight = (usd_value(end_rec) / total_value_for_weight) * 100
    elif start_rec and total_value_for_weight > 0:
        weight = (usd_value(start_rec) / total_value_for_weight) * 100

    return PositionAnalysis(
        symbol=symbol,
        activity=activity,
        avg_entry_price=avg_entry,
        avg_exit_price=avg_exit,
        weight=weight,
        price_change_pct=price_pct,
        is_special_asset=special,
        is_china_equity=china_eq,
    )


def core_satellite_ratio(snap: SnapshotData) -> Tuple[float, float]:
    total = 0.0
    core = 0.0
    for symbol, rec in snap.positions.items():
        if is_excluded_from_equity(symbol, rec.asset_category):
            continue
        val = usd_value(rec)
        total += val
        if symbol in CORE_SYMBOLS:
            core += val
    if total <= 0:
        return 0.0, 0.0
    core_pct = (core / total) * 100
    return core_pct, 100 - core_pct


def china_ratio(snap: SnapshotData) -> Tuple[float, float]:
    total = 0.0
    china = 0.0
    for symbol, rec in snap.positions.items():
        if is_excluded_from_equity(symbol, rec.asset_category):
            continue
        val = usd_value(rec)
        total += val
        if symbol in CHINA_EQUITY_SYMBOLS:
            china += val
    if total <= 0:
        return 0.0, 0.0
    china_pct = (china / total) * 100
    return china_pct, 100 - china_pct


def all_symbols(start_snap: SnapshotData, end_snap: SnapshotData) -> List[str]:
    syms = set(start_snap.positions.keys()) | set(end_snap.positions.keys())
    return sorted(syms)