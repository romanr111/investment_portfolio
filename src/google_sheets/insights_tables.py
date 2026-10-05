"""Builders for deterministic, typed portfolio insight worksheets."""

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from src.google_sheets.insights_cells import CellBlock, CellValue
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


INSIGHT_TAB_TITLES = (
    "Overview",
    "Holdings",
    "Allocation",
    "Comparison",
    "Income",
    "Liquidity",
    "Concentration",
    "FIRE",
)

LBL_IB_RETURN = "IB return - YTD - TWR"
LBL_UNREALIZED_PNL = "Unrealized P&L vs cost"
LBL_ESTIMATED_MONTHLY_INCOME = "Estimated investment income - monthly average"


@dataclass(frozen=True)
class ChartDefinition:
    title: str
    block_name: str
    chart_type: str
    domain_column: int
    series_columns: tuple[int, ...]
    header_offset: int = 1


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
    charts: tuple[ChartDefinition, ...] = ()


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
        _cell(row["unrealized_pnl_amount"], "number"),
        row["pnl_currency"],
        _percent(row["pnl_pct"]),
    )


def _overview_tab(
    data: dict,
    config: dict,
    comparison: dict,
    history_snapshots: list[dict],
    current_date: Optional[str],
) -> InsightTab:
    statuses = source_statuses(data)
    holdings = holdings_table(data)
    liquidity = liquidity_ladder(data, config)
    income = income_breakdown(data)
    fire = fire_progress(data, config)
    ib_performance = data.get("IB_PERFORMANCE")
    ib_performance = ib_performance if isinstance(ib_performance, dict) else {}
    twr_points = _number(ib_performance.get("rate_of_return_pct"))
    metadata = data.get("DATA_METADATA")
    metadata = metadata if isinstance(metadata, dict) else {}
    base_currency = data.get("BASE_CURRENCY") or metadata.get("base_currency") or "USD"

    has_9988 = any(row["symbol"] == "9988" for row in holdings["rows"])
    pnl_method = "Native-currency amount; percentages are relative to cost basis."
    if has_9988:
        pnl_method += " 9988 uses the configured manual cost-price override."

    summary_rows = (
        ("Portfolio overview",),
        ("Metric", "Value", "Definition / source"),
        ("Tracked asset value", _money(data.get("TOTAL_ASSETS")), "Gross tracked assets; liabilities are not deducted."),
        ("Change since previous snapshot", _money(comparison["change_total"]), comparison["label"]),
        ("Cash available now", _money(liquidity["cash_available_now"]), liquidity["cash_available_state"]),
        (
            LBL_ESTIMATED_MONTHLY_INCOME,
            _money(income["monthly_average"]),
            "Monthly average estimate; not a payment schedule. "
            f"Source completeness: {income['state']}.",
        ),
        (
            "FIRE target progress",
            _percent(fire["progress_fraction"]),
            "Included assets: " + ", ".join(fire["included_categories"]),
        ),
        ("Valuation date", _date_cell(current_date), "Selected snapshot valuation date."),
        ("Base currency", str(base_currency), "Values from combined_data; USD unless source metadata says otherwise."),
        ("Last successful refresh", statuses["last_successful_refresh"], "Pipeline timestamp when available."),
        ("Source status", _status(statuses["overall"]), "Current, Cached, or Unknown from saved metadata."),
        (
            LBL_IB_RETURN,
            _percent(twr_points / 100 if twr_points is not None else None),
            "Year-to-date time-weighted return as supplied by IB; measurement dates follow source coverage.",
        ),
        (LBL_UNREALIZED_PNL, pnl_method, "Absolute P&L is not converted to USD."),
        (
            "Benchmark note",
            "Not directly comparable until period, currency, and return methodology align.",
            "Benchmarks are shown as separate source measures.",
        ),
    )
    blocks = [CellBlock("summary", summary_rows)]

    change_rows = [
        ("Category", "Previous value USD", "Current value USD", "Change USD", "Previous weight", "Current weight", "Change (pp)", "State")
    ]
    for row in comparison["rows"]:
        change_rows.append(
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
        )
    blocks.append(
        CellBlock(
            "changes",
            (
                ("Balance changes - not investment profit",),
                ("Previous valuation date", _date_cell(comparison["previous_date"]), "Current valuation date", _date_cell(comparison["current_date"]), "Interval days", _cell(comparison["interval_days"], "number")),
                ("Attribution", _status(comparison["attribution_state"]), "External contributions are unavailable without complete reconciled activity."),
                *change_rows,
            ),
        )
    )

    target_rows = targets_and_deviations(data, config)
    target_rows.sort(key=lambda row: row["value"] if row["value"] is not None else float("-inf"), reverse=True)
    allocation_rows = [
        (
            "Category",
            "Value USD",
            "% of total assets",
            "Target weight",
            "Deviation (pp)",
            "Deviation basis",
            "Status",
        )
    ]
    allocation_rows.extend(
        (
            row["category"],
            _money(row["value"]),
            _percent(row["actual_weight"]),
            _percent(row["target_weight"]),
            _pp(row["deviation_pp"]),
            row["deviation_pp_basis"],
            _status(row["state"]),
        )
        for row in target_rows
    )
    blocks.append(CellBlock("allocation", (("Allocation by tracked category",), *allocation_rows)))

    history_by_date = {}
    for snapshot in history_snapshots:
        snapshot_date = snapshot.get("as_of_date")
        snapshot_data = snapshot.get("data")
        if snapshot_date and isinstance(snapshot_data, dict):
            try:
                normalized_date = date.fromisoformat(str(snapshot_date)[:10]).isoformat()
            except ValueError:
                continue
            amount = _number(snapshot_data.get("TOTAL_ASSETS"))
            if amount is not None:
                history_by_date[normalized_date] = amount
    history_rows = [("Valuation date", "Tracked asset value USD")]
    history_rows.extend(
        (_date_cell(day), _money(amount)) for day, amount in sorted(history_by_date.items())
    )
    blocks.append(CellBlock("history", (("Tracked assets over time",), *history_rows)))

    return InsightTab(
        title="Overview",
        blocks=tuple(blocks),
        header_offsets={"changes": 3, "allocation": 1, "history": 1},
        filter_block_name="allocation",
        freeze_rows=2,
        charts=(
            ChartDefinition("Tracked assets over time", "history", "LINE", 0, (1,)),
            ChartDefinition("Allocation by category", "allocation", "BAR", 0, (1,)),
        ),
    )


def _holdings_tab(data: dict) -> InsightTab:
    holdings = holdings_table(data)
    all_rows = holdings["rows"]
    regular_rows = holdings["regular_rows"]
    tiny_rows = holdings["tiny_rows"]
    rows: list[tuple[Any, ...]] = [
        ("Portfolio holdings",),
        ("Position amounts use the pipeline base currency. P&L amounts remain in native currency." ,),
        ("Tracked assets", _money(data.get("TOTAL_ASSETS")), "Gross tracked assets; liability coverage is not established."),
        ("Holdings detail total", _money(holdings["total_value"]), "Sum of listed position detail."),
        ("Reconciliation difference", _money(holdings["reconciliation_delta"]), "Tracked assets minus listed detail."),
        ("Tiny holdings", _money(holdings["tiny_total"]), holdings["tiny_threshold_note"]),
        (LBL_UNREALIZED_PNL, "Native currency amount; percentage is relative to cost basis."),
        ("IB weight denominator", "IB account portfolio value, distinct from total tracked assets."),
        ("",),
    ]
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
    filter_end_offset = 10 + len(regular_rows)
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
        header_offsets={"holdings": 9},
        filter_block_name="holdings",
        filter_end_offset=filter_end_offset,
        freeze_rows=10,
        freeze_columns=2,
        row_groups=group_ranges,
    )


def _allocation_tab(data: dict, config: dict) -> InsightTab:
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
        )
        for row in target_rows
    )

    component_rows = [("Component", "Value USD", "Status")]
    other_assets = data.get("OTHER_ASSETS")
    if isinstance(other_assets, dict) and other_assets and "Other Bets" not in other_assets:
        component_rows.extend(
            (str(name), _money(_number(value)), "Named component; included in subtotal below")
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
            ("Other Bets detail", _status("Unavailable"), "Subtotal retained; named components are not supplied.")
        )

    return InsightTab(
        title="Allocation",
        blocks=(
            CellBlock("allocation", (("Allocation targets are optional; no default target is selected.",), *rows)),
            CellBlock("other_bets", (("Other Bets breakdown",), *component_rows)),
        ),
        header_offsets={"allocation": 1, "other_bets": 1},
        filter_block_name="allocation",
        freeze_rows=2,
        charts=(ChartDefinition("Allocation by category", "allocation", "BAR", 0, (1,)),),
    )


def _sum_known_values(values: Any) -> Optional[float]:
    parsed = [_number(value) for value in values]
    if not parsed or any(value is None for value in parsed):
        return None
    return sum(value for value in parsed if value is not None)


def _comparison_tab(current: dict, previous: Optional[dict], current_date: Optional[str], previous_date: Optional[str]) -> InsightTab:
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
                    ("Previous valuation date", _date_cell(comparison["previous_date"]), "Current valuation date", _date_cell(comparison["current_date"]), "Interval days", _cell(comparison["interval_days"], "number")),
                    ("Attribution status", _status(comparison["attribution_state"]), comparison["label"]),
                    *rows,
                    *(("Change total", _money(comparison["change_total"]), "New balances included; closed balances are labeled separately."),),
                ),
            ),
        ),
        header_offsets={"comparison": 3},
        filter_block_name="comparison",
        freeze_rows=4,
    )


def _income_tab(data: dict) -> InsightTab:
    income = income_breakdown(data)
    rows = [("Income source", "Principal USD", "Estimated annual rate", "Estimated annual income USD", "Monthly average USD", "Status")]
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
    receipt_rows = [("Receipt date", "Source", "Amount", "Currency", "Cash treatment", "Status")]
    raw_receipts = income["receipts"]["rows"]
    if raw_receipts:
        for receipt in raw_receipts:
            if isinstance(receipt, dict):
                receipt_rows.append(
                    (
                        _date_cell(receipt.get("date")),
                        receipt.get("source", "Unknown"),
                        _money(receipt.get("amount")),
                        receipt.get("currency", "Unknown"),
                        receipt.get("cash_treatment", "Unknown"),
                        _status(receipt.get("state", "Available")),
                    )
                )
    else:
        receipt_rows.append(("", "", _status(income["receipts"]["message"]), "", "", _status(income["receipts"]["state"])))

    return InsightTab(
        title="Income",
        blocks=(
            CellBlock(
                "income",
                (
                    (LBL_ESTIMATED_MONTHLY_INCOME,),
                    ("Configured rates are estimates, not guaranteed realised returns. Receipts are shown only from supported transaction data.",),
                    *rows,
                    ("Total annual estimate", _money(income["annual_income"]), "Total monthly average", _money(income["monthly_average"]), "Coverage", _status(income["state"])),
                ),
            ),
            CellBlock(
                "receipts",
                (
                    ("Actual monthly receipts",),
                    ("Coverage start", _date_cell(income["receipts"]["coverage_start"]), "Coverage end", _date_cell(income["receipts"]["coverage_end"]), "Receipt coverage", _status(income["receipts"]["state"])),
                    *receipt_rows,
                ),
            ),
        ),
        header_offsets={"income": 2, "receipts": 2},
        filter_block_name="income",
        freeze_rows=3,
    )


def _liquidity_tab(data: dict, config: dict) -> InsightTab:
    liquidity = liquidity_ladder(data, config)
    rows = (
        ("Liquidity and balance sheet coverage",),
        ("Measure", "Amount USD", "Status / definition"),
        ("Cash available now", _money(liquidity["cash_available_now"]), liquidity["cash_available_state"]),
        ("Assets requiring sale", _money(liquidity["assets_for_sale"]), liquidity["assets_for_sale_state"]),
        ("Withdrawal-restricted assets", _money(liquidity["restricted_assets"]), liquidity["restricted_assets_state"]),
        ("Unclassified cash", _money(liquidity["unclassified_cash"]), "Not treated as immediately accessible without classification."),
        ("Essential monthly spending", _money(liquidity["essential_monthly_spending"]), liquidity["spending_state"]),
        ("Cash runway (months)", _cell(liquidity["runway_months"], "number"), liquidity["runway_state"]),
        ("Tracked gross assets", _money(liquidity["gross_tracked_assets"]), "Gross asset total from combined_data."),
        ("Liabilities", _money(liquidity["liabilities"]), liquidity["liabilities_state"]),
        ("Net worth after known liabilities", _money(liquidity["net_worth_after_known_liabilities"]), liquidity["net_worth_state"]),
    )
    return InsightTab(
        title="Liquidity",
        blocks=(CellBlock("liquidity", rows),),
        header_offsets={"liquidity": 1},
        freeze_rows=2,
    )


def _concentration_tab(data: dict) -> InsightTab:
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
            (row["category"], _money(row["amount"]), _percent(row["weight"]), "Alternative view of the same assets")
            for row in views[dimension]
        )
        block_name = dimension
        blocks.append(CellBlock(block_name, ((title,), *rows)))
        headers[block_name] = 1
    blocks.insert(
        0,
        CellBlock(
            "note",
            (("Alternative exposure views; amounts are not additional assets. Underlying currency or geography is Unknown unless source metadata identifies it.",),),
        ),
    )
    return InsightTab(
        title="Concentration",
        blocks=tuple(blocks),
        header_offsets=headers,
        freeze_rows=2,
    )


def _fire_tab(data: dict, config: dict) -> InsightTab:
    fire = fire_progress(data, config)
    values = {row["category"]: row for row in category_rows(data)}
    summary = (
        ("FIRE target progress",),
        ("Measure", "Value", "Status / definition"),
        ("Current eligible value", _money(fire["eligible_value"]), fire["eligible_value_state"]),
        ("Configured target", _money(fire["target"]), fire["state"]),
        ("Remaining to target", _money(fire["remaining"]), "Floored at zero; no completion forecast."),
        ("Progress", _percent(fire["progress_fraction"]), "Progress bar capped at 100%; no return or contribution forecast."),
        ("Estimated income coverage of spending", _percent(fire["income_coverage_fraction"]), fire["income_coverage_state"]),
        ("Included categories", ", ".join(fire["included_categories"]), "Change the local config only when the eligibility set is intentional."),
    )
    rows = [("Category", "Tracked value USD", "Included in FIRE value", "Status")]
    rows.extend(
        (
            category,
            _money(values[category]["value"]),
            "Yes" if category in fire["included_categories"] else "No",
            _status(values[category]["state"]),
        )
        for category in CATEGORIES
    )
    return InsightTab(
        title="FIRE",
        blocks=(CellBlock("summary", summary), CellBlock("eligibility", (("Eligible asset categories",), *rows))),
        header_offsets={"summary": 1, "eligibility": 1},
        filter_block_name="eligibility",
        freeze_rows=2,
    )


def build_insight_tabs(
    combined_data: dict,
    config: Optional[dict] = None,
    previous_snapshot: Optional[dict] = None,
    previous_date: Optional[str] = None,
    current_date: Optional[str] = None,
    history_snapshots: Optional[list[dict]] = None,
) -> dict[str, InsightTab]:
    """Build all generated insight tabs from combined_data and optional local settings."""
    settings = config if isinstance(config, dict) else {}
    valuation_date = _current_date(combined_data, current_date)
    history = history_snapshots or []
    comparison = snapshot_comparison(
        combined_data, previous_snapshot, valuation_date, previous_date
    )

    tabs = (
        _overview_tab(combined_data, settings, comparison, history, valuation_date),
        _holdings_tab(combined_data),
        _allocation_tab(combined_data, settings),
        _comparison_tab(combined_data, previous_snapshot, valuation_date, previous_date),
        _income_tab(combined_data),
        _liquidity_tab(combined_data, settings),
        _concentration_tab(combined_data),
        _fire_tab(combined_data, settings),
    )
    return {tab.title: tab for tab in tabs}
