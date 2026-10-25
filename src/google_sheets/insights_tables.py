"""Typed sections for the single dated portfolio worksheet."""

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from src.google_sheets.insights_cells import CellBlock, CellValue, render_blocks
from src.google_sheets.insights_finance import (
    category_rows,
    fire_progress,
    holdings_table,
    income_breakdown,
    liquidity_ladder,
    snapshot_comparison,
    source_statuses,
)

LBL_IB_RETURN = "IB return - YTD - TWR"
# The compact holdings column is narrow; the header reads as two deliberate lines.
LBL_UNREALIZED_PNL_COMPACT = "Unrealized P&L\nvs cost"


@dataclass(frozen=True)
class InsightTab:
    title: str
    blocks: tuple[CellBlock, ...]
    header_offsets: dict[str, int] = field(default_factory=dict)
    filter_block_name: Optional[str] = None
    filter_end_offset: Optional[int] = None
    freeze_rows: int = 2
    freeze_columns: int = 0
    row_groups: tuple[tuple[str, int, int], ...] = ()
    column_widths: tuple[int, ...] = ()
    emphasis_rows: tuple[tuple[str, int], ...] = ()
    pnl_columns: tuple[tuple[str, int], ...] = ()


def _cell(value: Any, kind: str) -> CellValue:
    if value is None:
        return CellValue("Unavailable", "status")
    return CellValue(value, kind)


def _money(value: Any) -> CellValue:
    return _cell(value, "money")


def _percent(value: Any) -> CellValue:
    return _cell(value, "percent")


def _status(value: Any) -> CellValue:
    return CellValue("Unknown" if value is None else str(value), "status")


def _date_cell(value: Optional[str]) -> CellValue:
    if value is None:
        return _status("Unknown")
    try:
        return CellValue(date.fromisoformat(str(value)[:10]), "date")
    except ValueError:
        return _status("Unknown")


def _balance_change_label(previous_date: Optional[str]) -> str:
    """State the comparison period in the label so the delta reads unambiguous."""
    if previous_date is None:
        return "Balance change"
    try:
        parsed = date.fromisoformat(str(previous_date)[:10])
    except ValueError:
        return "Balance change"
    return f"Balance change\nvs {parsed.day} {parsed.strftime('%b')} {parsed.year}"


def _current_date(data: dict, current_date: Optional[str]) -> Optional[str]:
    if current_date:
        try:
            return date.fromisoformat(str(current_date)[:10]).isoformat()
        except ValueError:
            return None
    value = data.get("as_of_date")
    if not value:
        metadata = data.get("DATA_METADATA")
        value = metadata.get("last_updated") if isinstance(metadata, dict) else None
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError:
        return None


def _number(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def build_portfolio_tab(
    combined_data: dict,
    config: Optional[dict] = None,
    previous_snapshot: Optional[dict] = None,
    previous_date: Optional[str] = None,
    current_date: Optional[str] = None,
) -> InsightTab:
    """Build the one dated compact portfolio snapshot; no worksheet discovery or I/O.

    Only the four visible panels are generated: FIRE/performance, holdings grouped
    by asset category, portfolio totals/allocation, and estimated income. Full
    holdings tables, allocation targets, comparisons, receipts, liquidity, FIRE
    detail, exposure views, benchmarks and methodology prose are no longer
    rendered.
    """
    settings = config if isinstance(config, dict) else {}
    valuation_date = _current_date(combined_data, current_date)
    if valuation_date is None:
        raise ValueError("A valid valuation date is required before writing Sheets")
    previous_date = (
        _current_date(previous_snapshot, previous_date) if previous_snapshot else None
    )
    comparison = snapshot_comparison(
        combined_data, previous_snapshot, valuation_date, previous_date
    )
    liquidity = liquidity_ladder(combined_data, settings)
    income = income_breakdown(combined_data)
    fire = fire_progress(combined_data, settings)
    statuses = source_statuses(combined_data)
    twr = _number((combined_data.get("IB_PERFORMANCE") or {}).get("rate_of_return_pct"))
    holdings = holdings_table(combined_data)
    holding_rows = [
        ("Holdings - USD",),
        ("Asset", "Value", LBL_UNREALIZED_PNL_COMPACT),
    ]
    grouped = {}
    ib_data = combined_data.get("IB_DATA")
    ib_data = ib_data if isinstance(ib_data, dict) else {}
    china_symbols = ib_data.get("China Stocks") or {}
    china_symbols = china_symbols if isinstance(china_symbols, dict) else {}
    for row in holdings["rows"]:
        if row["value_usd"] == 0:
            continue
        category = row["category"]
        if category == "Stocks" and row["symbol"] in china_symbols:
            category = "China Stocks"
        grouped.setdefault(category, []).append(row)
    emphasis = []
    for category in (
        "Bonds",
        "China Stocks",
        "Stocks",
        "Precious Metals",
        "Commodities",
        "REIT",
        "Crypto Coins",
        "Crypto Lending",
        "P2P Lending",
        "Cash",
        "Other Bets",
    ):
        positions = grouped.get(category, [])
        if not positions:
            continue
        if len(holding_rows) > 2:
            holding_rows.append(("",))
        if len(positions) > 1:  # a lone category row is data, not a summary
            emphasis.append(("holdings", len(holding_rows)))
        total = (
            sum(row["value_usd"] for row in positions)
            if all(row["value_usd"] is not None for row in positions)
            else None
        )
        holding_rows.append((category, _cell(total, "amount")))
        for row in positions:
            if not row["tiny"] and row["symbol"] != category:  # symbol stays visible; skip exact category-name echo
                holding_rows.append(
                    (
                        row["symbol"],
                        _cell(row["value_usd"], "amount"),
                        _percent(row["pnl_pct"]) if row["pnl_pct"] is not None else "",
                    )
                )
        tiny = [row for row in positions if row["tiny"]]
        if tiny and len(tiny) < len(positions):
            holding_rows.append(
                (
                    "Other positions (<$100)",
                    _cell(sum(row["value_usd"] for row in tiny), "amount"),
                )
            )

    summary_rows = [("Portfolio", _date_cell(valuation_date))]
    if fire["target"] is not None:
        summary_rows = [
            ("FIRE progress", _cell(fire["progress_fraction"], "weight")),
            ("Target", _cell(fire["target"], "amount")),
        ]
    performance_rows = [
        ("Performance - YTD",),
        (LBL_IB_RETURN, _percent(twr / 100 if twr is not None else None)),
    ]
    index_data = combined_data.get("INDEX_PERFORMANCE")
    if isinstance(index_data, dict):
        for key, item in index_data.items():
            if (
                isinstance(item, dict)
                and _number(item.get("rate_of_return_pct")) is not None
            ):
                performance_rows.append(
                    (
                        item.get("name", key),
                        _percent(_number(item["rate_of_return_pct"]) / 100),
                    )
                )
    performance_rows.extend(
        (
            ("As of", _date_cell(valuation_date)),
            ("History", CellValue(("Timeline", "timeline"), "link")),
        )
    )
    summary_rows.append(
        ("Data status", _status(statuses["overall"]))
        if statuses["overall_key"] != "Current"
        else ("",)
    )
    if (
        holdings["reconciliation_delta"] is not None
        and abs(holdings["reconciliation_delta"]) > 0.01
    ):
        summary_rows.append(
            ("Unreconciled assets", _money(holdings["reconciliation_delta"]))
        )

    allocation_rows = [
        ("Portfolio value", _cell(combined_data.get("TOTAL_ASSETS"), "amount"), "USD"),
        ("Category", "Value", "Weight"),
    ]
    allocation_rows.extend(
        (row["category"], _cell(row["value"], "amount"), _cell(row["weight"], "weight"))
        for row in sorted(
            category_rows(combined_data),
            key=lambda row: row["value"] if row["value"] is not None else float("-inf"),
            reverse=True,
        )
        if row["value"] not in (None, 0)
    )
    if any(row["value"] is None for row in category_rows(combined_data)):
        allocation_rows[0] = (
            "Portfolio value (partial)",
            _cell(combined_data.get("TOTAL_ASSETS"), "amount"),
            "USD",
        )
    if comparison["balance_change_total"] is not None:
        allocation_rows.extend(
            (
                ("",),
                (
                    _balance_change_label(previous_date),
                    _money(comparison["balance_change_total"]),
                ),
            )
        )
        emphasis.append(("compact_allocation", len(allocation_rows) - 1))
    if liquidity["cash_available_now"] is not None:
        allocation_rows.append(
            ("Accessible cash", _cell(liquidity["cash_available_now"], "amount"))
        )
    income_rows = [
        ("Estimated income",),
        ("Source", "Monthly USD"),
    ]
    income_rows.extend(
        (
            item["source"],
            _cell(item["monthly_average"], "amount"),
        )
        for item in income["items"]
        if item["monthly_average"] not in (None, 0)
    )
    income_rows.extend(
        (
            ("",),
            (
                "Monthly average"
                + (" (partial)" if income["state"] == "Incomplete" else ""),
                _cell(income["monthly_average"], "amount"),
            ),
            (
                "Annual estimate",
                _cell(
                    income["annual_income"],
                    "amount",
                ),
            ),
        )
    )
    blocks = [
        CellBlock("holdings", tuple(holding_rows), start_row=0, start_column=3),
        CellBlock("summary", tuple(summary_rows), start_row=0),
        CellBlock(
            "performance", tuple(performance_rows), start_row=len(summary_rows) + 1
        ),
        CellBlock(
            "compact_allocation",
            tuple(allocation_rows),
            start_row=0,
            start_column=6,
        ),
        CellBlock("compact_income", tuple(income_rows), start_row=0, start_column=10),
    ]
    return InsightTab(
        title=date.fromisoformat(valuation_date).strftime("%d %b %Y"),
        blocks=tuple(blocks),
        header_offsets={
            "holdings": 1,
            "compact_allocation": 1,
            "compact_income": 1,
        },
        freeze_rows=2,
        freeze_columns=4,
        column_widths=(190, 120, 100, 190, 110, 150, 150, 160, 100, 28, 220, 115),
        emphasis_rows=tuple(emphasis),
        pnl_columns=(("holdings", 2),),
    )