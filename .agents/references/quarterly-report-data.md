# Quarterly report reference

Data sources, snapshot matching and core/satellite rules for the quarterly report. `AGENTS.md` links here from its "Where to look" table; the step-by-step runbook is the `quarterly-report` skill.

## Quarterly report generation

- `just report YEAR QUARTER` (e.g. `just report 2026 2`) generates both quarterly outputs in `portfolio_yic_reports/`: Markdown tables (`analyze_portfolio_reports.py` -> `portfolio_report_YYYY_qN.md`) and the styled HTML report (`generate_quarterly_report.py` -> `portfolio_report_qN_YYYY.html`).
- Data sources (two separate IBKR Flex queries):
  - **Positions query** (`stocks_count_trades`) — Query ID `1188471`, `Period=LastBusinessDay`. One Flex Query, no per-quarter reconfiguration. CI cron fetches on 1st day of Jan/Apr/Jul/Oct at 06:00 UTC, capturing last business day of previous quarter.
  - **Trades query** (`stocks_trades_quarterly`) — Query ID `1575659`, `Period=LastQuarter`. Fetched in the same CI run as positions.
  - Snapshots saved to `data/ib_flex_snapshots/` as `stocks_count_trades_<toDate>_<timestamp>.xml` (positions) and `trades_<toDate>_<timestamp>.xml` (trades).
  - `just fetch-snapshots` downloads artifacts from last 4 CI runs into `data/ib_flex_snapshots/`.
  - `load_portfolios(year, quarter)` matches snapshots by XML `toDate` (last business day of quarter-start month for initial, last business day of quarter-end month for final). Tolerance +/-3 days.
  - `data/final_data.json` written by `just run` (YTD performance, current allocation).
  - Dated snapshots auto-archived to `data/snapshots/` on each pipeline run (start-of-quarter "Було" column).
- Core/Satellite split is derived from the `core: true` flags in `analytics/models/economic_profiles_v1.json` (read once by `core_symbols()` in `portfolio_yic_reports/analyze_portfolio_reports.py`; the file is resolved beside the report script first, then via the installed analytics package; if neither location is readable the report aborts with a clear error, and no flagged profile renders 0%/100%). The bonds/gold table weights use the IBKR subset only (stocks + special assets), not the full portfolio.
- Step-by-step runbook (preconditions, hardcoded one-off cleanup, CLI flags, verification): the `quarterly-report` skill in `.agents/skills/quarterly-report/SKILL.md`.

## Snapshot download order

- The quarterly report requires the IB Flex snapshots in `data/ib_flex_snapshots/`. Run `just fetch-snapshots` to download CI artifacts before running `just report YEAR QUARTER`. The schedule lives in `.github/workflows/flex-snapshot.yml` (single cron `0 6 1 1,4,7,10 *`, positions + trades in one run).
