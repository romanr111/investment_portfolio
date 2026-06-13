# Investment Portfolio

Personal portfolio automation for live IB Gateway data, dividend income estimates, Google Sheets updates, historical snapshots, and Dalio-style risk analysis.

## Main Command

```bash
python -m src.portfolio_sync
```

This bootstraps `.venv` when needed, installs `requirements.txt`, loads `data/ib_flex_env.sh` if present, then runs the portfolio pipeline.

By default it:
- fetches current portfolio data from Interactive Brokers Gateway
- calculates allocation and dividend income
- writes a dated `combined_data` snapshot under `data/snapshots`
- updates the configured Google Sheet
- skips retrospective history sync and Dalio analysis

## Local Setup

Private data stays local. Git tracks only `data/README.md`; credentials, account data, generated snapshots, and local environment files are ignored.

Expected local files:
- `data/credentials.json` for Google Sheets
- `data/ib_flex_env.sh` for IB/Flex settings

Required environment values:
- `IB_GATEWAY_HOST`
- `IB_GATEWAY_PORT`
- `IB_FLEX_TOKEN`
- `IB_FLEX_QUERY_ID_YTD_PERFORMANCE`
- `IB_ACCOUNT_ID`

Example local env file:

```bash
export IB_GATEWAY_HOST=127.0.0.1
export IB_GATEWAY_PORT=7497
export IB_ACCOUNT_ID=DU123456
export IB_FLEX_TOKEN=...
export IB_FLEX_QUERY_ID_YTD_PERFORMANCE=...
```

Do not commit real credentials or account files.

## Common Runs

Run without updating Google Sheets:

```bash
python -m src.portfolio_sync --skip-sheet-update
```

Refresh all data sources:

```bash
python -m src.portfolio_sync --force-refresh
```

Sync historical monthly data from Google Sheets:

```bash
python -m src.portfolio_sync --run-history-sync
```

Run the full pipeline plus Dalio analysis:

```bash
python -m src.portfolio_sync --run-history-sync --run-dalio-analysis
```

Run only Dalio analysis from an existing CSV:

```bash
python -m src.portfolio_sync --dalio-only --run-dalio-analysis --dalio-input-csv data/portfolio_history.csv
```

## Outputs

- `data/snapshots/combined_data_<date>_<timestamp>.json`
- `data/snapshots/combined_data_latest.json`
- `data/portfolio_history.csv`
- `data/portfolio_history.jsonl`
- `analytics/output/`

## Notes

- Interactive Brokers live positions come from IB Gateway via `ib_insync`.
- YTD performance comes from IBKR Flex Web Service.
- Dividend yields come from yfinance/Yahoo data; Yahoo forward-dividend fallback is called once per ticker to avoid duplicate retry delays.
- Historical sync defaults to monthly rows and blank `return_pct` to avoid false returns from deposits or withdrawals.

## Tests

```bash
python3 -m unittest discover -s tests
```
