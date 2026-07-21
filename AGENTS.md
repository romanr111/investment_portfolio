# Investment Portfolio - agent guide

Personal portfolio automation: IB Gateway live data, dividend income estimates, Google Sheets sync, historical snapshots, Dalio-style risk analysis, and automated quarterly YIC portfolio reports. Python 3; venv at `venv/`; env vars loaded from `data/ib_flex_env.sh` (local-only).

## Quarterly report generation

- `just report` generates both quarterly outputs in `portfolio_yic_reports/`: Markdown tables (`analyze_portfolio_reports.py` → `portfolio_report_YYYY_qN.md`) and the styled HTML report (`generate_quarterly_report.py` → `portfolio_report_qN_YYYY.html`, e.g. `portfolio_report_q2_2026.html`, rendered by `quarterly_report_html.py`).
- Data sources (two separate IBKR Flex queries):
  - **Positions query** (`stocks_count_trades`) — Query ID `1188471`. Fetch twice:
    - `portfolio_yic_reports/stocks_count_trades1.xml` with `toDate` = first day of the quarter (quarter start positions).
    - `portfolio_yic_reports/stocks_count_trades2.xml` with `toDate` = last day of the quarter (quarter end positions).
  - **Trades query** (`stocks_trades_quarterly`) — Query ID `1575659`. Fetch once per quarter covering the full quarter and save as `portfolio_yic_reports/stocks_trades_quarterly_YYYY_qN.xml`. Required only if closed positions should show realized P/L. The parser merges its `<Trade buySell="SELL">` elements into the final portfolio.
  - Fetch both using the existing `IBFlexPerformanceFetcher` in `src/brokers/ib_flex_performance.py` with `IB_FLEX_TOKEN` from `data/ib_flex_env.sh`. Query IDs are configured in IBKR Account Management.
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
- The quarterly report requires IB Flex snapshots in `data/ib_flex_snapshots/`. If no snapshot matches the quarter boundary, the generator refuses with a `ValueError` (incomplete quarters cannot be reported).
- GitHub Actions workflow `.github/workflows/flex-snapshot.yml` fetches IB Flex snapshots automatically on quarter boundaries. Download artifacts and place XMLs in `data/ib_flex_snapshots/` before running `just report`.

## Data invariants (every change)

- The quarterly report **never re-fetches or recomputes** TWR/benchmarks/income. It reads `data/snapshots/combined_data_*.json` written by `just run`.
- `combined_data` is the single source of truth for both Google Sheets and the quarterly report. Do not duplicate fetch/calc logic in the report package.
- Ticker sets, FX rates, and hardcoded prices live in `portfolio_yic_reports/analyze_portfolio_reports.py` only. Do not redefine them elsewhere.

## Workflow

Use `commit-hygiene`, `code-review`, `self-review` skills for project workflows.