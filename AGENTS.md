# Investment Portfolio - agent guide

Personal portfolio automation: IB Gateway live data, dividend income estimates, Google Sheets sync, historical snapshots, Dalio-style risk analysis, and automated quarterly YIC portfolio reports. Python 3; venv at `venv/`; env vars loaded from `data/ib_flex_env.sh` (local-only).

## Where to look (load on demand)

| Task | Read |
|------|------|
| Run / build / test / fetch-snapshot / report commands and flags | `.agents/references/commands.md` |
| Work on the quarterly report or IB Flex fetcher | `.agents/references/flex-report.md` |
| Symbol / caller / dependency analysis, worktree setup | `.agents/references/codegraph.md` |
| Bulky output, logs, diffs, cross-session memory | `~/.config/opencode/references/headroom.md` |

## Key functionality

**Portfolio sync pipeline** (`just run` / `python -m src.portfolio_sync`): the global workflow that collects all data. Auto-bootstraps `.venv`, loads `data/ib_flex_env.sh`, then by default:
1. Fetches live positions from IB Gateway (`ib_insync`)
2. Fetches YTD performance from IB Flex Web Service
3. Calculates allocation and dividend income (yfinance/Yahoo)
4. Writes `data/snapshots/combined_data_<date>_<timestamp>.json` (+ `_latest.json`)
5. Updates Google Sheets (`data/credentials.json`)
6. Skips history sync and Dalio analysis by default

For full-collection command, flags, env vars, and outputs see `.agents/references/commands.md`.

**Quarterly report** (`just report`): generates `portfolio_yic_reports/REPORT_YYYY_qN.md` from IB Flex snapshots + portfolio_history + combined_data + Dalio. See `.agents/references/flex-report.md`.

**Dalio risk analysis** (`analytics/dalio_holy_grail.py`): Holy Grail risk analyzer. See `README.md` for full flag reference.

## Architecture map

- `src/` - portfolio sync pipeline (IB Gateway fetch, allocation, dividends, Sheets update, history)
- `src/brokers/ib_flex_portfolio.py` - shared IB Flex snapshot fetcher (query 1188471)
- `portfolio_yic_reports/auto/` - automated quarterly report generator (CLI, parser, analyzer, renderer)
- `analytics/` - Dalio Holy Grail risk analyzer
- `tests/` - test suite; `tests/fixtures/` for quarterly report fixtures
- `data/` - local-only: snapshots, combined_data, portfolio_history.csv, credentials, env

## Non-negotiables (every change)

- Keep `data/` local-only. Only `data/README.md` is tracked. Do not commit credentials, snapshots, or private sheets config.
- Use Headroom as the primary context-optimization layer for bulky/noisy outputs (build logs, test output, JSON, verbose diagnostics, large diffs). Do not default to RTK when Headroom is available. Retrieve exact original diagnostics when details matter.
- Use CodeGraph before broad text search or raw file-read loops. Run `just graph-bootstrap` before CodeGraph work in every worktree.
- Prefer `just` for project commands when a recipe exists (see `justfile` or `.agents/references/commands.md`). Prefer `just test` over invoking `unittest` directly.
- Quarterly report tests are isolated: `venv/bin/python -m unittest discover -s tests -p test_quarterly_report_generator.py` (26 tests). The full `just test` suite requires dependencies (pandas, numpy, requests) that may be missing in worktree venvs; use the primary worktree venv at `/Users/roman/Documents/Development/investment_portfolio/venv/bin/python` when needed.
- The quarterly report requires IB Flex snapshots in `data/ib_flex_snapshots/`. If no snapshot matches the quarter boundary, the generator refuses with a `ValueError` (incomplete quarters cannot be reported).
- GitHub Actions workflow `.github/workflows/flex-snapshot.yml` fetches IB Flex snapshots automatically on quarter boundaries (1st day of Jan/Apr/Jul/Oct at 06:00 UTC; last day of Mar/Jun/Sep/Dec at 22:00 UTC). Snapshots are stored as artifacts (365-day retention) with Telegram notifications. Download artifacts and place XMLs in `data/ib_flex_snapshots/` before running `just report`.
