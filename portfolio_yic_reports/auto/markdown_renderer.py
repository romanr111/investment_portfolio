"""Markdown renderer for the quarterly report (Ukrainian, 8-section spec)."""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

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
    position_contributions,
    special_assets_value,
    top_positions_by_weight,
)

MINUS = "\u2212"  # U+2212

BUCKET_TRANSLATION: Dict[str, str] = {
    "Stocks": "Акції IBKR",
    "Bonds": "Облігації",
    "Cash": "Грошові кошти",
    "Commodities": "Товарні активи",
    "Crypto Coins": "Криптовалюти",
    "Crypto Lending": "Криптокредитування",
    "P2P Lending": "P2P-кредитування",
    "Precious Metals": "Дорогоцінні метали",
    "Other Bets": "Інші активи",
}

# Genitive (властивий) form for "зростання/зменшення частки {name}" — lowercase.
BUCKET_TRANSLATION_GENITIVE: Dict[str, str] = {
    "Stocks": "акцій IBKR",
    "Bonds": "облігацій",
    "Cash": "грошових коштів",
    "Commodities": "товарних активів",
    "Crypto Coins": "криптовалют",
    "Crypto Lending": "криптокредитування",
    "P2P Lending": "P2P-кредитування",
    "Precious Metals": "дорогоцінних металів",
    "Other Bets": "інших активів",
}

# Asset buckets NOT held at IBKR — excluded from the IBKR TWR return.
NON_IBKR_BUCKETS: List[str] = [
    "Other Bets",
    "Crypto Lending",
    "Crypto Coins",
    "P2P Lending",
]


def _translate_bucket(name: str) -> str:
    return BUCKET_TRANSLATION.get(name, name)


def _translate_bucket_genitive(name: str) -> str:
    return BUCKET_TRANSLATION_GENITIVE.get(name, name.lower())


def _signed_pct(value: Optional[float], decimals: int = 1) -> str:
    """Format a percentage with + prefix or Unicode minus, e.g. +4.2 / −6.8 / N/A."""
    if value is None:
        return "N/A"
    if value > 0:
        return f"+{value:.{decimals}f}%"
    if value < 0:
        return f"{MINUS}{abs(value):.{decimals}f}%"
    return f"{value:.{decimals}f}%"


def _signed_pp(value: Optional[float], decimals: int = 2) -> str:
    """Format a percentage-points change (no % suffix), with sign."""
    if value is None:
        return "N/A"
    if value > 0:
        return f"+{value:.{decimals}f}"
    if value < 0:
        return f"{MINUS}{abs(value):.{decimals}f}"
    return f"{value:.{decimals}f}"


def _pct_trim(value: float, max_decimals: int = 2) -> str:
    """Format a percentage, trimming trailing zeros (e.g. 23.00 -> 23, 21.50 -> 21.5)."""
    s = f"{value:.{max_decimals}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


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
    if analysis.activity.startswith("\u2716"):
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
            activity = f"\u2795 Збільшив (+{int(round(abs(pct)))}%)"
        elif pct < -5:
            activity = f"\u2796 Зменшив (-{int(round(abs(pct)))}%)"
        else:
            activity = "Без змін"
        avg_entry = end_bills.weighted_avg_price
        if total_value > 0:
            weight = (end_bills.total_value / total_value) * 100
    elif start_bills and not end_bills:
        activity = "\u2716 Закрита позиція"
        avg_entry = start_bills.weighted_avg_price
    elif end_bills and not start_bills:
        activity = "\U0001F195 Нова позиція"
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


def _compute_equity_analyses(
    start_snap: SnapshotData,
    end_snap: SnapshotData,
    trades_snap: Optional[SnapshotData] = None,
) -> List[PositionAnalysis]:
    """Compute PositionAnalysis for every equity position (excludes special
    assets and BILLs). Shared by sections 4 and 8."""
    equity_total = equity_total_value(end_snap)
    start_equity_total = equity_total_value(start_snap)
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
    return analyses


def _compute_special_analyses(
    start_snap: SnapshotData,
    end_snap: SnapshotData,
    trades_snap: Optional[SnapshotData] = None,
) -> Tuple[List[PositionAnalysis], Optional[PositionAnalysis]]:
    """Compute PositionAnalysis for special assets (bonds/metals/commodities)
    and the aggregated BILLS row. Total denominator is the combined IB total
    (equity + special assets)."""
    combined_end = equity_total_value(end_snap) + special_assets_value(end_snap)
    combined_start = (
        equity_total_value(start_snap) + special_assets_value(start_snap)
    )
    rows: List[PositionAnalysis] = []
    for symbol in all_symbols(start_snap, end_snap):
        if symbol not in SPECIAL_ASSET_TICKERS:
            continue
        a = analyze_position(
            symbol, start_snap, end_snap, combined_end,
            combined_start, trades_snap=trades_snap,
        )
        if a is None or (not a.activity.strip() and a.avg_entry_price == 0.0):
            continue
        rows.append(a)

    start_bills, end_bills = aggregate_bills(start_snap, end_snap)
    bills = _bills_analysis("BILLS", start_bills, end_bills, combined_end)
    return rows, bills


def render_special_assets_table(
    start_snap: SnapshotData,
    end_snap: SnapshotData,
    analyses_with_bills: List[PositionAnalysis],
    total_value: float,
    start_total_value: float = 0.0,
    trades_snap: Optional[SnapshotData] = None,
) -> str:
    """Render the bonds/metals/commodities markdown table (4 columns).

    Closed positions use ``start_total_value`` as denominator; if 0,
    falls back to ``total_value`` (end-period).
    """
    lines = [
        "| Позиція | Остання активність | Середня ціна входу | "
        "Вага (від загальної вартості) |",
        "|----------|--------------------------|----------------------------------|"
        "----------------|",
    ]
    rows: List[Tuple[float, bool, str]] = []
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


def render_allocation_diff_table(diff: AllocationDiff) -> Tuple[str, Optional[str]]:
    """Return (table_text, largest_change_blockquote_or_None).

    The change column is computed from the *displayed* (2-decimal rounded)
    was/now values, so the visible difference always matches the shown
    numbers. Using raw change_pct caused 0.01 p.p. mismatches (e.g.
    16.34 -> 13.02 displayed as -3.31 instead of -3.32).
    """
    lines = [
        "| Клас активів | Було | Стало | Зміна, п.п. |",
        "|--------------|------|------|--------------|",
    ]
    # Build display rows with rounded was/now + change derived from them.
    display_rows = []
    for r in diff.rows:
        was_disp = round(r.was_pct, 2)
        now_disp = round(r.now_pct, 2)
        display_rows.append((r.bucket, was_disp, now_disp, round(now_disp - was_disp, 2)))
    display_rows.sort(key=lambda row: row[2], reverse=True)
    for bucket, was_disp, now_disp, change_disp in display_rows:
        name = _translate_bucket(bucket)
        change = _signed_pp(change_disp, 2)
        lines.append(
            f"| {name} | {was_disp:.2f}% | {now_disp:.2f}% | {change} |"
        )
    table = "\n".join(lines)
    blockquote: Optional[str] = None
    if display_rows:
        biggest = max(display_rows, key=lambda row: abs(row[3]))
        if biggest[3] != 0:
            direction = "зростання" if biggest[3] > 0 else "зменшення"
            change = _signed_pp(biggest[3], 2)
            name = _translate_bucket_genitive(biggest[0])
            blockquote = (
                f"> Основна зміна кварталу — {direction} частки "
                f"{name} ({change} п.п.)."
            )
    return table, blockquote


def _income_index_blockquote(
    start_metrics: Dict, end_metrics: Dict
) -> Optional[str]:
    end_income = end_metrics.get("income_total_yearly")
    start_income_val = start_metrics.get("income_total_yearly")
    if end_income is None or start_income_val is None:
        return None
    if start_income_val <= 0:
        return None
    index_end = round((end_income / start_income_val) * 100, 1)
    return f"> Індекс прогнозного річного пасивного доходу: 100 → {index_end}"


def _income_change_pct(
    start_metrics: Dict, end_metrics: Dict
) -> Optional[float]:
    s = start_metrics.get("income_total_yearly")
    e = end_metrics.get("income_total_yearly")
    if s is None or e is None or s == 0:
        return None
    return (e - s) / s * 100


def _section1_summary(
    allocation_diff: AllocationDiff,
    end_metrics: Dict,
    start_metrics: Dict,
    equity_analyses: List[PositionAnalysis],
) -> List[str]:
    lines: List[str] = ["## 1. Коротко за квартал", ""]

    twr = end_metrics.get("twr")
    sp500 = end_metrics.get("benchmark_ytd_pct")
    nasdaq = end_metrics.get("benchmark_nasdaq_ytd_pct")
    lines.append(f"- IBKR YTD: **{_signed_pct(twr, 1)}**")
    lines.append(f"- S&P 500 YTD: **{_signed_pct(sp500, 1)}**")
    lines.append(f"- NASDAQ YTD: **{_signed_pct(nasdaq, 1)}**")
    if twr is not None and sp500 is not None:
        lines.append(f"- Відносно S&P 500: **{_signed_pp(twr - sp500, 1)} п.п.**")
    else:
        lines.append("- Відносно S&P 500: **N/A**")
    if twr is not None and nasdaq is not None:
        lines.append(f"- Відносно NASDAQ: **{_signed_pp(twr - nasdaq, 1)} п.п.**")
    else:
        lines.append("- Відносно NASDAQ: **N/A**")

    lines.append("")
    non_ibkr_pct = sum(
        r.now_pct for r in allocation_diff.rows if r.bucket in NON_IBKR_BUCKETS
    )
    non_ibkr_names = ", ".join(
        _translate_bucket(b) for b in NON_IBKR_BUCKETS
        if any(r.bucket == b for r in allocation_diff.rows)
    )
    if non_ibkr_names:
        lines.append(
            "*Доходи стосуються лише IBKR; структура активів — увесь портфель.*"
        )
        lines.append(
            f"*Не входять у доходність: {non_ibkr_names} "
            f"({non_ibkr_pct:.1f}% капіталу).*"
        )
    else:
        lines.append(
            "*Доходи стосуються лише IBKR; структура активів — увесь портфель.*"
        )
    return lines


def _section2_allocation(allocation_diff: AllocationDiff) -> List[str]:
    table, blockquote = render_allocation_diff_table(allocation_diff)
    lines = ["## 3. Зміни в структурі сукупного портфеля", "", table, ""]
    if blockquote:
        lines.append(blockquote)
    return lines


def _section3_performance(
    end_metrics: Dict,
    equity_analyses: List[PositionAnalysis],
) -> List[str]:
    twr = end_metrics.get("twr")
    sp500 = end_metrics.get("benchmark_ytd_pct")
    nasdaq = end_metrics.get("benchmark_nasdaq_ytd_pct")
    rel_sp500 = (twr - sp500) if (twr is not None and sp500 is not None) else None
    rel_nasdaq = (twr - nasdaq) if (twr is not None and nasdaq is not None) else None
    lines = [
        "## 2. Результати портфеля Interactive Brokers",
        "",
        "| Показник | YTD |",
        "|----------|-----|",
        f"| Дохідність IBKR | {_signed_pct(twr, 1)} |",
        f"| S&P 500 | {_signed_pct(sp500, 1)} |",
        f"| NASDAQ | {_signed_pct(nasdaq, 1)} |",
        f"| Відносно S&P 500 | {_signed_pp(rel_sp500, 1)} п.п. |",
        f"| Відносно NASDAQ | {_signed_pp(rel_nasdaq, 1)} п.п. |",
    ]
    return lines


def _strip_activity_icon(activity: str) -> str:
    """Strip the leading icon/emoji prefix from an activity string."""
    icons = [
        "\u2795 ",  # ➕
        "\u2796 ",  # ➖
        "\U0001F195 ",  # 🆕
        "\u2716 ",  # ✖
    ]
    for icon in icons:
        if activity.startswith(icon):
            return activity[len(icon):]
    return activity


def _action_label(activity: str) -> str:
    """Short passive-voice action label without the magnitude, e.g.
    'Збільшено' / 'Зменшено' / 'Нова' / 'Закрито'."""
    if "Збільшив" in activity:
        return "Збільшено"
    if "Зменшив" in activity:
        return "Зменшено"
    if "Нова" in activity:
        return "Нова"
    if "Закрита" in activity:
        return "Закрито"
    return _strip_activity_icon(activity)


def _position_change_str(analysis: PositionAnalysis) -> str:
    """For section 4: change in position percentage."""
    act = analysis.activity
    if "Нова" in act:
        return "\u2014"
    if "Закрита" in act:
        return "-100%"
    # increased/decreased: extract the (+N%) / (-N%) from the activity text
    import re
    m = re.search(r"\(([+\-]\d+)%\)", act)
    if m:
        return f"{m.group(1)}%"
    return ""


def _weight_after_str(analysis: PositionAnalysis) -> str:
    act = analysis.activity
    if "Закрита" in act:
        return "0%"
    if analysis.weight > 0:
        return f"{analysis.weight:.2f}%"
    return "-"


def _pl_str(analysis: PositionAnalysis) -> str:
    """Format unrealized P/L percentage with sign and Unicode minus."""
    if analysis.price_change_pct > 0:
        return f"+{analysis.price_change_pct:.1f}%"
    if analysis.price_change_pct < 0:
        return f"{MINUS}{abs(analysis.price_change_pct):.1f}%"
    return "0%"


def _activity_summary_lines(
    equity_analyses: List[PositionAnalysis],
    special_analyses: List[PositionAnalysis],
    bills_analysis: Optional[PositionAnalysis],
) -> List[str]:
    """One-line summary of quarterly activity for the composition section."""
    def _counts(analyses: List[PositionAnalysis]) -> Dict[str, int]:
        inc = sum(1 for a in analyses if "Збільшив" in a.activity)
        dec = sum(1 for a in analyses if "Зменшив" in a.activity)
        new = sum(1 for a in analyses if "Нова" in a.activity)
        closed = sum(1 for a in analyses if "Закрита" in a.activity)
        return {"inc": inc, "dec": dec, "new": new, "closed": closed}

    eq = _counts(equity_analyses)
    sp_all = special_analyses + ([bills_analysis] if bills_analysis else [])
    sp = _counts(sp_all)

    lines: List[str] = []
    eq_parts: List[str] = []
    if eq["inc"]:
        eq_parts.append(f"{eq['inc']} збільшено")
    if eq["new"]:
        eq_parts.append(f"{eq['new']} відкрито")
    if eq["closed"]:
        eq_parts.append(f"{eq['closed']} закрито")
    if eq_parts:
        lines.append(f"> **Акції:** {' · '.join(eq_parts)}")

    sp_parts: List[str] = []
    if sp["inc"]:
        sp_parts.append(f"{sp['inc']} збільшено")
    if sp["new"]:
        sp_parts.append(f"{sp['new']} відкрито")
    if sp["closed"]:
        sp_parts.append(f"{sp['closed']} закрито")
    if sp_parts:
        lines.append(f"> **Інші інструменти:** {' · '.join(sp_parts)}")
    return lines


def _section4_equity_open_table(
    equity_analyses: List[PositionAnalysis],
    start_snap: SnapshotData,
    end_snap: SnapshotData,
) -> List[str]:
    """4.1: all open equity positions sorted by weight desc, with activity + P/L."""
    open_positions = sorted(
        [a for a in equity_analyses if "Закрита" not in a.activity],
        key=lambda a: -a.weight,
    )
    lines = [
        "| Позиція | Остання активність | Вага | Середня ціна | P/L |",
        "|---------|--------------------|------|--------------|-----|",
    ]
    for a in open_positions:
        activity = a.activity
        weight = f"{a.weight:.2f}%" if a.weight > 0 else "-"
        avg_price = f"{a.avg_entry_price:.2f}$" if a.avg_entry_price > 0 else "-"
        pl = _pl_str(a)
        lines.append(
            f"| {a.symbol} | {activity} | {weight} | {avg_price} | {pl} |"
        )
    lines.append("| **Підсумок** | | **100.00%** | | |")
    return lines


def _section4_special_table(
    start_snap: SnapshotData,
    end_snap: SnapshotData,
    special_analyses: List[PositionAnalysis],
    bills_analysis: Optional[PositionAnalysis],
    trades_snap: Optional[SnapshotData],
) -> List[str]:
    """4.2: bonds/metals/commodities table (reuses render_special_assets_table)."""
    combined_end = equity_total_value(end_snap) + special_assets_value(end_snap)
    combined_start = (
        equity_total_value(start_snap) + special_assets_value(start_snap)
    )
    table = render_special_assets_table(
        start_snap, end_snap,
        analyses_with_bills=special_analyses + (
            [bills_analysis] if bills_analysis else []
        ),
        total_value=combined_end,
        start_total_value=combined_start,
        trades_snap=trades_snap,
    )
    if not table:
        return []
    return ["", table]


def _asset_class_label(symbol: str) -> str:
    """Ukrainian asset class label for the closed-positions table."""
    if symbol in SPECIAL_ASSET_TICKERS:
        from .config import PRECIOUS_METALS_TICKERS
        if symbol in PRECIOUS_METALS_TICKERS:
            return "Дорогоцінні метали"
        return "Облігації / товарні"
    return "Акції"


def _section4_closed_table(
    equity_analyses: List[PositionAnalysis],
    special_analyses: List[PositionAnalysis],
    bills_analysis: Optional[PositionAnalysis],
    start_snap: SnapshotData,
    end_snap: SnapshotData,
    trades_snap: Optional[SnapshotData],
) -> List[str]:
    """4.3: closed positions (equity + special) as a compact table."""
    closed: List[PositionAnalysis] = []
    for a in equity_analyses:
        if "Закрита" in a.activity:
            closed.append(a)
    for a in special_analyses:
        if "Закрита" in a.activity:
            closed.append(a)
    if bills_analysis and "Закрита" in bills_analysis.activity:
        closed.append(bills_analysis)
    if not closed:
        return []
    # Recompute exit price for closed special assets (they need trades_snap too)
    closed.sort(key=lambda a: -a.weight)
    lines = [
        "| Позиція | Клас активу | Ціна входу → виходу | Реалізований P/L |",
        "|---------|-------------|---------------------|------------------|",
    ]
    for a in closed:
        entry = f"{a.avg_entry_price:.2f}$" if a.avg_entry_price > 0 else "-"
        exit_price = a.avg_exit_price
        exit_str = f"{exit_price:.2f}$" if exit_price > 0 else "—"
        if entry != "-" and exit_price > 0:
            pl = _pl_str(a)
        else:
            pl = "—"
        asset_class = _asset_class_label(a.symbol)
        lines.append(
            f"| {a.symbol} | {asset_class} | {entry} → {exit_str} | {pl} |"
        )
    return lines


def _section4_composition(
    equity_analyses: List[PositionAnalysis],
    special_analyses: List[PositionAnalysis],
    bills_analysis: Optional[PositionAnalysis],
    start_snap: SnapshotData,
    end_snap: SnapshotData,
    trades_snap: Optional[SnapshotData],
) -> List[str]:
    """Unified section 4: composition + quarterly changes.

    Replaces the former separate 'changes' (§4) and 'full appendix' (§8)
    sections. Three subsections: open equity, special assets, closed.
    """
    lines = ["## 4. Склад і зміни портфеля IBKR", ""]

    # 4.1 Open equity
    lines.append("### Акції — відкриті позиції")
    lines.append("")
    lines.extend(_section4_equity_open_table(equity_analyses, start_snap, end_snap))
    lines.append("")

    # Core/Satellite, China/Other, total equity value
    core_pct, sat_pct = core_satellite_ratio(end_snap)
    lines.append(
        f"Співвідношення Core/Satellite (акції): "
        f"{_pct_trim(core_pct)}% / {_pct_trim(sat_pct)}%."
    )
    lines.append("")
    china_pct, rest_pct = china_ratio(end_snap)
    lines.append(
        f"Співвідношення Китай/Інші (акції): "
        f"{_pct_trim(china_pct)}% / {_pct_trim(rest_pct)}%."
    )
    lines.append("")
    total_equity = equity_total_value(end_snap)
    lines.append(
        "**Загальна вартість всіх акцій (в USD, без облігацій, золота та "
        f"товарних активів): {total_equity:,.2f}$**"
    )
    lines.append("")

    # 4.2 Special assets
    lines.append("### Облігації, золото та товарні активи")
    lines.append("")
    special = _section4_special_table(
        start_snap, end_snap, special_analyses, bills_analysis, trades_snap
    )
    if special:
        lines.extend(special)
    lines.append("")

    # 4.3 Closed positions
    closed = _section4_closed_table(
        equity_analyses, special_analyses, bills_analysis,
        start_snap, end_snap, trades_snap,
    )
    if closed:
        lines.append("### Закриті протягом кварталу позиції")
        lines.append("")
        lines.extend(closed)

    return lines


def _section5_income(
    start_metrics: Dict, end_metrics: Dict
) -> List[str]:
    lines = ["## 5. Дивіденди та процентні доходи сукупного портфеля", ""]
    any_rendered = False

    change = _income_change_pct(start_metrics, end_metrics)
    if change is not None:
        lines.append(
            f"- Зміна прогнозного річного доходу за квартал: "
            f"**{_signed_pct(change, 1)}**"
        )
        any_rendered = True

    total = end_metrics.get("income_total_yearly")
    stocks = end_metrics.get("income_stocks_yearly")
    fixed = end_metrics.get("income_fixed_yearly")
    if total is not None and total > 0:
        if stocks is not None:
            lines.append(
                f"- Частка дивідендів у доходах: "
                f"**{round(stocks / total * 100)}%**"
            )
            any_rendered = True
        if fixed is not None:
            lines.append(
                f"- Частка процентних надходжень: "
                f"**{round(fixed / total * 100)}%**"
            )
            any_rendered = True

    start_fp = start_metrics.get("freedom_progress")
    end_fp = end_metrics.get("freedom_progress")
    if start_fp and end_fp:
        lines.append(
            f"- Прогрес до цілі фінансової незалежності: "
            f"**{start_fp} → {end_fp}**"
        )
        any_rendered = True

    if not any_rendered:
        return ["## 5. Дивіденди та процентні доходи сукупного портфеля", "",
                "Дані про доходи недоступні за квартал."]

    bq = _income_index_blockquote(start_metrics, end_metrics)
    if bq:
        lines.append("")
        lines.append(bq)
    return lines


def _section6_risk(
    dalio: Dict,
    end_snap: SnapshotData,
) -> List[str]:
    """Reader-facing concentration view.

    HHI is dropped (no scale for readers); it lives in analytics/output/summary.json
    for the author. Effective bets are shown only when correlation coverage is
    complete (penalty == 0); otherwise the estimate is too rough to publish.
    """
    bets = dalio.get("effective_bets")
    top = top_positions_by_weight(end_snap, 3)
    penalty = dalio.get("data_quality_penalty_pct")
    coverage_complete = penalty is not None and penalty == 0

    lines = ["## 6. Ризик і концентрація", ""]

    if top:
        lines.append(
            "Три найбільші позиції IBKR: **"
            + ", ".join(sym for sym, _ in top)
            + "**."
        )
    else:
        lines.append("Найбільші позиції IBKR: **N/A**.")

    if coverage_complete and bets is not None:
        lines.append(
            f"Кореляційно скоригована кількість незалежних ставок: "
            f"приблизно **{bets:.1f}**."
        )
    elif penalty is not None and penalty > 0:
        lines.append(
            "Оцінка кількості незалежних ставок недоступна через неповне "
            "покриття кореляційними даними."
        )
    elif bets is None:
        lines.append(
            "Оцінка кількості незалежних ставок недоступна (Dalio summary "
            "відсутній)."
        )

    return lines



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
    """Render the full quarterly report markdown (8-section Ukrainian spec)."""
    gen_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    period_label = format_quarter_ua(year, quarter)

    header_lines = [
        f"# Квартальний звіт: {period_label}",
        "",
    ]

    equity_analyses = _compute_equity_analyses(
        start_snap, end_snap, trades_snap
    )
    special_analyses, bills_analysis = _compute_special_analyses(
        start_snap, end_snap, trades_snap
    )

    sections: List[str] = []
    sections.extend(_section1_summary(
        allocation_diff, end_metrics, start_metrics, equity_analyses
    ))
    sections.append("")
    sections.extend(_section3_performance(end_metrics, equity_analyses))
    sections.append("")
    sections.extend(_section2_allocation(allocation_diff))
    sections.append("")
    sections.extend(_section4_composition(
        equity_analyses, special_analyses, bills_analysis,
        start_snap, end_snap, trades_snap,
    ))
    sections.append("")
    sections.extend(_section5_income(start_metrics, end_metrics))
    sections.append("")
    if not skip_dalio and dalio:
        sections.extend(_section6_risk(dalio, end_snap))

    return "\n".join(header_lines + sections)