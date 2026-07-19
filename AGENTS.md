# Investment Portfolio - agent guide

Personal portfolio automation: IB Gateway live data, dividend income estimates, Google Sheets sync, historical snapshots, Dalio-style risk analysis, and automated quarterly YIC portfolio reports. Python 3; venv at `venv/`; env vars loaded from `data/ib_flex_env.sh` (local-only).

## Where to look (load on demand)

| Task | Read |
|------|------|
| Run / build / test / fetch-snapshot / report commands and flags | `.agents/references/commands.md` |
| Work on the quarterly report or IB Flex fetcher | `.agents/references/flex-report.md` |
| Quarterly data contracts, order of operations, source-of-truth map | `.agents/references/data-flow.md` |
| Symbol / caller / dependency analysis, worktree setup | `.agents/references/codegraph.md` |
| Bulky output, logs, diffs, cross-session memory | `~/.config/opencode/references/headroom.md` |

## Architecture map

- `src/` - portfolio sync pipeline (IB Gateway fetch, allocation, dividends, Sheets update, history)
- `src/brokers/ib_flex_portfolio.py` - shared IB Flex snapshot fetcher (query 1188471)
- `portfolio_yic_reports/auto/` - automated quarterly report generator (CLI, parser, analyzer, renderer)
- `portfolio_yic_reports/auto/config.py` - single source of truth for ticker sets, FX rates, hardcoded prices
- `portfolio_yic_reports/analyze_portfolio_reports.py` - legacy standalone CLI report (imports constants from `auto/config.py`)
- `analytics/` - Dalio Holy Grail risk analyzer
- `tests/` - test suite; `tests/fixtures/` for quarterly report fixtures
- `data/` - local-only: snapshots, combined_data, portfolio_history.csv, credentials, env

## Non-negotiables (every change)

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
- Ticker sets, FX rates, and hardcoded prices live in `portfolio_yic_reports/auto/config.py` only. Legacy modules import from there; do not redefine.
- For the full 3-stage data contract (gathering -> Flex snapshot -> report) and order of operations, see `.agents/references/data-flow.md`.

## Workflow

Use `commit-hygiene`, `code-review`, `self-review` skills for project workflows.