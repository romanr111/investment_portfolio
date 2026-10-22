"""Typed sections for the single dated portfolio worksheet."""

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from src.google_sheets.insights_cells import CellBlock, CellValue, render_blocks
from src.google_sheets.insights_finance import (
    CATEGORIES,
    category_rows,
    concentration_views,
    fire_progress,
    holdings_table,
    income_breakdown,
    liquidity_ladder,
    snapshot_comparison,
    source_statuses,
    targets_and_deviations,
)

LBL_IB_RETURN = "IB return - YTD - TWR"
LBL_UNREALIZED_PNL = "Unrealized P&L vs cost"
LBL_ESTIMATED_MONTHLY_INCOME = "Estimated investment income - monthly average"


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


_CATEGORY_COLORS = {
    "Stocks": {"red": 0.23, "green": 0.47, "blue": 0.75},
    "Bonds": {"red": 0.2, "green": 0.59, "blue": 0.42},
    "Other Bets": {"red": 0.93, "green": 0.65, "blue": 0.22},
    "Crypto Lending": {"red": 0.52, "green": 0.39, "blue": 0.71},
    "Precious Metals": {"red": 0.78, "green": 0.65, "blue": 0.25},
    "Crypto Coins": {"red": 0.77, "green": 0.37, "blue": 0.39},
    "Commodities": {"red": 0.3, "green": 0.62, "blue": 0.68},
    "Cash": {"red": 0.43, "green": 0.52, "blue": 0.58},
    "P2P Lending": {"red": 0.64, "green": 0.45, "blue": 0.3},
}


def _bar(value: Optional[float], color: str = "#3B78A4") -> CellValue:
    if value is None:
        return CellValue("Unavailable", "status")
    bounded = max(0.0, min(value, 1.0))
    return CellValue(
        f'=SPARKLINE({bounded},{{"charttype","bar";"max",1;"color1","{color}"}})',
        "formula",
    )


def _cell(value: Any, kind: str) -> CellValue:
    if value is None:
        return CellValue("Unavailable", "status")
    return CellValue(value, kind)


def _money(value: Any) -> CellValue:
    return _cell(value, "money")


def _percent(value: Any) -> CellValue:
    return _cell(value, "percent")


def _pp(value: Any) -> CellValue:
    return _cell(value, "pp")


def _status(value: Any) -> CellValue:
    return CellValue("Unknown" if value is None else str(value), "status")


def _date_cell(value: Optional[str]) -> CellValue:
    if value is None:
        return _status("Unknown")
    try:
        return CellValue(date.fromisoformat(str(value)[:10]), "date")
    except ValueError:
        return _status("Unknown")


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


def _holding_cells(row: dict) -> tuple[Any, ...]:
    return (
        row["asset"],
        row["account"],
        _money(row["value_usd"]),
        _percent(row["pct_total_assets"]),
        _percent(row["pct_ib_portfolio"]),
        _cell(row["unrealized_pnl_amount"], "native_amount"),
        row["pnl_currency"],
        _percent(row["pnl_pct"]),
    )


def _holdings_section(data: dict) -> InsightTab:
    holdings = holdings_table(data)
    all_rows = holdings["rows"]
    regular_rows = holdings["regular_rows"]
    tiny_rows = holdings["tiny_rows"]
    rows: list[tuple[Any, ...]] = []
    headers = (
        "Asset",
        "Account",
        "Value USD",
        "% of total assets",
        "% of IB portfolio",
        "Unrealized P&L",
        "P&L currency",
        LBL_UNREALIZED_PNL,
    )
    rows.append(headers)
    rows.extend(_holding_cells(row) for row in regular_rows)
    filter_end_offset = 1 + len(regular_rows)
    group_ranges = ()
    if tiny_rows:
        rows.append(
            (
                f"Tiny holdings subtotal - below USD {holdings['tiny_threshold_usd']:g}",
                "Expand details",
                _money(holdings["tiny_total"]),
                "",
                "",
                "",
                "",
                "",
            )
        )
        group_start = len(rows)
        rows.extend(_holding_cells(row) for row in tiny_rows)
        group_ranges = (("holdings", group_start, len(rows)),)
    elif not all_rows:
        rows.append(("No holdings supplied", _status("Unavailable")))

    return InsightTab(
        title="Holdings",
        blocks=(CellBlock("holdings", tuple(rows)),),
        header_offsets={"holdings": 0},
        filter_block_name="holdings",
        filter_end_offset=filter_end_offset,
        freeze_rows=1,
        freeze_columns=2,
        row_groups=group_ranges,
    )


def _allocation_section(data: dict, config: dict) -> InsightTab:
    target_rows = targets_and_deviations(data, config)
    target_rows.sort(
        key=lambda row: row["value"] if row["value"] is not None else float("-inf"),
        reverse=True,
    )
    rows = [
        (
            "Category",
            "Value USD",
            "% of total assets",
            "Target weight",
            "Deviation (pp)",
            "Deviation basis",
            "Status",
            "Allocation bar",
        )
    ]
    rows.extend(
        (
            row["category"],
            _money(row["value"]),
            _percent(row["actual_weight"]),
            _percent(row["target_weight"]),
            _pp(row["deviation_pp"]),
            row["deviation_pp_basis"],
            _status(row["state"]),
            _bar(
                row["actual_weight"],
                "#"
                + "".join(
                    f"{round(_CATEGORY_COLORS.get(row['category'], {'red': .4, 'green': .5, 'blue': .6})[key] * 255):02x}"
                    for key in ("red", "green", "blue")
                ),
            ),
        )
        for row in target_rows
    )

    component_rows = [("Component", "Value USD", "Status")]
    other_assets = data.get("OTHER_ASSETS")
    if (
        isinstance(other_assets, dict)
        and other_assets
        and "Other Bets" not in other_assets
    ):
        component_rows.extend(
            (
                str(name),
                _money(_number(value)),
                "Named component; included in subtotal below",
            )
            for name, value in other_assets.items()
        )
        component_rows.append(
            (
                "Other Bets subtotal",
                _money(_sum_known_values(other_assets.values())),
                "Sum of listed components",
            )
        )
    elif isinstance(other_assets, dict) and len(other_assets) > 1:
        reported_subtotal = _number(other_assets.get("Other Bets"))
        components = {
            name: _number(value)
            for name, value in other_assets.items()
            if name != "Other Bets"
        }
        components_total = _sum_known_values(components.values())
        reconciled = (
            reported_subtotal is not None
            and components_total is not None
            and abs(reported_subtotal - components_total) <= 0.01
        )
        component_status = (
            "Components reconcile to reported subtotal"
            if reconciled
            else "Detail only; not added to reported subtotal"
        )
        component_rows.extend(
            (str(name), _money(value), component_status)
            for name, value in components.items()
        )
        component_rows.append(
            (
                "Reported Other Bets subtotal",
                _money(reported_subtotal),
                "Category total uses this subtotal once",
            )
        )
    else:
        component_rows.append(
            (
                "Other Bets detail",
                _status("Unavailable"),
                "Subtotal retained; named components are not supplied.",
            )
        )

    return InsightTab(
        title="Allocation",
        blocks=(
            CellBlock(
                "allocation",
                (
                    (
                        "Allocation targets are optional; no default target is selected.",
                    ),
                    *rows,
                ),
            ),
            CellBlock("other_bets", (("Other Bets breakdown",), *component_rows)),
        ),
        header_offsets={"allocation": 1, "other_bets": 1},
        filter_block_name="allocation",
        freeze_rows=2,
    )


def _sum_known_values(values: Any) -> Optional[float]:
    parsed = [_number(value) for value in values]
    if not parsed or any(value is None for value in parsed):
        return None
    return sum(value for value in parsed if value is not None)


def _comparison_section(
    current: dict,
    previous: Optional[dict],
    current_date: Optional[str],
    previous_date: Optional[str],
) -> InsightTab:
    comparison = snapshot_comparison(current, previous, current_date, previous_date)
    rows = [
        (
            "Category",
            "Previous value USD",
            "Current value USD",
            "Change USD",
            "Previous weight",
            "Current weight",
            "Change (pp)",
            "State",
        )
    ]
    rows.extend(
        (
            row["category"],
            _money(row["previous"]),
            _money(row["current"]),
            _money(row["change"]),
            _percent(row["previous_weight"]),
            _percent(row["current_weight"]),
            _pp(row["change_pp"]),
            _status(row["state"]),
        )
        for row in comparison["rows"]
    )
    return InsightTab(
        title="Comparison",
        blocks=(
            CellBlock(
                "comparison",
                (
                    ("Balance changes - not investment profit",),
                    (
                        "Previous valuation date",
                        _date_cell(comparison["previous_date"]),
                        "Current valuation date",
                        _date_cell(comparison["current_date"]),
                        "Interval days",
                        _cell(comparison["interval_days"], "number"),
                    ),
                    (
                        "Attribution status",
                        _status(comparison["attribution_state"]),
                        comparison["label"],
                    ),
                    *rows,
                    *(
                        (
                            "Change total",
                            _money(comparison["change_total"]),
                            "New balances included; closed balances are labeled separately.",
                        ),
                    ),
                    (
                        "Closed balance adjustment",
                        _money(comparison["closed_balance_adjustment"]),
                    ),
                    (
                        "Headline balance change",
                        _money(comparison["balance_change_total"]),
                    ),
                    (
                        "Reconciliation difference",
                        _money(comparison["reconciliation_difference"]),
                        "Source rounding or uncovered amounts; not investment profit.",
                    ),
                ),
            ),
        ),
        header_offsets={"comparison": 3},
        filter_block_name="comparison",
        freeze_rows=4,
    )


def _income_section(data: dict) -> InsightTab:
    income = income_breakdown(data)
    rows = [
        (
            "Income source",
            "Principal USD",
            "Estimated annual rate",
            "Estimated annual income USD",
            "Monthly average USD",
            "Status",
        )
    ]
    rows.extend(
        (
            item["source"],
            _money(item["principal"]),
            _percent(item["annual_rate"]),
            _money(item["annual_income"]),
            _money(item["monthly_average"]),
            _status(item["state"]),
        )
        for item in income["items"]
    )
    receipt_rows = [
        ("Receipt date", "Source", "Amount", "Currency", "Cash treatment", "Status")
    ]
    raw_receipts = income["receipts"]["rows"]
    if raw_receipts:
        for receipt in raw_receipts:
            if isinstance(receipt, dict):
                receipt_rows.append(
                    (
                        _date_cell(receipt.get("date")),
                        receipt.get("source", "Unknown"),
                        _cell(receipt.get("amount"), "native_amount"),
                        receipt.get("currency", "Unknown"),
                        receipt.get("cash_treatment", "Unknown"),
                        _status(receipt.get("state", "Available")),
                    )
                )
    else:
        receipt_rows.append(
            (
                "",
                "",
                _status(income["receipts"]["message"]),
                "",
                "",
                _status(income["receipts"]["state"]),
            )
        )

    return InsightTab(
        title="Income",
        blocks=(
            CellBlock(
                "income",
                (
                    (LBL_ESTIMATED_MONTHLY_INCOME,),
                    (
                        "Configured rates are estimates, not guaranteed realised returns. Receipts are shown only from supported transaction data.",
                    ),
                    *rows,
                    (
                        "Total annual estimate",
                        _money(income["annual_income"]),
                        "Total monthly average",
                        _money(income["monthly_average"]),
                        "Coverage",
                        _status(income["state"]),
                    ),
                ),
            ),
            CellBlock(
                "receipts",
                (
                    ("Actual monthly receipts",),
                    (
                        "Coverage start",
                        _date_cell(income["receipts"]["coverage_start"]),
                        "Coverage end",
                        _date_cell(income["receipts"]["coverage_end"]),
                        "Receipt coverage",
                        _status(income["receipts"]["state"]),
                    ),
                    *receipt_rows,
                ),
            ),
        ),
        header_offsets={"income": 2, "receipts": 2},
        filter_block_name="income",
        freeze_rows=3,
    )


def _liquidity_section(data: dict, config: dict) -> InsightTab:
    liquidity = liquidity_ladder(data, config)
    rows = (
        ("Liquidity and balance sheet coverage",),
        ("Measure", "Amount USD", "Status / definition"),
        (
            "Cash available now",
            _money(liquidity["cash_available_now"]),
            liquidity["cash_available_state"],
        ),
        (
            "Assets requiring sale",
            _money(liquidity["assets_for_sale"]),
            liquidity["assets_for_sale_state"],
        ),
        (
            "Withdrawal-restricted assets",
            _money(liquidity["restricted_assets"]),
            liquidity["restricted_assets_state"],
        ),
        (
            "Unclassified cash",
            _money(liquidity["unclassified_cash"]),
            "Not treated as immediately accessible without classification.",
        ),
        (
            "Essential monthly spending",
            _money(liquidity["essential_monthly_spending"]),
            liquidity["spending_state"],
        ),
        (
            "Cash runway (months)",
            _cell(liquidity["runway_months"], "number"),
            liquidity["runway_state"],
        ),
        (
            "Tracked gross assets",
            _money(liquidity["gross_tracked_assets"]),
            "Gross asset total from combined_data.",
        ),
        (
            "Liabilities",
            _money(liquidity["liabilities"]),
            liquidity["liabilities_state"],
        ),
        (
            "Net worth after known liabilities",
            _money(liquidity["net_worth_after_known_liabilities"]),
            liquidity["net_worth_state"],
        ),
    )
    return InsightTab(
        title="Liquidity",
        blocks=(CellBlock("liquidity", rows),),
        header_offsets={"liquidity": 1},
        freeze_rows=2,
    )


def _concentration_section(data: dict) -> InsightTab:
    views = concentration_views(data)
    blocks = []
    headers = {}
    for dimension, title in (
        ("provider", "Broker, exchange, or lending platform"),
        ("trading_currency", "Trading currency"),
        ("underlying_geography", "Underlying geography"),
    ):
        rows = [("Exposure", "Amount USD", "Weight", "Status")]
        rows.extend(
            (
                row["category"],
                _money(row["amount"]),
                _percent(row["weight"]),
                "Alternative view of the same assets",
            )
            for row in views[dimension]
        )
        block_name = dimension
        blocks.append(CellBlock(block_name, ((title,), *rows)))
        headers[block_name] = 1
    blocks.insert(
        0,
        CellBlock(
            "note",
            (
                (
                    "Alternative exposure views; amounts are not additional assets. Underlying currency or geography is Unknown unless source metadata identifies it.",
                ),
            ),
        ),
    )
    return InsightTab(
        title="Concentration",
        blocks=tuple(blocks),
        header_offsets=headers,
        freeze_rows=2,
    )


def _fire_section(data: dict, config: dict) -> InsightTab:
    fire = fire_progress(data, config)
    summary = (
        ("FIRE target progress",),
        ("Measure", "Value", "Status / definition"),
        (
            "Portfolio value",
            _money(fire["eligible_value"]),
            fire["eligible_value_state"],
        ),
        ("Configured target", _money(fire["target"]), fire["state"]),
        (
            "Remaining to target",
            _money(fire["remaining"]),
            "Floored at zero; no completion forecast.",
        ),
        (
            "Progress",
            _percent(fire["progress_fraction"]),
            "Portfolio value / target. Bar capped at 100%; no forecast.",
            _bar(fire["progress_bar_fraction"]),
        ),
        (
            "Estimated income coverage of spending",
            _percent(fire["income_coverage_fraction"]),
            fire["income_coverage_state"],
        ),
    )
    return InsightTab(
        title="FIRE",
        blocks=(CellBlock("summary", summary),),
        header_offsets={"summary": 1},
        freeze_rows=2,
    )


def build_portfolio_tab(
    combined_data: dict,
    config: Optional[dict] = None,
    previous_snapshot: Optional[dict] = None,
    previous_date: Optional[str] = None,
    current_date: Optional[str] = None,
) -> InsightTab:
    """Build the one dated portfolio snapshot; no worksheet discovery or I/O."""
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
        ("Asset", "Value", LBL_UNREALIZED_PNL),
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
            if not row["tiny"] and len(positions) > 1:  # a single row's subtotal already says it all
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
            (
                "Unreconciled assets",
                _money(holdings["reconciliation_delta"]),
                "See details",
            )
        )

    allocation_section = _allocation_section(combined_data, settings)
    allocation_rows = [
        ("Portfolio value", _cell(combined_data.get("TOTAL_ASSETS"), "amount"), "USD"),
        ("Category", "Value", "Weight"),
    ]
    allocation_rows.extend(
        (row[0], _cell(row[1].value, "amount"), _cell(row[2].value, "weight"))
        for row in allocation_section.blocks[0].rows[2:]
        if _number(row[1].value) not in (None, 0)
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
                    "Balance change",
                    _money(comparison["balance_change_total"]),
                    _date_cell(previous_date),
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
    original = _holdings_section(combined_data)
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
        CellBlock("details", (("Details",),)),
        CellBlock("holding_details", (("Full holdings",), *original.blocks[0].rows)),
    ]
    headers = {
        "holdings": 1,
        "holding_details": 1,
        "compact_allocation": 1,
        "compact_income": 1,
    }
    for section in (
        allocation_section,
        _comparison_section(
            combined_data, previous_snapshot, valuation_date, previous_date
        ),
        _income_section(combined_data),
        _liquidity_section(combined_data, settings),
        _fire_section(combined_data, settings),
        _concentration_section(combined_data),
    ):
        for block in section.blocks:
            name = (
                "summary_fire"
                if section.title == "FIRE" and block.name == "summary"
                else block.name
            )
            blocks.append(CellBlock(name, block.rows))
            if block.name in section.header_offsets:
                headers[name] = section.header_offsets[block.name]
    benchmarks = [
        ("Saved benchmark returns - comparability is not established",),
        (
            "Benchmark",
            "YTD return",
            "Start date",
            "End date",
            "Currency",
            "Methodology",
        ),
    ]
    index_data = combined_data.get("INDEX_PERFORMANCE")
    if isinstance(index_data, dict):
        for key, item in index_data.items():
            if not isinstance(item, dict):
                continue
            points = _number(item.get("rate_of_return_pct"))
            benchmarks.append(
                (
                    item.get("name", key),
                    _percent(points / 100 if points is not None else None),
                    _date_cell(item.get("start_date")),
                    _date_cell(item.get("end_date")),
                    item.get("currency", "Unknown"),
                    item.get("methodology", "Source return; not aligned with IB TWR"),
                )
            )
    if len(benchmarks) == 2:
        benchmarks.append(("Benchmark coverage", _status("Unavailable")))
    blocks.append(CellBlock("benchmarks", tuple(benchmarks)))
    headers["benchmarks"] = 1
    blocks.append(
        CellBlock(
            "methodology",
            (
                ("Definitions and coverage",),
                (
                    "Tracked assets",
                    "Gross assets; net worth is shown separately only with known liabilities.",
                ),
                (
                    LBL_UNREALIZED_PNL,
                    "Native-currency amount; percentage versus cost. Missing currency or cost basis remains unavailable.",
                ),
                (
                    "IB weight",
                    "IB account denominator; distinct from total tracked assets.",
                ),
                (
                    "Income estimate",
                    "Monthly average, not a payment schedule. Configured rates are estimates.",
                ),
                (
                    "Benchmark comparison",
                    "Not comparable until measurement dates, currencies and return methodology align.",
                ),
                (
                    "Manual overrides",
                    "9988 uses a manual cost-price override when present in saved analytics.",
                ),
                ("Holdings detail total", _money(holdings["total_value"])),
                (
                    "Tracked assets minus holdings detail",
                    _money(holdings["reconciliation_delta"]),
                    "Residual is disclosed; asset values are never adjusted to force reconciliation.",
                ),
                (
                    "Tiny holdings",
                    holdings["tiny_threshold_note"],
                    _money(holdings["tiny_total"]),
                ),
                (
                    LBL_IB_RETURN,
                    _percent(twr / 100 if twr is not None else None),
                    "YTD TWR; period follows saved IB coverage.",
                ),
                (
                    "IB return coverage",
                    "Start date",
                    _date_cell(
                        (combined_data.get("IB_PERFORMANCE") or {}).get("start_date")
                    ),
                    "End date",
                    _date_cell(
                        (combined_data.get("IB_PERFORMANCE") or {}).get("end_date")
                    ),
                    "Currency",
                    (combined_data.get("IB_PERFORMANCE") or {}).get(
                        "currency", "Unknown"
                    ),
                    (combined_data.get("IB_PERFORMANCE") or {}).get(
                        "measure", "Unknown"
                    ),
                ),
                ("Investment income source", statuses["investment_income"]),
                ("Actual receipts coverage", statuses["actual_receipts"]),
            ),
        )
    )
    grid, _, ranges = render_blocks(blocks)
    groups = (("details", 1, len(grid) - ranges["details"][0]),)
    return InsightTab(
        title=date.fromisoformat(valuation_date).strftime("%d %b %Y"),
        blocks=tuple(blocks),
        header_offsets=headers,
        # Sheets filters hide entire rows; keep them below the adjacent summary panels.
        filter_block_name="holding_details",
        filter_end_offset=1 + original.filter_end_offset,
        freeze_rows=2,
        freeze_columns=4,
        row_groups=groups,
        column_widths=(190, 120, 100, 190, 110, 150, 150, 160, 100, 28, 220, 115),
        emphasis_rows=tuple(emphasis),
        pnl_columns=(("holdings", 2), ("holding_details", 7)),
    )
