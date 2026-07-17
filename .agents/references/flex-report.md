# Auto quarterly report subsystem

## Overview

The `portfolio_yic_reports/auto/` package generates Ukrainian quarterly YIC portfolio reports as Markdown (`REPORT_YYYY_qN.md`) by combining IB Flex portfolio snapshots, allocation diff, performance metrics, and Dalio risk analysis.

Entry point: `portfolio_yic_reports/auto/cli.py` (`just report`).

## Data flow

```
IB Flex query 1188471 (Open Positions + Trades, Period=Last Business Day, XML)
  -> just fetch-snapshot -> data/ib_flex_snapshots/stocks_count_trades_<toDate>_<timestamp>.xml
  -> flex_xml_parser.parse_snapshot -> positions + trades
  -> position_analyzer (equity/special-assets tables, closed positions)
  -> allocation_diff (from data/portfolio_history.csv, month-end bucket values)
  -> combined_loader (from data/snapshots/combined_data_*.json, nearest <= quarter boundary)
     -> Section 3: YTD TWR, dividends, freedom progress
  -> dalio_loader (from analytics/output/summary.json)
     -> Section 4: Dalio risk metrics
  -> markdown_renderer -> portfolio_yic_reports/REPORT_YYYY_qN.md
```

## Required env vars

Configured in `data/ib_flex_env.sh` (local-only, gitignored):

- `IB_FLEX_TOKEN` - IB Flex Web Service token
- `IB_FLEX_QUERY_ID_PORTFOLIO_SNAPSHOT` - query ID for portfolio snapshot (1188471)
- `IB_ACCOUNT_ID` - IB account ID

The main sync pipeline also requires `IB_GATEWAY_HOST`, `IB_GATEWAY_PORT`, `IB_FLEX_QUERY_ID_YTD_PERFORMANCE` (see `README.md`).

## Data sources

| Source | Path | Used for |
|--------|------|----------|
| IB Flex snapshots | `data/ib_flex_snapshots/stocks_count_trades_*.xml` | Positions, trades, equity tables |
| Portfolio history | `data/portfolio_history.csv` | Allocation diff (Section 1) |
| Combined data | `data/snapshots/combined_data_*.json` | YTD TWR, dividends, freedom progress (Section 3) |
| Dalio summary | `analytics/output/summary.json` | Dalio risk section (Section 4) |

## Snapshot matching

Snapshots are matched by `toDate` embedded in the XML filename (`stocks_count_trades_<toDate>_<timestamp>.xml`). The report generator finds the snapshot with `toDate <= quarter end` (nearest preceding). Same logic for the start-of-quarter boundary (previous quarter end).

If no matching snapshot exists, the command refuses with a `ValueError`. Incomplete quarters cannot be reported.

## Report output

`portfolio_yic_reports/REPORT_YYYY_qN.md` (Ukrainian).

## Key design decisions

- Allocation diff: only from `portfolio_history.csv` (not combined_data).
- Net worth: `combined_data.TOTAL_ASSETS` (not portfolio_history.csv sum).
- Equity table weights: equity-only total (sum to 100%); special-assets table: combined IB total (includes BILLS).
- Closed positions: use start-period denominator (not end-period).
- `portfolio_yic_reports/__init__.py`: lazy import via `__getattr__` to avoid hard dep on local-only `data/filters_constants`.
- Report language: Ukrainian.
- Shared Flex fetcher at `src/brokers/ib_flex_portfolio.py` (not in auto/ package).

## Module map

| Module | Role |
|--------|------|
| `cli.py` | argparse entry point, quarter resolution |
| `config.py` | `ReportConfig` dataclass, path constants, ticker sets |
| `dates.py` | quarter boundary calculation, snapshot matching by toDate |
| `flex_xml_parser.py` | parse IB Flex XML into positions + trades |
| `position_analyzer.py` | equity/special-assets tables, closed positions |
| `allocation_diff.py` | allocation diff from portfolio_history.csv |
| `combined_loader.py` | load/match combined_data snapshots, extract metrics |
| `dalio_loader.py` | load Dalio summary.json, extract metrics |
| `markdown_renderer.py` | render the full Ukrainian Markdown report |
| `report_generator.py` | orchestrator: ties all inputs together |

## Tests

`tests/test_quarterly_report_generator.py` - 26 tests using fixtures in `tests/fixtures/`. Run with:

```bash
venv/bin/python -m unittest discover -s tests -p test_quarterly_report_generator.py
```

Note: the worktree's own `venv/` may lack dependencies (pandas, numpy, requests). Use the primary worktree's venv at `/Users/roman/Documents/Development/investment_portfolio/venv/bin/python` if the worktree venv is not populated.