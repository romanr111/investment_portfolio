---
name: quarterly-report
description: Generate the quarterly investment report (styled HTML + Markdown) from IBKR Flex exports and pipeline data. Use when asked to create, update, or troubleshoot the quarterly portfolio report.
---

# Quarterly portfolio report

Produces two files in `portfolio_yic_reports/`: `portfolio_report_YYYY_qN.md` (tables) and `portfolio_report_qN_YYYY.html` (institutional-style, self-contained, print-ready).

## Preconditions

1. `just run` was executed on the last day of the quarter. It writes `data/final_data.json` (IBKR YTD TWR, S&P 500 YTD, asset allocation) and, via `main.py`'s `save_combined_data_snapshot_json`, already archives a dated snapshot to `data/snapshots/combined_data_{date}_{timestamp}Z.json` on every run — no separate archiving step is needed.
2. Fresh IBKR Flex exports in `portfolio_yic_reports/` (two separate queries):
   - **Positions query** (`stocks_count_trades`) — Query ID `1188471`. Fetch twice:
     - `stocks_count_trades1.xml` with `toDate` = first day of the quarter.
     - `stocks_count_trades2.xml` with `toDate` = last day of the quarter.
   - **Trades query** (`stocks_trades_quarterly`) — Query ID `1575659`. Fetch once per quarter covering the full quarter and save as `portfolio_yic_reports/stocks_trades_quarterly_YYYY_qN.xml`. Required only if closed positions should show realized P/L. The parser merges its `<Trade buySell="SELL">` elements into the final portfolio.
   - Fetch using the existing `IBFlexPerformanceFetcher` in `src/brokers/ib_flex_performance.py` with `IB_FLEX_TOKEN` from `data/ib_flex_env.sh`. Query IDs are configured in IBKR Account Management.
3. Review hardcoded one-offs in `portfolio_yic_reports/analyze_portfolio_reports.py` before running: `hardcoded_prices` in `PortfolioAnalyzer.__init__` and any share adjustments in `load_portfolios()`. Remove ones that no longer apply - IBKR restates split-adjusted history in new exports, so split fixes usually expire after one quarter (a stale fix shows up as a spurious "Збільшив/Зменшив" on an untouched position).

## Generate

```bash
just report YEAR QUARTER
```

`generate_quarterly_report.py` options:

- `--before PATH` - explicit start-of-quarter `data/snapshots/combined_data_*.json` snapshot. Auto-selected otherwise: newest one dated on or before quarter start + 5 days grace. Needed manually only when the auto-picked snapshot predates the `ASSET_ALLOCATION` field or is otherwise wrong (see Known caveats).
- `--after PATH` - explicit end-of-quarter `combined_data` snapshot. Allocation, YTD metrics, and aggregated crypto/lending/car/P2P sections are read from this file; raw ledger is never read by the report.
- `--ibkr-ytd N` / `--sp500-ytd N` - override the YTD figures from `final_data.json`.
- `--output PATH` - custom output location.
- `--open` - open the result in a browser.

## Verify

- Figures in the HTML match `portfolio_report_YYYY_qN.md` (both come from the same analyzer).
- The HTML is self-contained: no `http`, `<script>`, `<link>`, `src=` references.
- Open in a browser; print-to-PDF produces the distribution copy.
- `just test` covers the renderer and collectors (`tests/test_quarterly_report_html.py`).

## Design

The visual style lives in `portfolio_yic_reports/quarterly_report_html.py` (CSS constant plus render functions): paper background, serif headings, navy accent, KPI cards, inline weight bars, badge pills, print CSS. Keep the output self-contained - inline CSS only, no JS, no external resources.

## Known caveats

- Closed positions show exit prices and realized P/L only when the final Flex export includes sell `Trade` elements.
- Allocation category names and Ukrainian genitive forms: `CATEGORY_UK` in `generate_quarterly_report.py`; extend it when a new allocation category appears.
- Core/Satellite split is governed by `CORE_SYMBOLS`, the China split by `CHINA_EQUITY_SYMBOLS` (both in `analyze_portfolio_reports.py`).
- The "Було" column must come from the **end of the previous quarter** (= start of this quarter). `select_before_snapshot` picks the newest snapshot dated on/before the quarter start (plus `SNAPSHOT_GRACE_DAYS`) that actually carries allocation data, and the generator warns if the chosen snapshot drifts more than `SNAPSHOT_MAX_DRIFT_DAYS` from the boundary. Snapshots archived before the pipeline computed `ASSET_ALLOCATION` are empty and skipped automatically. When no valid snapshot exists near the boundary (e.g. Q2 2026, whose real 2026-04-01 snapshot predates that field), supply a manual backfill dated at the quarter start - see `data/snapshots/combined_data_2026-04-01_manual-backfill.json` (real end-of-Q1 values) - or pass `--before PATH`.
- Trust `data/final_data.json` / the matching `combined_data_*` snapshot as the authoritative source for both "Було" and "Стало" - not any hand-assembled report from earlier in the quarter, which may reflect a stale intermediate snapshot rather than the true quarter boundary.
