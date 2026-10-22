#!/usr/bin/env python3

"""
Quarterly HTML report generator.

Assembles the institutional-style quarterly report from:
- IBKR Flex exports `stocks_count_trades1.xml` / `2.xml` in this directory
  (section 3: IBKR positions), via analyze_portfolio_reports.load_portfolios;
- `data/final_data.json` (section 1 YTD figures and section 2 "Стало");
- a dated `data/snapshots/combined_data_*.json` snapshot (section 2 "Було"),
  archived on every `just run` by main.py's save_combined_data_snapshot_json.

Usage (from the repo root):
    venv/bin/python portfolio_yic_reports/generate_quarterly_report.py
    ... [--before PATH] [--after PATH] [--ibkr-ytd -6.8] [--sp500-ytd 9.3] [--output PATH] [--open]

Output: portfolio_report_qN_YYYY.html next to the Markdown report.
"""

import argparse
import json
import math
import re
import sys
import webbrowser
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from analyze_portfolio_reports import (
    PortfolioAnalyzer,
    TableFormatter,
    collect_special_asset_rows,
    collect_stock_rows,
    load_portfolios,
)
from src.portfolio_ledger.contract import reclassify_cash_equivalents, STABLECOINS
from analytics.holy_grail import saved_progress_view

from quarterly_report_html import (
    MINUS,
    AllocationRow,
    DetailTable,
    KpiCard,
    PositionRow,
    ReportData,
    render_report,
)

# Days after the initial Flex export date within which a snapshot still
# counts as the start-of-quarter state.
SNAPSHOT_GRACE_DAYS = 5

# If the chosen "Було" snapshot is further than this from the quarter
# boundary, warn - it likely does not reflect the true end of the prior quarter.
SNAPSHOT_MAX_DRIFT_DAYS = 10

# ASSET_ALLOCATION category -> (Ukrainian name, genitive form for prose)
CATEGORY_UK = {
    "Stocks": ("Акції IBKR", "акцій IBKR"),
    "Bonds": ("Облігації", "облігацій"),
    "Other Bets": (
        "Інші активи (Car Resale)",
        "інших активів (Car Resale)",
    ),
    "Crypto Lending": ("Криптокредитування", "криптокредитування"),
    "Precious Metals": ("Дорогоцінні метали", "дорогоцінних металів"),
    "Cash": ("Кеш", "кешу"),
    "Commodities": ("Товарні активи", "товарних активів"),
    "Crypto Coins": ("Криптовалюти", "криптовалют"),
    "P2P Lending": ("P2P-кредитування", "P2P-кредитування"),
    "REIT": ("REIT", "REIT"),
}

UK_MONTHS = [
    "Січень", "Лютий", "Березень", "Квітень", "Травень", "Червень",
    "Липень", "Серпень", "Вересень", "Жовтень", "Листопад", "Грудень",
]


UK_MONTHS_GENITIVE = [
    "січня", "лютого", "березня", "квітня", "травня", "червня",
    "липня", "серпня", "вересня", "жовтня", "листопада", "грудня",
]


def _quarter_month_range_uk(date_obj: datetime) -> str:
    """E.g. 2026-04-01 -> 'Квітень – Червень 2026 року'."""
    quarter = (date_obj.month - 1) // 3 + 1
    start_month = (quarter - 1) * 3 + 1
    end_month = start_month + 2
    return f"{UK_MONTHS[start_month - 1]} – {UK_MONTHS[end_month - 1]} {date_obj.year} року"


def _fmt_comma_signed1(value: float) -> str:
    sign = "+" if value > 0 else (MINUS if value < 0 else "")
    return f"{sign}{abs(value):.1f}".replace(".", ",")


def _fmt_comma_pct1(value: float) -> str:
    """Ukrainian prose style: one decimal, comma separator, typographic minus."""
    return _fmt_comma_signed1(value) + "%"


def _fmt_usd(value: Optional[float]) -> str:
    if value is None or not math.isfinite(float(value)):
        return "-"
    return f"${float(value):,.0f}"


def _fmt_optional_pct(value: Optional[float]) -> str:
    return "-" if value is None else f"{float(value):.2f}%"


def _value_change_pct(start: Optional[float], end: Optional[float]) -> Optional[float]:
    if start is None or end is None:
        return None
    start, end = float(start), float(end)
    if not math.isfinite(start) or not math.isfinite(end) or start <= 0 or end < 0:
        return None
    change = (end / start - 1) * 100
    return change if math.isfinite(change) else None


def build_alternative_asset_tables(
    after_data: Dict, quarter_key: str
) -> List[DetailTable]:
    after_data = reclassify_cash_equivalents(after_data)
    payload = after_data.get("data", after_data)
    quarter = payload.get("ACTIVITY_DATA", {}).get("quarters", {}).get(
        quarter_key, {}
    )
    tables: List[DetailTable] = []
    crypto_positions = []
    crypto_total = read_allocation_values(payload).get("Crypto Coins")
    partial_assets = []
    for row in quarter.get("crypto", []):
        if str(row.get("asset", "")).upper() in STABLECOINS:
            continue
        end = row.get("end_value_usd")
        start_qty, end_qty = row.get("start_quantity"), row.get("end_quantity")
        quantity_change = _value_change_pct(start_qty, end_qty)
        if (start_qty == 0 and end_qty is not None
                and math.isfinite(float(end_qty)) and end_qty > 0):
            kind, activity = "new", "Нова позиція"
        elif quantity_change is None:
            kind, activity = "unchanged", "Немає даних"
        elif end_qty == 0:
            kind, activity = "closed", "Закрита позиція"
        elif quantity_change == 0:
            kind, activity = "unchanged", "Без змін"
        else:
            kind = "increased" if quantity_change > 0 else "decreased"
            activity = f"{quantity_change:+.1f}%"
        weight = None
        if (crypto_total is not None and math.isfinite(crypto_total)
                and crypto_total > 0 and end is not None
                and math.isfinite(float(end)) and end >= 0):
            weight = float(end) / crypto_total * 100
        position = PositionRow(
            symbol=str(row.get("asset", "")), kind=kind, activity_text=activity,
            price_text="",
            weight_pct=weight, pl_pct=None,
        )
        crypto_positions.append(position)
        if row.get("coverage") != "complete":
            partial_assets.append(position.symbol)
    if crypto_positions:
        note = (
            "Кількість монет - зміна балансу за квартал, не прибуток. "
            "Вага - частка у криптовалютній частині портфеля на кінець кварталу."
        )
        if partial_assets:
            note += (" Неповна історія операцій: " + ", ".join(partial_assets)
                     + "; джерело зміни кількості не визначено.")
        tables.append(
            DetailTable(
                title="Криптовалюти",
                headers=["Позиція", "Зміна кількості монет", "Вага (криптовалюти)"],
                rows=[[
                    position.symbol, position.activity_text,
                    f"{position.weight_pct:.2f}%" if position.weight_pct is not None else "-",
                ] for position in crypto_positions],
                position_rows=crypto_positions, note=note, show_price_column=False,
                show_pl_column=False,
            )
        )

    sold_cars = quarter.get("sold_cars", [])
    if sold_cars:
        tables.append(
            DetailTable(
                title="Продані автомобілі",
                headers=["Актив", "Net proceeds", "Profit", "All-in profit", "ROI", "Днів"],
                rows=[
                    [
                        str(car.get("name", car.get("asset_id", ""))),
                        _fmt_usd(car.get("net_proceeds_usd")),
                        _fmt_usd(car.get("realized_profit_usd")),
                        _fmt_usd(car.get("all_in_profit_usd")),
                        _fmt_optional_pct(car.get("roi_pct")),
                        (
                            str(car.get("holding_days"))
                            if car.get("holding_days") is not None
                            else "-"
                        ),
                    ]
                    for car in sold_cars
                ],
            )
        )

    return tables


def generate_html_report_filename(date_str: str) -> str:
    """AGENTS.md naming convention: portfolio_report_qN_YYYY.html."""
    try:
        date_obj = datetime.strptime(date_str, "%Y%m%d")
    except (TypeError, ValueError):
        return "portfolio_report.html"
    quarter = (date_obj.month - 1) // 3 + 1
    return f"portfolio_report_q{quarter}_{date_obj.year}.html"


def _asset_allocation(final_data: Dict) -> Dict:
    """
    The ASSET_ALLOCATION dict. Accepts both the flat final_data.json
    structure and the {"data": {...}} wrapper used by the dated snapshots
    that `main.py` archives to data/snapshots/ on every `just run` (via
    src/portfolio_history/unified_history.save_combined_data_snapshot_json).
    """
    payload = final_data.get("data", final_data)
    return payload.get("ASSET_ALLOCATION", {})


def _allocation_entries(final_data: Dict) -> Dict[str, Dict]:
    """Raw category -> {"value": ..., "percentage": ...} entries."""
    return _asset_allocation(final_data).get("allocations", {})


def read_allocations(final_data: Dict) -> Dict[str, float]:
    """Category -> percentage of net worth."""
    return {
        category: float(entry.get("percentage", 0.0))
        for category, entry in _allocation_entries(final_data).items()
    }


def read_allocation_values(final_data: Dict) -> Dict[str, float]:
    """Category -> dollar value. Used to rank the "main change" KPI by real
    money moved, not by percentage-point share (which can shift purely
    because net worth itself changed between the before/after snapshots)."""
    return {
        category: float(entry.get("value", 0.0))
        for category, entry in _allocation_entries(final_data).items()
    }


def read_net_worth(final_data: Dict) -> float:
    """Top-level ASSET_ALLOCATION.net_worth, defaulting to 0.0."""
    return float(_asset_allocation(final_data).get("net_worth", 0.0))


_SNAPSHOT_DATE_RE = re.compile(r"^combined_data_(\d{4}-\d{2}-\d{2})_")


def snapshot_date_from_name(name: str) -> Optional[date]:
    """Parse the YYYY-MM-DD embedded in a combined_data snapshot filename."""
    match = _SNAPSHOT_DATE_RE.match(name)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y-%m-%d").date()
    except ValueError:
        return None


def select_before_snapshot(
    snapshots_dir: Path, quarter_start: datetime
) -> Optional[Path]:
    """
    Newest dated combined_data snapshot that actually carries allocation data,
    dated on or before quarter start (plus a few days of grace for pipeline
    runs shortly after the boundary).

    Snapshots archived before the pipeline computed ASSET_ALLOCATION carry no
    allocations; they are skipped so an older-but-populated snapshot (or the
    manual backfill) wins over a newer empty one.
    """
    cutoff = quarter_start.date() + timedelta(days=SNAPSHOT_GRACE_DAYS)
    dated = []
    for path in snapshots_dir.glob("combined_data_*.json"):
        snapshot_date = snapshot_date_from_name(path.name)
        if snapshot_date is None:  # e.g. combined_data_latest.json
            continue
        if snapshot_date <= cutoff:
            dated.append((snapshot_date, path.name, path))

    # Newest first; filename break keeps selection deterministic on ties.
    for _, _, path in sorted(dated, key=lambda item: (item[0], item[1]), reverse=True):
        try:
            with path.open(encoding="utf-8") as handle:
                if read_allocations(json.load(handle)):
                    return path
        except (OSError, json.JSONDecodeError):
            continue
    return None


def select_after_snapshot(
    snapshots_dir: Path, quarter_end: datetime, quarter_key: Optional[str] = None
) -> Optional[Path]:
    """
    Newest dated combined_data snapshot that carries allocation data, dated
    on or before quarter end (plus grace days). Used for the "Стало" column
    and YTD metrics instead of the always-current final_data.json.
    """
    if quarter_key:
        cutoff = quarter_end.date() + timedelta(days=SNAPSHOT_GRACE_DAYS)
        dated = [
            (snapshot_date, path.name, path)
            for path in snapshots_dir.glob("combined_data_*.json")
            if (snapshot_date := snapshot_date_from_name(path.name)) is not None
            and snapshot_date <= cutoff
        ]
        for _, _, path in sorted(
            dated, key=lambda item: (item[0], item[1]), reverse=True
        ):
            try:
                with path.open(encoding="utf-8") as handle:
                    payload = json.load(handle)
                data = payload.get("data", payload)
                quarters = data.get("ACTIVITY_DATA", {}).get("quarters", {})
                if read_allocations(payload) and quarter_key in quarters:
                    return path
            except (OSError, json.JSONDecodeError):
                continue
    return select_before_snapshot(snapshots_dir, quarter_end)


def build_allocation_rows(
    before: Dict[str, float], after: Dict[str, float]
) -> List[AllocationRow]:
    rows = []
    for category in sorted(
        set(before) | set(after), key=lambda c: (-after.get(c, 0.0), c)
    ):
        name = CATEGORY_UK.get(category, (category, category))[0]
        rows.append(
            AllocationRow(
                name=name,
                before_pct=before.get(category, 0.0),
                after_pct=after.get(category, 0.0),
            )
        )
    return rows


def find_main_change(
    before_pct: Dict[str, float], after_pct: Dict[str, float]
) -> Optional[Tuple[str, str, float, float]]:
    """Largest absolute allocation-share change, matching section 02.

    Return category names and its before/after shares. Exact ties use the
    category name for deterministic output. No change means no callout.
    """
    categories = set(before_pct) | set(after_pct)
    if not categories:
        return None
    category = max(
        categories,
        key=lambda c: (abs(after_pct.get(c, 0.0) - before_pct.get(c, 0.0)), c),
    )
    before = before_pct.get(category, 0.0)
    after = after_pct.get(category, 0.0)
    if before == after:
        return None
    nominative, genitive = CATEGORY_UK.get(category, (category, category))
    return nominative, genitive, before, after


def build_kpis(
    ibkr_ytd: float,
    sp500_ytd: float,
    main_change: Optional[Tuple[str, str, float, float]] = None,
) -> List[KpiCard]:
    spread = ibkr_ytd - sp500_ytd
    spread_label = (
        "Відставання від S&P 500"
        if spread < 0
        else "Випередження S&P 500"
    )
    kpis = [
        KpiCard(
            label="Мій портфель IBKR",
            value=_fmt_comma_pct1(ibkr_ytd),
            tone="neg" if ibkr_ytd < 0 else "pos",
            caption="З початку року",
        ),
        KpiCard(
            label="Індекс S&P 500",
            value=_fmt_comma_pct1(sp500_ytd),
            tone="neg" if sp500_ytd < 0 else "pos",
            caption="З початку року",
        ),
        KpiCard(
            label=spread_label,
            value=f"{abs(spread):.1f}".replace(".", ","),
            tone="neg" if spread < 0 else "pos",
            caption="відсоткового пункту\nз початку року",
        ),
    ]
    if main_change:
        category, genitive, before, after = main_change
        short_category = "Car Resale" if category == CATEGORY_UK["Other Bets"][0] else genitive
        kpis.append(
            KpiCard(
                label=f"Частка {short_category}",
                value=f"{after:.1f}%".replace(".", ","),
                tone="navy",
                caption=f"Було {before:.1f}%\nна початку кварталу".replace(".", ","),
                purpose="Найбільша зміна\nза квартал",
            )
        )
    return kpis


def build_footnotes(after: Dict[str, float]) -> List[str]:
    return ["Дохідність портфеля стосується лише активів на рахунку IBKR."]


def _position_row(row: Dict) -> PositionRow:
    return PositionRow(
        symbol=row["symbol"],
        kind=row["kind"],
        activity_text=row["activity_text"],
        price_text=row["price_text"],
        weight_pct=row.get("weight_pct"),
        weight_text=row.get("weight_text"),
        pl_pct=row.get("pl_pct"),
    )


def build_report_data(
    analyzer: PortfolioAnalyzer,
    final_to_date: str,
    ibkr_ytd: float,
    sp500_ytd: float,
    before_alloc: Dict[str, float],
    after_alloc: Dict[str, float],
    after_data: Optional[Dict] = None,
) -> ReportData:
    formatter = TableFormatter(analyzer)
    date_obj = datetime.strptime(final_to_date, "%Y%m%d")
    quarter = (date_obj.month - 1) // 3 + 1

    main_change = find_main_change(before_alloc, after_alloc)
    return ReportData(
        summary_title=(
            f"Підсумки на {date_obj.day} "
            f"{UK_MONTHS_GENITIVE[date_obj.month - 1]} {date_obj.year}"
        ),
        period_title=_quarter_month_range_uk(date_obj),
        quarter_label=f"Q{quarter}",
        year_label=str(date_obj.year),
        kpis=build_kpis(ibkr_ytd, sp500_ytd, main_change),
        footnotes=build_footnotes(after_alloc),
        allocation_rows=build_allocation_rows(before_alloc, after_alloc),
        stock_rows=[_position_row(r) for r in collect_stock_rows(analyzer)],
        core_satellite=formatter._calculate_core_satellite_ratio(),
        china_rest=formatter._calculate_china_ratio(),
        special_asset_rows=[
            _position_row(r) for r in collect_special_asset_rows(analyzer)
        ],
        alternative_asset_tables=build_alternative_asset_tables(
            after_data or {}, f"{date_obj.year}-Q{quarter}"
        ),
        holy_grail=saved_progress_view(after_data or {}, expected_date=date_obj.date().isoformat()),
    )


def main() -> int:
    base_dir = Path(__file__).resolve().parent
    repo_root = base_dir.parent

    parser = argparse.ArgumentParser(
        description="Generate the institutional-style quarterly HTML report."
    )
    parser.add_argument(
        "--year", type=int, required=True, help="Report year (e.g. 2026)."
    )
    parser.add_argument(
        "--quarter", type=int, choices=[1, 2, 3, 4], required=True,
        help="Report quarter (1-4)."
    )
    parser.add_argument(
        "--before",
        type=Path,
        help="Path to a data/snapshots/combined_data_*.json snapshot for the "
        "start of the quarter (default: auto-selected)",
    )
    parser.add_argument(
        "--after",
        type=Path,
        help="Path to a data/snapshots/combined_data_*.json snapshot for the "
        "end of the quarter (default: auto-selected by quarter end date)",
    )
    parser.add_argument(
        "--ibkr-ytd",
        type=float,
        help="Override IBKR YTD %% (default: IB_PERFORMANCE in final_data.json)",
    )
    parser.add_argument(
        "--sp500-ytd",
        type=float,
        help="Override S&P 500 YTD %% (default: INDEX_PERFORMANCE in final_data.json)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output HTML path (default: portfolio_yic_reports/portfolio_report_qN_YYYY.html)",
    )
    parser.add_argument(
        "--open", action="store_true", help="Open the generated report in a browser"
    )
    args = parser.parse_args()

    loaded = load_portfolios(args.year, args.quarter)
    if loaded is None:
        return 1
    initial_portfolio, final_portfolio, initial_to_date, final_to_date = loaded

    # Section 2 "Стало": use a quarter-end combined_data snapshot instead of
    # the always-current final_data.json, so historical reports don't mix
    # old positions with current allocations.
    snapshots_dir = repo_root / "data" / "snapshots"
    quarter_end_dt = datetime.strptime(final_to_date, "%Y%m%d")
    if args.after:
        after_path = args.after
    else:
        after_path = select_after_snapshot(
            snapshots_dir, quarter_end_dt, f"{args.year}-Q{args.quarter}"
        )
    if after_path is None or not after_path.exists():
        if args.after:
            print(f"Error: end-of-quarter snapshot not found: {args.after}")
            return 2
        # Fallback to final_data.json for the current quarter
        final_data_path = repo_root / "data" / "final_data.json"
        if not final_data_path.exists():
            print(f"Error: no end-of-quarter snapshot found in {snapshots_dir}")
            print(f"  and {final_data_path} not found. Run `just run` first.")
            return 2
        print("Warning: using current final_data.json (may not match quarter end)")
        with final_data_path.open(encoding="utf-8") as f:
            after_data = json.load(f)
    else:
        print(f"End-of-quarter allocation: {after_path}")
        with after_path.open(encoding="utf-8") as f:
            after_data = json.load(f)
    after_data = reclassify_cash_equivalents(after_data)
    after_payload = after_data.get("data", after_data)

    # Section 1: YTD figures
    ibkr_ytd = args.ibkr_ytd
    if ibkr_ytd is None:
        ib_perf = after_payload.get("IB_PERFORMANCE", {})
        ibkr_ytd = ib_perf.get("rate_of_return_pct")
        if ibkr_ytd is None or ib_perf.get("error"):
            print(
                "Error: IBKR YTD not available in final_data.json "
                f"(error: {ib_perf.get('error')}). Pass --ibkr-ytd."
            )
            return 2
    sp500_ytd = args.sp500_ytd
    if sp500_ytd is None:
        sp500 = after_payload.get("INDEX_PERFORMANCE", {}).get("SP500", {})
        sp500_ytd = sp500.get("rate_of_return_pct")
        if sp500_ytd is None or not sp500.get("success", True):
            print(
                "Error: S&P 500 YTD not available in final_data.json "
                f"(error: {sp500.get('error')}). Pass --sp500-ytd."
            )
            return 2

    # Section 2: allocation before/after
    after_alloc = read_allocations(after_data)
    quarter_start = datetime.strptime(initial_to_date, "%Y%m%d")
    if args.before:
        before_path = args.before
    else:
        snapshots_dir = repo_root / "data" / "snapshots"
        before_path = select_before_snapshot(snapshots_dir, quarter_start)
        if before_path is None:
            available = sorted(p.name for p in snapshots_dir.glob("combined_data_*.json"))
            print(
                "Error: no start-of-quarter snapshot found in "
                f"{snapshots_dir} (need a combined_data_YYYY-MM-DD_*.json dated on "
                f"or before {quarter_start.date()} + {SNAPSHOT_GRACE_DAYS} days grace)."
            )
            print(f"Available snapshots: {available or 'none'}")
            print("Pass --before PATH to use a specific snapshot.")
            return 2
    if not before_path.exists():
        print(f"Error: snapshot not found: {before_path}")
        return 2
    with before_path.open(encoding="utf-8") as f:
        before_data = json.load(f)
    before_data = reclassify_cash_equivalents(before_data)
    before_alloc = read_allocations(before_data)
    if not before_alloc:
        print(f"Error: no ASSET_ALLOCATION data in {before_path}")
        return 2
    print(f"Start-of-quarter allocation: {before_path}")

    snap_date = snapshot_date_from_name(before_path.name)
    if snap_date is not None:
        drift = abs((snap_date - quarter_start.date()).days)
        if drift > SNAPSHOT_MAX_DRIFT_DAYS:
            print(
                f'Warning: "Було" snapshot ({snap_date}) is {drift} days from the '
                f"quarter boundary ({quarter_start.date()}); it may not reflect the "
                "true end of the previous quarter. Re-run `just run` near quarter end "
                "or pass --before with the correct snapshot."
            )

    # Assemble and render
    analyzer = PortfolioAnalyzer(initial_portfolio, final_portfolio)
    report_data = build_report_data(
        analyzer,
        final_to_date,
        ibkr_ytd,
        sp500_ytd,
        before_alloc,
        after_alloc,
        after_data,
    )
    html_doc = render_report(report_data)

    output_path = args.output
    if output_path is None:
        output_path = base_dir / f"portfolio_report_q{args.quarter}_{args.year}.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_doc, encoding="utf-8")
    print(f"HTML звіт збережено у файл: {output_path}")

    if args.open:
        webbrowser.open(output_path.resolve().as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
