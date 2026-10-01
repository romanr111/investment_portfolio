# Command reference

## just recipes

The authoritative list lives in `justfile`. Key recipes:

- `just test` - run the Python test suite (`python3 -m unittest discover -s tests`)
- `just run` - run the main portfolio sync pipeline (`python -m src.portfolio_sync`)
- `just report` - generate the quarterly YIC portfolio report (Markdown + HTML) via `analyze_portfolio_reports.py` + `generate_quarterly_report.py`
- `just fetch-snapshot` - fetch a fresh IB Flex portfolio snapshot (query 1188471) into `data/ib_flex_snapshots/`

### `just run` (portfolio sync pipeline)

By default (`just run` with no flags):
1. Fetches live positions from IB Gateway (`ib_insync`)
2. Fetches YTD performance from IB Flex Web Service
3. Calculates allocation and dividend income (yfinance/Yahoo)
4. Writes `data/snapshots/combined_data_<date>_<timestamp>.json` (+ `_latest.json`)
5. Updates Google Sheets (`data/credentials.json`)
6. Skips history sync and Dalio analysis by default

Full data collection (all sources + history + Dalio):
```bash
just run -- --run-history-sync --run-dalio-analysis
```

Key flags:
- `--force-refresh` - re-fetch all data sources
- `--skip-sheet-update` - skip Google Sheets write
- `--run-history-sync` - sync monthly history from Google Sheets
- `--run-dalio-analysis` - run Dalio risk analyzer
- `--dalio-only` - skip fetch, run Dalio on existing CSV

Full flag list: `python -m src.portfolio_sync --help` or see `README.md`.

Required env vars (in `data/ib_flex_env.sh`): `IB_GATEWAY_HOST`, `IB_GATEWAY_PORT`, `IB_FLEX_TOKEN`, `IB_FLEX_QUERY_ID_YTD_PERFORMANCE`, `IB_ACCOUNT_ID`. For the quarterly report also: `IB_FLEX_QUERY_ID_PORTFOLIO_SNAPSHOT` (see `.agents/skills/quarterly-report/SKILL.md`).

Outputs: `data/snapshots/combined_data_*.json`, `data/portfolio_history.csv`, `data/portfolio_history.jsonl`, `analytics/output/` (Dalio).

### `just report` flags

`just report` runs both the Markdown generator (`analyze_portfolio_reports.py`) and the HTML generator (`generate_quarterly_report.py`) with no passthrough flags. To pass flags to the HTML generator, invoke it directly:

```bash
venv/bin/python portfolio_yic_reports/generate_quarterly_report.py --before path.json
venv/bin/python portfolio_yic_reports/generate_quarterly_report.py --ibkr-ytd -6.8 --sp500-ytd 9.3
venv/bin/python portfolio_yic_reports/generate_quarterly_report.py --output path.html --open
```

- `--before PATH` - explicit start-of-quarter `data/snapshots/combined_data_*.json` snapshot. Auto-selected otherwise: newest one dated on or before quarter start + 5 days grace that carries allocation data.
- `--ibkr-ytd N` / `--sp500-ytd N` - override the YTD figures (default: from `data/final_data.json`).
- `--output PATH` - output HTML path (default: `portfolio_yic_reports/portfolio_report_qN_YYYY.html`).
- `--open` - open the generated report in a browser.

### `just fetch-snapshot`

Downloads a portfolio snapshot XML from IB Flex query 1188471 and saves it to `data/ib_flex_snapshots/` as `stocks_count_trades_<toDate>_<timestamp>.xml`. Requires `IB_FLEX_TOKEN` and `IB_FLEX_QUERY_ID_PORTFOLIO_SNAPSHOT` env vars (see `data/ib_flex_env.sh`).

### CodeGraph recipes

- `just graph-bootstrap` - initialize CodeGraph for the current worktree
- `just graph-status` - check CodeGraph status
- `just graph-sync` - sync CodeGraph index
- `just graph-reindex` - force-reindex CodeGraph

See also `.agents/references/codegraph.md` for worktree setup and separation rules.