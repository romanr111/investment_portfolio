# Investment Portfolio - agent guide

Personal portfolio automation: IB Gateway live data, dividend income estimates, Google Sheets sync, historical snapshots, Dalio-style risk analysis, and automated quarterly YIC portfolio reports. Python 3; venv at `venv/`; env vars loaded from `data/ib_flex_env.sh` (local-only).

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
- Core/Satellite split is controlled by the hardcoded `CORE_SYMBOLS` set in `portfolio_yic_reports/analyze_portfolio_reports.py`; the bonds/gold table weights use the IBKR subset only (stocks + special assets), not the full portfolio.
- Step-by-step runbook (preconditions, hardcoded one-off cleanup, CLI flags, verification): the `quarterly-report` skill in `.claude/skills/quarterly-report/SKILL.md`.

## Python project notes

- Keep `data/` local-only. Only `data/README.md` is tracked. Do not commit credentials, snapshots, or private sheets config.
- Use Headroom as the primary context-optimization layer for bulky/noisy outputs. Do not default to RTK when Headroom is available.
- Use CodeGraph before broad text search or raw file-read loops. Run `just graph-bootstrap` before CodeGraph work in every worktree.
- Prefer `just` for project commands when a recipe exists (see `justfile` or `.agents/references/commands.md`).
- Quarterly report worktree venvs may lack deps (pandas, numpy, requests); use the primary worktree venv at `/Users/roman/Documents/Development/investment_portfolio/venv/bin/python` when needed.
- The quarterly report requires IB Flex snapshots in `data/ib_flex_snapshots/`. `load_portfolios()` matches by XML `toDate` with +/-3 day tolerance. Run `just fetch-snapshots` to download CI artifacts.
- GitHub Actions workflow `.github/workflows/flex-snapshot.yml` fetches IB Flex snapshots automatically on 1st day of Jan/Apr/Jul/Oct at 06:00 UTC (single cron, positions + trades in one run). Download artifacts via `just fetch-snapshots` before running `just report YEAR QUARTER`.

## Data invariants (every change)

- The quarterly report **never re-fetches or recomputes** TWR/benchmarks/income. It reads `data/snapshots/combined_data_*.json` written by `just run`.
- `combined_data` is the single source of truth for both Google Sheets and the quarterly report. Do not duplicate fetch/calc logic in the report package.
- Ticker sets, FX rates, and hardcoded prices live in `portfolio_yic_reports/analyze_portfolio_reports.py` only. Do not redefine them elsewhere.

## Workflow

Use `commit-hygiene`, `code-review`, `self-review` skills for project workflows.