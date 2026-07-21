# Data contracts & order of operations

Single source of truth for how portfolio data flows from fetch to report. Read this before touching the report generator or sync pipeline.

## Stage 1 - Data gathering (`just run` / `python -m src.portfolio_sync`)

- Fetches IB Gateway positions, IB Flex YTD performance, yfinance indices/dividends, crypto/P2P/other assets
- Writes single canonical snapshot: `data/snapshots/combined_data_<YYYY-MM-DD>_<YYYYMMDDTHHMMSSZ>.json` (+ `combined_data_latest.json`)
- Updates Google Sheets from the same in-memory dict (rows: B3=IB TWR, B4=S&P 500, B5=NASDAQ, K3=dividends, A1=FIRE progress)
- Optional: appends to `data/portfolio_history.csv`, writes `analytics/output/summary.json` (Dalio)

## Stage 2 - Flex snapshot fetch (`just fetch-snapshot` / GitHub Actions cron)

- Downloads IB Flex query 1188471 (positions) -> `data/ib_flex_snapshots/stocks_count_trades_<toDate>_<timestamp>.xml`
- Independent of Stage 1; runs on quarter boundaries (cron) or manually

## Stage 3 - Quarterly report (`just report` / `python -m portfolio_yic_reports.auto.cli`)

- Reads (never re-fetches): Stage 1 `combined_data_*.json` + `portfolio_history.csv` + `analytics/output/summary.json`; Stage 2 IB Flex XMLs
- `match_combined_snapshot` picks the latest-timestamp file with embedded date <= quarter boundary (deterministic tie-break by filename timestamp; no-suffix files sort before timestamped siblings)
- Section-to-source map: S1-3 from `combined_data` (TWR, S&P 500, NASDAQ, income, freedom); S2 from `portfolio_history.csv`; S4 from Flex XMLs; S6 from Dalio summary
- Output: `portfolio_yic_reports/REPORT_YYYY_qN.md`

## Quarterly cycle order

1. Run Stage 1 at quarter end (produces `combined_data_<quarter_end>.json`)
2. Run Stage 2 at quarter start AND quarter end (cron handles both)
3. Run Stage 3 after both stages complete: `just report -- --year YYYY --quarter Q`

## Shared constants (single source of truth)

- `HKD_TO_USD_RATE`, `HARDCODED_ENTRY_PRICES`, `CORE_SYMBOLS`, `CHINA_EQUITY_SYMBOLS`, `CHINESE_STOCKS`, `BOND_TICKERS`, `PRECIOUS_METALS_TICKERS`, `SPECIAL_ASSET_TICKERS`, `EXCLUDED_FROM_EQUITY` are defined in `portfolio_yic_reports/auto/config.py`
- The legacy `portfolio_yic_reports/analyze_portfolio_reports.py` imports these from `auto/config.py` - do not redefine them there