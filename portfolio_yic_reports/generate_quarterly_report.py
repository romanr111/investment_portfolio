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
    ... [--before PATH] [--ibkr-ytd -6.8] [--sp500-ytd 9.3] [--output PATH] [--open]

Output: portfolio_report_qN_YYYY.html next to the Markdown report.
"""

import argparse
import json
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
from quarterly_report_html import (
    MINUS,
    AllocationRow,
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

# Minimum |delta $| for the "main change" KPI, as a fraction of net worth.
# Below this, no category's move is treated as significant enough to report.
MAIN_CHANGE_MATERIALITY_PCT = 0.01

# ASSET_ALLOCATION category -> (Ukrainian name, genitive form for prose)
CATEGORY_UK = {
    "Stocks": ("Акції IBKR", "акцій IBKR"),
    "Bonds": ("Облігації", "облігацій"),
    "Other Bets": ("Інші активи", "інших активів"),
    "Crypto Lending": ("Криптокредитування", "криптокредитування"),
    "Precious Metals": ("Дорогоцінні метали", "дорогоцінних металів"),
    "Cash": ("Кеш", "кешу"),
    "Commodities": ("Товарні активи", "товарних активів"),
    "Crypto Coins": ("Криптовалюти", "криптовалют"),
    "P2P Lending": ("P2P-кредитування", "P2P-кредитування"),
    "REIT": ("REIT", "REIT"),
}

# Categories excluded from the IBKR YTD performance figure (footnote 2).
NOT_IN_PERFORMANCE = ["Other Bets", "Crypto Lending", "Crypto Coins", "P2P Lending"]

UK_MONTHS = [
    "Січень", "Лютий", "Березень", "Квітень", "Травень", "Червень",
    "Липень", "Серпень", "Вересень", "Жовтень", "Листопад", "Грудень",
]


def _quarter_month_range_uk(date_obj: datetime) -> str:
    """E.g. 2026-04-01 -> 'Квітень – Червень 2026 року'."""
    quarter = (date_obj.month - 1) // 3 + 1
    start_month = (quarter - 1) * 3 + 1
    end_month = start_month + 2
    return f"{UK_MONTHS[start_month - 1]} – {UK_MONTHS[end_month - 1]} {date_obj.year} року"


def _fmt_comma_pct1(value: float) -> str:
    """Ukrainian prose style: one decimal, comma separator, typographic minus."""
    sign = "+" if value > 0 else (MINUS if value < 0 else "")
    return f"{sign}{abs(value):.1f}".replace(".", ",") + "%"


def _fmt_signed_pct1(value: float) -> str:
    sign = "+" if value > 0 else (MINUS if value < 0 else "")
    return f"{sign}{abs(value):.1f}%"


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
    snapshots_dir: Path, quarter_end: datetime
) -> Optional[Path]:
    """
    Newest dated combined_data snapshot that carries allocation data, dated
    on or before quarter end (plus grace days). Used for the "Стало" column
    and YTD metrics instead of the always-current final_data.json.
    """
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
    before_pct: Dict[str, float],
    after_pct: Dict[str, float],
    before_value: Dict[str, float],
    after_value: Dict[str, float],
    net_worth: float,
    materiality_pct: float = MAIN_CHANGE_MATERIALITY_PCT,
) -> Optional[Tuple[str, str, float]]:
    """
    Allocation category with the largest |before -> after| dollar delta -
    not percentage-point delta, since a category's percentage share can
    shift purely because net worth itself changed between the before/after
    snapshots even if barely any real money moved in that category.

    Returns (nominative name, genitive name, delta_pct) of the $-ranked
    winner - the percentage-point delta is still what's displayed on the
    KPI card, kept consistent with section 02's allocation table. Returns
    None if there are no categories, or if the winning category's dollar
    move doesn't clear `materiality_pct` of net worth (nothing significant
    enough happened this quarter to call out).
    """
    categories = set(before_value) | set(after_value)
    if not categories:
        return None
    # Tie-break on category name for determinism - set iteration order is
    # not stable across process runs (hash randomization), so an exact-tie
    # in dollar delta could otherwise pick a different "winner" on every run.
    category = max(
        categories,
        key=lambda c: (abs(after_value.get(c, 0.0) - before_value.get(c, 0.0)), c),
    )
    usd_delta = after_value.get(category, 0.0) - before_value.get(category, 0.0)
    if net_worth <= 0 or abs(usd_delta) < materiality_pct * net_worth:
        return None
    delta_pct = after_pct.get(category, 0.0) - before_pct.get(category, 0.0)
    nominative, genitive = CATEGORY_UK.get(category, (category, category))
    return nominative, genitive, delta_pct


def build_kpis(
    ibkr_ytd: float,
    sp500_ytd: float,
    main_change: Optional[Tuple[str, str, float]] = None,
) -> List[KpiCard]:
    spread = ibkr_ytd - sp500_ytd
    spread_label = (
        "Відставання від S&P 500 (процентні пункти)"
        if spread < 0
        else "Випередження S&P 500 (процентні пункти)"
    )
    kpis = [
        KpiCard(
            label="IBKR YTD",
            value=_fmt_signed_pct1(ibkr_ytd),
            tone="neg" if ibkr_ytd < 0 else "pos",
        ),
        KpiCard(
            label="S&P 500 YTD",
            value=_fmt_signed_pct1(sp500_ytd),
            tone="neg" if sp500_ytd < 0 else "pos",
        ),
        KpiCard(
            label=spread_label,
            value=_fmt_comma_pct1(spread),
            tone="neg" if spread < 0 else "pos",
        ),
    ]
    if main_change:
        _, genitive, delta = main_change
        kpis.append(
            KpiCard(
                label=f"Головна зміна: частка {genitive}",
                value=_fmt_comma_pct1(delta),
                tone="neg" if delta < 0 else "pos",
            )
        )
    return kpis


def build_footnotes(after: Dict[str, float]) -> List[str]:
    footnotes = ["Доходи стосуються лише IBKR."]
    excluded_present = [c for c in NOT_IN_PERFORMANCE if c in after]
    if excluded_present:
        # Move "Other Bets" to the end so it appears after P2P Lending.
        if "Other Bets" in excluded_present:
            ordered = [c for c in excluded_present if c != "Other Bets"] + ["Other Bets"]
        else:
            ordered = excluded_present
        names = ", ".join(CATEGORY_UK.get(c, (c, c))[0] for c in ordered)
        share = round(sum(after[c] for c in excluded_present))
        footnotes.append(
            f"Не входять у доходність: {names} (~{share}% капіталу)."
        )
    return footnotes


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
    initial_to_date: str,
    ibkr_ytd: float,
    sp500_ytd: float,
    before_alloc: Dict[str, float],
    after_alloc: Dict[str, float],
    before_values: Dict[str, float],
    after_values: Dict[str, float],
    net_worth: float,
) -> ReportData:
    formatter = TableFormatter(analyzer)
    date_obj = datetime.strptime(initial_to_date, "%Y%m%d")
    quarter = (date_obj.month - 1) // 3 + 1

    main_change = find_main_change(
        before_alloc, after_alloc, before_values, after_values, net_worth
    )
    return ReportData(
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
        after_path = select_after_snapshot(snapshots_dir, quarter_end_dt)
    if after_path is None or not after_path.exists():
        # Fallback to final_data.json for the current quarter
        final_data_path = repo_root / "data" / "final_data.json"
        if not final_data_path.exists():
            print(f"Error: no end-of-quarter snapshot found in {snapshots_dir}")
            print(f"  and {final_data_path} not found. Run `just run` first.")
            return 2
        print("Warning: using current final_data.json (may not match quarter end)")
        with final_data_path.open(encoding="utf-8") as f:
            final_data = json.load(f)
    else:
        print(f"End-of-quarter allocation: {after_path}")
        with after_path.open(encoding="utf-8") as f:
            final_data = json.load(f)

    # Section 1: YTD figures
    ibkr_ytd = args.ibkr_ytd
    if ibkr_ytd is None:
        ib_perf = final_data.get("IB_PERFORMANCE", {})
        ibkr_ytd = ib_perf.get("rate_of_return_pct")
        if ibkr_ytd is None or ib_perf.get("error"):
            print(
                "Error: IBKR YTD not available in final_data.json "
                f"(error: {ib_perf.get('error')}). Pass --ibkr-ytd."
            )
            return 2
    sp500_ytd = args.sp500_ytd
    if sp500_ytd is None:
        sp500 = final_data.get("INDEX_PERFORMANCE", {}).get("SP500", {})
        sp500_ytd = sp500.get("rate_of_return_pct")
        if sp500_ytd is None or not sp500.get("success", True):
            print(
                "Error: S&P 500 YTD not available in final_data.json "
                f"(error: {sp500.get('error')}). Pass --sp500-ytd."
            )
            return 2

    # Section 2: allocation before/after
    after_alloc = read_allocations(final_data)
    after_values = read_allocation_values(final_data)
    net_worth = read_net_worth(final_data)
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
    before_alloc = read_allocations(before_data)
    before_values = read_allocation_values(before_data)
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
        initial_to_date,
        ibkr_ytd,
        sp500_ytd,
        before_alloc,
        after_alloc,
        before_values,
        after_values,
        net_worth,
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
