"""Markdown renderer for the quarterly report."""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from .allocation_diff import AllocationDiff
from .config import SPECIAL_ASSET_TICKERS
from .dates import format_quarter_ua, quarter_end_date
from .flex_xml_parser import SnapshotData
from .position_analyzer import (
    AggregateBills,
    PositionAnalysis,
    aggregate_bills,
    all_symbols,
    analyze_position,
    china_ratio,
    core_satellite_ratio,
    equity_total_value,
    special_assets_value,
)


def _fmt_price_cell(
    symbol: str,
    analysis: PositionAnalysis,
    end_snap: SnapshotData,
    start_snap: Optional[SnapshotData] = None,
) -> str:
    """Format entry/exit price cell with P&L percentage."""
    avg_price = analysis.avg_entry_price
    if avg_price <= 0:
        return "-"

    end_rec = end_snap.positions.get(symbol)
    if end_rec is not None:
        target_price = end_rec.mark_price
        if target_price <= 0:
            return f"{avg_price:.2f}$"
        pct = ((target_price - avg_price) / avg_price) * 100
        sign = "+" if pct > 0 else ""
        if abs(pct) < 1:
            pct_str = f"{sign}{pct:.1f}%"
        else:
            pct_str = f"{sign}{pct:.0f}%"
        if symbol == "COMB" and pct < 0:
            pct_str = f"{pct_str} дивіденди"
        return f"{avg_price:.2f}$ ({pct_str})"

    exit_price = analysis.avg_exit_price
    if exit_price > 0:
        pct = ((exit_price - avg_price) / avg_price) * 100
        sign = "+" if pct > 0 else ""
        if abs(pct) < 1:
            pct_str = f"{sign}{pct:.1f}%"
        else:
            pct_str = f"{sign}{pct:.0f}%"
        return f"{avg_price:.2f}$ → {exit_price:.2f}$ (Exit) ({pct_str})"

    if start_snap is not None:
        start_rec = start_snap.positions.get(symbol)
        if start_rec is not None and start_rec.mark_price > 0:
            pct = ((start_rec.mark_price - avg_price) / avg_price) * 100
            sign = "+" if pct > 0 else ""
            if abs(pct) < 1:
                pct_str = f"{sign}{pct:.1f}%"
            else:
                pct_str = f"{sign}{pct:.0f}%"
            return f"{avg_price:.2f}$ ({pct_str})"

    return f"{avg_price:.2f}$"


def _fmt_weight_cell(symbol: str, analysis: PositionAnalysis) -> str:
    if analysis.activity.startswith("✖"):
        return f"{analysis.weight:.2f}% → 0%" if analysis.weight > 0 else "-"
    if analysis.weight > 0:
        return f"{analysis.weight:.2f}%"
    return "-"


def _activity_counts(
    analyses: List[PositionAnalysis],
) -> Dict[str, int]:
    counts = {
        "increased": 0,
        "decreased": 0,
        "unchanged": 0,
        "new": 0,
        "eliminated": 0,
    }
    for a in analyses:
        act = a.activity
        if "Збільшив" in act:
            counts["increased"] += 1
        elif "Зменшив" in act:
            counts["decreased"] += 1
        elif "Нова" in act:
            counts["new"] += 1
        elif "Закрита" in act:
            counts["eliminated"] += 1
        else:
            counts["unchanged"] += 1
    return counts


def _bills_analysis(
    symbol_label: str,
    start_bills: Optional[AggregateBills],
    end_bills: Optional[AggregateBills],
    total_value: float,
) -> Optional[PositionAnalysis]:
    if start_bills is None and end_bills is None:
        return None
    activity = ""
    avg_entry = 0.0
    weight = 0.0
    price_pct = 0.0
    if start_bills and end_bills:
        if start_bills.total_value > 0:
            pct = (
                (end_bills.total_value - start_bills.total_value)
                / start_bills.total_value
                * 100
            )
        else:
            pct = 0.0
        if pct > 5:
            activity = f"➕ Збільшив (+{int(round(abs(pct)))}%)"
        elif pct < -5:
            activity = f"➖ Зменшив (-{int(round(abs(pct)))}%)"
        else:
            activity = "Без змін"
        avg_entry = end_bills.weighted_avg_price
        if total_value > 0:
            weight = (end_bills.total_value / total_value) * 100
    elif start_bills and not end_bills:
        activity = "✖ Закрита позиція"
        avg_entry = start_bills.weighted_avg_price
    elif end_bills and not start_bills:
        activity = "🆕 Нова позиція"
        avg_entry = end_bills.weighted_avg_price
        if total_value > 0:
            weight = (end_bills.total_value / total_value) * 100

    return PositionAnalysis(
        symbol=symbol_label,
        activity=activity,
        avg_entry_price=avg_entry,
        avg_exit_price=0.0,
        weight=weight,
        price_change_pct=price_pct,
        is_special_asset=True,
        is_china_equity=False,
    )


def render_equity_table(
    start_snap: SnapshotData,
    end_snap: SnapshotData,
    trades_snap: Optional[SnapshotData] = None,
) -> str:
    """Render the main equity positions markdown table.

    Equity weights are computed against the equity-only total (stocks,
    excluding bonds/metals/commodities/BILLs) so the active weights sum to
    100%. The special-assets table uses the combined IB total.
    Closed positions use the start-period equity total as denominator.
    """
    equity_total = equity_total_value(end_snap)
    start_equity_total = equity_total_value(start_snap)
    combined_total = equity_total + special_assets_value(end_snap)
    syms = all_symbols(start_snap, end_snap)
    analyses: List[PositionAnalysis] = []
    for symbol in syms:
        if symbol in SPECIAL_ASSET_TICKERS:
            continue
        start_rec = start_snap.positions.get(symbol)
        end_rec = end_snap.positions.get(symbol)
        start_is_bill = start_rec is not None and start_rec.asset_category == "BILL"
        end_is_bill = end_rec is not None and end_rec.asset_category == "BILL"
        if start_is_bill or end_is_bill:
            continue
        a = analyze_position(
            symbol, start_snap, end_snap, equity_total,
            start_equity_total, trades_snap=trades_snap,
        )
        if a is not None:
            analyses.append(a)

    # Insert aggregated BILLS as a special-asset row (shown in special table)
    start_bills, end_bills = aggregate_bills(start_snap, end_snap)
    bills_analysis = _bills_analysis(
        "BILLS", start_bills, end_bills, combined_total
    )

    analyses.sort(key=lambda a: ("Закрита" in a.activity, -a.weight), reverse=False)

    lines = [
        "| Позиція | Остання активність | Середня ціна входу | Вага |",
        "|----------|--------------------------|----------------------------------|----------------|",
    ]
    for a in analyses:
        price_cell = _fmt_price_cell(a.symbol, a, end_snap, start_snap)
        weight_cell = _fmt_weight_cell(a.symbol, a)
        lines.append(
            f"| {a.symbol} | {a.activity} | {price_cell} | {weight_cell} |"
        )

    counts = _activity_counts(analyses)
    summary = (
        f"↑{counts['increased']} "
        f"↓{counts['decreased']} "
        f"={counts['unchanged']} "
        f"+{counts['new']} "
        f"-{counts['eliminated']}"
    )
    lines.append(f"| **Підсумок** | {summary} | | **100.00%** |")
    lines.append("")
    lines.append("Примітка: комісії, дивіденди та FX не враховані.")
    lines.append("")
    lines.append("Для закритих позицій друга ціна — середня ціна виходу.")
    lines.append("")

    core_pct, sat_pct = core_satellite_ratio(end_snap)
    lines.append(
        f"Співвідношення Core/Satellite (акції): {core_pct:.2f}% / {sat_pct:.2f}%."
    )
    lines.append("")
    china_pct, rest_pct = china_ratio(end_snap)
    lines.append(
        f"Співвідношення Китай/Інші (акції): {china_pct:.2f}% / {rest_pct:.2f}%."
    )
    lines.append("")

    total_equity = equity_total_value(end_snap)
    lines.append(
        "**Загальна вартість всіх акцій (в USD, без облігацій, золота та "
        f"товарних активів): {total_equity:,.2f}$**"
    )

    special_table = render_special_assets_table(
        start_snap, end_snap, analyses_with_bills=analyses + (
            [bills_analysis] if bills_analysis else []
        ),
        total_value=combined_total,
        start_total_value=start_equity_total
        + special_assets_value(start_snap),
        trades_snap=trades_snap,
    )
    if special_table:
        lines.append("")
        lines.append("")
        lines.append("## Облігації, золото та товарні активи")
        lines.append("")
        lines.append(special_table)

    return "\n".join(lines)


def render_special_assets_table(
    start_snap: SnapshotData,
    end_snap: SnapshotData,
    analyses_with_bills: List[PositionAnalysis],
    total_value: float,
    start_total_value: float = 0.0,
    trades_snap: Optional[SnapshotData] = None,
) -> str:
    """Render the bonds/metals/commodities markdown table.

    Closed positions use ``start_total_value`` as denominator; if 0,
    falls back to ``total_value`` (end-period).
    """
    lines = [
        "| Позиція | Остання активність | Середня ціна входу | "
        "Вага (від загальної вартості) |",
        "|----------|--------------------------|----------------------------------|"
        "----------------|",
    ]
    rows: List[tuple] = []
    syms = all_symbols(start_snap, end_snap)
    for symbol in syms:
        if symbol not in SPECIAL_ASSET_TICKERS:
            continue
        a = analyze_position(
            symbol, start_snap, end_snap, total_value,
            start_total_value, trades_snap=trades_snap,
        )
        if a is None or (not a.activity.strip() and a.avg_entry_price == 0.0):
            continue
        price_cell = _fmt_price_cell(symbol, a, end_snap, start_snap)
        weight_cell = _fmt_weight_cell(symbol, a)
        rows.append((a.weight, "Закрита" in a.activity, f"| {symbol} | {a.activity} | {price_cell} | {weight_cell} |"))

    # Aggregated BILLS row
    for a in analyses_with_bills:
        if a.symbol == "BILLS" and a.activity:
            price_cell = (
                f"{a.avg_entry_price:.2f}$" if a.avg_entry_price > 0 else "-"
            )
            weight_cell = (
                f"{a.weight:.2f}%" if a.weight > 0 else "-"
            )
            rows.append(
                (a.weight, "Закрита" in a.activity, f"| T Bills | {a.activity} | {price_cell} | {weight_cell} |")
            )

    rows.sort(key=lambda r: (r[1], -r[0]), reverse=False)
    if not rows:
        return ""
    lines.extend(r[2] for r in rows)
    return "\n".join(lines)


def render_allocation_diff_table(diff: AllocationDiff) -> str:
    lines = [
        "| Bucket | Was % | Now % | Change | Value change $ |",
        "|--------|-------|-------|--------|----------------|",
    ]
    rows = sorted(diff.rows, key=lambda r: abs(r.change_pct), reverse=True)
    for r in rows:
        change_sign = "+" if r.change_pct > 0 else ""
        val_sign = "+" if r.value_change > 0 else ""
        lines.append(
            f"| {r.bucket} | {r.was_pct:.2f}% | {r.now_pct:.2f}% | "
            f"{change_sign}{r.change_pct:.2f}% | "
            f"{val_sign}{r.value_change:,.0f}$ |"
        )
    return "\n".join(lines)


def render_section3(
    start_metrics: Dict,
    end_metrics: Dict,
) -> str:
    lines: List[str] = ["## 3. Доходність та дивіденди", ""]
    twr = end_metrics.get("twr")
    if twr is not None:
        lines.append(f"- YTD TWR: {twr}%")
    dividends = end_metrics.get("dividends_yearly")
    if dividends is not None:
        lines.append(f"- Річний дивідендний дохід: ${dividends:,}")
    start_fp = start_metrics.get("freedom_progress")
    end_fp = end_metrics.get("freedom_progress")
    if start_fp and end_fp:
        lines.append(f"- FIN_FREEDOM_GOAL_PROGRESS: {start_fp} → {end_fp}")
    elif end_fp:
        lines.append(f"- FIN_FREEDOM_GOAL_PROGRESS: {end_fp}")
    return "\n".join(lines)


def render_dalio_section(dalio: Dict) -> str:
    lines: List[str] = ["## 4. Ризик-аналіз Dalio", ""]
    hhi = dalio.get("hhi")
    if hhi is not None:
        lines.append(f"- HHI: {hhi:.2f}")
    bets = dalio.get("effective_bets")
    if bets is not None:
        lines.append(f"- Effective bets: {bets:.2f}")
    rebalance = dalio.get("rebalance_due")
    next_date = dalio.get("next_rebalance_date")
    rebalance_str = "так" if rebalance else "ні"
    if next_date:
        lines.append(f"- Rebalance due: {rebalance_str} (next: {next_date})")
    else:
        lines.append(f"- Rebalance due: {rebalance_str}")
    penalty = dalio.get("data_quality_penalty_pct")
    if penalty is not None and penalty > 0:
        lines.append(
            f"- Red flag: data quality penalty {penalty:.1f}% "
            "(correlation coverage incomplete)"
        )
    corr_breach = dalio.get("corr_breach_count")
    if corr_breach:
        lines.append(f"- Red flag: {corr_breach} correlation breach(es)")
    drift_breach = dalio.get("weight_drift_breach_count")
    if drift_breach:
        lines.append(f"- Red flag: {drift_breach} weight drift breach(es)")
    return "\n".join(lines)


def render_report(
    year: int,
    quarter: int,
    start_snap: SnapshotData,
    end_snap: SnapshotData,
    allocation_diff: AllocationDiff,
    start_metrics: Dict,
    end_metrics: Dict,
    dalio: Dict,
    skip_dalio: bool,
    trades_snap: Optional[SnapshotData] = None,
) -> str:
    """Render the full quarterly report markdown."""
    gen_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    total_assets = end_metrics.get("total_assets")
    period_label = format_quarter_ua(year, quarter)

    header_lines = [
        f"# Квартальний звіт: {period_label}",
        "",
        f"- Період: {period_label}",
        f"- Дата генерації: {gen_date}",
    ]
    if total_assets is not None:
        header_lines.append(f"- Net worth: ${total_assets:,}")

    snapshot_note = (
        f"- Звіт на дату: {end_snap.to_date_iso or end_snap.to_date} "
        f"(квартал завершено: {quarter_end_label(year, quarter)})"
    )
    header_lines.append(snapshot_note)
    header_lines.append("")

    # Section 1: allocation diff
    sections: List[str] = []
    sections.append("## 1. Зміни в алокації")
    sections.append("")
    sections.append(render_allocation_diff_table(allocation_diff))
    sections.append("")

    # Section 2: equity portfolio
    sections.append("## 2. Акціонарний портфель (IB)")
    sections.append("")
    sections.append(render_equity_table(start_snap, end_snap, trades_snap))
    sections.append("")

    # Section 3: performance
    sections.append(render_section3(start_metrics, end_metrics))
    sections.append("")

    # Section 4: Dalio
    if not skip_dalio and dalio:
        sections.append(render_dalio_section(dalio))
        sections.append("")

    # Section 5: summary
    sections.append("## 5. Підсумок та наступні кроки")
    sections.append("")
    sections.extend(_render_summary(allocation_diff, dalio, skip_dalio))

    return "\n".join(header_lines + sections)


def quarter_end_label(year: int, quarter: int) -> str:
    return quarter_end_date(year, quarter).isoformat()


def _render_summary(
    allocation_diff: AllocationDiff, dalio: Dict, skip_dalio: bool
) -> List[str]:
    lines: List[str] = []
    notable = [
        r
        for r in allocation_diff.rows
        if abs(r.change_pct) >= 5
    ]
    if notable:
        lines.append("Помітні зміни в алокації:")
        for r in notable:
            sign = "+" if r.change_pct > 0 else ""
            lines.append(f"- {r.bucket}: {sign}{r.change_pct:.2f}%")
    else:
        lines.append("- Зміни в алокації в межах норми.")
    lines.append("")
    if not skip_dalio and dalio:
        rebalance = dalio.get("rebalance_due")
        if rebalance:
            lines.append("- Рекомендація: провести ребалансування портфеля.")
        else:
            lines.append("- Ребалансування не потрібне.")
    return lines