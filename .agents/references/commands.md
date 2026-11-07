# Command reference

## just recipes

The authoritative list lives in `justfile`. Key recipes:

- `just test` - run the Python test suite (`python3 -m unittest discover -s tests`)
- `just run` - run the main portfolio sync pipeline (`python -m src.portfolio_sync`)
- `just report` - generate the quarterly YIC portfolio report (Markdown + HTML) via `analyze_portfolio_reports.py` + `generate_quarterly_report.py`
- `just fetch-snapshots` - download the Flex snapshot artifacts of the last 4 CI runs into `data/ib_flex_snapshots/` (needs an authenticated `gh`)
- `just risk-progress --snapshot data/snapshots/combined_data_<date>_<timestamp>.json [--car-proxies PATH]` - effective-independent-streams view (`risk_progress_v1`) with car-business scenarios when a proxy block exists; reads a saved snapshot, writes nothing unless `--out NEW_FILE` is given
- `just car-proxies build --raw data/car_category/raw_<date> --proxy-csv <csv> --as-of <as_of_date> --out data/car_category/proxies_<date>.json` - freeze the public used-vehicle proxy series (offline, refuses to overwrite); copy to `data/car_category/proxies_latest.json` for `just run` to derive `risk_progress_v1`. `report --block PATH` prints the series.

### Car-category tracker (method v3)

- `just car-category build --raw data/car_category/raw_<date> --long-returns <csv> --as-of <as_of_date> --out data/car_category/block_<date>.json` - freeze the Manheim index and long group histories into one block (offline, refuses to overwrite). Copy it to `data/car_category/block_latest.json` for `just run` to derive `allocation_score_v3`; `just holy-grail --car-category PATH` does the same for a derived snapshot copy.
- `just car-category report --snapshot PATH --block PATH [--append-history data/car_category/history.jsonl]` - per-group correlations with the used-vehicle price index, v2 vs v3 scores, and the equivalent uniform car correlation. Read-only apart from the optional append-only history.
- `just car-crisis --raw ... --long-returns ... --out ... [--fetch-manheim-url URL --as-of DATE [--bls-contact CONTACT]]` - H1-H3 crisis test; the fetch variant downloads the raw files into a new directory first (BLS needs a contact you choose, otherwise its CPI file is skipped). See `docs/car-flip-category-evidence.md`.
- `just car-proxy` - listed auto-remarketing equity basket vs the car business (equity beta, not a measurement; superseded by the price index above).
- Data lives in ignored `data/car_category/`; method notes are in `docs/diversification-methodology.md` (v3 section).

### `just run` (portfolio sync pipeline)

By default (`just run` with no flags):
1. Fetches live positions from IB Gateway (`ib_async`, pinned `ib_async==2.1.0`)
2. Fetches YTD performance from IB Flex Web Service
3. Calculates allocation and dividend income (yfinance/Yahoo)
4. Writes `data/snapshots/combined_data_<date>_<timestamp>.json` (+ `_latest.json`)
5. Updates Google Sheets (`data/credentials.json`)
6. Skips history sync and Dalio analysis by default

Flag passthrough works in both documented forms: `just run --run-history-sync`
and `just run -- --run-history-sync` (the bare `--` separator is dropped before
the module sees the flags).

Full data collection (all sources + history + Dalio):
```bash
just run --run-history-sync --run-dalio-analysis
```

Key flags:
- `--force-refresh` - re-fetch all data sources
- `--skip-sheet-update` - skip Google Sheets write
- `--run-history-sync` - sync monthly history from Google Sheets
- `--run-dalio-analysis` - run Dalio risk analyzer
- `--dalio-only` - skip fetch, run Dalio on existing CSV

Full flag list: `python -m src.portfolio_sync --help` or see `README.md`.

Required env vars (in `data/ib_flex_env.sh`): `IB_GATEWAY_HOST`, `IB_GATEWAY_PORT`, `IB_FLEX_TOKEN`, `IB_FLEX_QUERY_ID_YTD_PERFORMANCE`, `IB_ACCOUNT_ID`. For the quarterly report also: `IB_FLEX_QUERY_ID_PORTFOLIO_SNAPSHOT` (see `.agents/skills/quarterly-report/SKILL.md`).

### `just run-guarded` (lock, receipts, retries, healthcheck pings)

Runs the same sync under `src.job_control.run_job` (POSIX only):

- advisory lock `data/run/sync.lock`: a second concurrent run exits 3 with
  `outcome=locked` on stderr and receipt, without pinging;
- one JSON receipt per run appended to `data/run/receipts.jsonl` (fields:
  schema, job, start_utc, end_utc, duration_s, attempts, exit_code, outcome,
  command, pid, retry_delay_s, notified); local-only, safe to delete;
- healthcheck pings only when `HEALTHCHECK_SYNC_URL` is set: `/start` before
  the first attempt, bare URL on success, `/fail` after the last failed
  attempt; ping failures are stderr warnings and never change the exit code;
- receipt and lock files are recreated on the next run if deleted.

Wrapper options exist only on the direct module call:

```bash
python -m src.job_control.run_job --job sync --retries 2 -- venv/bin/python -m src.portfolio_sync
```

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

### `just edgar-watch`

Daily SEC EDGAR monitor for individual equity positions (module `src.edgar.watch`).

```bash
just edgar-watch --dry-alert                  # preview digest, no Telegram/healthcheck
just edgar-watch                              # full run: alerts + digest + healthcheck
just edgar-watch --limit-tickers 5            # largest N monitored positions only
just edgar-watch --extract-rf <SYMBOL>        # offline RF extraction probe (no state writes)
```

- Requires `SEC_USER_AGENT` in `data/ib_flex_env.sh` (honest shared default otherwise); `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` optional (digest skipped without them); healthcheck via `HEALTHCHECK_EDGAR_URL`.
- Reads the equity buckets (`Stocks`, `China Stocks`, `REIT`) from a `data/snapshots/combined_data_*.json` snapshot (default `combined_data_latest.json`, override with `--snapshot PATH`); never fetches prices or recomputes the snapshot.
- Flags: `--backfill-days N`, `--data-dir PATH`, `--healthcheck-url URL`, `--verbose`. Exit codes: 0 ok, 1 fatal (steady SEC 403/429: block stop, no state commit, no sends), 2 partial (per-CIK failures, successful CIKs committed), 3 busy (already running; flock in `data/edgar/watch.lock`).
- State and event log live in `data/edgar/` (see `data/README.md`). Alerts append before the state commit, so a lost digest is re-sent on the next run.
- The launchd plist `deploy/launchd/com.investment-portfolio.edgar-watch.plist` schedules the 09:00 local daily run. It can also be wrapped by `src.job_control.run_job --job edgar` for lock+receipts; note the wrapper and the watch both honor `HEALTHCHECK_EDGAR_URL`, so set it for one side only.
- `--extract-rf <SYMBOL>` fetches the two latest periodic filings of one symbol, prints the Item 1A extraction and diff counts, and writes a diff file to `data/edgar/rf_check/` without touching `state.json` or `alerts.jsonl`.
- Offline tests: `tests/test_edgar_severity.py`, `test_edgar_risk_factors.py`, `test_edgar_state.py`, `test_edgar_watch.py`, `test_edgar_telegram.py` with fixtures in `tests/fixtures/edgar/`; no test performs live sec.gov access. The live gates L1-L4 (single request, one CIK, full dry run, full live run) are owner-executed after `SEC_USER_AGENT` is configured.

### `just fetch-snapshots`

Downloads the artifacts of the last 4 runs of `.github/workflows/flex-snapshot.yml` (positions and quarterly trades XML) into `data/ib_flex_snapshots/` with the authenticated `gh` CLI. Download failures are suppressed and artifacts can land in nested folders: inspect the XML and keep validated exports in the top-level directory. There is no recipe for a direct fetch; a missing export is fetched with `IBFlexPortfolioFetcher` (`src/brokers/ib_flex_portfolio.py`; needs `IB_FLEX_TOKEN` and the query id env var, see `data/ib_flex_env.sh`), as shown in the `quarterly-report` skill.
